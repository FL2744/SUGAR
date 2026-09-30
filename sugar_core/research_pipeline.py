"""The research pipeline: Plan -> Search -> Collect -> Translate -> Process -> Results.

One ``ResearchPipeline`` executes one ``Run``. It reuses the registered collectors (no second
collection engine), runs independent platforms in parallel, retries transient failures with
backoff, keeps going when a single platform fails, and emits a structured activity event for
every step so a UI can show the work as it happens.

Failure classes (section 38): ``fatal`` (run cannot continue), ``source_specific`` (this platform
cannot be searched: credential rejected, access blocked), ``retryable`` (transient; retried, and
reported if retries are exhausted), ``skipped`` (never attempted: missing credential,
unsupported), and ``warning`` (work continued: e.g. a translation failed).
"""
from __future__ import annotations

import re
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any, Callable

from . import gazetteer as gz
from . import redaction
from .collector_registry import COLLECTORS, CollectorCapabilities, CollectorRequest, CollectorSpec
from .llm_providers import LLMProvider, ProviderError, call_with_retries
from .query_planner import dispatch_text
from .research_events import EventLog, STAGES
from .research_items import (
    DedupIndex, ResearchItem, detect_language, extract_paragraphs, is_language, matches_exclusion, record_to_item,
    start_chain, tag_geography,
)
from .research_plan import QuerySpec, ResearchPlanSpec, utc_now
from .research_runs import ResearchProject, RunRecord
from .utils import in_inclusive_date_range

SECRET_REMEDY = {
    "x_bearer_token": "Add an X bearer token in Settings → Platform credentials.",
    "mastodon_token": "Add a Mastodon access token in Settings → Platform credentials.",
}


class RunCancelled(Exception):
    pass


class PipelineError(Exception):
    """A fatal, run-level error with the responsible subsystem named."""

    def __init__(self, message: str, *, stage: str = "plan", subsystem: str = "pipeline") -> None:
        super().__init__(message)
        self.stage = stage
        self.subsystem = subsystem


def classify_failure(exc: BaseException, source: str) -> dict[str, Any]:
    """Classify a collector exception into a failure class with a researcher-facing message."""
    text = " ".join(str(exc).split())
    lowered = text.casefold()
    status = getattr(getattr(exc, "response", None), "status_code", None)
    retry_after = None
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        retry_after = float(headers.get("Retry-After")) if headers.get("Retry-After") else None
    except (TypeError, ValueError):
        retry_after = None
    if status is None:
        match = re.search(r"\b(?:http\s*)?\(?(4\d\d|5\d\d)\)?\b", lowered)
        status = int(match.group(1)) if match and ("http" in lowered or f"({match.group(1)})" in lowered) else None
    name = source.capitalize()
    if status == 429 or "rate limit" in lowered or "too many requests" in lowered:
        return {"classification": "retryable", "kind": "rate_limit", "status": 429, "retry_after": retry_after,
                "message": f"{name} collection was rate limited (HTTP 429)."}
    if status in (401, 403) or any(k in lowered for k in ("bearer token", "rejected the", "unauthorized", "forbidden", "captcha",
                                                          "login required", "requires a logged", "access control", "access-control",
                                                          "requires credential", "authentication required")):
        code = f" (HTTP {status})" if status else ""
        return {"classification": "source_specific", "kind": "access", "status": status,
                "message": f"{name} refused access{code}: {text[:200]}"}
    if status == 402 or "billing" in lowered or "credits" in lowered:
        return {"classification": "source_specific", "kind": "billing", "status": status,
                "message": f"{name} needs an account with search access or credits: {text[:200]}"}
    if status and status >= 500 or any(k in lowered for k in ("timed out", "timeout", "connection", "temporarily", "unavailable", "reset by peer")):
        code = f" (HTTP {status})" if status else ""
        return {"classification": "retryable", "kind": "transient", "status": status, "retry_after": retry_after,
                "message": f"{name} had a temporary problem{code}: {text[:200]}"}
    if isinstance(exc, (OSError,)) and not isinstance(exc, PermissionError):
        return {"classification": "retryable", "kind": "network", "status": status, "retry_after": retry_after,
                "message": f"{name} could not be reached: {text[:200]}"}
    return {"classification": "source_specific", "kind": "error", "status": status,
            "message": f"{name} collection failed ({type(exc).__name__}): {text[:200]}"}


class RunController:
    """Thread-safe pause / resume / cancel and live plan edits for a running pipeline."""

    def __init__(self) -> None:
        self._run = threading.Event()
        self._run.set()
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self.disabled_queries: set[str] = set()
        self.added_queries: list[QuerySpec] = []
        self.excluded_items: dict[str, str] = {}

    @property
    def paused(self) -> bool:
        return not self._run.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def pause(self) -> None:
        self._run.clear()

    def resume(self) -> None:
        self._run.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._run.set()          # release anything blocked on pause so it can observe the cancel

    def checkpoint(self) -> None:
        """Called between units of work: blocks while paused, raises once cancelled."""
        while not self._run.wait(0.2):
            if self._cancel.is_set():
                break
        if self._cancel.is_set():
            raise RunCancelled()

    def sleep(self, seconds: float, sleeper: Callable[[float], None] = time.sleep) -> None:
        """Interruptible sleep (a cancel ends the wait early)."""
        end = time.monotonic() + max(0.0, seconds)
        while time.monotonic() < end:
            self.checkpoint()
            sleeper(min(0.25, max(0.0, end - time.monotonic())))


class SourceHandle:
    def __init__(self, name: str, spec: CollectorSpec) -> None:
        self.name = name
        self.spec = spec
        self.status = "pending"        # pending | running | success | zero_result | partial | failed | skipped
        self.items = 0
        self.queries_run = 0
        self.queries_failed = 0
        self.error: dict[str, Any] = {}
        self.failed_query_ids: list[str] = []


