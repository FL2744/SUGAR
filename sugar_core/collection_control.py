from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .collector_registry import COLLECTORS
from .workspace import SugarWorkspace


_RUN_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_MAX_ITEMS = 100


def _control_path(workspace: SugarWorkspace, run_id: str) -> Path:
    identifier = str(run_id or "").strip()
    if not _RUN_ID.fullmatch(identifier):
        raise ValueError("Collection run ID must be an 8–64 character identifier.")
    return workspace.root / ".sugar" / "collection-runs" / f"{identifier}.json"


def _string_list(value: Any, field: str, *, maximum_length: int = 240) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_ITEMS:
        raise ValueError(f"{field} must be a list with at most {_MAX_ITEMS} values.")
    values = []
    for item in value:
        text = str(item).strip()
        if len(text) > maximum_length:
            raise ValueError(f"Each {field} value must be {maximum_length} characters or fewer.")
        if text and text not in values:
            values.append(text)
    return values


def _date_value(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO date (YYYY-MM-DD).") from exc
    return text


def _source_values(value: Any) -> list[str]:
    sources = [item.casefold() for item in _string_list(value, "sources", maximum_length=40)]
    unsupported = sorted(set(sources) - set(COLLECTORS))
    if unsupported:
        raise ValueError(f"Unsupported collection source(s): {', '.join(unsupported)}")
    return sources


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def start_collection_control(
    workspace: SugarWorkspace,
    run_id: str,
    *,
    sources: Any,
    since: Any = "",
    until: Any = "",
    post_languages: Any = None,
    terms: Any = None,
    excluded_topics: Any = None,
) -> dict[str, Any]:
    path = _control_path(workspace, run_id)
    if path.exists():
        raise ValueError("A collection run with this ID already exists.")
    payload = {
        "run_id": run_id,
        "status": "running",
        "revision": 1,
        "sources": _source_values(sources),
        "since": _date_value(since, "since"),
        "until": _date_value(until, "until"),
        "post_languages": [value.casefold() for value in _string_list(post_languages, "post_languages", maximum_length=16)],
        "terms": _string_list(terms, "terms"),
        "excluded_topics": _string_list(excluded_topics, "excluded_topics"),
        "retry_requests": [],
        "cancel_requested": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload["since"] and payload["until"] and payload["since"] > payload["until"]:
        raise ValueError("since must be on or before until.")
    _write(path, payload)
    return payload


def read_collection_control(workspace: SugarWorkspace, run_id: str) -> dict[str, Any] | None:
    path = _control_path(workspace, run_id)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("run_id") != run_id:
        raise ValueError("Collection run control file is invalid.")
    return payload


def update_collection_control(
    workspace: SugarWorkspace,
    run_id: str,
    *,
    sources: Any = None,
    since: Any = None,
    until: Any = None,
    post_languages: Any = None,
    terms: Any = None,
    excluded_topics: Any = None,
    retry_source: Any = None,
    cancel: Any = None,
) -> dict[str, Any]:
    path = _control_path(workspace, run_id)
    payload = read_collection_control(workspace, run_id)
    if payload is None or payload.get("status") != "running":
        raise ValueError("This collection run is no longer active.")
    if sources is not None:
        payload["sources"] = _source_values(sources)
    if since is not None:
        payload["since"] = _date_value(since, "since")
    if until is not None:
        payload["until"] = _date_value(until, "until")
    if payload.get("since") and payload.get("until") and payload["since"] > payload["until"]:
        raise ValueError("since must be on or before until.")
    if post_languages is not None:
        payload["post_languages"] = [value.casefold() for value in _string_list(post_languages, "post_languages", maximum_length=16)]
    if terms is not None:
        payload["terms"] = _string_list(terms, "terms")
    if excluded_topics is not None:
        payload["excluded_topics"] = _string_list(excluded_topics, "excluded_topics")
    if retry_source is not None:
        selected = _source_values([retry_source])
        if not selected:
            raise ValueError("Choose a valid collection source to retry.")
        source = selected[0]
        retry_requests = payload.setdefault("retry_requests", [])
        if len(retry_requests) >= _MAX_ITEMS:
            raise ValueError("A collection run can queue at most 100 source retries.")
        payload.setdefault("retry_requests", []).append({"id": uuid.uuid4().hex, "source": source})
    if cancel is not None:
        payload["cancel_requested"] = bool(cancel)
    payload["revision"] = int(payload.get("revision") or 0) + 1
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write(path, payload)
    return payload


def finish_collection_control(workspace: SugarWorkspace, run_id: str, *, status: str) -> None:
    if status not in {"completed", "failed", "cancelled"}:
        raise ValueError("Collection run status must be completed, failed, or cancelled.")
    path = _control_path(workspace, run_id)
    payload = read_collection_control(workspace, run_id)
    if payload is None:
        return
    payload["status"] = status
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write(path, payload)
