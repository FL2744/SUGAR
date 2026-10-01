from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .collection_coverage import SourceCoverage, classify_collection_error, coverage_payload
from .collector_registry import CollectorRequest, COLLECTORS, collect_registered_source, fetch_registered_item
from .enrichment import enrich_records
from .harvest import rate_limit_wait_seconds, run_harvest as _run_harvest
from .llm import ARC_BASE_URL, LLMConfig, create_client, default_model, translate_search_term
from .mapping import MapOptions, ReferenceLayer, create_map, load_map_frame
from .observation_storage import load_observations, observations_to_frame, save_observations
from .provider_pacing import SHARED_REQUEST_PACER
from .reporting import create_analysis_report
from .spatial import (
    SpatialOverlapConfig,
    analyze_spatial_overlap,
    save_spatial_matches,
    save_spatial_summary,
)
from .storage import save_records
from .utils import JsonCache, utc_iso
from .workspace_runtime import (
    choose_output_directory,
    register_workspace_outputs,
    workspace_from_config,
)

ProgressCallback = Callable[[str, dict[str, Any]], None]


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


def _estimated_record_memory(record: Any) -> int:
    try:
        payload = record.export_dict()
    except Exception:
        payload = vars(record)
    serialized = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
    # Reserve room for Python object overhead, enrichment fields, and table serialization.
    return max(2_048, len(serialized) * 4)


def _write_coverage(path: Path, entries: list[SourceCoverage], *, terms: list[str], since: str | None, until: str | None) -> dict[str, Any]:
    payload = coverage_payload(entries, terms=terms, since=since, until=until)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def _llm_config(config: dict[str, Any], secrets: dict[str, str]) -> LLMConfig:
    raw = config.get("llm") or {}
    provider = str(raw.get("provider", "openai"))
    base = str(raw.get("base_url", "") or "")
    if provider == "arc" and not base:
        base = ARC_BASE_URL
    if provider == "custom" and not base:
        raise ValueError("A base URL is required for a custom LLM endpoint.")
    return LLMConfig(
        provider=provider,
        model=str(raw.get("model") or default_model(provider)),
        api_key=secrets.get("llm_api_key", ""),
        base_url=base,
    )


def _platform_tuning(config: dict[str, Any]) -> dict[str, dict[str, int]]:
    raw = config.get("platform_tuning", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("platform_tuning must be an object keyed by source name.")
    supported = {"max_posts_per_query": 1000, "max_pages_per_query": 100}
    result: dict[str, dict[str, int]] = {}
    for source_value, options in raw.items():
        source = str(source_value).strip().casefold()
        if source not in COLLECTORS:
            raise ValueError(f"Unsupported platform_tuning source: {source or '(empty)'}.")
        if not isinstance(options, dict):
            raise ValueError(f"platform_tuning for {source} must be an object.")
        unknown = sorted(set(options) - set(supported))
        if unknown:
            raise ValueError(f"Unsupported platform_tuning field(s) for {source}: {', '.join(unknown)}.")
        normalized: dict[str, int] = {}
        for key, maximum in supported.items():
            if key not in options or options[key] in (None, ""):
                continue
            try:
                value = int(str(options[key]).strip())
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{source} {key} must be a positive integer.") from exc
            if value < 1:
                raise ValueError(f"{source} {key} must be a positive integer.")
            normalized[key] = min(maximum, value)
        result[source] = normalized
    return result


def _translated_terms(
    terms: list[str], languages: list[str], llm: LLMConfig, cache_dir: Path,
    progress: ProgressCallback | None = None, *, max_workers: int = 8,
) -> list[str]:
    terms = [str(x).strip() for x in terms if str(x).strip()]
    if not languages:
        return terms
    _notify(progress, "translating_search_terms", terms=len(terms), languages=len(languages))
    client = create_client(llm)
    cache = JsonCache(cache_dir / "llm.json")
    result = list(terms)
    seen = {x.casefold() for x in result}
    jobs = [(term, language) for term in terms for language in languages]
    total = len(jobs)
    completed = 0
    translations = [""] * total
    with ThreadPoolExecutor(max_workers=min(max(1, int(max_workers)), max(1, total)), thread_name_prefix="sugar-translate") as pool:
        pending = {
            pool.submit(translate_search_term, client, llm, cache, term, language): index
            for index, (term, language) in enumerate(jobs)
        }
        for future in as_completed(pending):
            translations[pending[future]] = future.result()
            completed += 1
            _notify(progress, "search_term_progress", current=completed, total=total)
    for value in translations:
        if value and value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())
    return result