class ResearchPipeline:
    def __init__(
        self,
        project: ResearchProject,
        run: RunRecord,
        plan: ResearchPlanSpec,
        *,
        secrets: dict[str, str] | None = None,
        provider: LLMProvider | None = None,
        registry: dict[str, CollectorSpec] | None = None,
        enabled_sources: list[str] | None = None,
        known_items: dict[str, dict[str, str]] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        source_items: list[ResearchItem] | None = None,
        extra_config: dict[str, Any] | None = None,
    ) -> None:
        self.project = project
        self.run = run
        self.plan = plan
        self.secrets = dict(secrets or {})
        redaction.register_secrets(self.secrets)
        self.provider = provider
        self.registry = registry if registry is not None else COLLECTORS
        self.enabled_sources = [s.casefold() for s in (enabled_sources or [])]
        self.known_items = dict(known_items or {})
        self.sleeper = sleeper
        self.source_items = source_items
        self.extra_config = dict(extra_config or {})
        self.controller = RunController()
        self.events = EventLog(run.run_id, project.events_path(run.run_id), capture_debug=run.debug)
        self.timings = self.events.timings
        self.dedup = DedupIndex(plan.dedup["threshold"], plan.dedup["enabled"])
        self.items: dict[str, ResearchItem] = {}
        self.queries: list[QuerySpec] = []
        self.sources: dict[str, SourceHandle] = {}
        self._lock = threading.RLock()
        self._futures: list[Future] = []
        self._translation_futures: list[Future] = []
        self._thread: threading.Thread | None = None
        self._search_pool: ThreadPoolExecutor | None = None
        self._translate_pool: ThreadPoolExecutor | None = None
        self._translation_blocked = ""
        self._translation_skipped_notice = False
        self._needs_translation = 0
        self._limit_notice = False
        self._last_save = 0.0
        self._outstanding = {s: 0 for s in STAGES}
        self.counts: dict[str, int] = {k: 0 for k in (
            "queries_total", "queries_done", "queries_failed", "sources_total", "sources_done", "sources_failed", "sources_skipped",
            "discovered", "collected", "processed", "translated", "translation_pending", "translation_failed", "rejected",
            "duplicates", "excluded", "new", "known", "changed", "warnings", "errors")}
        self._observe_provider()

    # ------------------------------------------------------------------ public control
    def start(self) -> threading.Thread:
        self._thread = threading.Thread(target=self.execute, name=f"sugar-{self.run.run_id}", daemon=True)
        self._thread.start()
        return self._thread

    def join(self, timeout: float | None = None) -> bool:
        if self._thread is not None:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True

    @property
    def active(self) -> bool:
        return self.run.status in {"queued", "running", "paused", "cancelling"}

    def pause(self) -> None:
        if self.run.status == "running":
            self.controller.pause()
            self._set_status("paused")
            self.events.emit("run.paused", stage=self.run.stage, message="Run paused. Work in flight will finish; nothing new starts.")

    def resume(self) -> None:
        if self.run.status == "paused":
            self.controller.resume()
            self._set_status("running")
            self.events.emit("run.resumed", stage=self.run.stage, message="Run resumed.")

    def cancel(self) -> None:
        if self.active:
            self._set_status("cancelling")
            self.controller.cancel()
            self.events.emit("run.cancelling", stage=self.run.stage, message="Cancelling. Results collected so far will be kept.")

    def exclude_item(self, item_id: str, reason: str = "Excluded by researcher") -> bool:
        with self._lock:
            item = self.items.get(item_id)
            self.controller.excluded_items[item_id] = reason
            if item is None or item.status == "excluded":
                return item is not None
            if item.status in {"collected", "processed"}:
                self.counts["collected"] = max(0, self.counts["collected"] - 1)
                if item.status == "processed":
                    self.counts["processed"] = max(0, self.counts["processed"] - 1)
            item.status = "excluded"
            item.rejection_reason = reason
            item.add_transformation("excluded", reason=reason)
            self.counts["excluded"] += 1
        self.events.emit("item.excluded", source=item.platform, message=f"Excluded item: {reason}", item_id=item_id, reason=reason,
                         applies_to="results (already-collected items) and remaining pipeline stages")
        return True

    def set_query_enabled(self, query_id: str, enabled: bool) -> None:
        if enabled:
            self.controller.disabled_queries.discard(query_id)
        else:
            self.controller.disabled_queries.add(query_id)
        self.events.emit("query.disabled" if not enabled else "research.plan.updated", message=(
            "Query disabled for the rest of this run; searches already finished are unchanged." if not enabled else "Query re-enabled."),
            query_id=query_id, enabled=enabled, applies_to="queries not yet dispatched")

    def add_query(self, text: str, *, platform: str = "", language: str = "") -> QuerySpec:
        spec = QuerySpec(text=text, origin="analyst", platform=platform, language=language, rationale="Added by the researcher during the run.")
        self.controller.added_queries.append(spec)
        with self._lock:
            self.counts["queries_total"] += len(self._sources_for_query(spec))
        self.run.generated_searches.append({k: getattr(spec, k) for k in spec.__dataclass_fields__})
        self.events.emit("research.plan.updated", message=f"Added query “{spec.text}”. It will be searched by platforms that have not finished.",
                         query=spec.text, query_id=spec.id, applies_to="platforms still searching; finished platforms are not re-queried")
        return spec

    def retry_source(self, source: str) -> bool:
        with self._lock:
            handle = self.sources.get(source)
            if handle is None or handle.status not in {"failed", "partial"} or not self.active or self._search_pool is None:
                return False
            handle.status = "pending"
            handle.error = {}
            retry_ids = set(handle.failed_query_ids)
            handle.failed_query_ids = []
            self.counts["sources_failed"] = max(0, self.counts["sources_failed"] - 1)
            self.counts["sources_done"] = max(0, self.counts["sources_done"] - 1)
            handle.queries_failed = 0
            self.run.errors = [e for e in self.run.errors if not (e.get("source") == source and e.get("classification") in {"retryable", "source_specific"})]
        self.events.emit("source.retry.scheduled", source=source, message=f"Retrying {source.capitalize()} at the researcher's request.", manual=True)
        self._submit_source(handle, only_query_ids=retry_ids or None)
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self.run.counts = dict(self.counts)
            self.run.counts["queries_done"] = self.counts["queries_done"]
            summary = self.run.summary()
            summary["sources"] = {n: self._source_row(h) for n, h in self.sources.items()}
            summary["stage_states"] = self.run.stage_states
            summary["paused"] = self.controller.paused
            summary["last_seq"] = self.events.last_seq
            summary["timings"] = self.timings.snapshot()
            return summary

    # ------------------------------------------------------------------ internals
    def _observe_provider(self) -> None:
        if self.provider is None:
            return

        def observer(record: dict[str, Any]) -> None:
            self.timings.record("llm_call", float(record.get("ms", 0)) / 1000)
            self.events.emit("provider.call", debug=True, message=f"{record.get('purpose')} via {record.get('provider')}", **{k: v for k, v in record.items() if k != "kind"})

        self.provider.observer = observer
        self.provider.capture_content = bool(self.run.debug)

    def _set_status(self, status: str) -> None:
        self.run.status = status

    def _stage(self, stage: str, state: str, **extra: Any) -> None:
        with self._lock:
            row = self.run.stage_states.setdefault(stage, {"state": "pending"})
            if state == "running" and row.get("state") in {"running", "done"}:
                return
            if state == "done" and row.get("state") == "done":
                return
            row["state"] = state
            row[{"running": "started_at", "done": "finished_at", "failed": "finished_at", "skipped": "finished_at"}.get(state, "updated_at")] = utc_now()
            row.update(extra)
            if state == "running":
                self.run.stage = stage
        self.events.emit(f"stage.{'started' if state == 'running' else 'completed' if state == 'done' else state}", stage=stage,
                         message=f"{stage.capitalize()} {state}", state=state, **extra)
        self._save(force=True)

    def _save(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_save < 1.0:
            return
        self._last_save = now
        with self._lock:
            self.run.counts = dict(self.counts)
            self.run.sources = {n: self._source_row(h) for n, h in self.sources.items()}
            self.run.collected_source_ids = [i.item_id for i in self.items.values() if i.status in {"collected", "processed"}]
            try:
                with self.timings.measure("serialization"):
                    self.project.save_run(self.run)
            except OSError:
                pass

    @staticmethod
    def _source_row(handle: SourceHandle) -> dict[str, Any]:
        return {"status": handle.status, "items": handle.items, "queries_run": handle.queries_run,
                "queries_failed": handle.queries_failed, "error": handle.error}

    def _record_error(self, *, stage: str, subsystem: str, classification: str, message: str, source: str = "", exc: BaseException | None = None, **extra: Any) -> dict[str, Any]:
        row = {"at": utc_now(), "stage": stage, "subsystem": subsystem, "source": source, "classification": classification,
               "message": redaction.redact_text(message), **extra}
        if exc is not None and self.run.debug:
            row["traceback"] = redaction.redact_text("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-3000:])
        with self._lock:
            if classification == "warning":
                self.counts["warnings"] += 1
                self.run.warnings.append(row["message"])
            else:
                self.counts["errors"] += 1
                self.run.errors.append(row)
        return row

    # ------------------------------------------------------------------ main flow
    def execute(self) -> RunRecord:
        started = time.monotonic()
        self.run.started_at = utc_now()
        self._set_status("running")
        self.events.emit("run.started", stage="plan", message=f"{self.run.kind.replace('_', ' ').capitalize()} started.",
                         kind=self.run.kind, plan_id=self.plan.plan_id, plan_version=self.plan.version)
        self._save(force=True)
        fatal: PipelineError | None = None
        try:
            if self.run.kind == "reprocess":
                self._execute_reprocess()
            else:
                self._execute_collection()
        except RunCancelled:
            pass
        except PipelineError as exc:
            fatal = exc
            self._record_error(stage=exc.stage, subsystem=exc.subsystem, classification="fatal", message=str(exc), exc=exc)
            self.events.emit("run.failed", stage=exc.stage, severity="error", message=str(exc), subsystem=exc.subsystem, classification="fatal")
        except Exception as exc:                      # unexpected: still fatal, but never silent
            fatal = PipelineError(f"Unexpected error in the research pipeline ({type(exc).__name__}): {exc}", subsystem="pipeline")
            self._record_error(stage=self.run.stage, subsystem="pipeline", classification="fatal", message=str(fatal), exc=exc)
            self.events.emit("run.failed", stage=self.run.stage, severity="error", message=str(fatal), subsystem="pipeline", classification="fatal",
                             **({"traceback": traceback.format_exc()[-3000:]} if self.run.debug else {}))
        finally:
            self._shutdown_pools()
            self._finalize(fatal, started)
        return self.run

    def _shutdown_pools(self) -> None:
        for pool in (self._search_pool, self._translate_pool):
            if pool is not None:
                pool.shutdown(wait=True, cancel_futures=False)

    def _execute_collection(self) -> None:
        plan = self.plan
        # ---- plan stage
        self._stage("plan", "running")
        with self.timings.measure("parsing"):
            queries = plan.enabled_queries()
        if not queries and not plan.topic:
            raise PipelineError("The plan has no topic or enabled queries, so there is nothing to search.")
        if not queries:
            queries = [QuerySpec(text=plan.topic, origin="request", rationale="Plan had no queries; searching the topic itself.")]
        self.events.emit("research.plan.created", stage="plan", message=f"Plan ready: {plan.topic}", plan=plan.to_dict(),
                         summary=plan.summary_rows(), fingerprint=plan.fingerprint())
        for q in queries:
            self.events.emit("query.generated", stage="plan", message=q.text, query_id=q.id, query=q.text, platform=q.platform,
                             language=q.language, origin=q.origin, rationale=q.rationale, geography=q.geography)
        handles = self._resolve_sources()
        self.queries = queries
        with self._lock:
            self.counts["sources_total"] = len(handles)
            self.counts["queries_total"] = sum(len(self._sources_for_query(q, handles)) for q in queries)
        self._stage("plan", "done", queries=len(queries), sources=[h.name for h in handles])

        # ---- search + collect (+ translate/process as items arrive)
        self._stage("search", "running")
        self._search_pool = ThreadPoolExecutor(max_workers=max(1, min(plan.concurrency["max_workers"], len(handles))), thread_name_prefix="sugar-search")
        self._translate_pool = ThreadPoolExecutor(max_workers=plan.translation["workers"], thread_name_prefix="sugar-translate")
        for handle in handles:
            self._submit_source(handle)
        self._wait_for(self._futures)
        self.controller.checkpoint()
        self._stage("search", "done", queries_done=self.counts["queries_done"], failed=self.counts["queries_failed"])
        self._stage("collect", "done", items=self.counts["collected"], duplicates=self.counts["duplicates"], rejected=self.counts["rejected"])
        self._finish_translation()
        self._stage("process", "running")
        self._process_results()
        self._stage("process", "done", processed=self.counts["processed"])

    def _wait_for(self, futures: list[Future]) -> None:
        """Wait until every submitted future is done, including ones added while waiting (e.g. manual retries)."""
        while True:
            with self._lock:
                pending = [f for f in futures if not f.done()]
            if not pending:
                return
            wait(pending, timeout=0.5)

    # ---- source resolution
    def _resolve_sources(self) -> list[SourceHandle]:
        plan = self.plan
        if plan.source_scope == "selected":
            names = list(plan.platforms)
        else:
            names = sorted(name for name, spec in self.registry.items() if spec.capabilities.keyword_search)
            if self.enabled_sources:
                names = [n for n in names if n in self.enabled_sources]
        names = [n for n in names if n not in plan.exclude_platforms]
        if plan.source_categories:
            names = [n for n in names if _category(n) in plan.source_categories]
        handles: list[SourceHandle] = []
        for name in names:
            spec = self.registry.get(name)
            if spec is None:
                self._skip_source(name, "SUGAR has no collector for this platform.", kind="unsupported")
                continue
            if not spec.capabilities.keyword_search or spec.search is None:
                self._skip_source(name, f"{name.capitalize()} does not support keyword search in SUGAR.", kind="unsupported")
                continue
            missing = [k for k in spec.required_secrets if not self.secrets.get(k, "").strip()]
            if missing:
                remedy = " ".join(SECRET_REMEDY.get(k, f"Add {k.replace('_', ' ')} in Settings → Platform credentials.") for k in missing)
                self._skip_source(name, f"{name.capitalize()} needs a credential that is not configured. {remedy}", kind="missing_credential")
                continue
            handle = SourceHandle(name, spec)
            self.sources[name] = handle
            handles.append(handle)
        if not handles:
            reasons = "; ".join(f"{n}: {s['error'].get('message', s['status'])}" for n, s in ((k, self._source_row(v)) for k, v in self.sources.items()))
            raise PipelineError("No platform can be searched right now. " + (reasons or "No enabled platform supports keyword search.")
                                + " Configure a credential or choose another platform, then rerun.", stage="plan", subsystem="source-resolution")
        return handles

    def _skip_source(self, name: str, message: str, *, kind: str) -> None:
        handle = self.sources.setdefault(name, SourceHandle(name, CollectorSpec(name=name, capabilities=CollectorCapabilities())))
        handle.status = "skipped"
        handle.error = {"classification": "skipped", "kind": kind, "message": message}
        with self._lock:
            self.counts["sources_skipped"] += 1
            self.counts["warnings"] += 1
            self.run.warnings.append(message)
        self.events.emit("source.skipped", source=name, stage="plan", message=message, classification="skipped", kind=kind)

    def _sources_for_query(self, q: QuerySpec, handles: list[SourceHandle] | None = None) -> list[SourceHandle]:
        pool = handles if handles is not None else [h for h in self.sources.values() if h.status != "skipped"]
        return [h for h in pool if not q.platform or q.platform == h.name]

    def _pending_queries(self) -> list[QuerySpec]:
        return list(self.queries) + list(self.controller.added_queries)

    def _submit_source(self, handle: SourceHandle, only_query_ids: set[str] | None = None) -> None:
        assert self._search_pool is not None
        future = self._search_pool.submit(self._search_source, handle, only_query_ids)
        with self._lock:
            self._futures.append(future)

    # ---- search
    def _search_source(self, handle: SourceHandle, only_query_ids: set[str] | None = None) -> None:
        plan = self.plan
        handle.status = "running"
        done_ids: set[str] = set()
        consecutive_failures = 0
        try:
            while True:
                self.controller.checkpoint()
                batch = [q for q in self._pending_queries() if (not q.platform or q.platform == handle.name)
                         and q.id not in done_ids and (only_query_ids is None or q.id in only_query_ids)]
                if not batch:
                    break
                query = batch[0]
                done_ids.add(query.id)
                if query.id in self.controller.disabled_queries:
                    self.events.emit("query.disabled", source=handle.name, message=f"Skipped disabled query “{query.text}”.", query_id=query.id, skipped=True)
                    with self._lock:
                        self.counts["queries_done"] += 1
                    continue
                ok = self._run_query(handle, query)
                if ok:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    handle.failed_query_ids.append(query.id)
                    if handle.error.get("classification") in {"source_specific", "fatal"} or consecutive_failures >= 2:
                        remaining = [q for q in self._pending_queries() if (not q.platform or q.platform == handle.name) and q.id not in done_ids]
                        with self._lock:
                            self.counts["queries_done"] += len(remaining)
                            self.counts["queries_failed"] += len(remaining)
                        handle.failed_query_ids.extend(q.id for q in remaining)
                        break
                if plan.concurrency["per_source_delay_seconds"] > 0:
                    self.controller.sleep(plan.concurrency["per_source_delay_seconds"], self.sleeper)
        except RunCancelled:
            handle.status = "cancelled"
            return
        finally:
            self._close_source(handle)

    def _close_source(self, handle: SourceHandle) -> None:
        if handle.status == "running":
            if handle.queries_failed and handle.queries_run > handle.queries_failed:
                handle.status = "partial"
            elif handle.queries_failed:
                handle.status = "failed"
            else:
                handle.status = "success" if handle.items else "zero_result"
        elif handle.status == "pending":
            handle.status = "success"
        with self._lock:
            self.counts["sources_done"] += 1
            if handle.status in {"failed", "partial"}:
                self.counts["sources_failed"] += 1
        self._save(force=True)

    def _run_query(self, handle: SourceHandle, query: QuerySpec) -> bool:
        plan = self.plan
        dispatched = dispatch_text(query, handle.name, plan.exclusions)
        limits = plan.limits
        per_source = limits["per_source"].get(handle.name, {})
        request = CollectorRequest(
            search_terms=[dispatched], since=plan.timeframe["start"] or None, until=plan.timeframe["end"] or None,
            max_posts_per_query=per_source.get("max_posts_per_query", limits["max_posts_per_query"]),
            max_pages_per_query=per_source.get("max_pages_per_query", limits["max_pages_per_query"]),
            config={"include_retweets": False, "post_languages": [c for c in plan.languages if c != "auto"][:5], **self.extra_config},
            secrets=self.secrets)
        max_attempts = plan.retry["max_attempts"]
        for attempt in range(1, max_attempts + 1):
            self.controller.checkpoint()
            self.events.emit("source.search.started", source=handle.name, message=f"Searching {handle.name.capitalize()} for “{dispatched}”",
                             query_id=query.id, query=query.text, dispatched=dispatched, attempt=attempt)
            self.events.emit("collector.request", debug=True, source=handle.name, stage="search", message="collector request",
                             search_terms=request.search_terms, since=request.since, until=request.until,
                             max_posts=request.max_posts_per_query, max_pages=request.max_pages_per_query)
            started = time.perf_counter()
            try:
                records = handle.spec.search(request)  # type: ignore[misc]
            except RunCancelled:
                raise
            except Exception as exc:
                elapsed = time.perf_counter() - started
                self.timings.record("search", elapsed, source=handle.name)
                partial_records = list(getattr(exc, "partial_records", ()) or ())
                info = classify_failure(exc, handle.name)
                if partial_records:
                    self._ingest(handle, query, dispatched, partial_records, elapsed)
                if info["classification"] == "retryable" and attempt < max_attempts:
                    delay = info.get("retry_after") or plan.retry["base_backoff_seconds"] * (2 ** (attempt - 1))
                    delay = min(float(delay), 300.0)
                    if info["kind"] == "rate_limit":
                        self.events.emit("provider.rate_limited", source=handle.name, message=f"{info['message']} SUGAR will retry in {delay:.0f} seconds.",
                                         status=429, retry_in_seconds=delay, attempt=attempt, query_id=query.id)
                    self.events.emit("source.retry.scheduled", source=handle.name,
                                     message=f"{info['message']} Retrying in {delay:.0f} seconds (attempt {attempt + 1} of {max_attempts}).",
                                     retry_in_seconds=delay, attempt=attempt + 1, max_attempts=max_attempts, query_id=query.id, classification="retryable")
                    self.controller.sleep(delay, self.sleeper)
                    continue
                with self._lock:
                    handle.queries_failed += 1
                    handle.queries_run += 1
                    self.counts["queries_done"] += 1
                    self.counts["queries_failed"] += 1
                handle.error = {"classification": info["classification"], "kind": info["kind"], "message": info["message"], "status": info.get("status"),
                                "retries_exhausted": info["classification"] == "retryable"}
                remedy = self._remedy(handle.name, info)
                self._record_error(stage="search", subsystem=f"{handle.name}-collector", classification=info["classification"],
                                   message=info["message"] + (f" {remedy}" if remedy else ""), source=handle.name, exc=exc, query_id=query.id,
                                   status=info.get("status"))
                self.events.emit("source.failed", source=handle.name, severity="error", classification=info["classification"], kind=info["kind"],
                                 message=info["message"] + (f" {remedy}" if remedy else "") + (" Other platforms continue." if len(self.sources) > 1 else ""),
                                 query_id=query.id, status=info.get("status"), retries_exhausted=info["classification"] == "retryable",
                                 **({"traceback": traceback.format_exc()[-3000:]} if self.run.debug else {}))
                return False
            elapsed = time.perf_counter() - started
            self.timings.record("search", elapsed, source=handle.name)
            with self._lock:
                handle.queries_run += 1
                self.counts["queries_done"] += 1
            self.events.emit("source.search.completed", source=handle.name, message=f"{handle.name.capitalize()}: {len(records)} result(s) for “{query.text}”",
                             query_id=query.id, query=query.text, count=len(records), ms=round(elapsed * 1000, 1))
            self._ingest(handle, query, dispatched, records, elapsed)
            return True
        return False

    @staticmethod
    def _remedy(source: str, info: dict[str, Any]) -> str:
        if info["kind"] == "access":
            return f"Check the {source.capitalize()} credential in Settings → Platform credentials."
        if info["kind"] == "billing":
            return "Check the account's plan or credits."
        return ""

    # ---- ingest one batch of records
    def _ingest(self, handle: SourceHandle, query: QuerySpec, dispatched: str, records: list[Any], elapsed: float) -> None:
        plan = self.plan
        per_record_ms = round(elapsed * 1000 / max(1, len(records)), 1)
        for record in records:
            self.controller.checkpoint()
            with self.timings.measure("parsing", source=handle.name):
                item, platform_language = record_to_item(record, run_id=self.run.run_id, project_id=self.run.project_id,
                                                         query_id=query.id, query_text=query.text, dispatched=dispatched)
            item.platform = item.platform or handle.name
            with self._lock:
                self.counts["discovered"] += 1
                existing = self.items.get(item.item_id)
                if existing is not None:
                    if query.text not in existing.queries:
                        existing.queries.append(query.text)
                    self.counts["duplicates"] += 1
                    same = True
                else:
                    self.items[item.item_id] = item
                    same = False
            self.events.emit("item.discovered", source=item.platform, message=(item.original_text or item.url)[:140], item_id=item.item_id,
                             url=item.url, query=query.text, query_id=query.id, author=item.author)
            if same:
                self.events.emit("duplicate.detected", source=item.platform, message="Already found by another query; merged.",
                                 item_id=item.item_id, duplicate_of=item.item_id, similarity=1.0, kind="same_item", query=query.text)
                continue
            if item.item_id in self.controller.excluded_items:
                self._reject(item, "excluded", self.controller.excluded_items[item.item_id])
                continue
            known = self.known_items.get(item.item_id)
            if known:
                item.known_from_run = known["run_id"]
                if known.get("content_hash") and known["content_hash"] != item.content_hash:
                    item.changed_since_known = True
                    item.add_transformation("changed_since_known", previous_run=known["run_id"])
                    self.events.emit("item.changed", source=item.platform, item_id=item.item_id, url=item.url,
                                     message="Content differs from the version collected earlier.", previous_run=known["run_id"])
            # -- filters
            since, until = plan.timeframe["start"] or None, plan.timeframe["end"] or None
            if item.published_at and not in_inclusive_date_range(item.published_at, since, until):
                self._reject(item, "rejected", f"Published {item.published_at[:10]}, outside the requested date range.")
                continue
            if len(item.original_text.strip()) < max(1, plan.extraction["min_chars"]):
                self._reject(item, "rejected", "The item has no text content to collect.")
                continue
            hit = matches_exclusion(item.original_text, plan.exclusions)
            if hit:
                self._reject(item, "rejected", f"Matches the exclusion “{hit}”.")
                continue
            with self._lock:
                accepted = self.counts["collected"]
                per_source_cap = plan.limits["per_source"].get(handle.name, {}).get("max_items")
                over_total = accepted >= plan.limits["max_items_total"]
                over_source = bool(per_source_cap) and handle.items >= per_source_cap
            if over_total or over_source:
                self._reject(item, "rejected", "The item limit for this run was reached." if over_total else f"The {handle.name} item limit was reached.")
                if not self._limit_notice:
                    self._limit_notice = True
                    self._record_error(stage="collect", subsystem="limits", classification="warning",
                                       message="An item limit was reached, so some results were not kept. Raise the limit in Advanced settings to collect more.")
                continue
            with self.timings.measure("deduplication"):
                duplicate = self.dedup.check(item.item_id, item.original_text)
            if duplicate:
                item.status = "duplicate"
                item.duplicate_of, item.similarity = duplicate[0], round(duplicate[1], 3)
                item.add_transformation("duplicate", duplicate_of=duplicate[0], similarity=item.similarity)
                with self._lock:
                    self.counts["duplicates"] += 1
                self.events.emit("duplicate.detected", source=item.platform, message=f"Near-duplicate of an earlier item ({item.similarity:.0%} similar).",
                                 item_id=item.item_id, duplicate_of=duplicate[0], similarity=item.similarity, kind="near_duplicate")
                continue
            # -- accepted
            self._stage("collect", "running")
            self.events.emit("item.download.started", source=item.platform, item_id=item.item_id, url=item.url, mode="batched_with_search")
            item.add_transformation("stored", chars=len(item.original_text))
            self.events.emit("item.download.completed", source=item.platform, item_id=item.item_id, url=item.url, bytes=len(item.original_text.encode("utf-8")),
                             ms=per_record_ms, mode="batched_with_search", message=f"Collected {item.url or item.item_id}")
            self.timings.record("download", per_record_ms / 1000, source=handle.name)
            self._process_item(item, platform_language)
            with self._lock:
                handle.items += 1
                item.status = "collected"
                self.counts["collected"] += 1
                if item.known_from_run:
                    self.counts["known"] += 1
                    self.counts["changed"] += 1 if item.changed_since_known else 0
                else:
                    self.counts["new"] += 1
            self._enqueue_translation(item)
            self._save()

    def _reject(self, item: ResearchItem, status: str, reason: str) -> None:
        item.status = status
        item.rejection_reason = reason
        item.add_transformation("rejected", reason=reason)
        with self._lock:
            self.counts["rejected" if status == "rejected" else "excluded"] += 1
        self.events.emit("parser.decision", debug=True, source=item.platform, message=reason, item_id=item.item_id, decision=status)
        self.events.emit("item.rejected" if status == "rejected" else "item.excluded", source=item.platform, message=reason,
                         item_id=item.item_id, reason=reason, url=item.url)

    def _process_item(self, item: ResearchItem, platform_language: str) -> None:
        with self.timings.measure("parsing", source=item.platform):
            code, method, confidence = detect_language(item.original_text, platform_language)
        item.language, item.language_method = code, method
        item.add_transformation("detect_language", language=code, method=method, confidence=confidence)
        self.events.emit("language.detected", source=item.platform, item_id=item.item_id, language=code, method=method, confidence=confidence,
                         message=f"{gz.LANGUAGE_NAMES.get(code, code)} ({method})")
        self.events.emit("extraction.started", source=item.platform, item_id=item.item_id)
        with self.timings.measure("extraction", source=item.platform):
            start_chain(item, query_id=item.query_id, query_text=item.query, dispatched=item.query_dispatched)
            count = extract_paragraphs(item, split=self.plan.extraction["paragraph_split"])
        query_geo = next((q.geography for q in self._pending_queries() if q.id == item.query_id), "")
        tag_geography(item, self.plan.geography, query_geography=query_geo)
        self.events.emit("extraction.completed", source=item.platform, item_id=item.item_id, paragraphs=count, geography=[g["name"] for g in item.geography],
                         message=f"{count} paragraph(s) extracted")

    # ---- translation
    def _translation_needed(self, item: ResearchItem) -> bool:
        policy = self.plan.translation["policy"]
        if policy == "never" or item.language in {"", "und"}:
            return False
        return not is_language(item.language, self.plan.translation["target_language"])

    def _enqueue_translation(self, item: ResearchItem) -> None:
        if not self._translation_needed(item):
            item.add_transformation("translation_not_needed", language=item.language)
            return
        with self._lock:
            self._needs_translation += 1
        if self.provider is None:
            if not self._translation_skipped_notice:
                self._translation_skipped_notice = True
                self.events.emit("translation.skipped", stage="translate", severity="warning",
                                 message="Some items need translation but no LLM provider is configured. Add one in Settings → LLM Providers, then choose Reprocess results.",
                                 reason="no_provider")
            item.translation = {"status": "skipped", "reason": "no_provider"}
            return
        assert self._translate_pool is not None
        with self._lock:
            self.counts["translation_pending"] += 1
        self._stage("translate", "running")
        future = self._translate_pool.submit(self._translate_item, item)
        with self._lock:
            self._translation_futures.append(future)

    def _translate_item(self, item: ResearchItem) -> None:
        try:
            self.controller.checkpoint()
        except RunCancelled:
            item.translation = {"status": "cancelled"}
            self._translation_done()
            return
        provider = self.provider
        assert provider is not None
        target = self.plan.translation["target_language"]
        with self._lock:
            blocked = self._translation_blocked
            excluded = item.status == "excluded"
        if excluded:
            self._translation_done()
            return
        if blocked:
            item.translation = {"status": "skipped", "reason": blocked}
            self.events.emit("translation.skipped", source=item.platform, item_id=item.item_id, severity="warning", message=blocked)
            self._translation_done()
            return
        source_name = gz.LANGUAGE_NAMES.get(item.language, item.language)
        self.events.emit("translation.started", source=item.platform, item_id=item.item_id, source_language=item.language,
                         target_language=target, chars=len(item.original_text), message=f"Translating from {source_name}")
        started = time.perf_counter()
        pieces: list[str] = []
        try:
            for paragraph in item.paragraphs[:6] or [{"index": 0, "node_id": "", "text": item.original_text[: self.plan.translation["max_chars_per_item"]]}]:
                self.controller.checkpoint()
                text = paragraph["text"][: self.plan.translation["max_chars_per_item"]]
                t0 = time.perf_counter()

                def on_retry(exc: ProviderError, attempt: int, delay: float) -> None:
                    self.events.emit("provider.rate_limited", source=f"llm:{provider.profile.type}", severity="warning", status=exc.status,
                                     message=f"{provider.label} is limiting requests. SUGAR will retry in {delay:.0f} seconds.", retry_in_seconds=delay, attempt=attempt)

                result = call_with_retries(lambda t=text: provider.translate(t, target, source_language=source_name),
                                           attempts=self.plan.retry["max_attempts"], base_delay=min(2.0, self.plan.retry["base_backoff_seconds"] or 2.0),
                                           sleep=lambda s: self.controller.sleep(s, self.sleeper), on_retry=on_retry)
                self.timings.record("translation", time.perf_counter() - t0, source=item.platform)
                translated = result.text.strip()
                pieces.append(translated)
                node = item.add_node("translated_paragraph", parent=paragraph.get("node_id", ""), key=f"{target}|{paragraph['index']}",
                                     data={"provider": provider.profile.type, "model": result.model or provider.model, "target_language": target,
                                           "run_id": self.run.run_id})
                self.project.append_translation(self.run.run_id, {
                    "translation_id": node.id, "run_id": self.run.run_id, "item_id": item.item_id, "paragraph_index": paragraph["index"],
                    "parent_node_id": paragraph.get("node_id", ""), "source_language": item.language, "target_language": target,
                    "original": paragraph["text"], "translated": translated, "provider": provider.profile.type,
                    "model": result.model or provider.model, "at": utc_now(), "ms": result.latency_ms, "url": item.url, "platform": item.platform})
            item.translation = {"status": "done", "text": "\n\n".join(pieces), "provider": provider.profile.type, "model": provider.model,
                                "target_language": target, "source_language": item.language, "at": utc_now()}
            item.add_transformation("translate", provider=provider.profile.type, model=provider.model, target_language=target)
            with self._lock:
                self.counts["translated"] += 1
            self.events.emit("translation.completed", source=item.platform, item_id=item.item_id, source_language=item.language, target_language=target,
                             original=item.original_text[:1200], translation=item.translation["text"][:1200], provider=provider.profile.type,
                             model=provider.model, ms=round((time.perf_counter() - started) * 1000, 1), url=item.url, message="Translated")
        except RunCancelled:
            item.translation = {"status": "cancelled"}
        except ProviderError as exc:
            item.translation = {"status": "failed", "error": str(exc)}
            with self._lock:
                self.counts["translation_failed"] += 1
                if exc.stage in {"credential", "model", "config"}:
                    self._translation_blocked = f"Translation stopped: {exc}"
            self._record_error(stage="translate", subsystem=f"llm-{provider.profile.type}", classification="warning",
                               message=f"Translation failed: {exc}", exc=exc, item_id=item.item_id)
            self.events.emit("translation.failed", source=item.platform, item_id=item.item_id, severity="warning", message=f"Translation failed: {exc}",
                             stage_of_failure=exc.stage, subsystem=f"llm-{provider.profile.type}")
        finally:
            self._translation_done()

    def _translation_done(self) -> None:
        with self._lock:
            self.counts["translation_pending"] = max(0, self.counts["translation_pending"] - 1)

    def _finish_translation(self) -> None:
        self._wait_for(self._translation_futures)
        if self._needs_translation or self.run.stage_states.get("translate", {}).get("state") == "running":
            if self.provider is None and self._needs_translation:
                self._stage("translate", "skipped", reason="no_provider", items=self._needs_translation)
            else:
                self._stage("translate", "done", translated=self.counts["translated"], failed=self.counts["translation_failed"])
        else:
            self._stage("translate", "skipped", reason="not_needed")

    # ---- process + finalize
    def _process_results(self) -> None:
        with self._lock:
            for item in self.items.values():
                if item.status == "collected":
                    item.status = "processed"
                    self.counts["processed"] += 1
        with self.timings.measure("serialization"):
            self.project.save_items(self.run.run_id, list(self.items.values()))

    def _execute_reprocess(self) -> None:
        """Repeat language detection, extraction and translation on a previous run's items without recollecting."""
        source = self.source_items or []
        if not source:
            raise PipelineError("The run being reprocessed has no collected items.", stage="plan", subsystem="reprocess")
        self._stage("plan", "running")
        self.events.emit("research.plan.created", stage="plan", message=f"Reprocessing {len(source)} items from {self.run.parent_run_id}",
                         plan=self.plan.to_dict(), summary=self.plan.summary_rows(), fingerprint=self.plan.fingerprint(), reprocess_of=self.run.parent_run_id)
        self._stage("plan", "done")
        self._stage("search", "skipped", reason="reprocess")
        self._translate_pool = ThreadPoolExecutor(max_workers=self.plan.translation["workers"], thread_name_prefix="sugar-translate")
        self._stage("collect", "running")
        for parent in source:
            self.controller.checkpoint()
            if parent.status not in {"collected", "processed"}:
                continue
            item = ResearchItem.from_dict(parent.to_dict())
            item.run_id = self.run.run_id
            item.derived_from = {"run_id": parent.run_id, "item_id": parent.item_id}
            item.translation, item.paragraphs, item.evidence_chain = {}, [], []
            item.add_transformation("reprocessed", from_run=parent.run_id)
            with self._lock:
                self.items[item.item_id] = item
                self.counts["discovered"] += 1
                self.counts["collected"] += 1
            self.dedup.check(item.item_id, item.original_text)
            self.events.emit("item.discovered", source=item.platform, item_id=item.item_id, url=item.url, message=item.original_text[:140], reprocess=True)
            self._process_item(item, "")
            self._enqueue_translation(item)
        self._stage("collect", "done", items=self.counts["collected"])
        self._finish_translation()
        self._stage("process", "running")
        self._process_results()
        self._stage("process", "done", processed=self.counts["processed"])

    def _completeness(self) -> dict[str, Any]:
        rows = {n: self._source_row(h) for n, h in self.sources.items()}
        incomplete = sorted(n for n, r in rows.items() if r["status"] in {"failed", "partial", "skipped", "cancelled"})
        total = len([r for r in rows.values()])
        ok = total - len(incomplete)
        parts = []
        for name in incomplete:
            row = rows[name]
            reason = row["error"].get("message") or ("the run was cancelled" if row["status"] == "cancelled" else "see errors")
            parts.append(f"{name.capitalize()} was {'skipped' if row['status'] == 'skipped' else 'not fully collected'}: {reason}")
        if self.counts["translation_failed"]:
            parts.append(f"{self.counts['translation_failed']} translation(s) failed.")
        if self._needs_translation and self.provider is None:
            parts.append(f"{self._needs_translation} item(s) were not translated because no LLM provider is configured.")
        if self._limit_notice:
            parts.append("An item limit stopped collection early.")
        complete = not parts
        summary = (f"Collected {self.counts['collected']} item(s) from {ok} of {total} platform(s)."
                   + ("" if complete else " Collection is INCOMPLETE: " + " ".join(parts)))
        return {"complete": complete, "sources": rows, "incomplete_sources": incomplete, "notes": parts, "summary": summary}

    def _finalize(self, fatal: PipelineError | None, started: float) -> None:
        duration = round((time.monotonic() - started) * 1000, 1)
        with self._lock:
            cancelled = self.controller.cancelled
            if not self.run.finished_at:
                self.run.finished_at = utc_now()
            self.run.completeness = self._completeness() if (self.sources or self.run.kind == "reprocess") else {"complete": False, "summary": "No collection was attempted."}
            if cancelled:
                status = "cancelled"
            elif fatal is not None or (self.counts["collected"] == 0 and self.sources and all(h.status in {"failed", "skipped"} for h in self.sources.values())):
                status = "failed"
            elif self.run.completeness.get("complete") and not self.run.warnings and not self.run.errors:
                status = "completed"
            else:
                status = "completed_with_warnings"
            self.run.status = status
            for stage in STAGES:
                state = self.run.stage_states.get(stage, {}).get("state")
                if state in {"pending", "running"}:
                    self.run.stage_states[stage] = {**self.run.stage_states.get(stage, {}), "state": "failed" if status == "failed" else "skipped",
                                                    "finished_at": utc_now()}
            self.run.stage = "results"
            self.run.stage_states["results"] = {"state": "done" if status != "failed" else "failed", "finished_at": utc_now()}
        try:
            self.project.save_items(self.run.run_id, list(self.items.values()))
        except OSError as exc:
            self._record_error(stage="results", subsystem="storage", classification="fatal", message=f"Could not save results: {exc}", exc=exc)
        timings = self.timings.snapshot()
        self.run.metrics = {"duration_ms": duration, "timings": timings, "events": self.events.last_seq}
        self.events.emit("timing.recorded", debug=True, message="Timing summary", **timings)
        if cancelled:
            self.events.emit("run.cancelled", stage="results", message="Run cancelled. Partial results were kept.")
        self.events.emit("pipeline.completed", stage="results", severity="info" if status.startswith("completed") else "warning" if status == "cancelled" else "error",
                         message=self.run.completeness.get("summary", status), status=status, counts=dict(self.counts),
                         completeness=self.run.completeness, duration_ms=duration)
        self._save(force=True)
        try:
            self.project.log(f"run_{status}" if status in {"failed", "cancelled"} else "run_completed",
                             {"run_id": self.run.run_id, "kind": self.run.kind, "status": status, "counts": dict(self.counts),
                              "summary": self.run.completeness.get("summary", "")})
            if self.run.kind == "refresh_sources":
                self.project.log("sources_refreshed", {"run_id": self.run.run_id, "new": self.counts["new"], "known": self.counts["known"]})
            if self.run.kind == "reprocess":
                self.project.log("results_reprocessed", {"run_id": self.run.run_id, "from": self.run.parent_run_id})
        except Exception:
            pass
        self.events.close()


def _category(platform: str) -> str:
    from .research_plan import PLATFORM_CATEGORIES
    return PLATFORM_CATEGORIES.get(platform, "social_media")
