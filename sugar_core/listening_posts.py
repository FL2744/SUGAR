from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .workspace import SugarWorkspace
from .workspace_memory import log_project_event, utc_now


MONITOR_SOURCES = {"bilibili", "weibo", "x", "bluesky", "mastodon"}
MONITOR_STATUSES = {"active", "paused"}


def _path(workspace: SugarWorkspace) -> Path:
    target = workspace.internal_path / "listening-posts.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read(workspace: SugarWorkspace) -> list[dict[str, Any]]:
    path = _path(workspace)
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError("Listening-post store must contain a JSON array of objects.")
    return payload


def _write(workspace: SugarWorkspace, rows: list[dict[str, Any]]) -> None:
    path = _path(workspace)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    workspace.register_artifact("listening_posts", path, label="Saved monitoring definitions")


def _material_path(workspace: SugarWorkspace) -> Path:
    target = workspace.internal_path / "listening-post-material.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_material(workspace: SugarWorkspace) -> list[dict[str, Any]]:
    path = _material_path(workspace)
    if not path.is_file():
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"Listening-post material line {number} must be an object.")
            rows.append(row)
    return rows


def _write_material(workspace: SugarWorkspace, rows: list[dict[str, Any]]) -> None:
    path = _material_path(workspace)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    temporary.replace(path)
    workspace.register_artifact("listening_post_material", path, label="Incoming evidence and analyst review state")


def list_monitor_material(workspace: SugarWorkspace, *, monitor_id: str = "", review_state: str = "") -> list[dict[str, Any]]:
    rows = _read_material(workspace)
    if monitor_id:
        rows = [row for row in rows if row.get("monitor_id") == monitor_id]
    if review_state:
        rows = [row for row in rows if row.get("review_state") == review_state]
    return sorted(rows, key=lambda row: (row.get("last_seen_at", ""), row.get("name", "").casefold()), reverse=True)


def capture_monitor_material(workspace: SugarWorkspace, monitor: dict[str, Any], source_file: str | Path, *, run_id: str) -> dict[str, Any]:
    """Index newly observed/changed records so repeat searches form a reviewable feed."""
    import pandas as pd

    source = Path(source_file).expanduser().resolve()
    if not source.is_file():
        return {"new": 0, "updated": 0, "unchanged": 0, "new_material_file": ""}
    frame = pd.read_csv(source, dtype=object).fillna("")
    rows = _read_material(workspace)
    by_key = {(str(row.get("monitor_id")), str(row.get("record_key"))): index for index, row in enumerate(rows)}
    new_rows: list[dict[str, Any]] = []
    new_count = updated_count = unchanged_count = 0
    now = utc_now()
    for row_number, (_, series) in enumerate(frame.iterrows(), start=2):
        item = {str(key): (value.item() if hasattr(value, "item") else value) for key, value in series.to_dict().items()}
        platform = str(item.get("platform") or "").strip().casefold()
        native_id = str(item.get("native_id") or item.get("tweet_id") or "").strip()
        key = str(item.get("record_key") or (f"{platform}:{native_id}" if native_id else "")).strip()
        canonical = str(item.get("canonical_url") or item.get("post_url") or item.get("source_url") or "").strip()
        if not key:
            identity = "|".join((platform, canonical, str(item.get("published_at") or ""),
                                  str(item.get("author_handle") or ""), str(item.get("original_text") or "")))
            key = "row_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
        content_hash = hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        compound = (str(monitor["monitor_id"]), key)
        existing_index = by_key.get(compound)
        if existing_index is None:
            record = {
                "material_id": str(uuid.uuid4()), "monitor_id": monitor["monitor_id"], "monitor_name": monitor["name"],
                "record_key": key, "content_hash": content_hash, "first_seen_at": now, "last_seen_at": now,
                "first_run_id": run_id, "last_run_id": run_id, "source_file": str(source),
                "source_row": row_number, "platform": platform, "actor_handle": str(item.get("author_handle") or item.get("username") or ""),
                "canonical_url": canonical, "published_at": str(item.get("published_at") or item.get("date_iso") or ""),
                "review_state": "unreviewed", "review_history": [], "change_state": "new",
            }
            rows.append(record)
            by_key[compound] = len(rows) - 1
            new_rows.append(item)
            new_count += 1
            continue
        record = rows[existing_index]
        if record.get("content_hash") != content_hash:
            record.setdefault("prior_content_hashes", []).append(record.get("content_hash", ""))
            record.update({"content_hash": content_hash, "last_seen_at": now, "last_run_id": run_id,
                           "source_file": str(source), "source_row": row_number, "change_state": "updated",
                           "review_state": "unreviewed", "canonical_url": canonical or record.get("canonical_url", "")})
            new_rows.append(item)
            updated_count += 1
        else:
            record.update({"last_seen_at": now, "last_run_id": run_id, "source_file": str(source), "source_row": row_number})
            unchanged_count += 1
    _write_material(workspace, rows)
    new_file = ""
    if new_rows:
        new_file_path = source.with_name(f"listening_post_{run_id}_new_material.csv")
        pd.DataFrame(new_rows).to_csv(new_file_path, index=False, encoding="utf-8-sig")
        workspace.register_artifact("listening_post_new_material", new_file_path,
                                     label=f"New or changed evidence — {monitor['name']}",
                                     metadata={"monitor_id": monitor["monitor_id"], "run_id": run_id,
                                               "new": new_count, "updated": updated_count})
        new_file = str(new_file_path)
    return {"new": new_count, "updated": updated_count, "unchanged": unchanged_count,
            "new_material_file": new_file, "material_count": len(rows)}


