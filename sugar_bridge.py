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
from sugar_core.llm import ARC_BASE_URL, LLMConfig, create_client
from sugar_core.service import run_analysis, run_harvest, run_ingest, run_map, run_overlap, run_search
from sugar_core.research_workspace import ResearchWorkspaceManager
from sugar_core.research_workspace_ops import RESEARCH_WORKSPACE_OPERATIONS, run_research_workspace_operation
from sugar_core.research_service import (
    apply_research_feedback,
    collect_research_plan,
    compile_research_strategy,
    create_research_plan,
    create_research_requirement,
    export_research_handoff,
    import_research_dataset,
    prepare_manual_review,
    review_research_plan,
    review_research_strategy,
    triage_research_records,
    update_research_plan_branch,
    update_research_strategy,
    verify_research_handoff,
)
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
_ACTIVE_SECRET_VALUES: set[str] = set()
WORKSPACE_OPERATIONS = {"workspace-init", "workspace-status", "workspace-register"}
BASE_OPERATIONS = {
    "search",
    "ingest",
    "research-requirement",
    "research-compile",
    "research-strategy-review",
    "research-strategy-update",
    "research-plan",
    "research-plan-review",
    "research-plan-update",
    "research-import",
    "research-prepare-review",
    "research-collect",
    "research-triage",
    "research-feedback",
    "research-handoff",
    "research-handoff-verify",
    "harvest",
    "weibo-investigate",
    "weibo-seed-harvest",
    "weibo-qualify",
    "map",
    "overlap",
    "analysis",
    "diagnostics",
    "llm-check",
} | WORKSPACE_OPERATIONS
ALL_OPERATIONS = BASE_OPERATIONS | DESKTOP_ANALYTIC_OPERATIONS | RESEARCH_WORKSPACE_OPERATIONS


