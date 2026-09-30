"""Project data model and run persistence for the research workbench.

On disk, inside a SUGAR workspace::

    research/
      project.json                     metadata, current plan, members, settings (credentials by reference only)
      plans/<plan_id>.v<N>.json        every saved plan version (append-only)
      runs/<run_id>/run.json           the Run object (section 24)
      runs/<run_id>/events.jsonl       activity history
      runs/<run_id>/items.jsonl        collected items with provenance + lineage
      runs/<run_id>/translations.jsonl translations linked to their source paragraphs
      notes.jsonl                      analyst notes (author + optional item reference)
      findings.jsonl                   coded findings linked into the evidence chain

Project history (the timeline of section 40) reuses the workspace's existing
``project-history.jsonl`` so it appears alongside every other SUGAR operation.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Iterator

import sugar_core
from . import redaction
from .research_items import ResearchItem
from .research_plan import ResearchPlanSpec, utc_now
from .workspace import SugarWorkspace
from .workspace_memory import list_project_history, log_project_event

RUN_KINDS = ("run", "rerun", "refresh_sources", "reprocess")
RUN_STATUSES = ("queued", "running", "paused", "cancelling", "completed", "completed_with_warnings", "failed", "cancelled")
TERMINAL_STATUSES = {"completed", "completed_with_warnings", "failed", "cancelled"}
PROJECT_SCHEMA = "1.0"
ROLES = ("owner", "editor", "commenter", "viewer")

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    try:
                        value = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(value, dict):
                        rows.append(value)
    except OSError:
        pass
    return rows


@dataclass
class RunRecord:
    run_id: str
    project_id: str
    kind: str = "run"
    parent_run_id: str = ""
    requirement: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    plan_id: str = ""
    plan_version: int = 1
    plan_fingerprint: str = ""
    provider_ref: dict[str, Any] = field(default_factory=dict)      # reference only, never a secret
    generated_searches: list[dict[str, Any]] = field(default_factory=list)
    status: str = "queued"
    stage: str = "plan"
    stage_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    collected_source_ids: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    completeness: dict[str, Any] = field(default_factory=dict)
    debug: bool = False
    note: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    software_version: str = ""
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.kind not in RUN_KINDS:
            raise ValueError(f"Unknown run kind {self.kind!r}.")
        self.created_at = self.created_at or utc_now()
        self.software_version = self.software_version or sugar_core.__version__

    def to_dict(self) -> dict[str, Any]:
        return redaction.redact({f.name: getattr(self, f.name) for f in fields(self)})

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "RunRecord":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in row.items() if k in names})

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "kind": self.kind, "parent_run_id": self.parent_run_id, "status": self.status,
            "stage": self.stage, "requirement": self.requirement, "topic": self.plan.get("topic", ""),
            "counts": self.counts, "created_at": self.created_at, "started_at": self.started_at,
            "finished_at": self.finished_at, "plan_id": self.plan_id, "plan_version": self.plan_version,
            "plan_fingerprint": self.plan_fingerprint,
            "completeness": {k: v for k, v in self.completeness.items() if k in {"complete", "incomplete_sources", "summary"}},
            "error_count": len(self.errors), "warning_count": len(self.warnings), "debug": self.debug,
        }


class ResearchProject:
    """Research-facing view of a SUGAR workspace."""

    def __init__(self, workspace: SugarWorkspace) -> None:
        self.workspace = workspace
        self.root = workspace.root / "research"
        self._lock = _lock_for(self.root)

    # -- metadata -----------------------------------------------------------------------
    @property
    def project_id(self) -> str:
        return self.workspace.manifest.project_id

    @property
    def meta_path(self) -> Path:
        return self.root / "project.json"

    def meta(self) -> dict[str, Any]:
        with self._lock:
            meta = _read_json(self.meta_path, None)
            if not isinstance(meta, dict):
                meta = {
                    "schema_version": PROJECT_SCHEMA, "research_question": "", "requirement_text": "", "status": "draft",
                    "current_plan_id": "", "current_plan_version": 0, "members": [], "settings": {"enabled_sources": [], "provider_profile_id": ""},
                    "created_at": utc_now(), "updated_at": utc_now(), "last_activity": "",
                }
            return meta

    def _save_meta(self, meta: dict[str, Any], *, activity: bool = True) -> dict[str, Any]:
        meta["updated_at"] = utc_now()
        if activity:
            meta["last_activity"] = meta["updated_at"]
        with self._lock:
            _atomic_write(self.meta_path, meta)
        return meta

    def log(self, event_type: str, details: dict[str, Any] | None = None, *, actor: str = "analyst") -> dict[str, Any]:
        return log_project_event(self.workspace, event_type, details or {}, actor=actor)

    def summary(self) -> dict[str, Any]:
        """Row shown in the project list: name, question, last activity, status, last updated."""
        meta = self.meta()
        runs = self.list_runs()
        status = meta.get("status", "draft")
        if any(r["status"] in {"running", "paused", "queued", "cancelling"} for r in runs):
            status = "running"
        elif runs:
            latest = runs[0]
            status = {"completed": "completed", "completed_with_warnings": "attention", "failed": "attention",
                      "cancelled": "ready"}.get(latest["status"], status)
        elif meta.get("current_plan_id"):
            status = "ready"
        history = list_project_history(self.workspace, limit=1)
        last_activity = (history[0].get("occurred_at") if history else "") or meta.get("last_activity") or self.workspace.manifest.updated_at
        return {
            "project_id": self.project_id, "name": self.workspace.manifest.name, "description": self.workspace.manifest.description,
            "research_question": meta.get("research_question", ""), "status": status, "last_activity": last_activity,
            "updated_at": max(str(meta.get("updated_at", "")), str(self.workspace.manifest.updated_at)),
            "run_count": len(runs), "member_count": len(meta.get("members", [])),
        }

    # -- requirement and plans ----------------------------------------------------------
    def save_requirement(self, text: str, *, actor: str = "analyst") -> dict[str, Any]:
        meta = self.meta()
        changed = " ".join(text.split()) != " ".join(str(meta.get("requirement_text", "")).split())
        meta["requirement_text"] = " ".join(text.split())
        self._save_meta(meta)
        if changed:
            self.log("requirement_edited", {"requirement": meta["requirement_text"]}, actor=actor)
        return meta

    def save_plan(self, plan: ResearchPlanSpec, *, reason: str = "saved", actor: str = "analyst") -> ResearchPlanSpec:
        """Persist a plan version. The stored file is immutable; edits create a new version."""
        with self._lock:
            meta = self.meta()
            if meta.get("current_plan_id") == plan.plan_id and int(meta.get("current_plan_version", 0)) >= plan.version:
                last = self.load_plan(plan.plan_id, meta["current_plan_version"])
                if last is not None and last.fingerprint() != plan.fingerprint():
                    plan.version = int(meta["current_plan_version"]) + 1
                    plan.updated_at = utc_now()
                elif last is not None:
                    return plan
            plan.updated_at = utc_now()
            _atomic_write(self.root / "plans" / f"{plan.plan_id}.v{plan.version}.json", plan.to_dict())
            meta["current_plan_id"] = plan.plan_id
            meta["current_plan_version"] = plan.version
            meta["research_question"] = plan.research_question
            meta["status"] = "ready" if meta.get("status") in {"draft", ""} else meta.get("status")
            self._save_meta(meta)
        self.log(f"plan_{reason}", {"plan_id": plan.plan_id, "version": plan.version, "fingerprint": plan.fingerprint(),
                                     "topic": plan.topic, "queries": len(plan.queries)}, actor=actor)
        return plan

    def load_plan(self, plan_id: str = "", version: int = 0) -> ResearchPlanSpec | None:
        meta = self.meta()
        plan_id = plan_id or meta.get("current_plan_id", "")
        version = version or int(meta.get("current_plan_version", 0) or 0)
        if not plan_id or not version:
            return None
        payload = _read_json(self.root / "plans" / f"{plan_id}.v{version}.json", None)
        if not isinstance(payload, dict):
            return None
        try:
            return ResearchPlanSpec.from_dict(payload)
        except (ValueError, TypeError):
            return None

    def plan_versions(self, plan_id: str = "") -> list[dict[str, Any]]:
        plan_id = plan_id or self.meta().get("current_plan_id", "")
        rows = []
        for path in sorted((self.root / "plans").glob(f"{plan_id}.v*.json")) if plan_id else []:
            payload = _read_json(path, {})
            rows.append({"plan_id": plan_id, "version": payload.get("version"), "updated_at": payload.get("updated_at"),
                         "topic": payload.get("topic"), "queries": len(payload.get("queries", []))})
        return sorted(rows, key=lambda r: int(r.get("version") or 0))

    # -- settings, members, notes ----------------------------------------------------------
    def update_settings(self, changes: dict[str, Any], *, actor: str = "analyst") -> dict[str, Any]:
        allowed = {"enabled_sources", "provider_profile_id", "debug", "notes_visible"}
        meta = self.meta()
        settings = dict(meta.get("settings") or {})
        applied = {k: v for k, v in changes.items() if k in allowed}
        settings.update(applied)
        meta["settings"] = settings
        self._save_meta(meta)
        if applied:
            self.log("settings_changed", {"changed": sorted(applied)}, actor=actor)
        return settings

    def add_member(self, name: str, role: str = "viewer", *, actor: str = "analyst") -> list[dict[str, Any]]:
        name = " ".join(str(name).split())
        if not name:
            raise ValueError("A member needs a name.")
        if role not in ROLES:
            raise ValueError(f"Role must be one of {', '.join(ROLES)}.")
        meta = self.meta()
        members = [m for m in meta.get("members", []) if m.get("name", "").casefold() != name.casefold()]
        members.append({"name": name, "role": role, "added_at": utc_now()})
        meta["members"] = members
        self._save_meta(meta)
        self.log("member_changed", {"member": name, "role": role, "action": "added"}, actor=actor)
        return members

    def add_note(self, text: str, *, author: str = "analyst", item_id: str = "", run_id: str = "") -> dict[str, Any]:
        text = str(text or "").strip()
        if not text:
            raise ValueError("A note cannot be empty.")
        note = {"note_id": f"nt_{uuid.uuid4().hex[:10]}", "text": text[:4000], "author": author, "item_id": item_id,
                "run_id": run_id, "created_at": utc_now()}
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / "notes.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(note, ensure_ascii=False) + "\n")
        meta = self.meta()
        self._save_meta(meta)
        self.log("note_added", {"note_id": note["note_id"], "item_id": item_id}, actor=author)
        return note

    def notes(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.root / "notes.jsonl")

    def add_finding(self, run_id: str, item_id: str, paragraph_node_id: str, label: str, *, author: str = "analyst",
                    detail: str = "") -> dict[str, Any]:
        """Record a coded finding and link it to its paragraph in the evidence chain (section 27)."""
        item = next((i for i in self.load_items(run_id) if i.item_id == item_id), None)
        if item is None:
            raise KeyError(f"Item {item_id} is not in run {run_id}.")
        if not any(n["id"] == paragraph_node_id for n in item.evidence_chain):
            raise KeyError("That paragraph is not part of the item's evidence chain.")
        node = item.add_node("coded_finding", parent=paragraph_node_id, key=label, data={"label": label, "detail": detail[:2000], "author": author})
        finding = {"finding_id": node.id, "run_id": run_id, "item_id": item_id, "label": label, "detail": detail[:2000],
                   "author": author, "created_at": utc_now(), "trace": [n["type"] for n in reversed(item.trace_back(node.id))]}
        self.save_items(run_id, [i if i.item_id != item_id else item for i in self.load_items(run_id)])
        with self._lock:
            with (self.root / "findings.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(finding, ensure_ascii=False) + "\n")
        self.log("finding_coded", {"finding_id": node.id, "item_id": item_id, "label": label}, actor=author)
        return finding

    def timeline(self, limit: int = 200) -> list[dict[str, Any]]:
        return list_project_history(self.workspace, limit=limit)

    # -- runs -----------------------------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        if not run_id or any(c in run_id for c in "/\\.") or not run_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Invalid run identifier.")
        return self.root / "runs" / run_id

    def new_run(self, *, kind: str = "run", plan: ResearchPlanSpec, requirement: str = "", parent_run_id: str = "",
                provider_ref: dict[str, Any] | None = None, debug: bool = False, note: str = "") -> RunRecord:
        run = RunRecord(
            run_id=f"run_{uuid.uuid4().hex[:12]}", project_id=self.project_id, kind=kind, parent_run_id=parent_run_id,
            requirement=requirement or plan.interpretation.get("request", "") or plan.research_question,
            plan=plan.to_dict(), plan_id=plan.plan_id, plan_version=plan.version, plan_fingerprint=plan.fingerprint(),
            provider_ref=provider_ref or {}, generated_searches=[dict(q) for q in plan.queries],
            stage_states={s: {"state": "pending"} for s in ("plan", "search", "collect", "translate", "process", "results")},
            debug=debug, note=note)
        self.save_run(run)
        return run

    def save_run(self, run: RunRecord) -> None:
        with _lock_for(self.run_dir(run.run_id)):
            _atomic_write(self.run_dir(run.run_id) / "run.json", run.to_dict())

    def get_run(self, run_id: str) -> RunRecord | None:
        row = _read_json(self.run_dir(run_id) / "run.json", None)
        return RunRecord.from_dict(row) if isinstance(row, dict) else None

    def list_runs(self) -> list[dict[str, Any]]:
        rows = []
        for path in (self.root / "runs").glob("run_*/run.json") if (self.root / "runs").is_dir() else []:
            row = _read_json(path, None)
            if isinstance(row, dict):
                try:
                    rows.append(RunRecord.from_dict(row).summary())
                except (TypeError, ValueError):
                    continue
        return sorted(rows, key=lambda r: (r["created_at"], r["run_id"]), reverse=True)

    def latest_run(self, *, completed_only: bool = True) -> dict[str, Any] | None:
        for row in self.list_runs():
            if not completed_only or row["status"] in {"completed", "completed_with_warnings"}:
                return row
        return None

    def events_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "events.jsonl"

    def save_items(self, run_id: str, items: list[ResearchItem]) -> None:
        path = self.run_dir(run_id) / "items.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".items-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                for item in items:
                    stream.write(json.dumps(redaction.redact(item.to_dict()), ensure_ascii=False) + "\n")
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def load_items(self, run_id: str) -> list[ResearchItem]:
        items = []
        for row in _read_jsonl(self.run_dir(run_id) / "items.jsonl"):
            try:
                items.append(ResearchItem.from_dict(row))
            except TypeError:
                continue
        return items

    def load_translations(self, run_id: str) -> list[dict[str, Any]]:
        return _read_jsonl(self.run_dir(run_id) / "translations.jsonl")

    def append_translation(self, run_id: str, row: dict[str, Any]) -> None:
        path = self.run_dir(run_id) / "translations.jsonl"
        with _lock_for(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(redaction.redact(row), ensure_ascii=False) + "\n")

    def known_items_index(self, exclude_run: str = "") -> dict[str, dict[str, str]]:
        """item_id -> {run_id, content_hash} for accepted items in earlier runs (latest run wins).

        Used by *Refresh sources* to tell new material from known material and to spot changed content.
        """
        index: dict[str, dict[str, str]] = {}
        for row in sorted(self.list_runs(), key=lambda r: r["created_at"]):
            if row["run_id"] == exclude_run:
                continue
            for item in self.load_items(row["run_id"]):
                if item.status in {"collected", "processed"}:
                    index[item.item_id] = {"run_id": row["run_id"], "content_hash": item.content_hash}
        return index

    def iter_known_item_ids(self, exclude_run: str = "") -> Iterator[tuple[str, str]]:
        for item_id, info in self.known_items_index(exclude_run).items():
            yield item_id, info["run_id"]
