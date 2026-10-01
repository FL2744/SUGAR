"""Research workbench service: the single entry point the HTTP API and CLI call.

It owns the live pipelines (one thread per active run), resolves providers and platform
credentials from the credential store, and implements the five distinct "refresh" operations
of section 25 rather than one vague Refresh:

===================  ==============================================================
Reinterpret request  re-run natural-language interpretation on the stored request
Rebuild plan         regenerate the collection plan (queries) from the requirement
Refresh sources      search again for newer/changed material; flags new vs known
Reprocess results    repeat translation/extraction on a run's items without recollecting
Rerun                execute the previous plan again, exactly as recorded
===================  ==============================================================
"""
from __future__ import annotations

import copy
import threading
import time
from datetime import date
from typing import Any, Callable

from . import redaction
from .collector_registry import COLLECTORS, CollectorSpec
from .credential_store import CredentialStore, PLATFORM_SECRET_ENV, default_store
from .llm_providers import LLMProvider, ProviderProfile, ProviderRegistry, create_provider
from .query_planner import rebuild_plan_queries
from .request_interpreter import interpret_request, manual_plan
from .research_events import EventLog
from .research_export import export_run, read_events_file, verify_export
from .research_pipeline import ResearchPipeline
from .research_plan import DEPTH_PRESETS, ResearchPlanSpec, build_plan, utc_now
from .research_results import item_row, query_items
from .research_runs import TERMINAL_STATUSES, ResearchProject
from .workspace import SugarWorkspace

PLATFORM_LABELS = {"x": "X (Twitter)", "bluesky": "Bluesky", "mastodon": "Mastodon", "bilibili": "Bilibili", "weibo": "Weibo", "wechat": "WeChat",
                   "wikipedia": "Wikipedia", "gdelt": "News (GDELT)", "openalex": "Scholarly (OpenAlex)", "rss": "News & institution feeds", "web": "Websites"}
PLATFORM_SECRET_HELP = {
    "x": [("x_bearer_token", "X bearer token", True)],
    "bluesky": [("bluesky_identifier", "Bluesky identifier (optional)", False), ("bluesky_app_password", "Bluesky app password (optional)", False)],
    "mastodon": [("mastodon_token", "Mastodon access token", True)],
    "weibo": [("weibo_cookie", "Weibo session cookie (optional)", False)],
    "openalex": [("openalex_api_key", "OpenAlex API key (optional, raises limits)", False)],
}
PLAN_REASONS = {"interpreted", "edited", "reinterpreted", "rebuilt", "saved", "manual"}


class RunConflict(Exception):
    pass


NO_PROVIDER = "none"   # provider choice meaning "built-in only, no model calls"


