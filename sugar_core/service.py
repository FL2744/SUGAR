from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .collection_coverage import SourceCoverage, classify_collection_error, coverage_payload
from .collector_registry import CollectorRequest, COLLECTORS, collect_registered_source, fetch_registered_item
from .enrichment import enrich_records
from .harvest import run_harvest as _run_harvest
from .llm import ARC_BASE_URL, LLMConfig, create_client, translate_search_term
from .mapping import MapOptions, ReferenceLayer, create_map, load_map_frame
from .observation_storage import load_observations, observations_to_frame, save_observations
from .reporting import create_analysis_report
from .research_workspace import ResearchWorkspaceState, SearchHistoryEntry
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
        model=str(raw.get("model", "gpt-5.6-luna")),
        api_key=secrets.get("llm_api_key", ""),
        base_url=base,
    )


def _translated_terms(
    terms: list[str], languages: list[str], llm: LLMConfig, cache_dir: Path,
    progress: ProgressCallback | None = None,
) -> list[str]:
    terms = [str(x).strip() for x in terms if str(x).strip()]
    if not languages:
        return terms
    _notify(progress, "translating_search_terms", terms=len(terms), languages=len(languages))
    client = create_client(llm)
    cache = JsonCache(cache_dir / "llm.json")
    result = list(terms)
    seen = {x.casefold() for x in result}
    total = len(terms) * len(languages)
    completed = 0
    for term in terms:
        for language in languages:
            value = translate_search_term(client, llm, cache, term, language)
            completed += 1
            if value and value.casefold() not in seen:
                result.append(value)
                seen.add(value.casefold())
            _notify(progress, "search_term_progress", current=completed, total=total)
    return result


def run_search(
    config: dict[str, Any], secrets: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
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
    terms = _translated_terms(config.get("terms") or [], translated_languages, llm, cache_dir, progress=progress)
    if not terms:
        raise ValueError("Enter at least one search term.")

    request = CollectorRequest(
        search_terms=terms,
        since=config.get("since") or None,
        until=config.get("until") or None,
        max_posts_per_query=int(config.get("max_posts_per_query", 10)),
        max_pages_per_query=int(config.get("max_pages_per_query", 1)),
        config=config,
        secrets=secrets,
    )

    records = []
    coverage: list[SourceCoverage] = []
    continue_on_source_error = bool(config.get("continue_on_source_error", False))
    access_modes = _harvest_access_modes(config, secrets)
    for source in sources:
        started_at = utc_iso()
        _notify(progress, "collecting", source=source)
        try:
            rows = collect_registered_source(source, request)
        except Exception as exc:
            partial_rows = list(getattr(exc, "partial_records", ()) or ())
            if partial_rows:
                records.extend(partial_rows)
            status = classify_collection_error(exc, records=len(partial_rows))
            entry = SourceCoverage(
                source=source,
                status=status,
                records=len(partial_rows),
                access_mode=access_modes.get(source, "collector_default"),
                reason=str(exc),
                error_type=type(exc).__name__,
                started_at=started_at,
                completed_at=utc_iso(),
            )
            coverage.append(entry)
            _write_coverage(
                coverage_path,
                coverage,
                terms=terms,
                since=config.get("since") or None,
                until=config.get("until") or None,
            )
            _notify(progress, "collection_failed", source=source, status=status, error_type=entry.error_type)
            if not continue_on_source_error:
                raise
            continue
        records.extend(rows)
        status = "success" if rows else "zero_result"
        coverage.append(SourceCoverage(
            source=source,
            status=status,
            records=len(rows),
            access_mode=access_modes.get(source, "collector_default"),
            started_at=started_at,
            completed_at=utc_iso(),
        ))
        _notify(progress, "collected", source=source, records=len(rows))

    coverage_payload_data = _write_coverage(
        coverage_path,
        coverage,
        terms=terms,
        since=config.get("since") or None,
        until=config.get("until") or None,
    )

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
        "since": config.get("since") or None,
        "until": config.get("until") or None,
        "collector_capabilities": {source: COLLECTORS[source].capabilities.as_dict() for source in sources},
        "source_coverage": coverage_payload_data,
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
    if workspace is not None:
        research_state = ResearchWorkspaceState.open(
            workspace.root,
            project_id=workspace.manifest.project_id,
        )
        research_state.record_search(
            SearchHistoryEntry(
                query_terms=terms,
                sources=sources,
                subproject_id=str(config.get("subproject_id") or ""),
                research_question=str(config.get("research_question") or ""),
                started_at=min(
                    (entry.started_at for entry in coverage if entry.started_at),
                    default=utc_iso(),
                ),
                completed_at=utc_iso(),
                result_count=len(records),
                status="partial" if any(entry.status in {"partial", "unavailable", "failure"} for entry in coverage) else "complete",
                collection_id=csv_path.stem,
                metadata={
                    "since": config.get("since") or None,
                    "until": config.get("until") or None,
                    "coverage_file": str(coverage_path),
                },
            )
        )
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
