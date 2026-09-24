from __future__ import annotations

import hashlib
import csv
import difflib
import json
import re
import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import pandas as pd

from .workspace import SugarWorkspace
from .reference_taxonomy import TAXONOMY_VERSION, normalize_labels


ENTITY_TYPES = {
    "network", "organization", "institution", "site", "program", "account", "event", "service"
}
ENTITY_STATUSES = {"active", "closed", "renamed", "relocated", "unknown"}
DELIVERY_MODES = {"physical", "mobile", "virtual", "hybrid", "digital"}
RELATIONSHIP_TYPES = {
    "hosts", "hosted_by", "partner_of", "affiliated_with", "member_of", "successor_to",
    "associated_account", "delivers", "sponsors", "serves", "located_at", "other",
}

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "entity_id": ("entity_id", "institution_id", "site_id", "record_id", "id", "uid"),
    "name": ("name", "institution_name", "site_name", "title", "organization", "program_name", "center"),
    "entity_type": ("entity_type", "institution_type", "type", "category", "kind"),
    "network": ("network", "network_name", "program_network", "sponsor_network"),
    "aliases": ("aliases", "alias", "alternate_names", "alternative_names", "other_names"),
    "country": ("country", "country_name", "nation"),
    "region": ("region", "state_province", "province", "subnational_area"),
    "city": ("city", "locality", "municipality", "town"),
    "address": ("address", "street_address", "location", "address_line"),
    "latitude": ("latitude", "lat", "y", "decimal_latitude"),
    "longitude": ("longitude", "lon", "lng", "long", "x", "decimal_longitude"),
    "location_precision": ("location_precision", "geo_precision", "precision"),
    "status": ("status", "current_status", "institution_status", "operational_status"),
    "status_date": ("status_date", "closed_date", "closure_date", "effective_date"),
    "opened_date": ("opened_date", "opening_date", "start_date"),
    "closed_date": ("closed_date", "closure_date", "end_date"),
    "source_url": ("source_url", "url", "website", "primary_source_url", "source"),
    "public_links": ("public_links", "links", "websites", "urls"),
    "accounts": ("accounts", "handles", "social_accounts", "social_media", "account_handles"),
    "host_entities": ("host_entities", "host_entity_ids", "host_ids", "host", "host_institution", "host_university"),
    "partner_entities": ("partner_entities", "partner_entity_ids", "partner_ids", "partners", "partner_institutions"),
    "audiences": ("audiences", "audience", "target_audiences", "participants"),
    "audience_descriptions": ("audience_descriptions", "audience_description", "source_audiences"),
    "program_domains": ("program_domains", "program_domain", "programs", "services", "activities"),
    "program_descriptions": ("program_descriptions", "program_description", "activity_descriptions", "source_programs"),
    "normalized_audiences": ("normalized_audiences",),
    "normalized_program_domains": ("normalized_program_domains",),
    "delivery_mode_descriptions": ("delivery_mode_descriptions", "delivery_description", "source_delivery_modes"),
    "normalized_delivery_modes": ("normalized_delivery_modes",),
    "delivery_modes": ("delivery_modes", "delivery_mode", "format", "delivery"),
    "coverage_scope": ("coverage_scope", "service_geography", "coverage", "geographic_scope"),
    "source_license": ("source_license", "license", "licence", "usage_terms", "data_license"),
    "description": ("description", "summary", "notes", "details"),
}

_CLAIM_FIELDS = {
    "name", "aliases", "country", "region", "city", "address", "latitude", "longitude",
    "location_precision", "status", "status_date", "opened_date", "closed_date", "public_links",
    "accounts", "host_entities", "partner_entities", "audiences", "program_domains",
    "audience_descriptions", "program_descriptions", "normalized_audiences", "normalized_program_domains",
    "delivery_modes", "delivery_mode_descriptions", "normalized_delivery_modes",
    "coverage_scope", "source_url", "description", "network",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "none", "null"} else text


def _relationship_date(value: Any, field: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(f"{field} must use YYYY-MM-DD.")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a real YYYY-MM-DD calendar date.") from exc
    return text


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        text = _clean(value)
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            parsed = None
        raw = parsed if isinstance(parsed, list) else re.split(r"[;|\n]", text)
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = _clean(item)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            result.append(text)
    return result


def _number(value: Any, field: str) -> float | None:
    text = _clean(value).lstrip("'")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric when supplied.") from exc
    if field == "latitude" and not -90 <= number <= 90:
        raise ValueError("latitude must be between -90 and 90.")
    if field == "longitude" and not -180 <= number <= 180:
        raise ValueError("longitude must be between -180 and 180.")
    return number


def _stable_id(*parts: Any) -> str:
    value = "|".join(_clean(item).casefold() for item in parts)
    return "ent_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _registry_dir(workspace: SugarWorkspace) -> Path:
    target = workspace.path_for("references") / "registry"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_no, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path.name} line {line_no} must be a JSON object.")
            rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def registry_paths(workspace: SugarWorkspace) -> dict[str, Path]:
    root = _registry_dir(workspace)
    return {
        "entities": root / "entities.jsonl",
        "relationships": root / "relationships.jsonl",
        "lifecycle": root / "lifecycle.jsonl",
        "history": root / "history.jsonl",
        "datasets": root / "datasets.jsonl",
    }