def review_monitor_material(workspace: SugarWorkspace, material_id: str, review_state: str, *, actor: str = "analyst", note: str = "") -> dict[str, Any]:
    state = str(review_state or "").casefold()
    if state not in {"human_verified", "needs_followup", "rejected", "unreviewed"}:
        raise ValueError("Material review state must be human_verified, needs_followup, rejected, or unreviewed.")
    rows = _read_material(workspace)
    record = next((row for row in rows if row.get("material_id") == material_id), None)
    if record is None:
        raise KeyError(f"No listening-post material with ID {material_id!r}.")
    previous = record.get("review_state", "unreviewed")
    record["review_state"] = state
    record.setdefault("review_history", []).append({"previous_state": previous, "review_state": state,
        "actor": str(actor or "analyst"), "note": str(note or ""), "reviewed_at": utc_now()})
    _write_material(workspace, rows)
    log_project_event(workspace, "listening_post_material_reviewed", {
        "material_id": material_id, "monitor_id": record.get("monitor_id"),
        "review_state": state, "note": str(note or ""),
    }, actor=actor)
    return record


def _terms(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text.casefold() not in {current.casefold() for current in result}:
            result.append(text)
    return result


def _next_due(cadence_minutes: int, *, from_time: str | None = None) -> str:
    base = datetime.fromisoformat((from_time or utc_now()).replace("Z", "+00:00"))
    return (base + timedelta(minutes=cadence_minutes)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_monitors(workspace: SugarWorkspace, *, status: str = "") -> list[dict[str, Any]]:
    rows = _read(workspace)
    if status:
        rows = [row for row in rows if row.get("status") == status]
    return sorted(rows, key=lambda row: (row.get("next_due_at", ""), row.get("name", "").casefold()))


def save_monitor(
    workspace: SugarWorkspace,
    *,
    name: str,
    terms: Any,
    sources: Any,
    cadence_minutes: int,
    target_entities: Any = None,
    geographies: Any = None,
    since: str = "",
    until: str = "",
    post_languages: Any = None,
    max_posts_per_query: int = 20,
    max_pages_per_query: int = 1,
    status: str = "active",
    monitor_id: str = "",
    actor: str = "analyst",
    reason: str = "",
) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    query_terms = _terms(terms)
    source_list = sorted({str(source).strip().casefold() for source in (sources if isinstance(sources, list) else [sources]) if str(source).strip()})
    targets = _terms(target_entities)
    if not clean_name:
        raise ValueError("A listening-post name is required.")
    if not query_terms and not targets:
        raise ValueError("A listening post requires search terms or target entities/accounts.")
    unknown = sorted(set(source_list) - MONITOR_SOURCES)
    if unknown:
        raise ValueError("Unsupported listening-post sources: " + ", ".join(unknown))
    if not source_list:
        raise ValueError("Select at least one supported source.")
    cadence = int(cadence_minutes)
    if cadence < 5 or cadence > 525600:
        raise ValueError("Cadence must be from 5 minutes to 365 days.")
    state = str(status or "active").casefold()
    if state not in MONITOR_STATUSES:
        raise ValueError("Listening posts may be active or paused.")
    max_posts = max(10, min(500, int(max_posts_per_query)))
    max_pages = max(1, min(100, int(max_pages_per_query)))
    rows = _read(workspace)
    identifier = str(monitor_id or uuid.uuid4())
    current = next((row for row in rows if row.get("monitor_id") == identifier), None)
    now = utc_now()
    monitor = {
        "schema_version": "1.0", "monitor_id": identifier, "name": clean_name,
        "terms": query_terms, "target_entities": targets, "sources": source_list,
        "geographies": _terms(geographies), "since": str(since or "").strip(),
        "until": str(until or "").strip(), "post_languages": _terms(post_languages),
        "cadence_minutes": cadence, "max_posts_per_query": max_posts,
        "max_pages_per_query": max_pages, "status": state,
        "created_at": (current or {}).get("created_at", now), "updated_at": now,
        "last_run_at": (current or {}).get("last_run_at", ""),
        "last_run_id": (current or {}).get("last_run_id", ""),
        "last_run_status": (current or {}).get("last_run_status", "not_run"),
        "next_due_at": (current or {}).get("next_due_at") or _next_due(cadence),
        "revision": int((current or {}).get("revision", 0)) + 1,
        "last_change_reason": str(reason or "").strip(),
        "last_changed_by": str(actor or "analyst").strip(),
    }
    if current:
        rows[rows.index(current)] = monitor
        event_type = "listening_post_updated"
    else:
        rows.append(monitor)
        event_type = "listening_post_created"
    _write(workspace, rows)
    log_project_event(workspace, event_type, {
        "monitor_id": identifier, "name": clean_name, "revision": monitor["revision"],
        "terms": query_terms, "sources": source_list, "cadence_minutes": cadence,
        "reason": str(reason or "").strip(),
    }, actor=actor)
    return monitor


def set_monitor_status(workspace: SugarWorkspace, monitor_id: str, status: str, *, actor: str = "analyst", reason: str = "") -> dict[str, Any]:
    state = str(status or "").casefold()
    if state not in MONITOR_STATUSES:
        raise ValueError("Listening posts may be active or paused.")
    rows = _read(workspace)
    monitor = next((row for row in rows if row.get("monitor_id") == monitor_id), None)
    if monitor is None:
        raise KeyError(f"No listening post with ID {monitor_id!r}.")
    monitor["status"] = state
    monitor["updated_at"] = utc_now()
    monitor["last_change_reason"] = str(reason or "").strip()
    monitor["last_changed_by"] = str(actor or "analyst").strip()
    monitor["revision"] = int(monitor.get("revision", 0)) + 1
    _write(workspace, rows)
    log_project_event(workspace, "listening_post_status_changed", {
        "monitor_id": monitor_id, "status": state, "reason": reason,
    }, actor=actor)
    return monitor


def due_monitors(workspace: SugarWorkspace, *, at: str | None = None) -> list[dict[str, Any]]:
    now = datetime.fromisoformat((at or utc_now()).replace("Z", "+00:00"))
    due: list[dict[str, Any]] = []
    for row in list_monitors(workspace, status="active"):
        due_at = str(row.get("next_due_at") or "")
        if not due_at:
            due.append(row)
            continue
        try:
            if datetime.fromisoformat(due_at.replace("Z", "+00:00")) <= now:
                due.append(row)
        except ValueError:
            due.append(row)
    return due


def complete_monitor_run(
    workspace: SugarWorkspace,
    monitor_id: str,
    *,
    run_id: str,
    status: str,
    outputs: list[str],
    error: str = "",
    completed_at: str | None = None,
) -> dict[str, Any]:
    rows = _read(workspace)
    monitor = next((row for row in rows if row.get("monitor_id") == monitor_id), None)
    if monitor is None:
        raise KeyError(f"No listening post with ID {monitor_id!r}.")
    now = completed_at or utc_now()
    monitor["last_run_at"] = now
    monitor["last_run_id"] = run_id
    monitor["last_run_status"] = status
    monitor["last_run_outputs"] = list(outputs)
    monitor["last_run_error"] = str(error or "")
    monitor["next_due_at"] = _next_due(int(monitor.get("cadence_minutes", 60)), from_time=now)
    monitor["updated_at"] = now
    _write(workspace, rows)
    log_project_event(workspace, "listening_post_run", {
        "monitor_id": monitor_id, "run_id": run_id, "status": status,
        "outputs": outputs, "error": error, "next_due_at": monitor["next_due_at"],
    })
    return monitor
