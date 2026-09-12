from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .collector_registry import CollectorRequest, COLLECTORS, collect_registered_source
from .enrichment import enrich_records
from .harvest import run_harvest as _run_harvest
from .llm import ARC_BASE_URL, LLMConfig, create_client, translate_search_term
from .mapping import create_map
from .reporting import create_analysis_report
from .storage import load_results, save_records
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


def _harvest_access_modes(config: dict[str, Any], secrets: dict[str, str]) -> dict[str, str]:
    sources = [str(value).strip().casefold() for value in (config.get("sources") or ["x"]) if str(value).strip()]
    modes: dict[str, str] = {}
    for source in sources:
        if source == "x":
            modes[source] = "authorized_api" if secrets.get("x_bearer_token", "").strip() else "missing_credential"
        elif source == "bluesky":
            authenticated = bool(
                secrets.get("bluesky_identifier", "").strip()
                and secrets.get("bluesky_app_password", "").strip()
            )
            modes[source] = "authenticated" if authenticated else "public_appview"
        elif source == "mastodon":
            modes[source] = "authenticated" if secrets.get("mastodon_token", "").strip() else "anonymous_instance"
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
    """Run the high-volume collector with a non-secret access-mode consistency guard."""
    secrets = secrets or {}
    modes = _harvest_access_modes(config, secrets)
    marker = _harvest_access_marker(config)
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
            json.dumps({"access_modes": modes}, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    outputs = _run_harvest(config, secrets, progress=progress)
    raw = config.get("harvest") or {}
    out_dir = Path(config.get("output_directory") or raw.get("output_directory") or Path.cwd()).expanduser().resolve()
    name = "_".join(str(raw.get("name") or config.get("name") or "sugar_harvest").split())
    manifest = out_dir / f"{name}.harvest.json"
    if manifest.is_file():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["access_modes"] = modes
        manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if str(marker.resolve()) not in outputs:
        outputs.append(str(marker.resolve()))
    return outputs


def run_map(config: dict[str, Any]) -> list[str]:
    source = Path(config["source_file"])
    output = Path(config.get("output_file") or source.with_name(source.stem + "_map.html"))
    return [create_map(load_results(source), output)]


def run_analysis(config: dict[str, Any]) -> list[str]:
    return create_analysis_report(
        config["source_file"], config["output_stem"], config.get("output_format", "both")
    )
