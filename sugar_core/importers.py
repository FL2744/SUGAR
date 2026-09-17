from __future__ import annotations

import csv
import hashlib
import json
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import PostRecord, merge_record
from .storage import save_records

IMPORT_SCHEMA_VERSION = "1.0"
IMPORTER_VERSION = "sugar-import-1.0"


class ImportValidationError(ValueError):
    """Raised when an external row cannot be normalized without inventing evidence."""


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "platform": ("source_platform", "network", "channel_type"),
    "native_id": ("id", "post_id", "status_id", "message_id", "item_id"),
    "canonical_url": ("url", "link", "post_url", "permalink"),
    "query": ("search_query", "search_term", "keyword", "matched_query"),
    "published_at": ("timestamp", "published", "published_date", "created_at", "date"),
    "author_handle": ("username", "handle", "author_username", "account"),
    "author_name": ("display_name", "author", "account_name"),
    "author_location": ("profile_location", "account_location"),
    "platform_language": ("language", "lang", "source_language"),
    "detected_language": ("detected_lang",),
    "original_text": ("text", "content", "body", "message", "post_text", "caption"),
    "translated_text": ("translation", "translated_en", "english_text"),
    "source_url": ("collection_url", "request_url", "search_url"),
    "source_host": ("source_system", "source_name", "provider"),
    "collected_at": ("collection_time", "collected", "retrieved_at"),
    "content_type": ("type", "record_type", "item_type"),
    "conversation_id": ("thread_id", "conversation", "root_id"),
    "parent_record_key": ("parent_id", "parent_record"),
    "thread_root_key": ("thread_root_id", "root_record"),
    "raw_stats": ("metrics", "statistics", "stats"),
    "engagement": ("engagement_metrics",),
}

ENGAGEMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "likes": ("likes", "like_count", "favorites", "favorite_count"),
    "replies": ("replies", "reply_count", "comments", "comment_count"),
    "reposts": ("reposts", "repost_count", "shares", "share_count", "retweets"),
    "views": ("views", "view_count", "plays", "play_count"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_blank(value: Any) -> bool:
    return value is None or _clean(value).casefold() in {"", "nan", "none", "<na>"}


def _json_dict(value: Any) -> dict[str, Any]:
    if _is_blank(value):
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: Any) -> list[str]:
    if _is_blank(value):
        return []
    if isinstance(value, list):
        return [_clean(item) for item in value if not _is_blank(item)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [_clean(value)]
        if isinstance(parsed, list):
            return [_clean(item) for item in parsed if not _is_blank(item)]
    return []


def _int_or_zero(value: Any) -> int:
    if _is_blank(value):
        return 0
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _float_or_none(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).casefold() in {"1", "true", "yes", "y"}


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ImportSpec:
    source_system: str = "external"
    platform_override: str = ""
    field_map: dict[str, str] = field(default_factory=dict)
    strict: bool = False
    preserve_unmapped_fields: bool = True

    def __post_init__(self) -> None:
        extra_fields = {
            "query_matches", "is_repost", "latitude", "longitude", "location_confidence",
            "inferred_location", "location_source", "location_reason", "geocode_display_name",
        }
        unknown = sorted(set(self.field_map) - set(FIELD_ALIASES) - extra_fields)
        if unknown:
            raise ValueError(f"Unsupported canonical import field(s): {', '.join(unknown)}")


@dataclass
class ImportResult:
    records: list[PostRecord]
    rejected: list[dict[str, Any]]
    duplicate_rows: int
    mapping_used: dict[str, str]
    imported_at: str
    source_sha256: str
    source_file: str
    source_system: str

    @property
    def accepted_rows(self) -> int:
        return len(self.records)


def parse_field_mappings(values: Iterable[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw in values:
        text = _clean(raw)
        if "=" not in text:
            raise ValueError(f"Invalid mapping {raw!r}; use CANONICAL=SOURCE_COLUMN.")
        canonical, source = (part.strip() for part in text.split("=", 1))
        if not canonical or not source:
            raise ValueError(f"Invalid mapping {raw!r}; use CANONICAL=SOURCE_COLUMN.")
        if canonical in mapping and mapping[canonical] != source:
            raise ValueError(f"Canonical field {canonical!r} is mapped more than once.")
        mapping[canonical] = source
    return mapping


def _rows_from_csv(path: Path) -> list[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("CSV input has no header row.")
        return [(index, dict(row)) for index, row in enumerate(reader, start=2)]


def _rows_from_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for index, line in enumerate(stream, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {index}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL line {index} must contain an object.")
            rows.append((index, payload))
    return rows


def load_external_rows(path: str | Path) -> list[tuple[int, dict[str, Any]]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.casefold() == ".csv":
        return _rows_from_csv(source)
    if source.suffix.casefold() in {".jsonl", ".ndjson"}:
        return _rows_from_jsonl(source)
    raise ValueError("External import currently supports CSV, JSONL, and NDJSON input.")


def _resolve(row: Mapping[str, Any], canonical: str, spec: ImportSpec) -> tuple[Any, str]:
    explicit = spec.field_map.get(canonical)
    if explicit:
        return row.get(explicit, ""), explicit
    candidates = (canonical, *FIELD_ALIASES.get(canonical, ()))
    present = [(name, row[name]) for name in candidates if name in row and not _is_blank(row[name])]
    if not present:
        return "", ""
    distinct = {_clean(value) for _, value in present}
    if len(distinct) > 1:
        names = ", ".join(name for name, _ in present)
        raise ImportValidationError(
            f"Ambiguous {canonical!r}: multiple populated source columns ({names}). Add an explicit mapping."
        )
    return present[0][1], present[0][0]


def _engagement(row: Mapping[str, Any], spec: ImportSpec) -> tuple[dict[str, int], set[str]]:
    raw, source = _resolve(row, "engagement", spec)
    used = {source} if source else set()
    parsed = {key: _int_or_zero(value) for key, value in _json_dict(raw).items()}
    for canonical, aliases in ENGAGEMENT_ALIASES.items():
        present = [(name, row[name]) for name in aliases if name in row and not _is_blank(row[name])]
        if present:
            name, value = present[0]
            parsed.setdefault(canonical, _int_or_zero(value))
            used.add(name)
    return parsed, used


def normalize_external_row(row: Mapping[str, Any], spec: ImportSpec) -> tuple[PostRecord, dict[str, str]]:
    resolved: dict[str, Any] = {}
    used_columns: dict[str, str] = {}
    for field_name in FIELD_ALIASES:
        value, source = _resolve(row, field_name, spec)
        resolved[field_name] = value
        if source:
            used_columns[field_name] = source

    for field_name in (
        "query_matches", "is_repost", "latitude", "longitude", "location_confidence",
        "inferred_location", "location_source", "location_reason", "geocode_display_name",
    ):
        source = spec.field_map.get(field_name, field_name if field_name in row else "")
        resolved[field_name] = row.get(source, "") if source else ""
        if source and not _is_blank(resolved[field_name]):
            used_columns[field_name] = source

    platform = _clean(spec.platform_override or resolved["platform"])
    native_id = _clean(resolved["native_id"])
    canonical_url = _clean(resolved["canonical_url"])
    if not platform:
        raise ImportValidationError("Missing platform/source identity. Supply a platform column or --platform override.")
    if not native_id and not canonical_url:
        raise ImportValidationError("Missing source item identity. Each row requires native_id or canonical_url.")

    query = _clean(resolved["query"])
    query_matches = _json_list(resolved.get("query_matches"))
    if query and query not in query_matches:
        query_matches.insert(0, query)

    engagement, engagement_columns = _engagement(row, spec)
    raw_stats = _json_dict(resolved["raw_stats"])
    used_source_columns = {name for name in used_columns.values() if name}
    used_source_columns.update(engagement_columns)
    if spec.preserve_unmapped_fields:
        extras = {
            str(key): value for key, value in row.items()
            if str(key) not in used_source_columns and not _is_blank(value)
        }
        if extras:
            raw_stats = dict(raw_stats)
            raw_stats.setdefault("external_fields", extras)

    record = PostRecord(
        platform=platform,
        native_id=native_id,
        canonical_url=canonical_url,
        query=query,
        query_matches=query_matches,
        content_type=_clean(resolved["content_type"]) or "post",
        parent_record_key=_clean(resolved.get("parent_record_key")),
        thread_root_key=_clean(resolved.get("thread_root_key")),
        conversation_id=_clean(resolved["conversation_id"]),
        source_mode=f"external_import:{spec.source_system or 'external'}",
        source_host=_clean(resolved["source_host"]) or _clean(spec.source_system),
        source_url=_clean(resolved["source_url"]),
        collected_at=_clean(resolved["collected_at"]),
        published_at=_clean(resolved["published_at"]),
        author_handle=_clean(resolved["author_handle"]),
        author_name=_clean(resolved["author_name"]),
        author_location=_clean(resolved["author_location"]),
        platform_language=_clean(resolved["platform_language"]),
        detected_language=_clean(resolved["detected_language"]),
        original_text=_clean(resolved["original_text"]),
        translated_text=_clean(resolved["translated_text"]),
        engagement=engagement,
        raw_stats=raw_stats,
        is_repost=_bool(resolved.get("is_repost")),
        inferred_location=_clean(resolved.get("inferred_location")),
        location_confidence=_float_or_none(resolved.get("location_confidence")) or 0.0,
        location_source=_clean(resolved.get("location_source")),
        location_reason=_clean(resolved.get("location_reason")),
        latitude=_float_or_none(resolved.get("latitude")),
        longitude=_float_or_none(resolved.get("longitude")),
        geocode_display_name=_clean(resolved.get("geocode_display_name")),
    )
    return record, used_columns


def import_external_records(path: str | Path, spec: ImportSpec | None = None) -> ImportResult:
    source = Path(path).expanduser().resolve()
    spec = spec or ImportSpec()
    records: OrderedDict[str, PostRecord] = OrderedDict()
    rejected: list[dict[str, Any]] = []
    mapping_used: dict[str, str] = {}
    duplicate_rows = 0

    for row_number, row in load_external_rows(source):
        try:
            record, row_mapping = normalize_external_row(row, spec)
            mapping_used.update(row_mapping)
            key = record.record_key
            if key in records:
                records[key] = merge_record(records[key], record)
                duplicate_rows += 1
            else:
                records[key] = record
        except (ImportValidationError, TypeError, ValueError) as exc:
            if spec.strict:
                raise ImportValidationError(f"Row {row_number}: {exc}") from exc
            rejected.append({"row": row_number, "error": str(exc), "record": dict(row)})

    if not records:
        details = f"; {len(rejected)} row(s) rejected" if rejected else ""
        raise ImportValidationError(f"External dataset produced no valid records{details}.")

    return ImportResult(
        records=list(records.values()),
        rejected=rejected,
        duplicate_rows=duplicate_rows,
        mapping_used=dict(sorted(mapping_used.items())),
        imported_at=_utc_now(),
        source_sha256=_source_sha256(source),
        source_file=source.name,
        source_system=spec.source_system,
    )


def _output_base(output_file: str | Path) -> Path:
    target = Path(output_file).expanduser().resolve()
    if target.suffix.casefold() in {".csv", ".xlsx", ".jsonl", ".ndjson", ".json"}:
        target = target.with_suffix("")
    return target


def save_import_result(result: ImportResult, output_file: str | Path, *, spec: ImportSpec) -> list[str]:
    base = _output_base(output_file)
    base.parent.mkdir(parents=True, exist_ok=True)
    csv_path = Path(f"{base}.csv")
    jsonl_path = Path(f"{base}.jsonl")
    rejected_path = Path(f"{base}.rejected.jsonl")
    manifest_path = Path(f"{base}.import.json")

    save_records(
        result.records,
        csv_path,
        metadata={
            "operation": "external_import",
            "import_schema_version": IMPORT_SCHEMA_VERSION,
            "importer_version": IMPORTER_VERSION,
            "source_file": result.source_file,
            "source_sha256": result.source_sha256,
            "source_system": result.source_system,
            "imported_at": result.imported_at,
            "accepted_records": result.accepted_rows,
            "rejected_rows": len(result.rejected),
            "duplicate_rows": result.duplicate_rows,
        },
    )
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in result.records:
            payload = asdict(record)
            payload["record_key"] = record.record_key
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    outputs = [str(csv_path), str(csv_path.with_suffix(".xlsx")), str(jsonl_path)]
    if result.rejected:
        with rejected_path.open("w", encoding="utf-8", newline="\n") as stream:
            for row in result.rejected:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        outputs.append(str(rejected_path))

    manifest = {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "importer_version": IMPORTER_VERSION,
        "imported_at": result.imported_at,
        "source_file": result.source_file,
        "source_sha256": result.source_sha256,
        "source_system": result.source_system,
        "platform_override": spec.platform_override,
        "field_map_requested": spec.field_map,
        "field_map_resolved": result.mapping_used,
        "strict": spec.strict,
        "preserve_unmapped_fields": spec.preserve_unmapped_fields,
        "accepted_records": result.accepted_rows,
        "rejected_rows": len(result.rejected),
        "duplicate_rows": result.duplicate_rows,
        "outputs": [Path(path).name for path in outputs],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    outputs.append(str(manifest_path))
    return outputs


def import_external_dataset(
    source_file: str | Path,
    output_file: str | Path,
    *,
    source_system: str = "external",
    platform: str = "",
    field_map: Mapping[str, str] | None = None,
    strict: bool = False,
    preserve_unmapped_fields: bool = True,
) -> list[str]:
    spec = ImportSpec(
        source_system=_clean(source_system) or "external",
        platform_override=_clean(platform),
        field_map=dict(field_map or {}),
        strict=bool(strict),
        preserve_unmapped_fields=bool(preserve_unmapped_fields),
    )
    return save_import_result(import_external_records(source_file, spec), output_file, spec=spec)
