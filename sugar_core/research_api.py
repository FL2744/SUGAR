"""HTTP routes for the research workbench (framework-neutral; ``sugar_api`` adapts them).

Every handler returns ``(status, payload)`` or a :class:`Stream` for Server-Sent Events. No
response ever contains a credential: providers are returned with ``has_credential`` only.
"""
from __future__ import annotations

import json
import platform
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterator

import sugar_core

from . import redaction
from .llm_providers import PROVIDER_TYPES, ProviderProfile
from .research_runs import TERMINAL_STATUSES, ResearchProject
from .workbench import ResearchWorkbench, RunConflict, WorkbenchError


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class Stream:
    """A Server-Sent Events response. ``frames()`` yields already-encoded SSE frames."""
    frames: Callable[[], Iterator[bytes]]


def _sse(event: str, data: Any, event_id: int | None = None) -> bytes:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return (f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n").encode("utf-8")


def _int(value: Any, default: int, low: int = 0, high: int = 100000) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return str(value).casefold() in {"1", "true", "yes", "on"}


def provider_catalog() -> list[dict[str, Any]]:
    return [{"id": t.id, "label": t.label, "credential_label": t.credential_label, "needs_credential": t.needs_credential,
             "needs_endpoint": t.needs_endpoint, "default_endpoint": t.default_endpoint, "default_model": t.default_model,
             "help": t.help, "supports_organization": t.supports_organization} for t in PROVIDER_TYPES.values()]


def profile_from_payload(payload: dict[str, Any], existing: ProviderProfile | None = None) -> ProviderProfile:
    """Build a profile from a UI payload. Secrets are never read from here."""
    base = {k: v for k, v in (existing.__dict__.items() if existing else []) if k in ProviderProfile.__dataclass_fields__}
    allowed = {"id", "name", "type", "endpoint", "model", "organization", "project", "advanced"}
    for key in allowed:
        if key in payload and payload[key] is not None:
            base[key] = payload[key]
    if existing is not None:
        base["id"] = existing.id
    try:
        return ProviderProfile(**base)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, str(exc)) from exc


def diagnostics_report(wb: ResearchWorkbench, projects: list[ResearchProject] | None = None) -> str:
    """A redacted, paste-able report for bug reports: versions, providers (no secrets), recent failures."""
    lines = ["# SUGAR diagnostic report", "", f"- SUGAR {sugar_core.__version__}", f"- Python {platform.python_version()} on {platform.platform()}",
             f"- Credential storage: {wb.store.backend}", "", "## Platforms"]
    for row in wb.platform_status():
        lines.append(f"- {row['label']}: {row['state']}" + (f" (missing: {', '.join(row['missing'])})" if row["missing"] else ""))
    lines += ["", "## LLM providers"]
    profiles = wb.providers.list()
    if not profiles:
        lines.append("- none configured")
    for p in profiles:
        pub = p.public_dict(wb.store)
        lines.append(f"- {p.name} · {p.type} · model `{p.effective_model()}` · credential: {'saved' if pub['has_credential'] else 'missing'} · "
                     f"last test: {p.status.get('state')} {p.status.get('message', '')[:160]}")
    for project in projects or []:
        lines += ["", f"## Project “{project.workspace.manifest.name}”"]
        for run in project.list_runs()[:5]:
            lines.append(f"- {run['run_id']} {run['kind']} {run['status']} · errors {run['error_count']} · warnings {run['warning_count']}")
            record = project.get_run(run["run_id"])
            for err in (record.errors if record else [])[:5]:
                lines.append(f"  - {err.get('classification')} · {err.get('stage')} · {err.get('subsystem')}: {err.get('message')}")
    lines += ["", "_Secrets are redacted from this report._"]
    return redaction.redact_text("\n".join(lines))


def dispatch(method: str, path: str, query: dict[str, str], body: dict[str, Any] | None, *, wb: ResearchWorkbench,
             resolve_project: Callable[[str], ResearchProject], list_projects: Callable[[], list[ResearchProject]]) -> tuple[int, Any] | Stream | None:
    """Route a request. Returns None when the path is not a workbench route."""
    body = body or {}
    try:
        return _route(method, path, query, body, wb, resolve_project, list_projects)
    except RunConflict as exc:
        raise ApiError(409, str(exc)) from exc
    except WorkbenchError as exc:
        raise ApiError(exc.status, str(exc)) from exc
    except KeyError as exc:
        raise ApiError(404, f"Not found: {exc.args[0] if exc.args else ''}") from exc
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc


