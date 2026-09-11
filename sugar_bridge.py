#!/usr/bin/env python3
"""JSON command bridge used by the native SUGAR macOS application."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Frozen executables also need explicit flushing when connected to the UI pipe.
for stream in (sys.stdout, sys.stderr):
    if stream is not None:
        stream.reconfigure(line_buffering=True, write_through=True)

os.environ["SUGAR_SKIP_DEPENDENCY_CHECK"] = "1"

import pandas as pd

import SUGAR as core
from sugar_analysis import create_analysis_report


def emit(event: str, **values):
    print(json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def configure_llm(config: dict):
    llm = config.get("llm", {})
    core.LLM_PROVIDER = llm.get("provider", "openai")
    core.LLM_MODEL = llm.get("model", "gpt-5.6-luna")
    requested_base_url = str(llm.get("base_url", "")).strip()
    if core.LLM_PROVIDER == "arc" and not requested_base_url:
        requested_base_url = core.ARC_BASE_URL
    if core.LLM_PROVIDER == "custom" and not requested_base_url:
        raise ValueError("Enter a base URL for the custom LLM endpoint.")
    core.LLM_BASE_URL = requested_base_url
    core.LLM_API_KEY = os.environ.get("SUGAR_LLM_API_KEY", "")
    if (config.get("translate_posts") or config.get("infer_locations")
            or config.get("translate_term_languages")) and not core.LLM_API_KEY:
        raise ValueError("An LLM API key is required for translation or location inference.")


def translated_terms(config: dict) -> list[str]:
    terms = [str(term).strip() for term in config.get("terms", []) if str(term).strip()]
    languages = config.get("translate_term_languages", [])
    if not languages:
        return terms
    client = core.create_llm_client()
    result = list(terms)
    seen = {term.casefold() for term in result}
    for term in terms:
        for language in languages:
            value = core.translate_search_term(client, term, language, core.LLM_MODEL)
            if value and value.casefold() not in seen:
                result.append(value)
                seen.add(value.casefold())
    return result


def run_search(config: dict):
    configure_llm(config)
    output_dir = Path(config.get("output_directory") or Path.home() / "Documents" / "SUGAR")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = output_dir / f"social_search_posts_{timestamp}.csv"
    core.GEOCODE_CACHE_FILE = str(output_dir / "geocode_cache.json")
    core.LLM_MODEL = config.get("llm", {}).get("model", "gpt-5.6-luna")
    core.INFER_LOCATIONS = bool(config.get("infer_locations", True))
    core.CREATE_MAP = False
    terms = translated_terms(config)
    if not terms:
        raise ValueError("Enter at least one search term.")
    sources = config.get("sources", ["x"])
    records = []
    common = dict(
        since=config.get("since") or None,
        until=config.get("until") or None,
        max_posts_per_query=int(config.get("max_posts_per_query", 10)),
        max_pages_per_query=int(config.get("max_pages_per_query", 1)),
        search_terms=terms,
        target_language=config.get("target_language", "English"),
        openai_model=core.LLM_MODEL,
        translate=bool(config.get("translate_posts", True)),
    )
    if "x" in sources:
        token = os.environ.get("SUGAR_X_BEARER_TOKEN", "")
        if not token:
            raise ValueError("An X bearer token is required for X searches.")
        records.extend(core.run_x_api_collection(
            bearer_token=token,
            search_mode=config.get("x_search_mode", "recent"),
            output_file=str(output_csv),
            handles=None,
            post_languages=config.get("post_languages", []),
            include_retweets=bool(config.get("include_retweets", False)),
            **common,
        ))
    if "bluesky" in sources:
        jwt = ""
        identifier = os.environ.get("SUGAR_BLUESKY_IDENTIFIER", "")
        password = os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", "")
        if identifier and password:
            jwt = core.create_bluesky_access_token(
                core.create_requests_session(), identifier, password
            )
        records.extend(core.run_bluesky_collection(access_jwt=jwt, **common))
    if "mastodon" in sources:
        records.extend(core.run_mastodon_collection(
            instance_url=config.get("mastodon_url", "https://mastodon.social"),
            access_token=os.environ.get("SUGAR_MASTODON_TOKEN", ""),
            include_reblogs=bool(config.get("include_retweets", False)),
            **common,
        ))
    frame = core.save_records(records, str(output_csv))
    if frame is None:
        raise RuntimeError("No posts were collected.")
    emit("complete", outputs=[str(output_csv), str(output_csv.with_suffix(".xlsx"))])


def run_map(config: dict):
    source = Path(config["source_file"])
    frame = pd.read_excel(source, sheet_name="posts") if source.suffix.lower() == ".xlsx" else pd.read_csv(source)
    output = Path(config.get("output_file") or source.with_name(source.stem + "_map.html"))
    core.create_tweet_map(frame, str(output))
    emit("complete", outputs=[str(output)])


def run_analysis(config: dict):
    outputs = create_analysis_report(
        source_file=config["source_file"],
        output_stem=config["output_stem"],
        output_format=config.get("output_format", "both"),
    )
    emit("complete", outputs=outputs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["search", "map", "analysis"])
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        {"search": run_search, "map": run_map, "analysis": run_analysis}[args.command](config)
    except Exception as exc:
        emit("error", message=str(exc))
        raise


if __name__ == "__main__":
    main()
