from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import __version__
from .workspace import SugarWorkspace
from .research_workspace import ListeningPost, ReferenceLayer, ResearchWorkspaceState, Subproject
from .workspace_share import export_project_share, import_project_share, verify_project_share


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

    path_p = sub.add_parser("path", help="Print a canonical workspace directory.")
    path_p.add_argument("workspace")
    path_p.add_argument("key")

    research = sub.add_parser("research-status", help="Show subprojects, history, listening posts, and reference layers.")
    research.add_argument("workspace")
    research.add_argument("--json", action="store_true", dest="as_json")

    subproject = sub.add_parser("subproject-add", help="Add a nested research subproject.")
    subproject.add_argument("workspace")
    subproject.add_argument("name")
    subproject.add_argument("--parent", default="")
    subproject.add_argument("--description", default="")
    subproject.add_argument("--tag", action="append", default=[])

    listening = sub.add_parser("listening-add", help="Create a persistent listening post.")
    listening.add_argument("workspace")
    listening.add_argument("name")
    listening.add_argument("--term", action="append", default=[])
    listening.add_argument("--source", action="append", default=[])
    listening.add_argument("--subproject", default="")
    listening.add_argument("--cadence", default="manual")

    layer = sub.add_parser("layer-add", help="Register a reusable reference layer.")
    layer.add_argument("workspace")
    layer.add_argument("source")
    layer.add_argument("--name", default="")
    layer.add_argument("--type", default="institution", dest="layer_type")
    layer.add_argument("--subproject", default="")

    share = sub.add_parser("share-export", help="Export the whole portable project as a verified ZIP.")
    share.add_argument("workspace")
    share.add_argument("output")
    share.add_argument("--include-external", action="store_true")

    verify_share = sub.add_parser("share-verify", help="Verify a SUGAR whole-project share ZIP.")
    verify_share.add_argument("share_file")

    import_share = sub.add_parser("share-import", help="Import a verified SUGAR whole-project share ZIP.")
    import_share.add_argument("share_file")
    import_share.add_argument("destination")

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

    if args.command == "research-status":
        workspace = SugarWorkspace.open(args.workspace)
        state = ResearchWorkspaceState.open(workspace.root, project_id=workspace.manifest.project_id)
        payload = {
            "dashboard": state.dashboard(),
            "subprojects": [asdict(item) for item in state.subprojects.values()],
            "search_history": [asdict(item) for item in state.search_history],
            "listening_posts": [asdict(item) for item in state.listening_posts.values()],
            "reference_layers": [asdict(item) for item in state.reference_layers.values()],
            "collaborators": [asdict(item) for item in state.collaborators.values()],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.as_json else state.path)
        return 0

    if args.command == "subproject-add":
        workspace = SugarWorkspace.open(args.workspace)
        state = ResearchWorkspaceState.open(workspace.root, project_id=workspace.manifest.project_id)
        item = state.add_subproject(
            Subproject(
                name=args.name,
                parent_subproject_id=args.parent,
                description=args.description,
                tags=args.tag,
            )
        )
        print(json.dumps(asdict(item), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "listening-add":
        workspace = SugarWorkspace.open(args.workspace)
        state = ResearchWorkspaceState.open(workspace.root, project_id=workspace.manifest.project_id)
        item = state.upsert_listening_post(
            ListeningPost(
                name=args.name,
                query_terms=args.term,
                sources=args.source,
                subproject_id=args.subproject,
                cadence=args.cadence,
            )
        )
        print(json.dumps(asdict(item), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "layer-add":
        workspace = SugarWorkspace.open(args.workspace)
        state = ResearchWorkspaceState.open(workspace.root, project_id=workspace.manifest.project_id)
        source = str(args.source)
        source_path = Path(source).expanduser().resolve()
        try:
            portable = source_path.relative_to(workspace.root).as_posix()
        except ValueError:
            portable = str(source_path)
        item = state.upsert_reference_layer(
            ReferenceLayer(
                name=args.name or source_path.stem,
                source=portable,
                layer_type=args.layer_type,
                subproject_id=args.subproject,
            )
        )
        workspace.register_artifact("reference", source_path, label=item.name)
        print(json.dumps(asdict(item), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "share-export":
        print(export_project_share(args.workspace, args.output, include_external_artifacts=args.include_external))
        return 0

    if args.command == "share-verify":
        payload = verify_project_share(args.share_file)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if payload.get("valid") else 1

    if args.command == "share-import":
        print(import_project_share(args.share_file, args.destination))
        return 0

    workspace = SugarWorkspace.open(args.workspace)
    try:
        print(workspace.path_for(args.key))
    except KeyError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
