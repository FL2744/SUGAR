#!/usr/bin/env python3
"""JSON command bridge used by the native SUGAR macOS application."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from typing import Any

# Frozen executables also need explicit flushing when connected to the UI pipe.
for stream in (sys.stdout, sys.stderr):
    if stream is not None:
        stream.reconfigure(line_buffering=True, write_through=True)

import sugar_core
from sugar_core.collector_registry import collector_capabilities
from sugar_core.service import run_analysis, run_harvest, run_map, run_search
from sugar_core.weibo_investigation import investigate_weibo_seed, save_weibo_investigation
from sugar_core.weibo_qualification import run_weibo_qualification


def emit(event: str, **values) -> None:
    print(json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def secrets_from_environment() -> dict[str, str]:
    return {
        "x_bearer_token": os.environ.get("SUGAR_X_BEARER_TOKEN", ""),
        "llm_api_key": os.environ.get("SUGAR_LLM_API_KEY", ""),
        "bluesky_identifier": os.environ.get("SUGAR_BLUESKY_IDENTIFIER", ""),
        "bluesky_app_password": os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", ""),
        "mastodon_token": os.environ.get("SUGAR_MASTODON_TOKEN", ""),
        # Optional only. SUGAR never generates or harvests a Weibo session cookie.
        "weibo_cookie": os.environ.get("SUGAR_WEIBO_COOKIE", ""),
    }


def backend_info() -> dict[str, Any]:
    return {
        "version": sugar_core.__version__,
        "architecture": platform.machine() or "unknown",
        "python": platform.python_version(),
        "runtime": "bundled" if getattr(sys, "frozen", False) else "python",
        "system": platform.platform(),
        "collectors": collector_capabilities(),
        "operations": [
            "search",
            "harvest",
            "weibo-investigate",
            "weibo-qualify",
            "map",
            "analysis",
            "diagnostics",
        ],
    }


def progress_event(event: str, values: dict) -> None:
    emit(event, **values)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["search", "harvest", "weibo-investigate", "weibo-qualify", "map", "analysis", "diagnostics"],
    )
    parser.add_argument("--config")
    args = parser.parse_args(argv)

    if args.command == "diagnostics":
        emit("diagnostics", **backend_info())
        return 0
    if not args.config:
        parser.error("--config is required for search, harvest, weibo-investigate, weibo-qualify, map, and analysis")

    try:
        emit("backend", **backend_info())
        config = load_config(args.config)
        if args.command == "search":
            outputs = run_search(config, secrets_from_environment(), progress=progress_event)
        elif args.command == "harvest":
            emit("starting", operation="harvest")
            outputs = run_harvest(config, secrets_from_environment(), progress=progress_event)
        elif args.command == "weibo-investigate":
            emit("starting", operation="weibo-investigate")
            secrets = secrets_from_environment()
            result = investigate_weibo_seed(
                config["seed"],
                max_comments=int(config.get("max_comments", 100)),
                comment_pages=int(config.get("comment_pages", 5)),
                max_reposts=int(config.get("max_reposts", 100)),
                repost_pages=int(config.get("repost_pages", 5)),
                author_posts=int(config.get("author_posts", 40)),
                author_pages=int(config.get("author_pages", 2)),
                cookie=secrets.get("weibo_cookie", ""),
            )
            outputs = save_weibo_investigation(
                result,
                config.get("output_directory") or ".",
                name=str(config.get("name") or "weibo_investigation"),
            )
            emit(
                "weibo_investigation",
                seed_record_key=result.seed.record_key,
                comments=len(result.comments),
                reposts=len(result.reposts),
                author_posts=len(result.author_posts),
                surface_status=result.surface_status,
            )
        elif args.command == "weibo-qualify":
            emit("starting", operation="weibo-qualify")
            outputs = run_weibo_qualification(
                config,
                secrets_from_environment(),
                progress=progress_event,
            )
        elif args.command == "map":
            emit("starting", operation="map")
            emit("mapping", source_file=str(config.get("source_file", "")))
            outputs = run_map(config)
        else:
            emit("starting", operation="analysis")
            emit("analyzing", source_file=str(config.get("source_file", "")))
            outputs = run_analysis(config)
        emit("complete", outputs=outputs)
        return 0
    except Exception as exc:
        emit("error", message=str(exc), exception=type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())