def _route(method, path, query, body, wb, resolve_project, list_projects):  # noqa: C901 - a flat route table is clearest
    if path == "/api/platforms" and method == "GET":
        return 200, {"platforms": wb.platform_status()}
    if path == "/api/platform-credentials" and method == "POST":
        wb.set_platform_secret(str(body.get("key") or ""), str(body.get("value") or ""))
        return 200, {"platforms": wb.platform_status()}
    if path == "/api/diagnostics/report" and method == "GET":
        return 200, {"report": diagnostics_report(wb, list_projects())}

    # ---- providers
    if path == "/api/providers" and method == "GET":
        return 200, {"profiles": [p.public_dict(wb.store) for p in wb.providers.list()], "default_profile_id": wb.providers.default_id(),
                     "types": provider_catalog(), "credential_storage": wb.store.backend}
    if path == "/api/providers" and method == "POST":
        payload = body.get("profile") or {}
        existing = wb.providers.get(str(payload.get("id") or "")) if payload.get("id") else None
        profile = profile_from_payload(payload, existing)
        secret = body.get("secret")
        if secret is not None and not isinstance(secret, str):
            raise ApiError(400, "The credential must be text.")
        saved = wb.providers.upsert(profile, secret=secret, make_default=bool(body.get("make_default")))
        return 200, {"profile": saved.public_dict(wb.store), "default_profile_id": wb.providers.default_id()}
    if path == "/api/providers/test" and method == "POST":
        profile = profile_from_payload(body.get("profile") or {})
        secret = body.get("secret")
        if secret in (None, "") and body.get("profile", {}).get("id"):
            saved = wb.providers.get(str(body["profile"]["id"]))
            secret = wb.providers.secret_for(saved) if saved else ""
        report = wb.test_provider(profile.id, overrides=profile, secret=str(secret or ""))
        return 200, {"report": report}
    if path == "/api/providers/default" and method == "POST":
        wb.providers.set_default(str(body.get("profile_id") or ""))
        return 200, {"default_profile_id": wb.providers.default_id()}
    match = re.fullmatch(r"/api/providers/([A-Za-z0-9_\-]+)/test", path)
    if match and method == "POST":
        return 200, {"report": wb.test_provider(match.group(1)), "profile": wb.providers.get(match.group(1)).public_dict(wb.store)}
    match = re.fullmatch(r"/api/providers/([A-Za-z0-9_\-]+)", path)
    if match and method == "DELETE":
        if not wb.providers.delete(match.group(1)):
            raise ApiError(404, "That provider profile does not exist.")
        return 200, {"deleted": match.group(1), "default_profile_id": wb.providers.default_id()}

    # ---- interpretation
    if path == "/api/interpret" and method == "POST":
        text = str(body.get("text") or "")
        project = resolve_project(str(body["workspace_id"])) if body.get("workspace_id") else None
        return 200, wb.interpret(text, mode=str(body.get("mode") or "auto"), provider_id=str(body.get("provider_id") or ""), project=project)
    if path == "/api/plan/manual" and method == "POST":
        return 200, wb.manual_plan(dict(body.get("fields") or {}))
    if path == "/api/plan/normalize" and method == "POST":
        plan, issues = wb.normalize_plan(dict(body.get("plan") or {}))
        return 200, {"plan": plan.to_dict(), "summary": plan.summary_rows(), "issues": issues}

    # ---- project-scoped
    match = re.fullmatch(r"/api/workspaces/([0-9a-fA-F-]+)/(research|runs|timeline)(?:/(.*))?", path)
    if not match:
        return None
    project = resolve_project(match.group(1))
    area, rest = match.group(2), match.group(3) or ""
    if area == "timeline" and method == "GET":
        return 200, {"events": project.timeline(_int(query.get("limit"), 100, 1, 1000))}
    if area == "research":
        return _research_routes(method, rest, query, body, wb, project)
    return _run_routes(method, rest, query, body, wb, project)


