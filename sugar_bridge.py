#!/usr/bin/env python3
"""Line-delimited JSON command bridge shared by the SUGAR desktop frontends."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from dataclasses import asdict
from typing import Any

for stream in (sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(line_buffering=True, write_through=True)

import sugar_core
from sugar_core.collector_registry import collector_capabilities
from sugar_core.desktop_ops import DESKTOP_ANALYTIC_OPERATIONS, run_desktop_analytic_operation
from sugar_core.public_import import run_public_import
from sugar_core.service import run_analysis, run_harvest, run_map, run_overlap, run_search
from sugar_core.weibo_investigation import investigate_weibo_seed, save_weibo_investigation
from sugar_core.weibo_qualification import run_weibo_qualification
from sugar_core.weibo_seed_harvest import SeedHarvestConfig, run_weibo_seed_harvest
from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_runtime import (
    choose_output_directory,
    register_workspace_outputs,
    workspace_from_config,
)

BRIDGE_PROTOCOL_VERSION = 3
WORKSPACE_OPERATIONS = {"workspace-init", "workspace-status", "workspace-register"}
BASE_OPERATIONS = {
    "search",
    "harvest",
    "import-public",
    "weibo-investigate",
    "weibo-seed-harvest",
    "weibo-qualify",
    "map",
    "overlap",
    "analysis",
    "diagnostics",
} | WORKSPACE_OPERATIONS
ALL_OPERATIONS = BASE_OPERATIONS | DESKTOP_ANALYTIC_OPERATIONS


def emit(event: str, **values: Any) -> None:
    print(json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("Desktop bridge configuration must be a JSON object.")
    return payload


def secrets_from_environment() -> dict[str, str]:
    return {
        "x_bearer_token": os.environ.get("SUGAR_X_BEARER_TOKEN", ""),
        "llm_api_key": os.environ.get("SUGAR_LLM_API_KEY", ""),
        "bluesky_identifier": os.environ.get("SUGAR_BLUESKY_IDENTIFIER", ""),
        "bluesky_app_password": os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", ""),
        "mastodon_token": os.environ.get("SUGAR_MASTODON_TOKEN", ""),
        "weibo_cookie": os.environ.get("SUGAR_WEIBO_COOKIE", ""),
        "zhihu_access_secret": os.environ.get("SUGAR_ZHIHU_ACCESS_SECRET", ""),
    }


def backend_info() -> dict[str, Any]:
    return {
        "version": sugar_core.__version__,
        "bridge_protocol": BRIDGE_PROTOCOL_VERSION,
        "architecture": platform.machine() or "unknown",
        "python": platform.python_version(),
        "runtime": "bundled" if getattr(sys, "frozen", False) else "python",
        "system": platform.platform(),
        "os": platform.system().lower(),
        "collectors": collector_capabilities(),
        "operations": sorted(ALL_OPERATIONS),
    }


def progress_event(event: str, values: dict[str, Any]) -> None:
    emit(event, **values)


def _run_weibo_investigation(config: dict[str, Any], secrets: dict[str, str]) -> list[str]:
    emit("starting", operation="weibo-investigate")
    workspace = workspace_from_config(config)
    out_dir = choose_output_directory(config.get("output_directory"), workspace, "raw")
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
        out_dir,
        name=str(config.get("name") or "weibo_investigation"),
    )
    register_workspace_outputs(workspace, outputs, operation="weibo-investigate")
    emit(
        "weibo_investigation",
        seed_record_key=result.seed.record_key,
        comments=len(result.comments),
        reposts=len(result.reposts),
        author_posts=len(result.author_posts),
        surface_status=result.surface_status,
    )
    return outputs


def _workspace_path(config: dict[str, Any]) -> str:
    value = str(config.get("workspace") or config.get("path") or "").strip()
    if not value:
        raise ValueError("workspace is required.")
    return value


def _run_workspace_operation(command: str, config: dict[str, Any]) -> list[str]:
    if command == "workspace-init":
        workspace = SugarWorkspace.create(
            _workspace_path(config),
            name=str(config.get("name") or "").strip(),
            description=str(config.get("description") or "").strip(),
            exist_ok=bool(config.get("exist_ok", False)),
        )
        emit("workspace_status", **workspace.status())
        return [str(workspace.manifest_path), str(workspace.database_path)]

    workspace = SugarWorkspace.open(_workspace_path(config))
    if command == "workspace-status":
        emit("workspace_status", **workspace.status())
        return [str(workspace.manifest_path)]

    artifact_path = str(config.get("artifact") or config.get("artifact_path") or "").strip()
    if not artifact_path:
        raise ValueError("artifact is required.")
    metadata = config.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("workspace artifact metadata must be a JSON object.")
    artifact = workspace.register_artifact(
        str(config.get("kind") or ""),
        artifact_path,
        label=str(config.get("label") or ""),
        metadata=metadata,
        require_exists=not bool(config.get("allow_missing", False)),
    )
    payload = asdict(artifact)
    payload["absolute_path"] = str(workspace.artifact_absolute_path(artifact))
    emit("workspace_artifact", artifact=payload)
    return [payload["absolute_path"]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=sorted(ALL_OPERATIONS))
    parser.add_argument("--config")
    args = parser.parse_args(argv)

    if args.command == "diagnostics":
        emit("diagnostics", **backend_info())
        return 0
    if not args.config:
        parser.error(f"--config is required for {args.command}")

    try:
        emit("backend", **backend_info())
        config = load_config(args.config)
        secrets = secrets_from_environment()
        if args.command in WORKSPACE_OPERATIONS:
            outputs = _run_workspace_operation(args.command, config)
        elif args.command == "search":
            outputs = run_search(config, secrets, progress=progress_event)
        elif args.command == "harvest":
            emit("starting", operation="harvest")
            outputs = run_harvest(config, secrets, progress=progress_event)
        elif args.command == "import-public":
            outputs = run_public_import(config, secrets, progress=progress_event)
        elif args.command == "weibo-investigate":
            outputs = _run_weibo_investigation(config, secrets)
        elif args.command == "weibo-seed-harvest":
            emit("starting", operation="weibo-seed-harvest")
            workspace = workspace_from_config(config)
            raw = config.get("seed_harvest") or config
            out_dir = choose_output_directory(
                config.get("output_directory") or raw.get("output_directory"),
                workspace,
                "raw",
            )
            harvest_config = SeedHarvestConfig(
                seeds=tuple(raw.get("seeds") or []),
                name=str(raw.get("name") or "weibo_seed_harvest"),
                max_comments=int(raw.get("max_comments", 20)),
                comment_pages=int(raw.get("comment_pages", 1)),
                max_reposts=int(raw.get("max_reposts", 0)),
                repost_pages=int(raw.get("repost_pages", 1)),
                author_posts=int(raw.get("author_posts", 0)),
                author_pages=int(raw.get("author_pages", 1)),
                max_retries=int(raw.get("max_retries", 2)),
                base_backoff_seconds=float(raw.get("base_backoff_seconds", 5.0)),
                max_inline_wait_seconds=float(raw.get("max_inline_wait_seconds", 120.0)),
                inter_seed_delay_seconds=float(raw.get("inter_seed_delay_seconds", 1.0)),
                continue_on_error=bool(raw.get("continue_on_error", True)),
            )
            outputs = run_weibo_seed_harvest(
                harvest_config,
                out_dir,
                cookie=secrets.get("weibo_cookie", ""),
                progress=progress_event,
            )
            register_workspace_outputs(workspace, outputs, operation="weibo-seed-harvest", kind="harvest")
        elif args.command == "weibo-qualify":
            emit("starting", operation="weibo-qualify")
            workspace = workspace_from_config(config)
            effective = dict(config)
            effective["output_directory"] = str(
                choose_output_directory(config.get("output_directory"), workspace, "raw")
            )
            outputs = run_weibo_qualification(effective, secrets, progress=progress_event)
            register_workspace_outputs(workspace, outputs, operation="weibo-qualify")
        elif args.command == "map":
            emit("starting", operation="map")
            emit("mapping", source_file=str(config.get("source_file", "")))
            outputs = run_map(config)
        elif args.command == "overlap":
            emit("starting", operation="spatial_overlap")
            outputs = run_overlap(config, progress=progress_event)
        elif args.command == "analysis":
            emit("starting", operation="analysis")
            emit("analyzing", source_file=str(config.get("source_file", "")))
            outputs = run_analysis(config)
        else:
            outputs = run_desktop_analytic_operation(
                args.command,
                config,
                secrets,
                progress=progress_event,
            )
        emit("complete", outputs=outputs)
        return 0
    except Exception as exc:
        emit("error", message=str(exc), exception=type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
