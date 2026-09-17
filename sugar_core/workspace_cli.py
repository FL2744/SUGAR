from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Any

from . import __version__
from .errors import error_payload
from .workspace import SugarWorkspace
from .workspace_archive import create_workspace_archive, restore_workspace_archive


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
    parser.add_argument("--version", action="version", version=__version__)
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

    path_p = sub.add_parser("path", help="Print a canonical workspace directory.")
    path_p.add_argument("workspace")
    path_p.add_argument("key")

    archive = sub.add_parser("archive", help="Create a validated portable archive of project-contained files.")
    archive.add_argument("workspace")
    archive.add_argument("output")
    archive.add_argument("--discover", action="store_true")

    restore = sub.add_parser("restore", help="Validate and restore a portable workspace archive.")
    restore.add_argument("archive")
    restore.add_argument("output")

    return parser


def _open(path: str, *, discover: bool = False) -> SugarWorkspace:
    return SugarWorkspace.discover(path) if discover else SugarWorkspace.open(path)


def _run(argv=None) -> int:
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

    if args.command == "archive":
        workspace = _open(args.workspace, discover=args.discover)
        print(create_workspace_archive(workspace, args.output))
        return 0

    if args.command == "restore":
        workspace = restore_workspace_archive(args.archive, args.output)
        print(workspace.manifest_path)
        return 0

    workspace = SugarWorkspace.open(args.workspace)
    try:
        print(workspace.path_for(args.key))
    except KeyError as exc:
        parser.error(str(exc))
    return 0


def main(argv=None) -> int:
    return _run(argv)


def console_main(argv=None) -> int:
    try:
        return _run(argv)
    except KeyboardInterrupt as exc:
        print(json.dumps({"event": "error", **error_payload(exc)}), file=sys.stderr)
        return 130
    except Exception as exc:
        print(json.dumps({"event": "error", **error_payload(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(console_main())
