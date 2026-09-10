from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .collectors import collect_x, collect_bluesky, collect_mastodon, create_bluesky_access_token, create_session
from .enrichment import enrich_records
from .llm import ARC_BASE_URL, LLMConfig, create_client, translate_search_term
from .mapping import create_map
from .reporting import create_analysis_report
from .storage import load_results, save_records
from .utils import JsonCache


def _llm_config(config: dict[str, Any], secrets: dict[str, str]) -> LLMConfig:
    raw = config.get("llm") or {}; provider = str(raw.get("provider", "openai")); base = str(raw.get("base_url", "") or "")
    if provider == "arc" and not base: base = ARC_BASE_URL
    if provider == "custom" and not base: raise ValueError("A base URL is required for a custom LLM endpoint.")
    return LLMConfig(provider=provider, model=str(raw.get("model", "gpt-5.6-luna")), api_key=secrets.get("llm_api_key", ""), base_url=base)


def _translated_terms(terms: list[str], languages: list[str], llm: LLMConfig, cache_dir: Path) -> list[str]:
    terms = [str(x).strip() for x in terms if str(x).strip()]
    if not languages: return terms
    client = create_client(llm); cache = JsonCache(cache_dir / "llm.json"); result=list(terms); seen={x.casefold() for x in result}
    for term in terms:
        for language in languages:
            value = translate_search_term(client, llm, cache, term, language)
            if value and value.casefold() not in seen: result.append(value); seen.add(value.casefold())
    return result


def run_search(config: dict[str, Any], secrets: dict[str, str] | None = None) -> list[str]:
    secrets = secrets or {}; out_dir = Path(config.get("output_directory") or Path.cwd()).expanduser().resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S"); csv_path = out_dir / f"social_search_posts_{stamp}.csv"; cache_dir = out_dir / ".sugar-cache"
    llm = _llm_config(config, secrets); translate=bool(config.get("translate_posts", True)); infer=bool(config.get("infer_locations", True))
    terms = _translated_terms(config.get("terms") or [], config.get("translate_term_languages") or [], llm, cache_dir)
    if not terms: raise ValueError("Enter at least one search term.")
    common = dict(search_terms=terms, since=config.get("since") or None, until=config.get("until") or None,
                  max_posts_per_query=int(config.get("max_posts_per_query", 10)), max_pages_per_query=int(config.get("max_pages_per_query", 1)))
    records=[]; sources=config.get("sources") or ["x"]
    if "x" in sources:
        records += collect_x(bearer_token=secrets.get("x_bearer_token", ""), search_mode=config.get("x_search_mode", "recent"),
                             post_languages=config.get("post_languages") or [], include_reposts=bool(config.get("include_retweets", False)), **common)
    if "bluesky" in sources:
        jwt=""
        if secrets.get("bluesky_identifier") and secrets.get("bluesky_app_password"):
            jwt=create_bluesky_access_token(create_session(), secrets["bluesky_identifier"], secrets["bluesky_app_password"])
        records += collect_bluesky(access_jwt=jwt, **common)
    if "mastodon" in sources:
        records += collect_mastodon(instance_url=config.get("mastodon_url", "https://mastodon.social"), access_token=secrets.get("mastodon_token", ""),
                                    include_reposts=bool(config.get("include_retweets", False)), **common)
    records = enrich_records(records, llm=llm if (translate or infer) else None, translate=translate, infer_locations=infer,
                             target_language=config.get("target_language", "English"), cache_dir=cache_dir)
    metadata = {"sources": sources, "terms": terms, "since": config.get("since") or None, "until": config.get("until") or None,
                "llm_provider": llm.provider if (translate or infer) else None, "llm_model": llm.model if (translate or infer) else None}
    save_records(records, csv_path, metadata=metadata)
    return [str(csv_path), str(csv_path.with_suffix(".xlsx")), str(csv_path.with_suffix(".metadata.json"))]


def run_map(config: dict[str, Any]) -> list[str]:
    source = Path(config["source_file"]); output = Path(config.get("output_file") or source.with_name(source.stem + "_map.html"))
    return [create_map(load_results(source), output)]


def run_analysis(config: dict[str, Any]) -> list[str]:
    return create_analysis_report(config["source_file"], config["output_stem"], config.get("output_format", "both"))
