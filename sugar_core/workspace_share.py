from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .research_workspace import RESEARCH_STATE_FILENAME
from .workspace import CATALOG_FILENAME, INTERNAL_DIRECTORY, MANIFEST_FILENAME, SugarWorkspace

SHARE_MANIFEST = "sugar-share-manifest.json"
SHARE_SCHEMA_VERSION = "1.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_files(workspace: SugarWorkspace) -> list[Path]:
    files: list[Path] = []
    for path in workspace.root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace.root)
        if relative.parts and relative.parts[0] == INTERNAL_DIRECTORY:
            continue
        if relative.name == SHARE_MANIFEST:
            continue
        files.append(path)
    return sorted(files)


def export_project_share(
    workspace_path: str | Path,
    output_file: str | Path,
    *,
    include_external_artifacts: bool = False,
) -> str:
    workspace = SugarWorkspace.open(workspace_path)
    target = Path(output_file).expanduser().resolve()
    if target.suffix.casefold() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sugar-share-") as temp:
        staging = Path(temp) / workspace.root.name
        shutil.copytree(
            workspace.root,
            staging,
            ignore=shutil.ignore_patterns(INTERNAL_DIRECTORY),
        )

        externals: list[dict[str, Any]] = []
        if include_external_artifacts:
            external_dir = staging / "shared-external"
            for artifact in workspace.list_artifacts():
                if not artifact.external or not artifact.exists:
                    continue
                source = workspace.artifact_absolute_path(artifact)
                destination = external_dir / artifact.kind / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                externals.append({
                    "kind": artifact.kind,
                    "original_path": str(source),
                    "shared_path": destination.relative_to(staging).as_posix(),
                })

        entries = []
        for path in sorted(p for p in staging.rglob("*") if p.is_file() and p.name != SHARE_MANIFEST):
            entries.append({
                "path": path.relative_to(staging).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            })
        manifest = {
            "schema_version": SHARE_SCHEMA_VERSION,
            "project_id": workspace.manifest.project_id,
            "project_name": workspace.manifest.name,
            "workspace_schema_version": workspace.manifest.schema_version,
            "portable_files": entries,
            "external_artifacts_included": externals,
            "notes": [
                "Local .sugar runtime state is intentionally excluded and rebuilt on open.",
                "Runtime credentials and secrets are not part of SUGAR project state.",
                "External artifacts are excluded unless explicitly requested.",
            ],
        }
        (staging / SHARE_MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        temporary = target.with_suffix(target.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(p for p in staging.rglob("*") if p.is_file()):
                archive.write(path, arcname=f"{staging.name}/{path.relative_to(staging).as_posix()}")
        temporary.replace(target)
    return str(target)


def verify_project_share(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    errors: list[str] = []
    with zipfile.ZipFile(source, "r") as archive:
        names = archive.namelist()
        manifest_names = [name for name in names if name.endswith("/" + SHARE_MANIFEST)]
        if len(manifest_names) != 1:
            return {"valid": False, "errors": ["Share ZIP must contain exactly one share manifest."], "project_id": ""}
        manifest_name = manifest_names[0]
        manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
        if manifest.get("schema_version") != SHARE_SCHEMA_VERSION:
            errors.append("Unsupported share schema version.")
        root_prefix = manifest_name[: -len(SHARE_MANIFEST)]
        required = {MANIFEST_FILENAME, CATALOG_FILENAME, RESEARCH_STATE_FILENAME}
        present = {name[len(root_prefix):] for name in names if name.startswith(root_prefix)}
        missing = sorted(required - present)
        if missing:
            errors.append("Missing required portable project files: " + ", ".join(missing))
        for entry in manifest.get("portable_files") or []:
            relative = str(entry.get("path") or "")
            archive_name = root_prefix + relative
            if archive_name not in names:
                errors.append(f"Missing shared file: {relative}")
                continue
            digest = hashlib.sha256(archive.read(archive_name)).hexdigest()
            if digest != entry.get("sha256"):
                errors.append(f"Hash mismatch: {relative}")
    return {
        "valid": not errors,
        "errors": errors,
        "project_id": str(manifest.get("project_id") or ""),
        "project_name": str(manifest.get("project_name") or ""),
        "file_count": len(manifest.get("portable_files") or []),
    }


def import_project_share(path: str | Path, destination: str | Path) -> str:
    verification = verify_project_share(path)
    if not verification["valid"]:
        raise ValueError("Invalid SUGAR project share: " + "; ".join(verification["errors"]))
    source = Path(path).expanduser().resolve()
    destination_root = Path(destination).expanduser().resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as archive:
        top_levels = sorted({Path(name).parts[0] for name in archive.namelist() if Path(name).parts})
        if len(top_levels) != 1:
            raise ValueError("Project share must contain one project root.")
        project_name = top_levels[0]
        target = destination_root / project_name
        if target.exists():
            raise FileExistsError(target)
        for member in archive.infolist():
            member_path = Path(member.filename)
            resolved = (destination_root / member_path).resolve()
            try:
                resolved.relative_to(destination_root)
            except ValueError as exc:
                raise ValueError("Unsafe path in project share.") from exc
        archive.extractall(destination_root)
    workspace = SugarWorkspace.open(target)
    share_manifest_path = target / SHARE_MANIFEST
    if share_manifest_path.is_file():
        share_manifest = json.loads(share_manifest_path.read_text(encoding="utf-8"))
        for raw in share_manifest.get("external_artifacts_included") or []:
            if not isinstance(raw, dict):
                continue
            shared_path = str(raw.get("shared_path") or "").strip()
            kind = str(raw.get("kind") or "shared_external").strip() or "shared_external"
            if not shared_path:
                continue
            imported_path = (target / shared_path).resolve()
            try:
                imported_path.relative_to(target)
            except ValueError:
                continue
            if imported_path.is_file():
                workspace.register_artifact(
                    kind,
                    imported_path,
                    label=f"Imported shared external: {imported_path.name}",
                    metadata={
                        "operation": "project_share_import",
                        "original_external_path": str(raw.get("original_path") or ""),
                    },
                )
    return str(target)