def _institution_routes(method, rest, query, body, wb, project):
    from . import institutions as inst
    actor = str(body.get("_author") or "Researcher")
    try:
        if rest == "institutions" and method == "GET":
            return 200, inst.list_institutions(project, network=query.get("network", ""), status=query.get("status", ""), country=query.get("country", ""),
                                               query=query.get("q", ""), since=query.get("since", ""), confidence_level=query.get("confidence", ""),
                                               placed=query.get("placed", ""), program=query.get("program", ""), audience=query.get("audience", ""))
        if rest == "institutions" and method == "POST":
            evidence, urls = [], []
            cache: dict[str, dict[str, object]] = {}
            for row in body.get("evidence") or []:
                if row.get("url") and not row.get("item_id"):
                    urls.append({"url": row.get("url"), "note": row.get("note") or ""})
                    continue
                run_id, item_id = str(row.get("run_id") or ""), str(row.get("item_id") or "")
                if run_id not in cache:
                    cache[run_id] = {i.item_id: i for i in wb.items(project, run_id)}
                item = cache[run_id].get(item_id)
                if item is None:
                    raise WorkbenchError(f"Item {item_id} was not found in run {run_id}.", 404)
                evidence.append((item, str(row.get("quote") or "")))
            return 200, {"institution": inst.promote(project, dict(body.get("values") or {}), evidence, actor=actor,
                                                     entity_id=str(body.get("entity_id") or ""), source_urls=urls)}
        if rest == "institutions/candidates" and method == "POST":
            run_id = str(body.get("run_id") or "")
            items = wb.items(project, run_id)
            provider, budget = None, None
            if str(body.get("mode") or "auto") != "deterministic":
                provider = wb.resolve_provider(project=project, profile_id=str(body.get("provider_id") or ""))
                budget = inst.LLMBudget(int(body.get("max_calls") or 40))
            return 200, inst.candidates(project, items, provider=provider, budget=budget)
        if rest == "institutions/geocode" and method == "POST":
            return 200, inst.geocode_missing(project, actor=actor, limit=_int(str(body.get("limit") or "25"), 25, 1, 100))
        match = re.fullmatch(r"institutions/([A-Za-z0-9\-]+)", rest)
        if match and method == "GET":
            return 200, {"institution": inst.institution_detail(project, match.group(1))}
        match = re.fullmatch(r"institutions/([A-Za-z0-9\-]+)/history", rest)
        if match and method == "POST":
            return 200, inst.page_history(project, match.group(1))
        match = re.fullmatch(r"institutions/([A-Za-z0-9\-]+)/(review|merge)", rest)
        if match and method == "POST":
            if match.group(2) == "review":
                return 200, {"institution": inst.verify(project, match.group(1), str(body.get("claim_id") or ""), str(body.get("state") or ""),
                                                        actor=actor, note=str(body.get("note") or ""))}
            return 200, {"institution": inst.merge(project, match.group(1), str(body.get("drop_id") or ""), actor=actor, reason=str(body.get("reason") or ""))}
    except KeyError as exc:
        raise WorkbenchError(str(exc.args[0]) if exc.args else "Not found.", 404) from exc
    except ValueError as exc:
        raise WorkbenchError(str(exc)) from exc
    return None


def _research_routes(method, rest, query, body, wb, project):
    if rest == "institutions" or rest.startswith("institutions/"):
        return _institution_routes(method, rest, query, body, wb, project)
    if rest == "" and method == "GET":
        return 200, wb.project_overview(project)
    if rest == "plan" and method == "POST":
        return 200, wb.save_plan(project, dict(body.get("plan") or {}), reason=str(body.get("reason") or "saved"),
                                 request=str(body.get("request") or ""), actor=str(body.get("actor") or "analyst"))
    if rest == "rebuild-plan" and method == "POST":
        return 200, wb.rebuild_plan(project)
    if rest == "reinterpret" and method == "POST":
        return 200, wb.reinterpret(project, mode=str(body.get("mode") or "auto"))
    if rest == "requirement" and method == "POST":
        return 200, {"requirement_text": project.save_requirement(str(body.get("text") or ""), actor=str(body.get("actor") or "analyst"))["requirement_text"]}
    if rest == "settings" and method == "POST":
        return 200, {"settings": project.update_settings(dict(body.get("changes") or {}), actor=str(body.get("actor") or "analyst"))}
    if rest == "notes" and method == "POST":
        return 200, {"note": project.add_note(str(body.get("text") or ""), author=str(body.get("author") or "analyst"), item_id=str(body.get("item_id") or ""),
                                              run_id=str(body.get("run_id") or ""))}
    if rest == "review" and method == "GET":
        item_id = str(query.get("item_id") or "")
        return 200, ({"item_id": item_id, "review": project.review.state(item_id)} if item_id else {"summary": project.review.summary()})
    if rest == "review" and method == "POST":
        try:
            state = project.review.apply(str(body.get("item_id") or ""), {k: v for k, v in body.items() if k != "item_id"},
                                         author=str(body.get("_author") or "Researcher"))
        except ValueError as exc:
            raise WorkbenchError(str(exc)) from exc
        return 200, {"item_id": str(body.get("item_id")), "review": state, "summary": project.review.summary()}
    if rest == "notes" and method == "GET":
        return 200, {"notes": project.notes()}
    return None


