#!/usr/bin/env python3
"""JSON command bridge used by the native SUGAR macOS application."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys

import sugar_core
from sugar_core.service import run_analysis, run_map, run_search


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
    }


def backend_info() -> dict[str, str]:
    return {
        "version": sugar_core.__version__,
        "architecture": platform.machine() or "unknown",
        "python": platform.python_version(),
        "runtime": "bundled" if getattr(sys, "frozen", False) else "python",
        "system": platform.platform(),
    }


def progress_event(event: str, values: dict) -> None:
    emit(event, **values)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["search", "map", "analysis", "diagnostics"])
    parser.add_argument("--config")
    args = parser.parse_args(argv)

    if args.command == "diagnostics":
        emit("diagnostics", **backend_info())
        return 0
    if not args.config:
        parser.error("--config is required for search, map, and analysis")

    try:
        emit("backend", **backend_info())
        config = load_config(args.config)
        if args.command == "search":
            outputs = run_search(config, secrets_from_environment(), progress=progress_event)
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
