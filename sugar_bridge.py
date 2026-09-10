#!/usr/bin/env python3
"""JSON command bridge used by the native SUGAR macOS application."""
from __future__ import annotations

import argparse
import json
import os

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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["search", "map", "analysis"])
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "search":
            outputs = run_search(config, secrets_from_environment())
        elif args.command == "map":
            outputs = run_map(config)
        else:
            outputs = run_analysis(config)
        emit("complete", outputs=outputs)
        return 0
    except Exception as exc:
        emit("error", message=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