def _run_routes(method, rest, query, body, wb, project):
    if rest == "" and method == "GET":
        return 200, {"runs": wb.list_runs(project)}
    if rest == "" and method == "POST":
        return 201, wb.start_run(project, kind=str(body.get("kind") or "run"), parent_run_id=str(body.get("parent_run_id") or ""),
                                 plan_payload=body.get("plan") if isinstance(body.get("plan"), dict) else None, debug=bool(body.get("debug")),
                                 secret_overrides=body.get("secrets") if isinstance(body.get("secrets"), dict) else None)
    match = re.fullmatch(r"(run_[A-Za-z0-9]+)(?:/(.*))?", rest)
    if not match:
        return None
    run_id, sub = match.group(1), match.group(2) or ""
    if sub == "" and method == "GET":
        return 200, {"run": wb.get_run(project, run_id)}
    if sub == "events" and method == "GET":
        return 200, wb.events(project, run_id, _int(query.get("after"), 0), stage=query.get("stage", ""), source=query.get("source", ""),
                              severity=query.get("severity", ""), limit=_int(query.get("limit"), 1000, 1, 5000))
    if sub == "stream" and method == "GET":
        return _stream(wb, project, run_id, _int(query.get("after"), 0))
    if sub == "control" and method == "POST":
        params = {k: v for k, v in body.items() if k != "action"}
        return 200, wb.control(project, run_id, str(body.get("action") or ""), **params)
    if sub == "results" and method == "GET":
        return 200, wb.results(project, run_id, group_by=query.get("group_by", "none"), text=query.get("q", ""), platform=query.get("platform", ""),
                               language=query.get("language", ""), status=query.get("status", "accepted"), geography=query.get("geography", ""),
                               translated=query.get("translated", ""), verdict=query.get("verdict", ""), tag=query.get("tag", ""), new_only=_bool(query.get("new_only")), limit=_int(query.get("limit"), 200, 1, 1000),
                               offset=_int(query.get("offset"), 0))
    match = re.fullmatch(r"items/(it_[A-Za-z0-9]+)", sub)
    if match and method == "GET":
        return 200, {"item": wb.item_detail(project, run_id, match.group(1))}
    if sub == "translations" and method == "GET":
        return 200, {"translations": project.load_translations(run_id)[-_int(query.get("limit"), 200, 1, 2000):]}
    if sub == "export" and method == "POST":
        result = wb.export(project, run_id)
        return 200, {"directory": result["directory"].replace(str(project.workspace.root), "").lstrip("/\\"),
                     "archive": result["archive"].replace(str(project.workspace.root), "").lstrip("/\\"),
                     "files": result["files"], "manifest": result["manifest"]}
    if sub == "findings" and method == "POST":
        return 200, {"finding": project.add_finding(run_id, str(body.get("item_id") or ""), str(body.get("paragraph_node_id") or ""),
                                                    str(body.get("label") or ""), author=str(body.get("author") or "analyst"), detail=str(body.get("detail") or ""))}
    return None


def _stream(wb: ResearchWorkbench, project: ResearchProject, run_id: str, after: int) -> Stream:
    if project.get_run(run_id) is None:
        raise ApiError(404, "Run not found.")

    def frames() -> Iterator[bytes]:
        cursor = after
        log = wb.event_log(project, run_id)
        if log is None:                      # finished run: replay what was stored, then end
            for row in wb.events(project, run_id, cursor, limit=5000)["events"]:
                yield _sse("activity", row, row["seq"])
            yield _sse("end", {"status": wb.get_run(project, run_id)["status"]})
            return
        yield _sse("hello", {"run_id": run_id, "after": cursor})
        while True:
            fresh = log.since(cursor, limit=500)
            for event in fresh:
                cursor = event.seq
                row = event.as_dict()
                row["lag_ms"] = round(log.note_delivery(event), 1)
                yield _sse("activity", row, event.seq)
            if fresh:
                snap = wb.get_run(project, run_id)
                yield _sse("progress", {"status": snap["status"], "stage": snap["stage"], "counts": snap.get("counts", {}),
                                        "stage_states": snap.get("stage_states", {}), "sources": snap.get("sources", {}), "paused": snap.get("paused", False)})
                continue
            if log.closed and log.last_seq <= cursor:
                break
            if not log.wait_for(cursor, 15.0):
                yield b": keep-alive\n\n"
        yield _sse("end", {"status": wb.get_run(project, run_id)["status"], "terminal": wb.get_run(project, run_id)["status"] in TERMINAL_STATUSES})

    return Stream(frames)


__all__ = ["ApiError", "Stream", "dispatch", "diagnostics_report", "provider_catalog", "sys"]
