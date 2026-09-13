from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .collector_registry import CollectorRequest, COLLECTORS, collect_registered_source
from .enrichment import enrich_records
from .llm import ARC_BASE_URL, LLMConfig, create_client, translate_search_term
from .mapping import MapOptions, ReferenceLayer, create_map, load_map_frame
from .reporting import create_analysis_report
from .storage import save_records
from .utils import JsonCache

ProgressCallback = Callable[[str, dict[str, Any]], None]


def _notify(progress: ProgressCallback | None, event: str, **values: Any) -> None:
    if progress is not None:
        progress(event, values)


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

    out_dir = Path(config.get("output_directory") or Path.cwd()).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"social_search_posts_{stamp}.csv"
    cache_dir = out_dir / ".sugar-cache"
    llm = _llm_config(config, secrets)

    _notify(progress, "starting", operation="search", sources=sources)
    terms = _translated_terms(
        config.get("terms") or [], translated_languages, llm, cache_dir, progress=progress
    )
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
    for source in sources:
        _notify(progress, "collecting", source=source)
        rows = collect_registered_source(source, request)
        records.extend(rows)
        _notify(progress, "collected", source=source, records=len(rows))

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
        "collector_capabilities": {
            source: COLLECTORS[source].capabilities.as_dict() for source in sources
        },
        "llm_provider": llm.provider if (translate or infer) else None,
        "llm_model": llm.model if (translate or infer) else None,
    }
    _notify(progress, "saving", records=len(records), output=str(csv_path))
    save_records(records, csv_path, metadata=metadata)
    outputs = [
        str(csv_path),
        str(csv_path.with_suffix(".xlsx")),
        str(csv_path.with_suffix(".metadata.json")),
    ]
    _notify(progress, "saved", outputs=outputs)
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


def _map_reference_layers(config: dict[str, Any]) -> list[ReferenceLayer]:
    raw = config.get("map") or {}
    specs = raw.get("reference_layers") or []
    if isinstance(specs, (str, Path, dict)):
        specs = [specs]

    layers: list[ReferenceLayer] = []
    for spec in specs:
        if isinstance(spec, (str, Path)):
            path = Path(spec)
            name = path.stem.replace("_", " ").replace("-", " ").title()
            color = ""
            show = True
        elif isinstance(spec, dict):
            raw_path = spec.get("file") or spec.get("path")
            if not raw_path:
                raise ValueError("Each map reference layer requires a file/path.")
            path = Path(raw_path)
            name = str(spec.get("name") or path.stem).strip() or "Reference"
            color = str(spec.get("color") or "").strip()
            show = bool(spec.get("show", True))
        else:
            raise TypeError("Map reference layers must be file paths or dictionaries.")
        layers.append(
            ReferenceLayer(
                name=name,
                frame=load_map_frame(path),
                color=color,
                show=show,
            )
        )
    return layers


def run_map(config: dict[str, Any]) -> list[str]:
    source = Path(config["source_file"])
    output = Path(config.get("output_file") or source.with_name(source.stem + "_map.html"))
    return [
        create_map(
            load_map_frame(source),
            output,
            options=_map_options(config),
            reference_layers=_map_reference_layers(config),
        )
    ]


def run_analysis(config: dict[str, Any]) -> list[str]:
    return create_analysis_report(
        config["source_file"], config["output_stem"], config.get("output_format", "both")
    )
