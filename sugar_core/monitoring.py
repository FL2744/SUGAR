"""Keeping the picture current: scheduled refreshes, and a digest of what changed.

A *monitor* repeats a project's current plan on a schedule. Each pass flags new and changed items and ends with a
*digest*: what is new, which institutions appeared, closed, were renamed or moved, which programs and audiences
changed, and which sources could not be read. The institution part compares the registry with its state at the
previous digest, so it also picks up changes made by hand or by an import between passes.

The scheduler is a polite background loop. It never starts a run while another is active in the same project, never
more than one project run at a time per project, and a failed pass is recorded in the digest rather than retried
in a tight loop.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .reference_registry import list_entities
from .research_plan import utc_now

CADENCES_HOURS = (1, 6, 12, 24, 72, 168, 336, 720)
TERMINAL = {"completed", "completed_with_warnings", "failed", "cancelled"}


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------------ monitors
def list_monitors(project: Any) -> list[dict[str, Any]]:
    return [dict(m) for m in (project.meta().get("settings") or {}).get("monitors", []) if isinstance(m, dict)]


def _save(project: Any, monitors: list[dict[str, Any]], actor: str) -> None:
    project.update_settings({"monitors": monitors}, actor=actor)


def save_monitor(project: Any, *, name: str, cadence_hours: int, monitor_id: str = "", enabled: bool = True, note: str = "", actor: str = "analyst") -> dict[str, Any]:
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("Give the monitor a name.")
    if int(cadence_hours) not in CADENCES_HOURS:
        raise ValueError("Choose how often to check: " + ", ".join(f"{h}h" for h in CADENCES_HOURS) + ".")
    if project.load_plan() is None:
        raise ValueError("This project has no research plan yet. Interpret a research request first; a monitor repeats the current plan.")
    monitors = list_monitors(project)
    existing = next((m for m in monitors if m["id"] == monitor_id), None) if monitor_id else None
    if existing is None:
        existing = {"id": f"mon_{uuid.uuid4().hex[:8]}", "created_at": utc_now(), "last_run_at": "", "last_run_id": "", "last_status": "", "next_due_at": _iso(_now_dt())}
        monitors.append(existing)
    existing.update({"name": name[:80], "cadence_hours": int(cadence_hours), "enabled": bool(enabled), "note": str(note or "")[:300]})
    if existing.get("last_run_at"):
        last = _parse(existing["last_run_at"])
        existing["next_due_at"] = _iso(last + timedelta(hours=int(cadence_hours))) if last else _iso(_now_dt())
    _save(project, monitors, actor)
    project.log("monitor_saved", {"monitor_id": existing["id"], "name": existing["name"], "cadence_hours": existing["cadence_hours"]}, actor=actor)
    return existing


def delete_monitor(project: Any, monitor_id: str, *, actor: str = "analyst") -> None:
    monitors = [m for m in list_monitors(project) if m["id"] != monitor_id]
    _save(project, monitors, actor)
    project.log("monitor_deleted", {"monitor_id": monitor_id}, actor=actor)


def due_monitors(project: Any, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or _now_dt()
    return [m for m in list_monitors(project) if m.get("enabled") and (_parse(m.get("next_due_at", "")) or now) <= now]


# ------------------------------------------------------------------------------------------------ registry snapshots and digests
def _snapshot(project: Any) -> dict[str, dict[str, Any]]:
    return {e["entity_id"]: {"name": e.get("name", ""), "status": e.get("status", "unknown"), "city": e.get("city", ""), "country": e.get("country", ""), "network": e.get("network", ""),
                             "programs": sorted(e.get("normalized_program_domains", [])), "audiences": sorted(e.get("normalized_audiences", [])), "sources": len({
                                 str(r.get("source_url", "")) for c in e.get("claims", []) for r in c.get("evidence_refs", []) if isinstance(r, dict)})}
            for e in list_entities(project.workspace)}


def diff_registry(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Institution-level changes between two snapshots. Each says what changed and from what to what."""
    changes: list[dict[str, Any]] = []
    for eid, now in after.items():
        was = before.get(eid)
        if was is None:
            changes.append({"entity_id": eid, "name": now["name"], "kind": "new", "detail": f"New record{' in ' + now['country'] if now['country'] else ''}", "after": now["status"]})
            continue
        if was["status"] != now["status"]:
            kind = "closed" if now["status"] == "closed" else "reopened" if was["status"] == "closed" else "status"
            changes.append({"entity_id": eid, "name": now["name"], "kind": kind, "detail": f"Status {was['status']} → {now['status']}", "before": was["status"], "after": now["status"]})
        if was["name"] != now["name"]:
            changes.append({"entity_id": eid, "name": now["name"], "kind": "renamed", "detail": f"Name “{was['name']}” → “{now['name']}”", "before": was["name"], "after": now["name"]})
        if (was["city"], was["country"]) != (now["city"], now["country"]):
            changes.append({"entity_id": eid, "name": now["name"], "kind": "moved", "detail": f"Place {', '.join(p for p in (was['city'], was['country']) if p) or 'unknown'} → {', '.join(p for p in (now['city'], now['country']) if p) or 'unknown'}"})
        added_p = sorted(set(now["programs"]) - set(was["programs"]))
        added_a = sorted(set(now["audiences"]) - set(was["audiences"]))
        if added_p or added_a:
            changes.append({"entity_id": eid, "name": now["name"], "kind": "activity", "detail": "New " + "; ".join(x for x in (("programs: " + ", ".join(added_p)) if added_p else "", ("audiences: " + ", ".join(added_a)) if added_a else "") if x)})
    for eid, was in before.items():
        if eid not in after:
            changes.append({"entity_id": eid, "name": was["name"], "kind": "removed", "detail": "Record merged or removed"})
    return changes