def _redact_runtime_secrets(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for secret in sorted(_ACTIVE_SECRET_VALUES, key=len, reverse=True):
            if len(secret) >= 8:
                result = result.replace(secret, "[REDACTED]")
        return result
    if isinstance(value, dict):
        return {key: _redact_runtime_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_runtime_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_runtime_secrets(item) for item in value]
    return value


def emit(event: str, **values: Any) -> None:
    payload = _redact_runtime_secrets({"event": event, **values})
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("Desktop bridge configuration must be a JSON object.")
    return payload


def secrets_from_environment() -> dict[str, str]:
    secrets = {
        "x_bearer_token": os.environ.get("SUGAR_X_BEARER_TOKEN", ""),
        "llm_api_key": os.environ.get("SUGAR_LLM_API_KEY", ""),
        "bluesky_identifier": os.environ.get("SUGAR_BLUESKY_IDENTIFIER", ""),
        "bluesky_app_password": os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", ""),
        "mastodon_token": os.environ.get("SUGAR_MASTODON_TOKEN", ""),
        "weibo_cookie": os.environ.get("SUGAR_WEIBO_COOKIE", ""),
    }
    _ACTIVE_SECRET_VALUES.clear()
    _ACTIVE_SECRET_VALUES.update(
        str(value) for value in secrets.values() if str(value)
    )
    return secrets


def backend_info() -> dict[str, Any]:
    optional_credentials = {
        "llm_api_key": bool(os.environ.get("SUGAR_LLM_API_KEY", "").strip()),
        "x_bearer_token": bool(os.environ.get("SUGAR_X_BEARER_TOKEN", "").strip()),
        "bluesky_identifier": bool(os.environ.get("SUGAR_BLUESKY_IDENTIFIER", "").strip()),
        "bluesky_app_password": bool(os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", "").strip()),
        "mastodon_token": bool(os.environ.get("SUGAR_MASTODON_TOKEN", "").strip()),
        "weibo_cookie": bool(os.environ.get("SUGAR_WEIBO_COOKIE", "").strip()),
    }
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
        "deployment": {
            "virginia_tech_required": False,
            "llm_required_for_core_workflows": False,
            "supported_llm_providers": ["openai", "custom", "arc"],
            "arc_role": "optional_classroom_development",
        },
        "optional_credentials": optional_credentials,
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


def _run_llm_check(config: dict[str, Any], secrets: dict[str, str]) -> list[str]:
    raw = config.get("llm") or {}
    if not isinstance(raw, dict):
        raise ValueError("llm configuration must be an object.")
    provider = str(raw.get("provider") or "openai").strip()
    model = str(raw.get("model") or "gpt-5.6-luna").strip()
    base_url = str(raw.get("base_url") or "").strip()
    llm_config = LLMConfig(
        provider=provider,
        model=model,
        api_key=secrets.get("llm_api_key", ""),
        base_url=base_url,
    )
    client = create_client(llm_config)
    response = client.models.list()
    model_ids = sorted(
        str(getattr(item, "id", "")).strip()
        for item in getattr(response, "data", [])
        if str(getattr(item, "id", "")).strip()
    )
    endpoint = base_url or (ARC_BASE_URL if provider == "arc" else "provider default")
    emit(
        "llm_connection",
        provider=provider,
        endpoint=endpoint,
        model=model,
        selected_model_available=(not model_ids or model in model_ids),
        available_model_count=len(model_ids),
        available_models=model_ids,
    )
    return []


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
        research = ResearchWorkspaceManager(workspace)
        emit("workspace_research_status", **research.status())
        return [str(workspace.manifest_path), str(workspace.database_path), str(research.state_path)]

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
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"cli", "project", "state", "intel"}:
        mode = argv.pop(0)
        if mode == "cli":
            from sugar_core.cli import main as command_main
        elif mode == "project":
            from sugar_core.workspace_cli import main as command_main
        elif mode == "state":
            from sugar_core.state_cli import main as command_main
        else:
            from sugar_core.state_intel_cli import main as command_main
        return int(command_main(argv) or 0)

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
        if args.command == "llm-check":
            outputs = _run_llm_check(config, secrets)
        elif args.command in RESEARCH_WORKSPACE_OPERATIONS:
            outputs = run_research_workspace_operation(
                args.command,
                config,
                secrets,
                progress=progress_event,
            )
        elif args.command in WORKSPACE_OPERATIONS:
            outputs = _run_workspace_operation(args.command, config)
        elif args.command == "search":
            outputs = run_search(config, secrets, progress=progress_event)
        elif args.command == "ingest":
            outputs = run_ingest(config, secrets, progress=progress_event)
        elif args.command == "research-requirement":
            outputs = create_research_requirement(config, progress=progress_event)
        elif args.command == "research-compile":
            outputs = compile_research_strategy(config, secrets, progress=progress_event)
        elif args.command == "research-strategy-review":
            outputs = review_research_strategy(config, progress=progress_event)
        elif args.command == "research-strategy-update":
            outputs = update_research_strategy(config, progress=progress_event)
        elif args.command == "research-plan":
            outputs = create_research_plan(config, secrets, progress=progress_event)
        elif args.command == "research-plan-review":
            outputs = review_research_plan(config, progress=progress_event)
        elif args.command == "research-plan-update":
            outputs = update_research_plan_branch(config, progress=progress_event)
        elif args.command == "research-import":
            outputs = import_research_dataset(config, progress=progress_event)
        elif args.command == "research-prepare-review":
            outputs = prepare_manual_review(config, progress=progress_event)
        elif args.command == "research-collect":
            outputs = collect_research_plan(config, secrets, progress=progress_event)
        elif args.command == "research-triage":
            outputs = triage_research_records(config, secrets, progress=progress_event)
        elif args.command == "research-feedback":
            outputs = apply_research_feedback(config, progress=progress_event)
        elif args.command == "research-handoff":
            outputs = export_research_handoff(config, progress=progress_event)
        elif args.command == "research-handoff-verify":
            outputs = verify_research_handoff(config, progress=progress_event)
        elif args.command == "harvest":
            emit("starting", operation="harvest")
            outputs = run_harvest(config, secrets, progress=progress_event)
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