class WorkbenchError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class ResearchWorkbench:
    def __init__(self, *, providers: ProviderRegistry | None = None, store: CredentialStore | None = None,
                 registry: dict[str, CollectorSpec] | None = None, sleeper: Callable[[float], None] | None = None) -> None:
        self.store = store or default_store()
        self.providers = providers or ProviderRegistry(store=self.store)
        self.registry = registry if registry is not None else COLLECTORS
        self.sleeper = sleeper
        self._live: dict[tuple[str, str], ResearchPipeline] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ platforms & providers
    def platform_secrets(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        secrets = self.store.platform_secrets()
        for key, value in (overrides or {}).items():
            if key in PLATFORM_SECRET_ENV and str(value or "").strip():
                secrets[key] = str(value).strip()
        redaction.register_secrets(secrets)
        return secrets

    def platform_status(self, overrides: dict[str, str] | None = None) -> list[dict[str, Any]]:
        secrets = self.platform_secrets(overrides)
        rows = []
        for name, spec in sorted(self.registry.items()):
            missing = [k for k in spec.required_secrets if not secrets.get(k, "").strip()]
            supported = spec.capabilities.keyword_search and spec.search is not None
            rows.append({
                "id": name, "label": PLATFORM_LABELS.get(name, name.capitalize()), "keyword_search": supported,
                "description": spec.description, "requires": list(spec.required_secrets), "missing": missing,
                "state": "unsupported" if not supported else "needs_credential" if missing else "ready",
                "secrets": [{"key": key, "label": label, "required": required, "configured": bool(secrets.get(key)),
                             "source": self.store.source_of(f"platform:{key}")} for key, label, required in PLATFORM_SECRET_HELP.get(name, [])],
            })
        return rows

    def available_platforms(self) -> list[str]:
        return [r["id"] for r in self.platform_status() if r["keyword_search"]]

    def set_platform_secret(self, key: str, value: str) -> None:
        if key not in PLATFORM_SECRET_ENV:
            raise WorkbenchError(f"Unknown platform credential {key!r}.")
        if value.strip():
            self.store.set(f"platform:{key}", value.strip())
        else:
            self.store.delete(f"platform:{key}")

    def resolve_provider(self, plan: ResearchPlanSpec | None = None, project: ResearchProject | None = None, *,
                         profile_id: str = "", observer: Callable[[dict[str, Any]], None] | None = None) -> LLMProvider | None:
        wanted = profile_id or (plan.provider.get("profile_id") if plan else "") or \
            ((project.meta().get("settings") or {}).get("provider_profile_id", "") if project else "") or self.providers.default_id()
        if wanted == NO_PROVIDER:             # an explicit "no AI" choice never falls back to a default
            return None
        profile = self.providers.get(wanted) if wanted else None
        if profile is None:
            return None
        if plan and plan.provider.get("model") and plan.provider["model"] != profile.model:
            profile = ProviderProfile(**{**profile.__dict__, "model": plan.provider["model"]})
        secret = self.providers.secret_for(profile)
        if profile.meta.needs_credential and not secret:
            return None
        return create_provider(profile, secret, observer=observer)

    def test_provider(self, profile_id: str, *, overrides: ProviderProfile | None = None, secret: str | None = None) -> dict[str, Any]:
        """Test a saved profile (or an unsaved draft with an explicit secret) and remember the outcome."""
        profile = overrides or self.providers.get(profile_id)
        if profile is None:
            raise WorkbenchError("That provider profile does not exist.", 404)
        key = secret if secret is not None else self.providers.secret_for(profile)
        report = create_provider(profile, key).test_connection()
        if overrides is None:
            self.providers.record_status(profile.id, state="ok" if report.ok else "failed",
                                         message=report.message or "Connection verified.", stage=report.error_stage)
        return report.as_dict()

    # ------------------------------------------------------------------ interpretation and plans
    def interpret(self, text: str, *, mode: str = "auto", provider_id: str = "", project: ResearchProject | None = None,
                  today: date | None = None, base_plan: ResearchPlanSpec | None = None) -> dict[str, Any]:
        no_ai = provider_id == NO_PROVIDER
        provider = None if mode == "deterministic" or no_ai else self.resolve_provider(project=project, profile_id=provider_id)
        result = interpret_request(text, provider=provider, mode=mode, today=today, available_platforms=self.available_platforms(),
                                   base_plan=base_plan)
        payload = result.as_dict()
        payload["provider_configured"] = provider is not None
        if result.plan is not None:
            if provider is not None:
                result.plan.provider["profile_id"] = provider.profile.id
            elif provider_id:
                result.plan.provider["profile_id"] = provider_id   # keep the choice so the run honours it
                if no_ai:
                    result.plan.provider["use_for_planning"] = False
            payload["plan"] = result.plan.to_dict()
        if provider_id and not no_ai and mode != "deterministic" and provider is None:
            chosen = self.providers.get(provider_id)
            label = chosen.name if chosen else "The selected provider"
            payload.setdefault("issues", []).append({
                "field": "provider", "severity": "warning", "repaired": False,
                "message": f"{label} could not be used (missing key or not found), so the built-in interpreter was used. "
                           "SUGAR does not switch to another provider on its own."})
        return payload

    def manual_plan(self, fields: dict[str, Any]) -> dict[str, Any]:
        plan, issues = manual_plan(fields, available_platforms=self.available_platforms())
        return {"plan": plan.to_dict() if plan else None, "summary": plan.summary_rows() if plan else [],
                "issues": [i.as_dict() for i in issues], "method": "manual"}

    def normalize_plan(self, payload: dict[str, Any]) -> tuple[ResearchPlanSpec, list[dict[str, Any]]]:
        plan, issues = build_plan(payload, available_platforms=set(self.available_platforms()))
        if plan is None:
            raise WorkbenchError("; ".join(i.message for i in issues if i.severity == "error") or "The plan is not valid.")
        return plan, [i.as_dict() for i in issues]

    def save_plan(self, project: ResearchProject, payload: dict[str, Any], *, reason: str = "saved", request: str = "",
                  actor: str = "analyst") -> dict[str, Any]:
        payload = self._follow_depth_change(project, payload)
        plan, issues = self.normalize_plan(payload)
        reason = reason if reason in PLAN_REASONS else "saved"
        if request:
            project.save_requirement(request, actor=actor)
        saved = project.save_plan(plan, reason=reason, actor=actor)
        return {"plan": saved.to_dict(), "summary": saved.summary_rows(), "issues": issues}

    @staticmethod
    def _follow_depth_change(project: ResearchProject, payload: dict[str, Any]) -> dict[str, Any]:
        """When only the depth changed, limits that still equal the old depth's preset follow the new preset."""
        current = project.load_plan(payload.get("plan_id", "") or "")
        depth = str(payload.get("depth", "")).casefold()
        if current is None or depth not in DEPTH_PRESETS or depth == current.depth:
            return payload
        limits = dict(payload.get("limits") or {})
        old = DEPTH_PRESETS[current.depth]
        for key, value in DEPTH_PRESETS[depth].items():
            if limits.get(key) in (None, old[key]):
                limits[key] = value
        return {**payload, "limits": limits}

    def rebuild_plan(self, project: ResearchProject) -> dict[str, Any]:
        """Regenerate the collection plan from the requirement. Returns a *proposal*; nothing is saved."""
        current = project.load_plan()
        if current is None:
            raise WorkbenchError("This project has no plan yet. Interpret a research request first.", 404)
        proposal = ResearchPlanSpec.from_dict(copy.deepcopy(current.to_dict()))
        proposal.queries = [q for q in proposal.queries if q.get("origin") == "analyst"]
        provider = self.resolve_provider(proposal, project)
        proposal, warnings = rebuild_plan_queries(proposal, provider=provider, available_platforms=self.available_platforms())
        return {"plan": proposal.to_dict(), "summary": proposal.summary_rows(), "warnings": warnings, "operation": "rebuild_plan",
                "note": "Analyst-added queries were kept; generated queries were rebuilt. Review, then save."}

    def reinterpret(self, project: ResearchProject, *, mode: str = "auto") -> dict[str, Any]:
        text = project.meta().get("requirement_text", "")
        if not text:
            raise WorkbenchError("This project has no stored research request to reinterpret.", 404)
        out = self.interpret(text, mode=mode, project=project, base_plan=project.load_plan())
        out["operation"] = "reinterpret_request"
        return out

    # ------------------------------------------------------------------ runs
    def _active(self, project: ResearchProject) -> ResearchPipeline | None:
        with self._lock:
            for (pid, _), pipeline in self._live.items():
                if pid == project.project_id and pipeline.active:
                    return pipeline
        return None

    def start_run(self, project: ResearchProject, *, kind: str = "run", parent_run_id: str = "", plan_payload: dict[str, Any] | None = None,
                  debug: bool = False, secret_overrides: dict[str, str] | None = None, wait: bool = False,
                  restrict_sources: list[str] | None = None) -> dict[str, Any]:
        if self._active(project) is not None:
            raise RunConflict("A run is already active in this project. Pause or cancel it, or wait for it to finish.")
        parent = None
        if kind in {"rerun", "reprocess", "refresh_sources"}:
            parent_row = project.get_run(parent_run_id) if parent_run_id else None
            if parent_row is None:
                latest = project.latest_run(completed_only=kind != "rerun")
                parent_row = project.get_run(latest["run_id"]) if latest else None
            if parent_row is None:
                raise WorkbenchError(f"There is no earlier run to use for “{kind.replace('_', ' ')}”. Start a normal run first.", 404)
            parent = parent_row
        if plan_payload is not None:
            plan, _ = self.normalize_plan(plan_payload)
        elif kind == "rerun" and parent is not None:
            plan = ResearchPlanSpec.from_dict(copy.deepcopy(parent.plan))
        else:
            plan = project.load_plan()
            if plan is None:
                raise WorkbenchError("This project has no research plan yet. Interpret a research request first.", 404)
        note = ""
        source_items = None
        known: dict[str, dict[str, str]] = {}
        if kind == "refresh_sources" and parent is not None:
            # Same scope, searched again; items are flagged new / known / changed against every earlier run.
            known = project.known_items_index()
            note = f"Searching again; compared with {len(known)} item(s) from earlier runs (latest: {parent.run_id})."
        if kind == "reprocess" and parent is not None:
            source_items = project.load_items(parent.run_id)
        if restrict_sources:
            plan = ResearchPlanSpec.from_dict({**plan.to_dict(), "source_scope": "selected", "platforms": restrict_sources})
        plan = project.save_plan(plan, reason="saved") if plan_payload is not None or not project.meta().get("current_plan_id") else plan
        provider = self.resolve_provider(plan, project)
        provider_ref = {"profile_id": provider.profile.id, "type": provider.profile.type, "model": provider.model,
                        "name": provider.profile.name, "credential_ref": provider.profile.credential_ref} if provider else {}
        run = project.new_run(kind=kind, plan=plan, parent_run_id=parent.run_id if parent else "", provider_ref=provider_ref,
                              debug=debug or bool((project.meta().get("settings") or {}).get("debug")), note=note)
        settings = project.meta().get("settings") or {}
        pipeline = ResearchPipeline(project, run, plan, secrets=self.platform_secrets(secret_overrides), provider=provider, registry=self.registry,
                                    enabled_sources=settings.get("enabled_sources") or None, known_items=known, source_items=source_items,
                                    extra_config={"rss_feeds": [f for f in (settings.get("rss_feeds") or []) if isinstance(f, str)],
                                                  "web_seeds": [f for f in (settings.get("web_seeds") or []) if isinstance(f, str)]},
                                    **({"sleeper": self.sleeper} if self.sleeper else {}))
        with self._lock:
            self._live[(project.project_id, run.run_id)] = pipeline
            self._trim()
        project.log("run_started", {"run_id": run.run_id, "kind": kind, "plan_id": plan.plan_id, "plan_version": plan.version,
                                    "parent_run_id": run.parent_run_id, "topic": plan.topic})
        if wait:
            pipeline.execute()
        else:
            pipeline.start()
        return {"run": pipeline.snapshot()}

    def _trim(self) -> None:
        finished = [k for k, p in self._live.items() if not p.active]
        for key in finished[:-12]:
            self._live.pop(key, None)

    def pipeline(self, project: ResearchProject, run_id: str) -> ResearchPipeline | None:
        with self._lock:
            return self._live.get((project.project_id, run_id))

    def get_run(self, project: ResearchProject, run_id: str) -> dict[str, Any]:
        live = self.pipeline(project, run_id)
        if live is not None:
            snap = live.snapshot()
            row = live.run.to_dict()
            row.update(snap)
            row["errors"] = list(live.run.errors)
            row["warnings"] = list(live.run.warnings)
            row["completeness"] = live.run.completeness
            row["live"] = True
            return row
        record = project.get_run(run_id)
        if record is None:
            raise WorkbenchError("Run not found.", 404)
        row = record.to_dict()
        row["live"] = False
        row["summary"] = record.summary()
        return row

    def list_runs(self, project: ResearchProject) -> list[dict[str, Any]]:
        rows = project.list_runs()
        for row in rows:
            live = self.pipeline(project, row["run_id"])
            if live is not None:
                snap = live.snapshot()
                row.update({k: snap[k] for k in ("status", "stage", "counts")})
        return rows

    def events(self, project: ResearchProject, run_id: str, after: int = 0, *, stage: str = "", source: str = "", severity: str = "",
               limit: int = 1000) -> dict[str, Any]:
        live = self.pipeline(project, run_id)
        if live is not None:
            if not live.active:                  # the status turns terminal a moment before the log closes; let it finish
                deadline = time.monotonic() + 2.0
                while not live.events.closed and time.monotonic() < deadline:
                    time.sleep(0.02)
            rows = [e.as_dict() for e in live.events.since(after, stage=stage, source=source, severity=severity, limit=limit)]
            return {"events": rows, "last_seq": live.events.last_seq, "finished": not live.active and live.events.closed, "live": True}
        rows = read_events_file(project.events_path(run_id), after, stage=stage, source=source, severity=severity, limit=limit)
        record = project.get_run(run_id)
        if record is None:
            raise WorkbenchError("Run not found.", 404)
        return {"events": rows, "last_seq": rows[-1]["seq"] if rows else after, "finished": record.status in TERMINAL_STATUSES, "live": False}

    def event_log(self, project: ResearchProject, run_id: str) -> EventLog | None:
        live = self.pipeline(project, run_id)
        return live.events if live else None

    def control(self, project: ResearchProject, run_id: str, action: str, **params: Any) -> dict[str, Any]:
        live = self.pipeline(project, run_id)
        if action == "retry_source" and (live is None or not live.active):
            source = str(params.get("source") or "")
            if not source:
                raise WorkbenchError("Choose which source to retry.")
            return self.start_run(project, kind="rerun", parent_run_id=run_id, restrict_sources=[source])
        if live is None or not live.active:
            raise WorkbenchError("That run is not active. Only running or paused runs can be controlled; use Rerun, Refresh sources or Reprocess instead.", 409)
        if action == "pause":
            live.pause()
        elif action == "resume":
            live.resume()
        elif action == "cancel":
            live.cancel()
        elif action == "retry_source":
            if not live.retry_source(str(params.get("source") or "")):
                raise WorkbenchError("That source cannot be retried right now (it must have failed and the run must still be active).", 409)
        elif action == "exclude_item":
            if not live.exclude_item(str(params.get("item_id") or ""), str(params.get("reason") or "Excluded by researcher")):
                raise WorkbenchError("That item is not part of this run yet.", 404)
        elif action == "disable_query":
            live.set_query_enabled(str(params.get("query_id") or ""), False)
        elif action == "enable_query":
            live.set_query_enabled(str(params.get("query_id") or ""), True)
        elif action == "add_query":
            live.add_query(str(params.get("text") or ""), platform=str(params.get("platform") or ""), language=str(params.get("language") or ""))
        else:
            raise WorkbenchError(f"Unknown control action {action!r}.")
        return {"run": live.snapshot()}

    # ------------------------------------------------------------------ results
    def items(self, project: ResearchProject, run_id: str) -> list:
        live = self.pipeline(project, run_id)
        if live is not None:
            with live._lock:
                return [copy.deepcopy(i) for i in live.items.values()]
        if project.get_run(run_id) is None:
            raise WorkbenchError("Run not found.", 404)
        return project.load_items(run_id)

    def results(self, project: ResearchProject, run_id: str, *, verdict: str = "", tag: str = "", **filters: Any) -> dict[str, Any]:
        items = all_items = self.items(project, run_id)
        review = project.review.state()
        if verdict:
            items = [i for i in items if (review.get(i.item_id, {}).get("verdict", "") or "unreviewed") == verdict]
        if tag:
            items = [i for i in items if tag.casefold() in review.get(i.item_id, {}).get("tags", [])]
        try:
            result = query_items(items, **filters)
        except ValueError as exc:
            raise WorkbenchError(str(exc)) from exc
        rows = result["items"] + [row for group in result["groups"] for row in group["items"]]
        for row in rows:
            state = review.get(row["item_id"])
            row["review"] = {"verdict": state["verdict"], "tags": state["tags"], "comments": len(state["comments"])} if state else {"verdict": "", "tags": [], "comments": 0}
        result["review"] = project.review.summary({i.item_id for i in all_items})
        return result

    def item_detail(self, project: ResearchProject, run_id: str, item_id: str) -> dict[str, Any]:
        item = next((i for i in self.items(project, run_id) if i.item_id == item_id), None)
        if item is None:
            raise WorkbenchError("Item not found.", 404)
        detail = item_row(item, detail=True)
        detail["translations"] = [t for t in project.load_translations(run_id) if t.get("item_id") == item_id]
        detail["notes"] = [n for n in project.notes() if n.get("item_id") == item_id]
        detail["review"] = project.review.state(item_id)
        return detail

    def export(self, project: ResearchProject, run_id: str) -> dict[str, Any]:
        live = self.pipeline(project, run_id)
        if live is not None and live.active:
            raise WorkbenchError("Wait for the run to finish (or cancel it) before exporting.", 409)
        try:
            return export_run(project, run_id)
        except KeyError as exc:
            raise WorkbenchError(str(exc), 404) from exc

    verify_export = staticmethod(verify_export)

    # ------------------------------------------------------------------ projects
    @staticmethod
    def open_project(path: str) -> ResearchProject:
        return ResearchProject(SugarWorkspace.open(path))

    def project_overview(self, project: ResearchProject) -> dict[str, Any]:
        meta = project.meta()
        plan = project.load_plan()
        return {"summary": project.summary(), "requirement_text": meta.get("requirement_text", ""),
                "plan": plan.to_dict() if plan else None, "plan_summary": plan.summary_rows() if plan else [],
                "plan_versions": project.plan_versions(), "settings": meta.get("settings", {}), "members": project.members(),
                "runs": self.list_runs(project), "notes": project.notes()[-50:], "generated_at": utc_now()}
