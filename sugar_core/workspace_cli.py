from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from typing import Any

from . import __version__
from .research_workspace import (
    ResearchWorkspaceManager,
    import_project_bundle,
    user_support_payload,
)
from .workspace import SugarWorkspace


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise argparse.ArgumentTypeError("value must be a JSON object.")
    return payload


def _list_value(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace("|", ",").replace(";", ",").split(",") if item.strip()]


def _artifact_payload(workspace: SugarWorkspace, artifact) -> dict[str, Any]:
    payload = asdict(artifact)
    payload["absolute_path"] = str(workspace.artifact_absolute_path(artifact))
    return payload


def _runtime_secrets() -> dict[str, str]:
    return {
        "x_bearer_token": os.environ.get("SUGAR_X_BEARER_TOKEN", ""),
        "llm_api_key": os.environ.get("SUGAR_LLM_API_KEY", ""),
        "bluesky_identifier": os.environ.get("SUGAR_BLUESKY_IDENTIFIER", ""),
        "bluesky_app_password": os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", ""),
        "mastodon_token": os.environ.get("SUGAR_MASTODON_TOKEN", ""),
        "weibo_cookie": os.environ.get("SUGAR_WEIBO_COOKIE", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sugar-project",
        description="Create, organize, monitor, share, and inspect persistent SUGAR research workspaces.",
    )
    parser.add_argument("--version", action="version", version=f"sugar-project {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a new SUGAR project workspace.")
    init.add_argument("path")
    init.add_argument("--name", required=True)
    init.add_argument("--description", default="")
    init.add_argument("--exist-ok", action="store_true")

    status = sub.add_parser("status", help="Show workspace identity, layout, artifact health, and research-memory counts.")
    status.add_argument("path", nargs="?", default=".")
    status.add_argument("--discover", action="store_true")
    status.add_argument("--json", action="store_true", dest="as_json")

    register = sub.add_parser("register", help="Register or refresh a workspace artifact.")
    register.add_argument("workspace")
    register.add_argument("kind")
    register.add_argument("artifact")
    register.add_argument("--label", default="")
    register.add_argument("--metadata", type=_json_object, default={})
    register.add_argument("--allow-missing", action="store_true")

    list_p = sub.add_parser("list", help="List registered project artifacts.")
    list_p.add_argument("workspace")
    list_p.add_argument("--kind")
    list_p.add_argument("--json", action="store_true", dest="as_json")

    catalog = sub.add_parser("catalog", help="Show the portable artifact catalog used to rebuild local workspace state.")
    catalog.add_argument("workspace")
    catalog.add_argument("--json", action="store_true", dest="as_json")

    path_p = sub.add_parser("path", help="Print a canonical workspace directory.")
    path_p.add_argument("workspace")
    path_p.add_argument("key")

    research_status = sub.add_parser("research-status", help="Show subprojects, entities, layers, listening posts, and recent history.")
    research_status.add_argument("workspace")
    research_status.add_argument("--json", action="store_true", dest="as_json")

    subproject = sub.add_parser("subproject-add", help="Add a nested research track.")
    subproject.add_argument("workspace")
    subproject.add_argument("name")
    subproject.add_argument("--description", default="")
    subproject.add_argument("--parent-id", default="")
    subproject.add_argument("--status", default="active")
    subproject.add_argument("--tags", type=_list_value, default=[])

    collaborator = sub.add_parser("collaborator-add", help="Record a project collaborator/reviewer role.")
    collaborator.add_argument("workspace")
    collaborator.add_argument("name")
    collaborator.add_argument("--email", default="")
    collaborator.add_argument("--role", default="viewer", choices=["owner", "editor", "reviewer", "viewer"])

    institutions = sub.add_parser("institutions-import", help="Import a lifecycle-aware institution registry from CSV/JSONL/GeoJSON/XLSX.")
    institutions.add_argument("workspace")
    institutions.add_argument("input_file")
    institutions.add_argument("--subproject-id", default="")
    institutions.add_argument("--keep-existing", action="store_true")

    layer = sub.add_parser("layer-add", help="Add a portable reference/map layer.")
    layer.add_argument("workspace")
    layer.add_argument("input_file")
    layer.add_argument("--name", default="")
    layer.add_argument("--subproject-id", default="")
    layer.add_argument("--kind", default="reference")
    layer.add_argument("--hidden", action="store_true")
    layer.add_argument("--external", action="store_true", help="Reference the original file instead of copying it into the project.")

    listening = sub.add_parser("listening-add", help="Create a saved listening post.")
    listening.add_argument("workspace")
    listening.add_argument("name")
    listening.add_argument("--subproject-id", default="")
    listening.add_argument("--entity-ids", type=_list_value, default=[])
    listening.add_argument("--handles", type=_list_value, default=[])
    listening.add_argument("--terms", type=_list_value, default=[])
    listening.add_argument("--sources", type=_list_value, default=["bilibili"])
    listening.add_argument("--cadence", default="manual", choices=["manual", "hourly", "daily", "weekly", "monthly"])
    listening.add_argument("--disabled", action="store_true")

    listen_run = sub.add_parser("listening-run", help="Run a saved listening post through the normal collection pipeline.")
    listen_run.add_argument("workspace")
    listen_run.add_argument("listening_post_id")
    listen_run.add_argument("--since", default="")
    listen_run.add_argument("--until", default="")
    listen_run.add_argument("--max-posts-per-query", type=int, default=20)
    listen_run.add_argument("--max-pages-per-query", type=int, default=1)

    history = sub.add_parser("history", help="Search saved project search history.")
    history.add_argument("workspace")
    history.add_argument("--query", default="")
    history.add_argument("--subproject-id", default="")
    history.add_argument("--json", action="store_true", dest="as_json")

    map_p = sub.add_parser("map", help="Build the project reference/institution map with toggleable layers.")
    map_p.add_argument("workspace")
    map_p.add_argument("--output-file", default="")
    map_p.add_argument("--subproject-id", default="")
    map_p.add_argument("--exclude-closed", action="store_true")

    conversations = sub.add_parser("conversations", help="Build a speaker-separated thread/dialogue view from a SUGAR dataset.")
    conversations.add_argument("workspace")
    conversations.add_argument("records")
    conversations.add_argument("--output-file", default="")
    conversations.add_argument("--subproject-id", default="")

    share = sub.add_parser("share", help="Export a portable integrity-hashed .sugarproject.zip.")
    share.add_argument("workspace")
    share.add_argument("--output-file", default="")

    share_import = sub.add_parser("share-import", help="Import and verify a portable SUGAR project bundle.")
    share_import.add_argument("bundle")
    share_import.add_argument("destination")
    share_import.add_argument("--overwrite", action="store_true")

    sub.add_parser("help-workflows", help="Print concise end-user guidance for projects, monitoring, mapping, sharing, and conversations.")
    return parser


def _open(path: str, *, discover: bool = False) -> SugarWorkspace:
    return SugarWorkspace.discover(path) if discover else SugarWorkspace.open(path)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        workspace = SugarWorkspace.create(
            args.path,
            name=args.name,
            description=args.description,
            exist_ok=args.exist_ok,
        )
        ResearchWorkspaceManager(workspace)
        print(workspace.manifest_path)
        return 0

    if args.command == "status":
        workspace = _open(args.path, discover=args.discover)
        payload = workspace.status()
        payload["research"] = ResearchWorkspaceManager(workspace).status()
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        print(f"{payload['name']}  [{payload['project_id']}]")
        print(f"Root: {payload['root']}")
        print(f"Artifacts: {payload['artifact_count']} ({payload['missing_artifacts']} missing)")
        research = payload["research"]
        print(
            "Research: "
            f"{research['subprojects']} subprojects · {research['entities']} entities "
            f"({research['closed_entities']} closed) · {research['reference_layers']} layers · "
            f"{research['listening_posts']} listening posts · {research['history_events']} history events"
        )
        for kind, count in payload["artifact_counts"].items():
            print(f"  {kind}: {count}")
        print("Paths:")
        for key, value in payload["layout"].items():
            print(f"  {key}: {value}")
        return 0

    if args.command == "register":
        workspace = SugarWorkspace.open(args.workspace)
        artifact = workspace.register_artifact(
            args.kind,
            args.artifact,
            label=args.label,
            metadata=args.metadata,
            require_exists=not args.allow_missing,
        )
        print(json.dumps(_artifact_payload(workspace, artifact), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "list":
        workspace = SugarWorkspace.open(args.workspace)
        artifacts = workspace.list_artifacts(args.kind)
        if args.as_json:
            print(
                json.dumps(
                    [_artifact_payload(workspace, artifact) for artifact in artifacts],
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        for artifact in artifacts:
            state = "ok" if artifact.exists else "missing"
            portable = "external" if artifact.external else "project"
            label = f" — {artifact.label}" if artifact.label else ""
            print(f"{artifact.kind}\t{artifact.path}\t{state}\t{portable}{label}")
        return 0

    if args.command == "catalog":
        workspace = SugarWorkspace.open(args.workspace)
        payload = workspace.export_catalog()
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(workspace.catalog_path)
        return 0

    if args.command == "path":
        workspace = SugarWorkspace.open(args.workspace)
        try:
            print(workspace.path_for(args.key))
        except KeyError as exc:
            parser.error(str(exc))
        return 0

    if args.command == "share-import":
        workspace = import_project_bundle(args.bundle, args.destination, overwrite=args.overwrite)
        print(workspace.manifest_path)
        return 0

    if args.command == "help-workflows":
        print(json.dumps(user_support_payload(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    manager = ResearchWorkspaceManager.open(args.workspace)

    if args.command == "research-status":
        payload = manager.status()
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(
                f"{payload['name']}: {payload['subprojects']} subprojects, {payload['entities']} entities, "
                f"{payload['reference_layers']} layers, {payload['listening_posts']} listening posts, "
                f"{payload['history_events']} history events"
            )
        return 0

    if args.command == "subproject-add":
        item = manager.add_subproject(
            args.name,
            description=args.description,
            parent_id=args.parent_id,
            status=args.status,
            tags=args.tags,
        )
        print(json.dumps(asdict(item), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "collaborator-add":
        item = manager.add_collaborator(args.name, email=args.email, role=args.role)
        print(json.dumps(asdict(item), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "institutions-import":
        result = manager.import_institutions(
            args.input_file,
            subproject_id=args.subproject_id,
            replace_existing=not args.keep_existing,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "layer-add":
        item = manager.add_reference_layer(
            args.input_file,
            name=args.name,
            subproject_id=args.subproject_id,
            kind=args.kind,
            visible=not args.hidden,
            copy_into_workspace=not args.external,
        )
        print(json.dumps(asdict(item), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "listening-add":
        item = manager.add_listening_post(
            args.name,
            subproject_id=args.subproject_id,
            entity_ids=args.entity_ids,
            handles=args.handles,
            query_terms=args.terms,
            sources=args.sources,
            cadence=args.cadence,
            enabled=not args.disabled,
        )
        print(json.dumps(asdict(item), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "listening-run":
        result = manager.run_listening_post(
            args.listening_post_id,
            secrets=_runtime_secrets(),
            overrides={
                "since": args.since,
                "until": args.until,
                "max_posts_per_query": args.max_posts_per_query,
                "max_pages_per_query": args.max_pages_per_query,
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "history":
        rows = manager.search_history(args.query, subproject_id=args.subproject_id)
        if args.as_json:
            print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for row in rows:
                terms = ", ".join(row.get("terms") or [])
                sources = ", ".join(row.get("sources") or [])
                print(f"{row.get('timestamp')}\t{sources}\t{terms}\t{row.get('result_count')}")
        return 0

    if args.command == "map":
        outputs = manager.create_map(
            args.output_file or None,
            subproject_id=args.subproject_id,
            include_closed=not args.exclude_closed,
        )
        print("\n".join(outputs))
        return 0

    if args.command == "conversations":
        outputs = manager.build_conversation_view(
            args.records,
            output_file=args.output_file or None,
            subproject_id=args.subproject_id,
        )
        print("\n".join(outputs))
        return 0

    if args.command == "share":
        print(manager.export_share_bundle(args.output_file or None))
        return 0

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
