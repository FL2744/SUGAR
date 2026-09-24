from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from typing import Any

from . import __version__
from .workspace import SugarWorkspace


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise argparse.ArgumentTypeError("--metadata must be a JSON object.")
    return payload


def _artifact_payload(workspace: SugarWorkspace, artifact) -> dict[str, Any]:
    payload = asdict(artifact)
    payload["absolute_path"] = str(workspace.artifact_absolute_path(artifact))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sugar-project",
        description="Create and inspect persistent SUGAR research workspaces.",
    )
    parser.add_argument("--version", action="version", version=f"sugar-project {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a new SUGAR project workspace.")
    init.add_argument("path")
    init.add_argument("--name", required=True)
    init.add_argument("--description", default="")
    init.add_argument("--exist-ok", action="store_true")

    status = sub.add_parser("status", help="Show workspace identity, layout, and artifact health.")
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

    pipeline = sub.add_parser("pipeline", help="Report derivation freshness and the required incremental rebuild order.")
    pipeline.add_argument("workspace")

    merge = sub.add_parser("merge", help="Merge evidence and provenance from separate analyst projects.")
    merge.add_argument("destination")
    merge.add_argument("sources", nargs="+", help="One or more source SUGAR workspace paths.")
    merge.add_argument("--name", default="Merged SUGAR Research")

    path_p = sub.add_parser("path", help="Print a canonical workspace directory.")
    path_p.add_argument("workspace")
    path_p.add_argument("key")

    projects = sub.add_parser("projects", help="Find SUGAR projects beneath a folder, including subprojects.")
    projects.add_argument("root")
    projects.add_argument("--json", action="store_true", dest="as_json")

    dashboard_p = sub.add_parser("dashboard", help="Show project status, child projects, artifacts, and recent activity.")
    dashboard_p.add_argument("workspace")

    history = sub.add_parser("history", help="Show the reproducible project run and change history.")
    history.add_argument("workspace")
    history.add_argument("--limit", type=int, default=200)

    child = sub.add_parser("subproject", help="Create a named research track inside a project.")
    child.add_argument("workspace")
    child.add_argument("name")
    child.add_argument("--description", default="")

    export = sub.add_parser("export-project", help="Create a portable, integrity-checked project bundle.")
    export.add_argument("workspace")
    export.add_argument("output", nargs="?")

    import_p = sub.add_parser("import-project", help="Import a portable project bundle into a new folder.")
    import_p.add_argument("bundle")
    import_p.add_argument("destination")

    registry = sub.add_parser("registry", help="Inspect, export, and import evidence-backed institution records.")
    registry.add_argument("workspace")
    registry.add_argument("--network", default="")
    registry.add_argument("--status", default="")
    registry.add_argument("--country", default="")
    registry.add_argument("--query", default="")
    registry.add_argument("--json", action="store_true", dest="as_json")

    registry_preview = sub.add_parser("registry-preview", help="Preview a reference dataset, suggested mappings, and invalid rows.")
    registry_preview.add_argument("source")

    registry_import = sub.add_parser("registry-import", help="Preview and import a mapped CSV/XLSX/GeoJSON reference dataset.")
    registry_import.add_argument("workspace")
    registry_import.add_argument("source")
    registry_import.add_argument("--mapping", required=True, type=_json_object, help='JSON object, e.g. {"name":"Institution","status":"Status"}')
    registry_import.add_argument("--dataset-name", default="")
    registry_import.add_argument("--network", default="")
    registry_import.add_argument("--geographic-scope", default="")
    registry_import.add_argument("--coverage-limits", default="")
    registry_import.add_argument("--license-notes", default="")
    registry_import.add_argument("--accept-partial", action="store_true")

    registry_export = sub.add_parser("registry-export", help="Export canonical registry records to CSV, JSONL, or GeoJSON.")
    registry_export.add_argument("workspace")
    registry_export.add_argument("output")
    registry_export.add_argument("--format", default="")

    template = sub.add_parser("reference-template", help="Create a blank source-backed institution/service registry schema.")
    template.add_argument("workspace")
    template.add_argument("template", choices=("american_spaces", "educationusa", "language_education_centers", "technical_training_workshops", "custom"))

    monitor_list = sub.add_parser("monitor-list", help="List saved listening posts.")
    monitor_list.add_argument("workspace")
    monitor_list.add_argument("--json", action="store_true", dest="as_json")

    monitor_add = sub.add_parser("monitor-add", help="Save a persistent query-driven listening post.")
    monitor_add.add_argument("workspace")
    monitor_add.add_argument("name")
    monitor_add.add_argument("--terms", default="")
    monitor_add.add_argument("--targets", default="")
    monitor_add.add_argument("--sources", default="bilibili")
    monitor_add.add_argument("--cadence-minutes", type=int, default=1440)
    monitor_add.add_argument("--geographies", default="")

    monitor_feed = sub.add_parser("monitor-feed", help="Show incoming evidence and its analyst review state.")
    monitor_feed.add_argument("workspace")
    monitor_feed.add_argument("--monitor-id", default="")
    monitor_feed.add_argument("--review-state", default="")

    monitor_review = sub.add_parser("monitor-review", help="Record an analyst decision on incoming monitoring evidence.")
    monitor_review.add_argument("workspace")
    monitor_review.add_argument("material_id")
    monitor_review.add_argument("review_state", choices=("human_verified", "needs_followup", "rejected", "unreviewed"))
    monitor_review.add_argument("--actor", default="analyst")
    monitor_review.add_argument("--note", default="")

    monitor_due = sub.add_parser("monitor-run-due", help="Run active listening posts whose cadence is due; suitable for an OS scheduler.")
    monitor_due.add_argument("workspace")
    monitor_due.add_argument("--max-monitors", type=int, default=10)

    conversation = sub.add_parser("conversation-view", help="Reconstruct explicit reply, quote, mention, and actor links from a record file.")
    conversation.add_argument("source")
    conversation.add_argument("output")
    conversation.add_argument("--conversation-id", default="")

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
        print(workspace.manifest_path)
        return 0

    if args.command == "status":
        workspace = _open(args.path, discover=args.discover)
        payload = workspace.status()
        if args.as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        print(f"{payload['name']}  [{payload['project_id']}]")
        print(f"Root: {payload['root']}")
        print(f"Artifacts: {payload['artifact_count']} ({payload['missing_artifacts']} missing)")
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

    if args.command == "pipeline":
        from .workspace_pipeline import pipeline_report

        report = pipeline_report(SugarWorkspace.open(args.workspace))
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "merge":
        from .workspace_merge import merge_workspaces

        report = merge_workspaces(args.destination, args.sources, name=args.name)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "projects":
        from .workspace_memory import list_projects
        payload = list_projects(args.root)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.as_json else "\n".join(f"{row['name']}\t{row['root']}\t{row['project_id']}" for row in payload))
        return 0

    if args.command == "dashboard":
        from .workspace_memory import dashboard
        print(json.dumps(dashboard(SugarWorkspace.open(args.workspace)), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "history":
        from .workspace_memory import list_project_history
        print(json.dumps(list_project_history(SugarWorkspace.open(args.workspace), limit=args.limit), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "subproject":
        from .workspace_memory import create_subproject
        workspace = create_subproject(SugarWorkspace.open(args.workspace), args.name, description=args.description)
        print(json.dumps({"project_id": workspace.manifest.project_id, "name": workspace.manifest.name, "root": str(workspace.root)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-project":
        from .project_bundle import export_project_bundle
        workspace = SugarWorkspace.open(args.workspace)
        output = args.output or (workspace.path_for("exports") / f"{workspace.manifest.name.strip().replace(' ', '-')}.sugar.zip")
        print(json.dumps(export_project_bundle(workspace, output), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "import-project":
        from .project_bundle import import_project_bundle
        print(json.dumps(import_project_bundle(args.bundle, args.destination), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "registry":
        from .reference_registry import list_entities
        filters = {key: getattr(args, key) for key in ("network", "status", "country", "query") if getattr(args, key)}
        payload = list_entities(SugarWorkspace.open(args.workspace), filters=filters)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.as_json else "\n".join(f"{row['entity_id']}\t{row.get('status','unknown')}\t{row.get('network','')}\t{row.get('name','')}\t{row.get('city','')}, {row.get('country','')}" for row in payload))
        return 0

    if args.command == "registry-preview":
        from .reference_registry import preview_reference_import
        print(json.dumps(preview_reference_import(args.source), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "registry-import":
        from .reference_registry import import_reference_dataset, preview_reference_import
        preview = preview_reference_import(args.source)
        if preview["error_count"] and not args.accept_partial:
            parser.error(f"Preview found {preview['error_count']} invalid rows; inspect preview and pass --accept-partial only after review.")
        result = import_reference_dataset(SugarWorkspace.open(args.workspace), args.source, mapping=args.mapping,
            dataset_name=args.dataset_name, network=args.network, geographic_scope=args.geographic_scope,
            known_coverage_limits=args.coverage_limits, license_notes=args.license_notes,
            accept_partial=args.accept_partial)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "registry-export":
        from .reference_registry import export_registry
        print(export_registry(SugarWorkspace.open(args.workspace), args.output, format=args.format or None))
        return 0

    if args.command == "reference-template":
        from .reference_templates import write_reference_template
        print(json.dumps({"template": args.template,
                          "path": write_reference_template(SugarWorkspace.open(args.workspace), args.template),
                          "contains_institution_records": False}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "monitor-list":
        from .listening_posts import list_monitors
        payload = list_monitors(SugarWorkspace.open(args.workspace))
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.as_json else "\n".join(f"{row['monitor_id']}\t{row['status']}\t{row['cadence_minutes']} min\t{row['name']}\t{row['next_due_at']}" for row in payload))
        return 0

    if args.command == "monitor-add":
        from .listening_posts import save_monitor
        split = lambda value: [item.strip() for item in value.split(",") if item.strip()]
        payload = save_monitor(SugarWorkspace.open(args.workspace), name=args.name, terms=split(args.terms),
            target_entities=split(args.targets), sources=split(args.sources), cadence_minutes=args.cadence_minutes,
            geographies=split(args.geographies))
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "monitor-feed":
        from .listening_posts import list_monitor_material
        payload = list_monitor_material(SugarWorkspace.open(args.workspace), monitor_id=args.monitor_id, review_state=args.review_state)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "monitor-review":
        from .listening_posts import review_monitor_material
        payload = review_monitor_material(SugarWorkspace.open(args.workspace), args.material_id, args.review_state, actor=args.actor, note=args.note)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "monitor-run-due":
        from .desktop_ops import run_desktop_analytic_operation
        secrets = {
            "x_bearer_token": os.environ.get("SUGAR_X_BEARER_TOKEN", ""),
            "llm_api_key": os.environ.get("SUGAR_LLM_API_KEY", ""),
            "bluesky_identifier": os.environ.get("SUGAR_BLUESKY_IDENTIFIER", ""),
            "bluesky_app_password": os.environ.get("SUGAR_BLUESKY_APP_PASSWORD", ""),
            "mastodon_token": os.environ.get("SUGAR_MASTODON_TOKEN", ""),
            "weibo_cookie": os.environ.get("SUGAR_WEIBO_COOKIE", ""),
        }
        results: list[dict[str, Any]] = []
        run_desktop_analytic_operation("workspace-hub", {"workspace": args.workspace, "action": "monitor-run-due", "max_monitors": args.max_monitors}, secrets, progress=lambda event, payload: results.append({"event": event, **payload}))
        print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "conversation-view":
        from .conversations import save_conversation_view
        print(save_conversation_view(args.source, args.output, conversation_id=args.conversation_id))
        return 0

    workspace = SugarWorkspace.open(args.workspace)
    try:
        print(workspace.path_for(args.key))
    except KeyError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
