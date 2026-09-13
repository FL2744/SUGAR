from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from .llm import LLMConfig
from .models import PostRecord
from .observation_storage import save_observations
from .storage import load_results
from .triage import DEFAULT_PROJECT_CONTEXT, ProgressCallback, triage_posts


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _first(row: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and not _missing(row[key]) and row[key] != "":
            return row[key]
    return default


def _json_list(value: Any) -> list[str]:
    if _missing(value) or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value.strip() else []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    return []


def _json_dict(value: Any) -> dict[str, Any]:
    if _missing(value) or value == "":
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


def _float_or(value: Any, default: float | None) -> float | None:
    if _missing(value) or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not _missing(value):
        return bool(value)
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def post_record_from_mapping(row: Mapping[str, Any]) -> PostRecord:
    platform = str(_first(row, "platform", default="unknown"))
    native_id = str(_first(row, "native_id", "tweet_id"))
    canonical_url = str(_first(row, "canonical_url", "post_url", "x_url"))
    query = str(_first(row, "query"))
    query_matches = _json_list(_first(row, "query_matches", default=[]))
    if query and not query_matches:
        query_matches = [query]

    return PostRecord(
        platform=platform,
        native_id=native_id,
        canonical_url=canonical_url,
        query=query,
        query_matches=query_matches,
        content_type=str(_first(row, "content_type", default="post")),
        source_mode=str(_first(row, "source_mode", default="api")),
        source_host=str(_first(row, "source_host")),
        source_url=str(_first(row, "source_url")),
        collected_at=str(_first(row, "collected_at")),
        collector_version=str(_first(row, "collector_version", default="sugar-core-1.1")),
        schema_version=str(_first(row, "schema_version", default="1.1")),
        published_at=str(_first(row, "published_at", "date_iso", "date_raw")),
        author_handle=str(_first(row, "author_handle", "username")),
        author_name=str(_first(row, "author_name", "display_name")),
        author_location=str(_first(row, "author_location")),
        platform_language=str(_first(row, "platform_language")),
        detected_language=str(_first(row, "detected_language")),
        original_text=str(_first(row, "original_text")),
        translated_text=str(_first(row, "translated_text", "translated_en")),
        engagement={key: int(value or 0) for key, value in _json_dict(_first(row, "engagement", default={})).items()},
        raw_stats=_json_dict(_first(row, "raw_stats", default={})),
        is_repost=_bool(_first(row, "is_repost", "is_retweet", default=False)),
        inferred_location=str(_first(row, "inferred_location")),
        location_confidence=float(_float_or(_first(row, "location_confidence", default=0.0), 0.0) or 0.0),
        location_source=str(_first(row, "location_source")),
        location_reason=str(_first(row, "location_reason")),
        latitude=_float_or(_first(row, "latitude", default=None), None),
        longitude=_float_or(_first(row, "longitude", default=None), None),
        geocode_display_name=str(_first(row, "geocode_display_name")),
    )


def load_post_records(path: str | Path) -> list[PostRecord]:
    frame = load_results(path)
    return [post_record_from_mapping(row) for row in frame.to_dict(orient="records")]


def triage_dataset(
    source_file: str | Path,
    output_file: str | Path,
    *,
    llm: LLMConfig,
    cache_dir: str | Path | None = None,
    project_context: str = DEFAULT_PROJECT_CONTEXT,
    progress: ProgressCallback | None = None,
    continue_on_error: bool = True,
) -> list[str]:
    source_file = Path(source_file).expanduser().resolve()
    output_file = Path(output_file).expanduser().resolve()
    cache_path = Path(cache_dir).expanduser().resolve() if cache_dir else output_file.parent / ".sugar-cache"

    records = load_post_records(source_file)
    if not records:
        raise ValueError("The selected post dataset contains no records.")

    observations = triage_posts(
        records,
        llm=llm,
        cache_dir=cache_path,
        project_context=project_context,
        progress=progress,
        continue_on_error=continue_on_error,
    )
    save_observations(
        observations,
        output_file,
        metadata={
            "source_file": source_file.name,
            "triage_provider": llm.provider,
            "triage_model": llm.model,
            "triage_project_context": project_context,
        },
    )
    csv_path = output_file if output_file.suffix.lower() == ".csv" else output_file.with_suffix(".csv")
    return [
        str(csv_path),
        str(csv_path.with_suffix(".xlsx")),
        str(csv_path.with_suffix(".metadata.json")),
    ]