def suggest_field_mapping(columns: Iterable[Any]) -> dict[str, str]:
    normalized = {re.sub(r"[^a-z0-9]+", "_", str(column).casefold()).strip("_"): str(column) for column in columns}
    mapping: dict[str, str] = {}
    for canonical, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            key = re.sub(r"[^a-z0-9]+", "_", alias.casefold()).strip("_")
            if key in normalized:
                mapping[canonical] = normalized[key]
                break
    return mapping


def _rows_from_geojson(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        raise ValueError("GeoJSON must contain a FeatureCollection with a features array.")
    rows: list[dict[str, Any]] = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        row = dict(properties)
        geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
        coordinates = geometry.get("coordinates") or []
        if geometry.get("type") == "Point" and len(coordinates) >= 2:
            row.setdefault("longitude", coordinates[0])
            row.setdefault("latitude", coordinates[1])
        row.setdefault("entity_id", feature.get("id", ""))
        row.setdefault("_source_row", index)
        rows.append(row)
    return rows, sorted({str(key) for row in rows for key in row if key != "_source_row"})


def load_reference_table(path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.casefold()
    if suffix in {".csv", ".tsv"}:
        frame = pd.read_csv(source, sep="\t" if suffix == ".tsv" else ",", dtype=object)
        return frame.fillna("").to_dict(orient="records"), [str(item) for item in frame.columns]
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(source, dtype=object)
        return frame.fillna("").to_dict(orient="records"), [str(item) for item in frame.columns]
    if suffix in {".geojson", ".json"}:
        return _rows_from_geojson(source)
    raise ValueError("Reference datasets must be CSV, TSV, XLSX, XLS, JSON, or GeoJSON.")


def _mapped_value(row: dict[str, Any], mapping: dict[str, str], key: str) -> Any:
    column = mapping.get(key, "")
    return row.get(column) if column else None


def _validate_reference_row(row: dict[str, Any], mapping: dict[str, str], row_number: int) -> list[str]:
    errors: list[str] = []
    if not _clean(_mapped_value(row, mapping, "name")):
        errors.append("name is required")
    latitude = _mapped_value(row, mapping, "latitude")
    longitude = _mapped_value(row, mapping, "longitude")
    if bool(_clean(latitude)) != bool(_clean(longitude)):
        errors.append("latitude and longitude must be supplied together")
    try:
        _number(latitude, "latitude")
        _number(longitude, "longitude")
    except ValueError as exc:
        errors.append(str(exc))
    entity_type = _clean(_mapped_value(row, mapping, "entity_type")) or "institution"
    if entity_type.casefold() not in ENTITY_TYPES:
        errors.append(f"entity_type must be one of {', '.join(sorted(ENTITY_TYPES))}")
    status = _clean(_mapped_value(row, mapping, "status")) or "unknown"
    if status.casefold() not in ENTITY_STATUSES:
        errors.append(f"status must be one of {', '.join(sorted(ENTITY_STATUSES))}")
    source_url = _clean(_mapped_value(row, mapping, "source_url"))
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append("source_url must be an HTTP(S) URL")
    return [f"row {row_number}: {message}" for message in errors]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preview_reference_import(path: str | Path, *, sample_size: int = 12) -> dict[str, Any]:
    rows, columns = load_reference_table(path)
    mapping = suggest_field_mapping(columns)
    errors = [error for index, row in enumerate(rows, start=2) for error in _validate_reference_row(row, mapping, index)]
    required_mapping = [field for field in ("name",) if field not in mapping]
    bad_row_count = len({error.split(":", 1)[0] for error in errors})
    return {
        "path": str(Path(path).expanduser().resolve()), "sha256": _sha256(Path(path).expanduser().resolve()),
        "format": Path(path).suffix.casefold().lstrip("."), "columns": columns,
        "suggested_mapping": mapping, "row_count": len(rows),
        "valid_rows": max(0, len(rows) - bad_row_count), "error_count": len(errors),
        "errors": errors[:100], "required_mapping": required_mapping,
        "sample": rows[: max(1, min(50, sample_size))], "requires_analyst_confirmation": True,
    }


def _evidence_refs(values: Any) -> list[dict[str, Any]]:
    refs = values if isinstance(values, list) else [values] if values else []
    result: list[dict[str, Any]] = []
    for ref in refs:
        if isinstance(ref, str):
            text = ref.strip()
            if not text:
                continue
            parsed = urlparse(text)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Evidence references supplied as strings must be HTTP(S) URLs.")
            item = {"source_url": text}
        elif isinstance(ref, dict):
            item = {str(key): value for key, value in ref.items() if value not in (None, "")}
            source_url = _clean(item.get("source_url"))
            if source_url:
                parsed = urlparse(source_url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError("Evidence source_url must be an HTTP(S) URL.")
        else:
            raise ValueError("Evidence references must be URL strings or objects.")
        result.append(item)
    return result


def _claim_values(entity: dict[str, Any], field: str) -> list[dict[str, Any]]:
    return [claim for claim in entity.get("claims", []) if claim.get("field") == field and claim.get("review_state") != "rejected"]


def _resolved(entity: dict[str, Any], field: str) -> dict[str, Any]:
    claims = _claim_values(entity, field)
    by_value: dict[str, list[dict[str, Any]]] = {}
    values: dict[str, Any] = {}
    for claim in claims:
        value = claim.get("value")
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        by_value.setdefault(key, []).append(claim)
        values[key] = value
    if not by_value:
        return {"value": None, "state": "unknown", "claims": []}
    verified = {
        key: rows for key, rows in by_value.items()
        if any(row.get("review_state") == "human_verified" for row in rows)
    }
    if len(verified) == 1:
        key = next(iter(verified))
        return {
            "value": values[key],
            "state": "human_verified_with_conflicts" if len(by_value) > 1 else "human_verified",
            "claims": [claim for rows in by_value.values() for claim in rows],
        }
    if len(by_value) > 1:
        return {"value": None, "state": "conflicted", "claims": [claim for rows in by_value.values() for claim in rows]}
    key, rows = next(iter(by_value.items()))
    return {"value": values[key], "state": rows[-1].get("review_state", "unreviewed"), "claims": rows}


def _refresh_entity(entity: dict[str, Any]) -> dict[str, Any]:
    fields = sorted({str(claim.get("field")) for claim in entity.get("claims", []) if claim.get("field")})
    entity["resolved_fields"] = {field: _resolved(entity, field) for field in fields}
    for field in ("name", "network", "status", "status_date", "opened_date", "closed_date", "country", "region", "city", "address", "latitude", "longitude", "location_precision", "description"):
        resolved = entity["resolved_fields"].get(field, {})
        default = "unknown" if field == "status" else ""
        entity[field] = resolved.get("value") if resolved.get("value") is not None else default
    for field in ("aliases", "public_links", "accounts", "host_entities", "partner_entities", "audiences",
                  "audience_descriptions", "normalized_audiences", "program_domains", "program_descriptions",
                  "normalized_program_domains", "delivery_modes", "delivery_mode_descriptions",
                  "normalized_delivery_modes", "coverage_scope"):
        values: list[str] = []
        for claim in _claim_values(entity, field):
            for value in _list(claim.get("value")):
                if value.casefold() not in {item.casefold() for item in values}:
                    values.append(value)
        entity[field] = values
    if not entity["program_descriptions"]:
        entity["program_descriptions"] = list(entity["program_domains"])
    if not entity["audience_descriptions"]:
        entity["audience_descriptions"] = list(entity["audiences"])
    entity["normalized_program_domains"] = normalize_labels(
        [*entity["program_descriptions"], *entity["program_domains"], *entity["normalized_program_domains"]],
        category="program",
    )
    entity["normalized_audiences"] = normalize_labels(
        [*entity["audience_descriptions"], *entity["audiences"], *entity["normalized_audiences"]],
        category="audience",
    )
    if not entity["delivery_mode_descriptions"]:
        entity["delivery_mode_descriptions"] = list(entity["delivery_modes"])
    entity["normalized_delivery_modes"] = normalize_labels(
        [*entity["delivery_mode_descriptions"], *entity["delivery_modes"], *entity["normalized_delivery_modes"]],
        category="delivery",
    )
    entity["conflicted_fields"] = sorted(
        field for field, resolution in entity["resolved_fields"].items() if resolution.get("state") == "conflicted"
    )
    return entity


def list_entities(workspace: SugarWorkspace, *, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    entities = [_refresh_entity(dict(row)) for row in _jsonl(registry_paths(workspace)["entities"])]
    query = _clean(filters.get("query")).casefold()
    for field in ("network", "entity_type", "status", "country", "city"):
        expected = _clean(filters.get(field)).casefold()
        if expected:
            entities = [row for row in entities if _clean(row.get(field)).casefold() == expected]
    if query:
        def matches(row: dict[str, Any]) -> bool:
            haystack = " ".join([
                _clean(row.get("name")), _clean(row.get("network")), _clean(row.get("entity_type")),
                _clean(row.get("country")), _clean(row.get("city")), *(_list(row.get("aliases"))),
                *(_list(row.get("program_descriptions"))), *(_list(row.get("audience_descriptions"))),
                *(_list(row.get("program_domains"))), *(_list(row.get("audiences"))),
            ]).casefold()
            return query in haystack
        entities = [row for row in entities if matches(row)]
    return sorted(entities, key=lambda row: (_clean(row.get("network")).casefold(), _clean(row.get("name")).casefold(), row["entity_id"]))


def _record_entity(
    workspace: SugarWorkspace,
    values: dict[str, Any],
    *,
    evidence_refs: Any,
    actor: str = "analyst",
    reason: str = "",
    review_state: str = "unreviewed",
    observed_at: str | None = None,
) -> dict[str, Any]:
    if not _clean(values.get("name")):
        raise ValueError("An institution or entity name is required.")
    entity_type = _clean(values.get("entity_type") or "institution").casefold()
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"entity_type must be one of: {', '.join(sorted(ENTITY_TYPES))}")
    refs = _evidence_refs(evidence_refs)
    if not refs:
        raise ValueError("At least one source/evidence reference is required for registry claims.")
    if review_state not in {"unreviewed", "human_verified", "needs_followup", "rejected"}:
        raise ValueError("Unsupported registry review state.")
    values = dict(values)
    program_labels = _list([*_list(values.get("program_descriptions")), *_list(values.get("program_domains")),
                            *_list(values.get("normalized_program_domains"))])
    if program_labels:
        values["program_descriptions"] = program_labels
        values["normalized_program_domains"] = normalize_labels(program_labels, category="program")
    audience_labels = _list([*_list(values.get("audience_descriptions")), *_list(values.get("audiences")),
                              *_list(values.get("normalized_audiences"))])
    if audience_labels:
        values["audience_descriptions"] = audience_labels
        values["normalized_audiences"] = normalize_labels(audience_labels, category="audience")
    delivery_labels = _list([*_list(values.get("delivery_mode_descriptions")), *_list(values.get("delivery_modes")),
                              *_list(values.get("normalized_delivery_modes"))])
    if delivery_labels:
        values["delivery_mode_descriptions"] = delivery_labels
        values["normalized_delivery_modes"] = normalize_labels(delivery_labels, category="delivery")
    entity_id = _clean(values.get("entity_id")) or str(uuid.uuid4())
    paths = registry_paths(workspace)
    entities = _jsonl(paths["entities"])
    index = next((i for i, item in enumerate(entities) if item.get("entity_id") == entity_id), None)
    if index is None:
        entity = {
            "schema_version": "1.0", "entity_id": entity_id, "entity_type": entity_type,
            "created_at": _now(), "updated_at": _now(), "claims": [],
        }
        entities.append(entity)
    else:
        entity = entities[index]
        if entity.get("entity_type") != entity_type:
            raise ValueError("An entity's type cannot be changed by an import; create a reviewed successor or correction record.")

    changed_fields: list[str] = []
    list_fields = {"aliases", "public_links", "accounts", "host_entities", "partner_entities", "audiences",
                   "audience_descriptions", "normalized_audiences", "program_domains", "program_descriptions",
                   "normalized_program_domains", "delivery_modes", "delivery_mode_descriptions",
                   "normalized_delivery_modes", "coverage_scope"}
    for field in sorted(_CLAIM_FIELDS):
        if field not in values:
            continue
        raw_value = values.get(field)
        if raw_value is None or raw_value == "":
            continue
        if field in list_fields:
            normalized: Any = _list(raw_value)
            if not normalized:
                continue
        elif field in {"latitude", "longitude"}:
            normalized = _number(raw_value, field)
        elif field == "status":
            normalized = _clean(raw_value).casefold()
            if normalized not in ENTITY_STATUSES:
                raise ValueError(f"status must be one of: {', '.join(sorted(ENTITY_STATUSES))}")
        else:
            normalized = _clean(raw_value)
        if normalized in (None, "", []):
            continue
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        prior = next((claim for claim in entity["claims"] if claim.get("field") == field and json.dumps(claim.get("value"), ensure_ascii=False, sort_keys=True) == encoded), None)
        if prior is not None:
            prior_refs = prior.setdefault("evidence_refs", [])
            for ref in refs:
                if ref not in prior_refs:
                    prior_refs.append(ref)
            prior["updated_at"] = _now()
            continue
        entity["claims"].append({
            "claim_id": str(uuid.uuid4()), "field": field, "value": normalized,
            "evidence_refs": refs, "observed_at": observed_at or _now(),
            "valid_from": _clean(values.get("valid_from")), "valid_to": _clean(values.get("valid_to")),
            "review_state": review_state, "reviewer": _clean(actor) if review_state == "human_verified" else "",
            "review_note": _clean(reason), "created_at": _now(),
        })
        changed_fields.append(field)

    old_status = _clean(entity.get("status") or "unknown")
    claimed_status = _clean(values.get("status")).casefold()
    entity["updated_at"] = _now()
    entity = _refresh_entity(entity)
    new_status = _clean(entity.get("status") or "unknown")
    if claimed_status in ENTITY_STATUSES and (new_status != old_status or "status" in changed_fields or "status_date" in changed_fields):
        _append_jsonl(paths["lifecycle"], {
            "event_id": str(uuid.uuid4()), "entity_id": entity_id,
            "event_type": new_status if new_status != "unknown" else "status_claim",
            "previous_status": old_status, "status": new_status if new_status != "unknown" else claimed_status,
            "effective_date": _clean(values.get("status_date") or values.get("closed_date") or values.get("opened_date")),
            "observed_at": observed_at or _now(), "evidence_refs": refs,
            "review_state": review_state, "reviewer": _clean(actor) if review_state == "human_verified" else "",
        })
    if index is None:
        entities[-1] = entity
    else:
        entities[index] = entity
    _write_jsonl(paths["entities"], entities)
    _append_jsonl(paths["history"], {
        "event_id": str(uuid.uuid4()), "event_type": "entity_updated" if changed_fields else "evidence_refreshed",
        "entity_id": entity_id, "fields": changed_fields, "actor": _clean(actor),
        "reason": _clean(reason), "observed_at": observed_at or _now(), "evidence_refs": refs,
    })
    workspace.register_artifact("reference_registry", paths["entities"], label="Evidence-backed entity registry")
    if paths["lifecycle"].is_file():
        workspace.register_artifact("reference_lifecycle", paths["lifecycle"], label="Evidence-backed entity lifecycle events")
    return entity


def upsert_entity(
    workspace: SugarWorkspace,
    values: dict[str, Any],
    *,
    evidence_refs: Any,
    actor: str = "analyst",
    reason: str = "",
    review_state: str = "unreviewed",
    observed_at: str | None = None,
) -> dict[str, Any]:
    return _record_entity(
        workspace, values, evidence_refs=evidence_refs, actor=actor, reason=reason,
        review_state=review_state, observed_at=observed_at,
    )


def add_relationship(
    workspace: SugarWorkspace,
    *,
    source_entity_id: str,
    target_entity_id: str,
    relationship_type: str,
    evidence_refs: Any,
    actor: str = "analyst",
    review_state: str = "unreviewed",
    valid_from: str = "",
    valid_to: str = "",
    note: str = "",
) -> dict[str, Any]:
    kind = _clean(relationship_type).casefold()
    if kind not in RELATIONSHIP_TYPES:
        raise ValueError(f"relationship_type must be one of: {', '.join(sorted(RELATIONSHIP_TYPES))}")
    if review_state not in {"unreviewed", "human_verified", "needs_followup", "rejected"}:
        raise ValueError("Unsupported relationship review state.")
    start_date = _relationship_date(valid_from, "valid_from")
    end_date = _relationship_date(valid_to, "valid_to")
    if start_date and end_date and end_date < start_date:
        raise ValueError("valid_to must be on or after valid_from.")
    source_id, target_id = _clean(source_entity_id), _clean(target_entity_id)
    if not source_id or not target_id or source_id == target_id:
        raise ValueError("Relationships require two different entity IDs.")
    available_ids = {row["entity_id"] for row in list_entities(workspace)}
    missing_ids = sorted({source_id, target_id} - available_ids)
    if missing_ids:
        raise KeyError("Relationship endpoints must exist in the registry: " + ", ".join(missing_ids))
    refs = _evidence_refs(evidence_refs)
    if not refs:
        raise ValueError("Relationships require at least one evidence reference.")
    path = registry_paths(workspace)["relationships"]
    rows = _jsonl(path)
    key = (source_id, target_id, kind, start_date, end_date)
    existing = next((row for row in rows if (
        row.get("source_entity_id"), row.get("target_entity_id"), row.get("relationship_type"),
        row.get("valid_from", ""), row.get("valid_to", "")
    ) == key), None)
    if existing:
        for ref in refs:
            if ref not in existing["evidence_refs"]:
                existing["evidence_refs"].append(ref)
        existing["updated_at"] = _now()
        relationship = existing
    else:
        relationship = {
            "relationship_id": str(uuid.uuid4()), "source_entity_id": source_id,
            "target_entity_id": target_id, "relationship_type": kind, "evidence_refs": refs,
            "valid_from": start_date, "valid_to": end_date, "note": _clean(note),
            "observed_at": _now(), "review_state": review_state,
            "reviewer": _clean(actor) if review_state == "human_verified" else "",
            "created_at": _now(), "updated_at": _now(),
        }
        rows.append(relationship)
    _write_jsonl(path, rows)
    _append_jsonl(registry_paths(workspace)["history"], {
        "event_id": str(uuid.uuid4()), "event_type": "relationship_added",
        "relationship_id": relationship["relationship_id"], "actor": _clean(actor), "observed_at": _now(),
    })
    workspace.register_artifact("reference_relationships", path, label="Evidence-backed entity relationships")
    return relationship


def list_relationships(workspace: SugarWorkspace, *, entity_id: str = "") -> list[dict[str, Any]]:
    rows = _jsonl(registry_paths(workspace)["relationships"])
    if entity_id:
        rows = [row for row in rows if entity_id in {row.get("source_entity_id"), row.get("target_entity_id")}]
    return rows


def list_lifecycle(workspace: SugarWorkspace, *, entity_id: str = "") -> list[dict[str, Any]]:
    rows = _jsonl(registry_paths(workspace)["lifecycle"])
    if entity_id:
        rows = [row for row in rows if row.get("entity_id") == entity_id]
    return rows


def entity_profile(workspace: SugarWorkspace, entity_id: str) -> dict[str, Any]:
    entity = next((row for row in list_entities(workspace) if row.get("entity_id") == entity_id), None)
    if entity is None:
        raise KeyError(f"No registry entity with ID {entity_id!r}.")
    entity["relationships"] = list_relationships(workspace, entity_id=entity_id)
    entity["lifecycle_history"] = list_lifecycle(workspace, entity_id=entity_id)
    evidence = {json.dumps(ref, ensure_ascii=False, sort_keys=True): ref
                for claim in entity.get("claims", []) for ref in claim.get("evidence_refs", [])}
    entity["source_evidence"] = list(evidence.values())
    return entity


def import_reference_dataset(
    workspace: SugarWorkspace,
    path: str | Path,
    *,
    mapping: dict[str, str],
    dataset_name: str = "",
    network: str = "",
    geographic_scope: str = "",
    known_coverage_limits: str = "",
    license_notes: str = "",
    actor: str = "analyst",
    review_state: str = "unreviewed",
    accept_partial: bool = False,
) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    rows, columns = load_reference_table(source)
    missing_columns = sorted(set(mapping.values()) - set(columns))
    if missing_columns:
        raise ValueError("Field mapping refers to missing source columns: " + ", ".join(missing_columns))
    if not mapping.get("name"):
        raise ValueError("Confirm a source column for the required name field before import.")
    errors = [error for index, row in enumerate(rows, start=2) for error in _validate_reference_row(row, mapping, index)]
    bad_rows = {int(error.split(":", 1)[0].split()[1]) for error in errors}
    if bad_rows and not accept_partial:
        raise ValueError(f"Dataset has {len(bad_rows)} invalid rows. Review preview and explicitly accept partial import to continue.")
    before_entities = list_entities(workspace)
    before_by_id = {entity["entity_id"]: entity for entity in before_entities}
    before_lifecycle_count = len(_jsonl(registry_paths(workspace)["lifecycle"]))
    digest = _sha256(source)
    paths = registry_paths(workspace)
    source_directory = paths["entities"].parent / "sources"
    source_directory.mkdir(parents=True, exist_ok=True)
    source_copy = source_directory / f"{digest[:12]}_{source.name}"
    if not source_copy.exists():
        shutil.copy2(source, source_copy)
    source_relative = source_copy.relative_to(workspace.root).as_posix()
    base = {
        "dataset_id": "ds_" + digest[:20], "name": _clean(dataset_name) or source.stem,
        "source_path": source_relative, "sha256": digest, "format": source.suffix.casefold().lstrip("."),
        "imported_at": _now(), "updated_at": _now(), "row_count": len(rows),
        "valid_rows": len(rows) - len(bad_rows), "invalid_rows": len(bad_rows),
        "field_mapping": mapping, "network": _clean(network),
        "geographic_scope": _clean(geographic_scope), "known_coverage_limits": _clean(known_coverage_limits),
        "license_notes": _clean(license_notes), "actor": _clean(actor),
        "normalization": {
            "version": TAXONOMY_VERSION,
            "method": "exact curated label mapping from explicitly supplied program/audience/delivery fields; source wording is retained",
        },
    }
    source_license_values = sorted({
        _clean(_mapped_value(row, mapping, "source_license"))
        for row in rows if _clean(_mapped_value(row, mapping, "source_license"))
    })
    base["source_license_values"] = source_license_values
    added = 0
    updated = 0
    relationship_candidates: list[dict[str, Any]] = []
    list_fields = {"aliases", "public_links", "accounts", "host_entities", "partner_entities", "audiences", "program_domains", "delivery_modes", "coverage_scope"}
    for row_number, row in enumerate(rows, start=2):
        if row_number in bad_rows:
            continue
        name = _clean(_mapped_value(row, mapping, "name"))
        item_network = _clean(_mapped_value(row, mapping, "network")) or _clean(network)
        external_id = _clean(_mapped_value(row, mapping, "entity_id"))
        entity_type = _clean(_mapped_value(row, mapping, "entity_type")) or "institution"
        if external_id:
            entity_id = external_id
        else:
            entity_id = _stable_id(workspace.manifest.project_id, item_network,
                                   _clean(_mapped_value(row, mapping, "name")),
                                   _clean(_mapped_value(row, mapping, "country")),
                                   _clean(_mapped_value(row, mapping, "region")),
                                   _clean(_mapped_value(row, mapping, "city")),
                                   _clean(_mapped_value(row, mapping, "address")))
        evidence = {
            "source_name": base["name"], "source_file": source_relative, "source_sha256": digest,
            "source_row": row_number, "source_url": _clean(_mapped_value(row, mapping, "source_url")),
            "license_notes": base["license_notes"], "imported_at": base["imported_at"],
        }
        values: dict[str, Any] = {"entity_id": entity_id, "entity_type": entity_type, "network": item_network,
                                  "name": name, "status": _clean(_mapped_value(row, mapping, "status")) or "unknown"}
        for field in _CLAIM_FIELDS - {"name", "network", "status"}:
            value = _mapped_value(row, mapping, field)
            if value not in (None, ""):
                values[field] = _list(value) if field in list_fields else value
        values["status_date"] = _clean(_mapped_value(row, mapping, "status_date") or _mapped_value(row, mapping, "closed_date") or _mapped_value(row, mapping, "opened_date"))
        was_existing = any(item.get("entity_id") == entity_id for item in _jsonl(paths["entities"]))
        _record_entity(workspace, values, evidence_refs=[evidence], actor=actor,
                       reason=f"Imported from {base['name']}", review_state=review_state)
        relationship_candidates.append({"entity_id": entity_id, "network": item_network,
                                         "host_entities": values.get("host_entities", []),
                                         "partner_entities": values.get("partner_entities", []),
                                         "evidence": evidence, "review_state": review_state})
        if was_existing:
            updated += 1
        else:
            added += 1
    datasets = _jsonl(paths["datasets"])
    datasets = [item for item in datasets if item.get("dataset_id") != base["dataset_id"]]
    datasets.append(base)
    _write_jsonl(paths["datasets"], datasets)
    indexed_entities = list_entities(workspace)
    after_by_id = {entity["entity_id"]: entity for entity in indexed_entities}
    changed_fields: list[dict[str, Any]] = []
    for entity_id in sorted(set(before_by_id) & set(after_by_id)):
        before, after = before_by_id[entity_id], after_by_id[entity_id]
        field_deltas = {}
        for field in ("name", "status", "country", "region", "city", "address", "latitude", "longitude",
                      "aliases", "host_entities", "partner_entities", "audiences", "audience_descriptions",
                      "normalized_audiences", "program_domains", "program_descriptions",
                      "normalized_program_domains", "delivery_modes", "delivery_mode_descriptions",
                      "normalized_delivery_modes"):
            if before.get(field) != after.get(field):
                field_deltas[field] = {"before": before.get(field), "after": after.get(field)}
        if field_deltas:
            changed_fields.append({"entity_id": entity_id, "fields": field_deltas})
    name_index: dict[str, list[str]] = {}
    for entity in indexed_entities:
        for label in [entity.get("entity_id", ""), entity.get("name", ""), *_list(entity.get("aliases"))]:
            key = _clean(label).casefold()
            if key:
                name_index.setdefault(key, []).append(entity["entity_id"])
    for candidate in relationship_candidates:
        source_id = candidate["entity_id"]
        relations: list[tuple[str, str]] = []
        for host in _list(candidate["host_entities"]):
            targets = list(dict.fromkeys(name_index.get(host.casefold(), [])))
            if len(targets) == 1 and targets[0] != source_id:
                relations.append((targets[0], "hosted_by"))
        for partner in _list(candidate["partner_entities"]):
            targets = list(dict.fromkeys(name_index.get(partner.casefold(), [])))
            if len(targets) == 1 and targets[0] != source_id:
                relations.append((targets[0], "partner_of"))
        network_entities = [entity for entity in indexed_entities
                            if _clean(entity.get("name")).casefold() == _clean(candidate.get("network")).casefold()
                            and entity.get("entity_type") in {"network", "organization"}]
        if len(network_entities) == 1 and network_entities[0]["entity_id"] != source_id:
            relations.append((network_entities[0]["entity_id"], "member_of"))
        for target_id, relationship_type in dict.fromkeys(relations):
            add_relationship(workspace, source_entity_id=source_id, target_entity_id=target_id,
                             relationship_type=relationship_type, evidence_refs=[candidate["evidence"]],
                             review_state=candidate["review_state"], note=f"Imported from {base['name']}")
    similar_name_candidates: list[dict[str, Any]] = []
    for entity in indexed_entities:
        if entity["entity_id"] not in before_by_id:
            continue
        existing_names = [entity.get("name", ""), *_list(entity.get("aliases"))]
        existing_normalized = [re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE) for value in existing_names if value]
        for imported_entity in indexed_entities:
            if imported_entity["entity_id"] in before_by_id:
                continue
            incoming_name = _clean(imported_entity.get("name"))
            incoming_normalized = re.sub(r"[\W_]+", "", incoming_name.casefold(), flags=re.UNICODE)
            if not incoming_normalized:
                continue
            score = max((difflib.SequenceMatcher(None, incoming_normalized, prior).ratio() for prior in existing_normalized), default=0.0)
            if 0.82 <= score < 1.0:
                similar_name_candidates.append({"incoming_entity_id": imported_entity["entity_id"],
                    "incoming_name": incoming_name, "existing_entity_id": entity["entity_id"],
                    "existing_name": entity.get("name", ""), "similarity": round(score, 3),
                    "decision": "analyst_review_required; records were not merged"})
    lifecycle_events = _jsonl(paths["lifecycle"])[before_lifecycle_count:]
    manifest_path = _registry_dir(workspace) / "dataset_manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": "1.0", "generated_at": _now(), "datasets": datasets,
        "coverage_statement": "Coverage is limited to the sources, network/geography, and dates documented in each dataset record.",
        "excluded_rows": errors[:500],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    workspace.register_artifact("reference_dataset_manifest", manifest_path, label="Reference dataset scope and provenance")
    workspace.register_artifact("reference_dataset_source", source_copy, label=base["name"], metadata={"sha256": digest, "license_notes": base["license_notes"]})
    return {"dataset": base, "added": added, "updated": updated, "excluded_rows": errors,
            "field_changes": changed_fields, "lifecycle_events": lifecycle_events,
            "similar_name_candidates": similar_name_candidates,
            "conflicted_entities": [{"entity_id": entity["entity_id"], "name": entity.get("name"),
                                     "conflicted_fields": entity.get("conflicted_fields", [])}
                                    for entity in list_entities(workspace) if entity.get("conflicted_fields")],
            "entity_count": len(list_entities(workspace))}


def export_registry(workspace: SugarWorkspace, output: str | Path, *, format: str | None = None) -> str:
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    kind = (format or target.suffix.lstrip(".") or "jsonl").casefold()
    entities = list_entities(workspace)
    if kind in {"jsonl", "ndjson"}:
        _write_jsonl(target, entities)
    elif kind == "csv":
        columns = ["entity_id", "entity_type", "network", "name", "aliases", "status", "country", "region", "city", "address", "latitude", "longitude", "location_precision", "audiences", "audience_descriptions", "normalized_audiences", "program_domains", "program_descriptions", "normalized_program_domains", "delivery_modes", "delivery_mode_descriptions", "normalized_delivery_modes", "coverage_scope", "public_links", "accounts", "host_entities", "partner_entities", "conflicted_fields", "claims"]
        with target.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for entity in entities:
                writer.writerow({key: json.dumps(entity.get(key), ensure_ascii=False) if isinstance(entity.get(key), (dict, list)) else entity.get(key, "") for key in columns})
    elif kind in {"geojson", "json"}:
        features = []
        for entity in entities:
            latitude, longitude = _number(entity.get("latitude"), "latitude"), _number(entity.get("longitude"), "longitude")
            if latitude is None or longitude is None:
                continue
            props = {key: value for key, value in entity.items() if key not in {"latitude", "longitude", "resolved_fields"}}
            features.append({"type": "Feature", "id": entity["entity_id"],
                             "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                             "properties": props})
        target.write_text(json.dumps({"type": "FeatureCollection", "features": features,
                                      "metadata": {"generated_at": _now(), "entity_count": len(entities),
                                                   "mapped_entity_count": len(features)}},
                                     ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        raise ValueError("Registry export format must be CSV, JSONL, JSON, or GeoJSON.")
    workspace.register_artifact("reference_registry_export", target, label=f"Registry export ({kind})")
    return str(target)


def compare_entities(left: dict[str, Any], right: dict[str, Any], *, coverage_documented: bool = False) -> dict[str, Any]:
    dimensions: dict[str, dict[str, Any]] = {}
    left_country, right_country = _clean(left.get("country")).casefold(), _clean(right.get("country")).casefold()
    left_city, right_city = _clean(left.get("city")).casefold(), _clean(right.get("city")).casefold()
    left_scope = {value.casefold(): value for value in _list(left.get("coverage_scope"))}
    right_scope = {value.casefold(): value for value in _list(right.get("coverage_scope"))}
    shared_scopes = sorted(left_scope[key] for key in set(left_scope) & set(right_scope))
    geographic_known = bool((left_country and right_country) or (left_scope and right_scope))
    same_country = left_country == right_country if left_country and right_country else None
    same_city = left_city == right_city if left_city and right_city else None
    distance = _geometry_distance_km(left, right)
    geo_match = bool(same_country is True or (same_city is True and same_country is not False)
                     or (distance is not None and distance <= 50) or shared_scopes)
    geographic_basis = (
        "shared_source_provided_service_scope" if shared_scopes else
        "same_city" if same_city is True and same_country is not False else
        "same_country" if same_country is True else
        "distance_within_50_km" if distance is not None and distance <= 50 else
        "none_observed"
    )
    dimensions["geographic"] = {
        "status": "supported" if geo_match else "no_match_in_documented_data" if geographic_known and coverage_documented else "unknown",
        "same_country": same_country, "same_city": same_city, "distance_km": distance,
        "shared_service_scope_terms": shared_scopes, "basis": geographic_basis,
        "evidence_refs": [*left.get("source_evidence", []), *right.get("source_evidence", [])],
        "note": "Shared coverage terms are exact source-provided matches. Country/city presence and distance are reported at their available precision; co-presence does not establish competition.",
    }
    for canonical_field, source_field, name in (
        ("normalized_audiences", "audience_descriptions", "audience"),
        ("normalized_program_domains", "program_descriptions", "program_service"),
        ("normalized_delivery_modes", "delivery_mode_descriptions", "delivery_mode"),
    ):
        a = {value.casefold(): value for value in _list(left.get(canonical_field))}
        b = {value.casefold(): value for value in _list(right.get(canonical_field))}
        source_a = {value.casefold(): value for value in _list(left.get(source_field))}
        source_b = {value.casefold(): value for value in _list(right.get(source_field))}
        overlap = sorted(a[key] for key in set(a) & set(b))
        source_overlap = sorted(source_a[key] for key in set(source_a) & set(source_b))
        dimensions[name] = {
            "status": "supported" if overlap else "observed_unclassified_label_overlap" if source_overlap else "no_match_in_documented_data" if a and b and coverage_documented else "unknown",
            "shared_values": overlap, "shared_source_labels": source_overlap,
            "left_values": list(a.values()), "right_values": list(b.values()),
            "left_source_descriptions": list(source_a.values()), "right_source_descriptions": list(source_b.values()),
            "evidence_refs": [*left.get("source_evidence", []), *right.get("source_evidence", [])],
            "note": "Normalized overlap uses exact curated taxonomy matches. Source wording is retained; unclassified wording is shown separately and does not become a normalized category.",
        }
    left_id, right_id = _clean(left.get("entity_id")), _clean(right.get("entity_id"))
    relation_rows = [*left.get("relationships", []), *right.get("relationships", [])]
    matched_relations = [row for row in relation_rows if {row.get("source_entity_id"), row.get("target_entity_id")} == {left_id, right_id}]
    dimensions["institutional"] = {
        "status": "supported" if matched_relations else "no_relationship_observed_within_registry" if coverage_documented else "unknown",
        "relationships": matched_relations,
        "evidence_refs": [ref for row in matched_relations for ref in row.get("evidence_refs", [])],
    }
    left_start, left_end = _documented_lifecycle_interval(left)
    right_start, right_end = _documented_lifecycle_interval(right)
    complete_intervals = all(value is not None for value in (left_start, left_end, right_start, right_end))
    intervals_valid = complete_intervals and left_start <= left_end and right_start <= right_end
    if intervals_valid:
        temporal_overlap = max(left_start, right_start) <= min(left_end, right_end)
        temporal_status = "supported" if temporal_overlap else "no_match_in_documented_data" if coverage_documented else "unknown"
    else:
        temporal_overlap = None
        temporal_status = "unknown"
    dimensions["temporal"] = {
        "status": temporal_status, "documented_interval_overlap": temporal_overlap,
        "left_interval": {"opened_date": left_start.isoformat() if left_start else "",
                          "closed_date": left_end.isoformat() if left_end else ""},
        "right_interval": {"opened_date": right_start.isoformat() if right_start else "",
                           "closed_date": right_end.isoformat() if right_end else ""},
        "evidence_refs": [*left.get("source_evidence", []), *right.get("source_evidence", [])],
        "note": "A temporal non-overlap is reported only when both records have sourced opening and closing dates (or a dated closed-status claim). Missing lifecycle bounds remain unknown.",
    }
    return {
        "left_entity_id": left_id, "right_entity_id": right_id, "dimensions": dimensions,
        "comparative_popularity": "not_assessed", "comparative_effectiveness": "not_assessed",
        "outcomes": "not_assessed", "causal_influence": "not_assessed",
        "interpretation": "These dimensions describe supported co-presence or shared attributes; they do not rate competition, popularity, effectiveness, or influence.",
    }


def _geometry_distance_km(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    lat1, lon1 = _number(left.get("latitude"), "latitude"), _number(left.get("longitude"), "longitude")
    lat2, lon2 = _number(right.get("latitude"), "latitude"), _number(right.get("longitude"), "longitude")
    if None in (lat1, lon1, lat2, lon2):
        return None
    from math import asin, cos, radians, sin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    value = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(value))


def _documented_lifecycle_interval(entity: dict[str, Any]) -> tuple[date | None, date | None]:
    def parse(value: Any) -> date | None:
        text = _clean(value)
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    opened = parse(entity.get("opened_date"))
    closed = parse(entity.get("closed_date"))
    if closed is None and _clean(entity.get("status")).casefold() == "closed":
        closed = parse(entity.get("status_date"))
    return opened, closed