def run_search(
    config: dict[str, Any], secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
    *,
    control_reader: Callable[[], dict[str, Any] | None] | None = None,
) -> list[str]:
    secrets = secrets or {}
    workspace = workspace_from_config(config)
    sources = [str(x).strip().lower() for x in (config.get("sources") or ["x"]) if str(x).strip()]
    unknown = sorted(set(sources) - set(COLLECTORS))
    if unknown:
        raise ValueError(f"Unsupported source(s): {', '.join(unknown)}")

    translate = bool(config.get("translate_posts", True))
    infer = bool(config.get("infer_locations", True))
    translated_languages = config.get("translate_term_languages") or []
    ai_needed = translate or infer or bool(translated_languages)
    if ai_needed and not secrets.get("llm_api_key", "").strip():
        raise ValueError("AI enrichment is enabled, but no LLM API key was provided.")

    out_dir = choose_output_directory(config.get("output_directory"), workspace, "raw", fallback=Path.cwd())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"social_search_posts_{stamp}.csv"
    coverage_path = csv_path.with_suffix(".coverage.json")
    cache_dir = workspace.path_for("cache") if workspace is not None else out_dir / ".sugar-cache"
    llm = _llm_config(config, secrets)

    _notify(progress, "starting", operation="search", sources=sources)
    terms = _translated_terms(
        config.get("terms") or [], translated_languages, llm, cache_dir, progress=progress,
        max_workers=int(config.get("translation_workers", 8)),
    )
    if not terms:
        raise ValueError("Enter at least one search term.")

    max_posts = min(1000, max(1, int(config.get("max_posts_per_query", 10))))
    max_pages = min(100, max(1, int(config.get("max_pages_per_query", 1))))
    platform_tuning = _platform_tuning(config)
    max_records = min(20_000, max(1, int(config.get("max_records", 20_000))))
    max_collection_calls = min(10_000, max(1, int(config.get("max_collection_calls", 10_000))))
    max_memory_bytes = min(512 * 1024 * 1024, max(1024 * 1024, int(config.get("max_memory_bytes", 64 * 1024 * 1024))))
    memory_worker_limit = max(1, max_memory_bytes // (2 * 1024 * 1024))
    max_parallel_sources = min(5, memory_worker_limit, max(1, int(config.get("max_parallel_sources", 5))))
    shared_request_interval = min(60.0, max(0.0, float(config.get("shared_request_interval_seconds", 0.2))))
    base_scope = {
        "sources": sources,
        "terms": terms,
        "since": config.get("since") or None,
        "until": config.get("until") or None,
        "post_languages": [str(value).strip().casefold() for value in config.get("post_languages") or [] if str(value).strip()],
        "excluded_topics": [str(value).strip() for value in config.get("excluded_topics") or [] if str(value).strip()],
    }
    records = []
    source_stats: dict[str, dict[str, Any]] = {}
    used_sources: list[str] = []
    used_terms: list[str] = []
    attempted: set[tuple[str, str]] = set()
    retried: set[tuple[str, str, str]] = set()
    processed_retries: set[str] = set()
    collection_calls = 0
    estimated_memory_bytes = 0
    cancelled = False
    limit_reached = False
    memory_limit_reached = False
    continue_on_source_error = bool(config.get("continue_on_source_error", False))
    access_modes = _harvest_access_modes(config, secrets)

    def current_scope() -> dict[str, Any]:
        current = dict(base_scope)
        if control_reader is not None:
            live = control_reader()
            if isinstance(live, dict):
                if live.get("status") != "running":
                    current["cancel_requested"] = True
                else:
                    for key in ("sources", "terms", "since", "until", "post_languages", "excluded_topics"):
                        if key in live:
                            current[key] = live[key]
                    current["retry_requests"] = live.get("retry_requests", [])
                    current["revision"] = live.get("revision", 0)
                    current["cancel_requested"] = bool(live.get("cancel_requested", False))
        current["sources"] = list(dict.fromkeys(str(value).strip().casefold() for value in current.get("sources", []) if str(value).strip()))
        current["terms"] = list(dict.fromkeys(str(value).strip() for value in current.get("terms", []) if str(value).strip()))
        current["post_languages"] = [str(value).strip().casefold() for value in current.get("post_languages", []) if str(value).strip()]
        current["excluded_topics"] = [str(value).strip() for value in current.get("excluded_topics", []) if str(value).strip()]
        return current

    def cancelled_while_waiting() -> bool:
        return bool(current_scope().get("cancel_requested"))

    def retain_records(rows: list[Any], count_limit: int) -> list[Any]:
        nonlocal estimated_memory_bytes, memory_limit_reached, limit_reached
        accepted = []
        for record in rows[:max(0, count_limit)]:
            estimated_size = _estimated_record_memory(record)
            if estimated_memory_bytes + estimated_size > max_memory_bytes:
                memory_limit_reached = True
                limit_reached = True
                _notify(
                    progress,
                    "warning",
                    message=f"Collection reached its {max_memory_bytes:,}-byte estimated memory budget; results are being saved as a bounded partial run.",
                )
                break
            accepted.append(record)
            estimated_memory_bytes += estimated_size
        return accepted

    def collect_one(source: str, request: CollectorRequest):
        if not SHARED_REQUEST_PACER.acquire(
            interval_seconds=shared_request_interval,
            cancelled=cancelled_while_waiting,
        ):
            return [], None, True
        try:
            return collect_registered_source(source, request), None, False
        except Exception as exc:
            wait = rate_limit_wait_seconds(exc, source)
            if wait is not None:
                SHARED_REQUEST_PACER.defer(wait)
            return list(getattr(exc, "partial_records", ()) or ()), exc, False

    fatal_error: Exception | None = None
    with ThreadPoolExecutor(max_workers=max_parallel_sources, thread_name_prefix="sugar-collect") as pool:
        while collection_calls < max_collection_calls:
            scope = current_scope()
            if scope.get("cancel_requested"):
                cancelled = True
                _notify(progress, "collection_stopped", reason="cancelled_between_requests", completed_requests=collection_calls)
                break
            active_sources = scope["sources"]
            active_terms = scope["terms"]
            if not active_terms:
                break
            remaining_budget = max_records - len(records)
            if remaining_budget <= 0:
                limit_reached = True
                break

            work: list[tuple[str, str, str | None]] = []
            selected_sources: set[str] = set()
            for retry in scope.get("retry_requests", []):
                if len(work) >= max_parallel_sources or not isinstance(retry, dict):
                    continue
                retry_id = str(retry.get("id") or "").strip()
                retry_source = str(retry.get("source") or "").strip().casefold()
                if not retry_id or not retry_source or retry_id in processed_retries:
                    continue
                if retry_source not in COLLECTORS:
                    processed_retries.add(retry_id)
                    _notify(progress, "collection_retry_rejected", source=retry_source, reason="unsupported_source")
                    continue
                if retry_source in selected_sources:
                    continue
                pending_term = next((term for term in active_terms if (retry_id, retry_source, term) not in retried), None)
                if pending_term is None:
                    processed_retries.add(retry_id)
                    continue
                work.append((retry_source, pending_term, retry_id))
                selected_sources.add(retry_source)

            for source in active_sources:
                if len(work) >= max_parallel_sources:
                    break
                if source in selected_sources:
                    continue
                pending_term = next((term for term in active_terms if (source, term) not in attempted), None)
                if pending_term is not None:
                    work.append((source, pending_term, None))
                    selected_sources.add(source)
            if not work:
                break
            if collection_calls + len(work) > max_collection_calls:
                work = work[:max_collection_calls - collection_calls]
            if len(work) > remaining_budget:
                work = work[:remaining_budget]
            memory_request_limit = max(1, max_memory_bytes // max(1, len(work) * 128 * 1024))
            per_request_budget = min(max(1, remaining_budget // len(work)), memory_request_limit)

            futures = {}
            for source, term, retry_id in work:
                if source not in COLLECTORS:
                    raise ValueError(f"Unsupported source in live collection scope: {source}")
                if retry_id is None:
                    attempted.add((source, term))
                else:
                    retried.add((retry_id, source, term))
                if source not in source_stats:
                    source_stats[source] = {
                        "started_at": utc_iso(),
                        "records": 0,
                        "attempts": 0,
                        "errors": [],
                        "had_result": False,
                    }
                source_stats[source]["attempts"] += 1
                if source not in used_sources:
                    used_sources.append(source)
                if term not in used_terms:
                    used_terms.append(term)
                request_config = dict(config)
                source_options = platform_tuning.get(source, {})
                source_max_posts = source_options.get("max_posts_per_query", max_posts)
                source_max_pages = source_options.get("max_pages_per_query", max_pages)
                request_config.update({
                    "sources": [source],
                    "post_languages": scope["post_languages"],
                    "excluded_topics": scope["excluded_topics"],
                    "max_posts_per_query": min(source_max_posts, per_request_budget),
                    "max_pages_per_query": source_max_pages,
                })
                request = CollectorRequest(
                    search_terms=[term],
                    since=scope.get("since") or None,
                    until=scope.get("until") or None,
                    max_posts_per_query=min(source_max_posts, per_request_budget),
                    max_pages_per_query=source_max_pages,
                    config=request_config,
                    secrets=secrets,
                )
                if source not in access_modes:
                    access_modes.update(_harvest_access_modes({"sources": [source]}, secrets))
                _notify(progress, "collecting", source=source, query=term, retry=retry_id is not None, scope_revision=scope.get("revision", 0))
                futures[(source, term, retry_id)] = pool.submit(collect_one, source, request)

            collection_calls += len(futures)
            outcomes = {item: future.result() for item, future in futures.items()}
            for source, term, retry_id in work:
                rows, error, skipped = outcomes[(source, term, retry_id)]
                stats = source_stats[source]
                if skipped:
                    _notify(progress, "collection_request_skipped", source=source, reason="cancelled_before_request")
                    continue
                if error is not None:
                    status = classify_collection_error(error, records=len(rows))
                    stats["errors"].append((status, str(error), type(error).__name__))
                    accepted = retain_records(rows, max_records - len(records))
                    records.extend(accepted)
                    stats["records"] += len(accepted)
                    _notify(progress, "collection_failed", source=source, query=term, status=status, error_type=type(error).__name__)
                    if not continue_on_source_error and fatal_error is None:
                        fatal_error = error
                    if memory_limit_reached:
                        break
                    continue
                excluded = [topic.casefold() for topic in scope["excluded_topics"]]
                included_rows = [
                    row for row in rows
                    if not any(
                        topic in " ".join(
                            str(getattr(row, field, "") or "")
                            for field in ("original_text", "translated_text")
                        ).casefold()
                        for topic in excluded
                    )
                ]
                accepted = retain_records(included_rows, max_records - len(records))
                records.extend(accepted)
                stats["records"] += len(accepted)
                stats["had_result"] = stats["had_result"] or bool(accepted)
                _notify(progress, "collected", source=source, query=term, records=len(accepted), excluded=len(rows) - len(included_rows))
                if memory_limit_reached or len(accepted) < len(included_rows) or len(records) >= max_records:
                    limit_reached = True
                    if not memory_limit_reached:
                        _notify(progress, "warning", message=f"Collection reached its {max_records:,}-record limit; results are being saved as a bounded partial run.")
                    break
            if fatal_error is not None:
                break
            if limit_reached:
                break

    if collection_calls >= max_collection_calls and not cancelled:
        limit_reached = True
        _notify(progress, "warning", message=f"Collection reached its {max_collection_calls:,}-request safety limit; results are being saved as a bounded partial run.")

    coverage: list[SourceCoverage] = []
    for source, stats in source_stats.items():
        errors = stats["errors"]
        if errors:
            if stats["records"]:
                status, reason, error_type = "partial", errors[-1][1], errors[-1][2]
            else:
                status, reason, error_type = errors[-1]
        elif memory_limit_reached:
            status, reason, error_type = "partial", "The estimated collection memory budget was reached before every returned record could be retained.", "MemoryBudgetExceeded"
        elif stats["had_result"]:
            status, reason, error_type = "success", "", ""
        else:
            status, reason, error_type = "zero_result", "", ""
        if cancelled and status in {"success", "zero_result"}:
            status, reason = "partial", "The analyst stopped the run between requests."
        elif limit_reached and status == "success":
            status, reason = "partial", "The bounded collection safety limit was reached."
        coverage.append(SourceCoverage(
            source=source,
            status=status,
            records=stats["records"],
            access_mode=access_modes.get(source, "collector_default"),
            reason=reason,
            error_type=error_type,
            started_at=stats["started_at"],
            completed_at=utc_iso(),
        ))
    terms = used_terms or terms
    sources = used_sources or sources
    final_scope = current_scope()

    coverage_payload_data = _write_coverage(
        coverage_path,
        coverage,
        terms=terms,
        since=final_scope.get("since") or None,
        until=final_scope.get("until") or None,
    )

    if fatal_error is not None:
        raise fatal_error

    _notify(progress, "enriching", records=len(records), translate=translate, infer_locations=infer)
    records = enrich_records(
        records,
        llm=llm if (translate or infer) else None,
        translate=translate,
        infer_locations=infer,
        target_language=config.get("target_language", "English"),
        cache_dir=cache_dir,
        progress=progress,
    )

    metadata = {
        "sources": sources,
        "terms": terms,
        "since": final_scope.get("since") or None,
        "until": final_scope.get("until") or None,
        "collector_capabilities": {source: COLLECTORS[source].capabilities.as_dict() for source in sources},
        "source_coverage": coverage_payload_data,
        "collection_cancelled": cancelled,
        "collection_limit_reached": limit_reached,
        "collection_requests": collection_calls,
        "max_records": max_records,
        "max_memory_bytes": max_memory_bytes,
        "estimated_record_memory_bytes": estimated_memory_bytes,
        "collection_memory_limit_reached": memory_limit_reached,
        "max_parallel_sources": max_parallel_sources,
        "shared_request_interval_seconds": shared_request_interval,
        "platform_tuning": platform_tuning,
        "llm_provider": llm.provider if (translate or infer) else None,
        "llm_model": llm.model if (translate or infer) else None,
        "workspace_project_id": workspace.manifest.project_id if workspace is not None else None,
    }
    _notify(progress, "saving", records=len(records), output=str(csv_path))
    save_records(records, csv_path, metadata=metadata)
    outputs = [
        str(csv_path),
        str(csv_path.with_suffix(".xlsx")),
        str(csv_path.with_suffix(".metadata.json")),
        str(coverage_path),
    ]
    register_workspace_outputs(workspace, outputs, operation="search", kind="raw_collection")
    _notify(progress, "saved", outputs=outputs)
    return outputs


def run_ingest(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> list[str]:
    """Ingest one known public item through the shared collector registry."""

    secrets = secrets or {}
    workspace = workspace_from_config(config)
    source = str(config.get("source") or "").strip().lower()
    identifier = str(config.get("identifier") or config.get("url") or config.get("item") or "").strip()
    query = str(config.get("query") or "").strip()
    if not source:
        raise ValueError("Choose a source for public-item ingestion.")
    if source not in COLLECTORS:
        raise ValueError(f"Unsupported source: {source}")
    if not identifier:
        raise ValueError("Enter a public URL or native item identifier.")

    out_dir = choose_output_directory(config.get("output_directory"), workspace, "raw", fallback=Path.cwd())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"public_item_{source}_{stamp}.csv"
    request = CollectorRequest(
        search_terms=[query] if query else [],
        config=config,
        secrets=secrets,
    )
    _notify(progress, "starting", operation="ingest", source=source)
    _notify(progress, "collecting", source=source)
    record = fetch_registered_item(source, identifier, request)
    _notify(progress, "collected", source=source, records=1)
    metadata = {
        "operation": "ingest",
        "source": source,
        "input_identifier": identifier,
        "query": query or None,
        "collector_capabilities": COLLECTORS[source].capabilities.as_dict(),
        "workspace_project_id": workspace.manifest.project_id if workspace is not None else None,
    }
    save_records([record], csv_path, metadata=metadata)
    outputs = [str(csv_path), str(csv_path.with_suffix(".xlsx")), str(csv_path.with_suffix(".metadata.json"))]
    register_workspace_outputs(workspace, outputs, operation="ingest", kind="raw_collection")
    _notify(progress, "saved", outputs=outputs)
    return outputs


def _harvest_access_modes(config: dict[str, Any], secrets: dict[str, str]) -> dict[str, str]:
    sources = [str(value).strip().casefold() for value in (config.get("sources") or ["x"]) if str(value).strip()]
    modes: dict[str, str] = {}
    for source in sources:
        if source == "x":
            modes[source] = "authorized_api" if secrets.get("x_bearer_token", "").strip() else "missing_credential"
        elif source == "bluesky":
            authenticated = bool(secrets.get("bluesky_identifier", "").strip() and secrets.get("bluesky_app_password", "").strip())
            modes[source] = "authenticated" if authenticated else "public_appview"
        elif source == "mastodon":
            modes[source] = "authenticated" if secrets.get("mastodon_token", "").strip() else "missing_credential"
        elif source == "weibo":
            modes[source] = "session" if secrets.get("weibo_cookie", "").strip() else "anonymous"
        elif source == "bilibili":
            modes[source] = "anonymous_public"
        else:
            modes[source] = "collector_default"
    return modes


def _harvest_access_marker(config: dict[str, Any]) -> Path:
    raw = config.get("harvest") or {}
    out_dir = Path(config.get("output_directory") or raw.get("output_directory") or Path.cwd()).expanduser().resolve()
    name = "_".join(str(raw.get("name") or config.get("name") or "sugar_harvest").split())
    return out_dir / f"{name}.harvest.access.json"


def run_harvest(
    config: dict[str, Any],
    secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> list[str]:
    secrets = secrets or {}
    workspace = workspace_from_config(config)
    effective = dict(config)
    effective["output_directory"] = str(
        choose_output_directory(config.get("output_directory"), workspace, "raw", fallback=Path.cwd())
    )
    modes = _harvest_access_modes(effective, secrets)
    marker = _harvest_access_marker(effective)
    marker.parent.mkdir(parents=True, exist_ok=True)
    if marker.is_file():
        existing = json.loads(marker.read_text(encoding="utf-8"))
        if existing.get("access_modes") != modes:
            raise ValueError(
                "This named harvest was created with different source access modes. "
                "Use a new harvest --name instead of mixing anonymous and authenticated coverage."
            )
    else:
        marker.write_text(
            json.dumps(
                {
                    "access_modes": modes,
                    "workspace_project_id": workspace.manifest.project_id if workspace is not None else None,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    outputs = _run_harvest(effective, secrets, progress=progress)
    raw = effective.get("harvest") or {}
    out_dir = Path(effective["output_directory"]).expanduser().resolve()
    name = "_".join(str(raw.get("name") or effective.get("name") or "sugar_harvest").split())
    manifest = out_dir / f"{name}.harvest.json"
    if manifest.is_file():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["access_modes"] = modes
        if workspace is not None:
            payload["workspace_project_id"] = workspace.manifest.project_id
        manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if str(marker.resolve()) not in outputs:
        outputs.append(str(marker.resolve()))
    register_workspace_outputs(workspace, outputs, operation="harvest", kind="harvest")
    return outputs


def _map_options(config: dict[str, Any]) -> MapOptions:
    raw = config.get("map") or {}
    heat_windows = raw.get("heat_windows", (30, 90, 365))
    if isinstance(heat_windows, str):
        heat_windows = [part.strip() for part in heat_windows.split(",") if part.strip()]
    windows = tuple(sorted({int(value) for value in heat_windows if int(value) > 0})) or (30, 90, 365)
    return MapOptions(
        title=str(raw.get("title", "SUGAR Research Activity Map")),
        subtitle=str(raw.get("subtitle", "Public-source activity, evidence, and geographic overlap")),
        heat_windows=windows,
        default_heat_window=int(raw.get("default_heat_window", 90)),
        max_popup_chars=max(300, int(raw.get("max_popup_chars", 2200))),
        cluster_disable_at_zoom=max(1, int(raw.get("cluster_disable_at_zoom", 11))),
        show_minimap=bool(raw.get("show_minimap", True)),
        show_measure_control=bool(raw.get("show_measure_control", True)),
        show_mouse_position=bool(raw.get("show_mouse_position", True)),
    )


def _load_reference_specs(specs: Any, *, context: str) -> list[tuple[str, Path, str, bool]]:
    if isinstance(specs, (str, Path, dict)):
        specs = [specs]
    result: list[tuple[str, Path, str, bool]] = []
    for spec in specs or []:
        if isinstance(spec, (str, Path)):
            path = Path(spec)
            name = path.stem.replace("_", " ").replace("-", " ").title()
            color = ""
            show = True
        elif isinstance(spec, dict):
            raw_path = spec.get("file") or spec.get("path")
            if not raw_path:
                raise ValueError(f"Each {context} reference layer requires a file/path.")
            path = Path(raw_path)
            name = str(spec.get("name") or path.stem).strip() or "Reference"
            color = str(spec.get("color") or "").strip()
            show = bool(spec.get("show", True))
        else:
            raise TypeError(f"{context.title()} reference layers must be file paths or dictionaries.")
        result.append((name, path, color, show))
    return result


def _map_reference_layers(config: dict[str, Any]) -> list[ReferenceLayer]:
    raw = config.get("map") or {}
    layers: list[ReferenceLayer] = []
    for name, path, color, show in _load_reference_specs(raw.get("reference_layers") or [], context="map"):
        layers.append(ReferenceLayer(name=name, frame=load_map_frame(path), color=color, show=show))
    return layers


def run_map(config: dict[str, Any]) -> list[str]:
    workspace = workspace_from_config(config)
    source = Path(config["source_file"]).expanduser().resolve()
    if config.get("output_file"):
        output = Path(config["output_file"]).expanduser().resolve()
    elif workspace is not None:
        output = workspace.path_for("maps") / f"{source.stem}_map.html"
    else:
        output = source.with_name(source.stem + "_map.html")
    outputs = [
        create_map(
            load_map_frame(source),
            output,
            options=_map_options(config),
            reference_layers=_map_reference_layers(config),
        )
    ]
    register_workspace_outputs(workspace, outputs, operation="map", kind="map")
    return outputs


def run_overlap(config: dict[str, Any], progress: ProgressCallback | None = None) -> list[str]:
    workspace = workspace_from_config(config)
    source = Path(config["source_file"]).expanduser().resolve()
    raw = config.get("spatial") or {}
    specs = raw.get("reference_layers") or raw.get("references") or config.get("reference_layers") or []
    loaded_specs = _load_reference_specs(specs, context="spatial")
    if not loaded_specs:
        raise ValueError("Spatial overlap analysis requires at least one reference layer.")

    bands = raw.get("distance_bands_km", raw.get("bands_km", (5, 25, 100, 250)))
    if isinstance(bands, str):
        bands = [part.strip() for part in bands.split(",") if part.strip()]
    overlap_config = SpatialOverlapConfig(
        distance_bands_km=tuple(float(value) for value in bands),
        max_distance_km=float(raw["max_distance_km"]) if raw.get("max_distance_km") not in (None, "") else None,
        stored_matches_per_observation=int(raw.get("stored_matches_per_observation", raw.get("top_k", 5))),
        include_rejected=bool(raw.get("include_rejected", False)),
    )

    _notify(progress, "starting", operation="spatial_overlap", source_file=str(source))
    observations = load_observations(source)
    reference_layers: list[tuple[str, Any]] = []
    map_layers: list[ReferenceLayer] = []
    for name, path, color, show in loaded_specs:
        frame = load_map_frame(path)
        reference_layers.append((name, frame))
        map_layers.append(ReferenceLayer(name=name, frame=frame, color=color, show=show))
    _notify(progress, "spatial_matching", observations=len(observations), reference_layers=len(reference_layers), max_distance_km=overlap_config.max_distance_km)
    enriched, matches, summary = analyze_spatial_overlap(observations, reference_layers, config=overlap_config)

    explicit_output = config.get("output_file") or raw.get("output_file")
    if explicit_output:
        output = Path(explicit_output).expanduser().resolve()
    elif workspace is not None:
        output = workspace.path_for("observations") / f"{source.stem}_spatial.csv"
    else:
        output = source.with_name(source.stem + "_spatial.csv")
    output_csv = output if output.suffix.casefold() == ".csv" else output.with_suffix(".csv")
    output_stem = output_csv.with_suffix("")
    save_observations(enriched, output_csv, metadata={"spatial_analysis": summary})
    outputs = [str(output_csv), str(output_csv.with_suffix(".xlsx")), str(output_csv.with_suffix(".metadata.json"))]
    outputs.extend(save_spatial_matches(matches, output_stem.with_name(output_stem.name + "_matches.csv")))
    outputs.append(save_spatial_summary(summary, output_stem.with_name(output_stem.name + "_summary.json")))

    if bool(raw.get("create_map", config.get("create_map", False))):
        explicit_map = raw.get("map_output") or config.get("map_output")
        if explicit_map:
            map_output = Path(explicit_map).expanduser().resolve()
        elif workspace is not None:
            map_output = workspace.path_for("maps") / f"{output_stem.name}_map.html"
        else:
            map_output = output_stem.with_name(output_stem.name + "_map.html")
        map_config = dict(config)
        map_config["map"] = {**(config.get("map") or {}), "reference_layers": []}
        create_map(observations_to_frame(enriched), map_output, options=_map_options(map_config), reference_layers=map_layers)
        outputs.append(str(map_output.expanduser().resolve()))

    register_workspace_outputs(workspace, outputs, operation="overlap")
    _notify(progress, "spatial_complete", observations_matched=summary["observations_matched"], pair_matches=summary["retained_pair_matches"], outputs=outputs)
    return outputs


def run_analysis(config: dict[str, Any]) -> list[str]:
    workspace = workspace_from_config(config)
    source = Path(config["source_file"]).expanduser().resolve()
    stem_value = config.get("output_stem")
    if stem_value:
        stem = Path(stem_value).expanduser().resolve()
    elif workspace is not None:
        stem = workspace.path_for("reports") / f"{source.stem}_analysis"
    else:
        stem = source.with_name(source.stem + "_analysis")
    outputs = create_analysis_report(source, stem, config.get("output_format", "both"))
    register_workspace_outputs(workspace, outputs, operation="analysis", kind="report")
    return outputs