def _digest_path(project: Any):
    return project.root / "digests.jsonl"


def list_digests(project: Any, limit: int = 30) -> list[dict[str, Any]]:
    try:
        lines = _digest_path(project).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return list(reversed(rows))[:limit]


def build_digest(project: Any, *, run_id: str = "", monitor_id: str = "", trigger: str = "manual", items: list[Any] | None = None, run_row: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record what changed since the previous digest and store the registry state to compare against next time."""
    snapshot_path = project.root / "registry-snapshot.json"
    try:
        before = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        before = None
    after = _snapshot(project)
    changes = diff_registry(before, after) if before is not None else []
    first = before is None
    new_items = [i for i in (items or []) if not getattr(i, "known_from_run", "") and getattr(i, "status", "") in {"collected", "processed"}]
    changed_items = [i for i in (items or []) if getattr(i, "changed_since_known", False)]
    completeness = (run_row or {}).get("completeness") or {}
    digest = {
        "id": f"dg_{uuid.uuid4().hex[:10]}", "at": utc_now(), "run_id": run_id, "monitor_id": monitor_id, "trigger": trigger, "first_pass": first,
        "run_status": (run_row or {}).get("status", ""),
        "counts": {"new_items": len(new_items), "changed_items": len(changed_items), "institution_changes": len(changes), "institutions": len(after),
                   "incomplete_sources": len(completeness.get("incomplete_sources", []))},
        "new_items": [{"item_id": i.item_id, "platform": i.platform, "url": i.url, "text": (i.original_text or "")[:160]} for i in new_items[:25]],
        "changed_items": [{"item_id": i.item_id, "platform": i.platform, "url": i.url, "text": (i.original_text or "")[:160]} for i in changed_items[:25]],
        "institution_changes": changes[:100], "incomplete_sources": completeness.get("incomplete_sources", []),
        "summary": _summary(first, len(new_items), len(changed_items), changes, completeness),
    }
    with project._lock:
        project.root.mkdir(parents=True, exist_ok=True)
        with _digest_path(project).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(digest, ensure_ascii=False) + "\n")
        snapshot_path.write_text(json.dumps(after, ensure_ascii=False), encoding="utf-8")
    project.log("digest_created", {"digest_id": digest["id"], "run_id": run_id, "counts": digest["counts"]}, actor="SUGAR")
    return digest


def _summary(first: bool, new_items: int, changed: int, changes: list[dict[str, Any]], completeness: dict[str, Any]) -> str:
    if first:
        return "Baseline recorded. Future digests will show what changed from here."
    parts = []
    if new_items:
        parts.append(f"{new_items} new item{'s' if new_items != 1 else ''}")
    if changed:
        parts.append(f"{changed} changed item{'s' if changed != 1 else ''}")
    kinds: dict[str, int] = {}
    for c in changes:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    labels = {"new": "new institution", "closed": "closure", "reopened": "reopening", "renamed": "rename", "moved": "move", "activity": "activity update", "status": "status change", "removed": "merge"}
    for kind, n in kinds.items():
        parts.append(f"{n} {labels.get(kind, kind)}{'s' if n != 1 else ''}")
    if completeness.get("incomplete_sources"):
        parts.append(f"{len(completeness['incomplete_sources'])} source(s) could not be read")
    return ", ".join(parts).capitalize() + "." if parts else "Nothing changed since the last check."


# ------------------------------------------------------------------------------------------------ running
def run_monitor(wb: Any, project: Any, monitor_id: str, *, now: datetime | None = None, actor: str = "SUGAR") -> dict[str, Any]:
    """Start one pass of a monitor: a source refresh if a run exists, otherwise a first run of the current plan."""
    now = now or _now_dt()
    monitors = list_monitors(project)
    monitor = next((m for m in monitors if m["id"] == monitor_id), None)
    if monitor is None:
        raise KeyError("That monitor does not exist.")
    kind = "refresh_sources" if project.latest_run(completed_only=True) else "run"
    started = wb.start_run(project, kind=kind)
    run_id = (started.get("run") or started).get("run_id", "")
    monitor.update({"last_run_at": _iso(now), "last_run_id": run_id, "last_status": "running", "next_due_at": _iso(now + timedelta(hours=int(monitor["cadence_hours"])))})
    _save(project, monitors, actor)
    project.log("monitor_run_started", {"monitor_id": monitor_id, "run_id": run_id, "kind": kind}, actor=actor)
    return {"monitor": monitor, "run_id": run_id, "kind": kind}


def finalize_finished(wb: Any, project: Any) -> list[dict[str, Any]]:
    """Create a digest for every monitor pass that has finished since it started."""
    made = []
    monitors = list_monitors(project)
    digested = {d.get("run_id") for d in list_digests(project, 500)}
    changed = False
    for monitor in monitors:
        run_id = monitor.get("last_run_id", "")
        if not run_id or monitor.get("last_status") != "running" or run_id in digested:
            continue
        row = project.get_run(run_id)
        status = row.status if row is not None and hasattr(row, "status") else (row or {}).get("status", "")
        if status not in TERMINAL:
            continue
        try:
            items = wb.items(project, run_id)
        except Exception:
            items = []
        run_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row or {})
        made.append(build_digest(project, run_id=run_id, monitor_id=monitor["id"], trigger="schedule", items=items, run_row=run_dict))
        monitor["last_status"] = status
        changed = True
    if changed:
        _save(project, monitors, "SUGAR")
    return made


class MonitorScheduler:
    """Checks every project once a minute for due monitors and finished passes. Failures are logged, never raised."""

    def __init__(self, projects: Callable[[], list[Any]], workbench: Callable[[], Any], *, interval: float = 60.0, clock: Callable[[], datetime] = _now_dt,
                 on_error: Callable[[str], None] | None = None) -> None:
        self.projects, self.workbench, self.interval, self.clock = projects, workbench, interval, clock
        self.on_error = on_error or (lambda message: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> dict[str, int]:
        started = digested = 0
        wb = self.workbench()
        for project in self.projects():
            try:
                digested += len(finalize_finished(wb, project))
                for monitor in due_monitors(project, self.clock()):
                    try:
                        run_monitor(wb, project, monitor["id"], now=self.clock())
                        started += 1
                    except Exception as exc:         # a busy project or a missing plan just waits for the next pass
                        self._defer(project, monitor, str(exc))
            except Exception as exc:
                self.on_error(f"monitor tick failed: {exc}")
        return {"started": started, "digests": digested}

    def _defer(self, project: Any, monitor: dict[str, Any], reason: str) -> None:
        monitors = list_monitors(project)
        for m in monitors:
            if m["id"] == monitor["id"]:
                m["next_due_at"] = _iso(self.clock() + timedelta(minutes=30))     # try again later; do not hammer
                m["last_status"] = f"deferred: {reason[:120]}"
        _save(project, monitors, "SUGAR")

    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.wait(self.interval):
                self.tick()
        self._thread = threading.Thread(target=loop, name="sugar-monitors", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


__all__ = ["CADENCES_HOURS", "MonitorScheduler", "build_digest", "delete_monitor", "diff_registry", "due_monitors", "finalize_finished", "list_digests", "list_monitors", "run_monitor", "save_monitor"]
