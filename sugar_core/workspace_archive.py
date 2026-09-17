"""Portable, validated archives for SUGAR project workspaces."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from . import __version__
from .utils import atomic_path
from .workspace import MANIFEST_FILENAME, SugarWorkspace

ARCHIVE_SCHEMA_VERSION = "1"
_MAX_MEMBERS = 100_000
_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


def _archive_metadata(workspace: SugarWorkspace, files: list[str]) -> dict[str, Any]:
    return {
        "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
        "sugar_version": __version__,
        "project_id": workspace.manifest.project_id,
        "workspace_schema_version": workspace.manifest.schema_version,
        "file_count": len(files),
        "files": files,
        "external_artifact_count": sum(1 for artifact in workspace.list_artifacts() if artifact.external),
        "note": "External artifact references remain external and are not copied into this archive.",
    }


def _relative_file_names(root: Path, archive_path: Path) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or path.resolve() == archive_path:
            continue
        relative = path.relative_to(root).as_posix()
        if relative.endswith(".tmp") or "/." in relative and relative.split("/")[-1].startswith("."):
            continue
        result.append((path, relative))
    result.sort(key=lambda item: item[1])
    return result


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def create_workspace_archive(workspace: SugarWorkspace | str | Path, output: str | Path) -> Path:
    """Write a deterministic archive of project-contained workspace files."""

    if not isinstance(workspace, SugarWorkspace):
        workspace = SugarWorkspace.open(workspace)
    target = Path(output).expanduser().resolve()
    try:
        target.relative_to(workspace.root)
    except ValueError:
        pass
    else:
        raise ValueError("Workspace archive output must be outside the workspace root.")
    if target.is_dir():
        raise ValueError("Workspace archive output must be a file outside the workspace root.")
    files = _relative_file_names(workspace.root, target)
    names = [name for _path, name in files]
    if MANIFEST_FILENAME not in names:
        raise ValueError(f"Workspace archive requires {MANIFEST_FILENAME}.")

    with atomic_path(target) as temporary:
        with zipfile.ZipFile(temporary, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            metadata = _archive_metadata(workspace, names)
            archive.writestr(
                _zip_info("archive-metadata.json"),
                json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
            for path, name in files:
                with path.open("rb") as source, archive.open(_zip_info(name), mode="w") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
    return target


def _safe_member_name(name: str) -> str:
    if "\\" in name or PureWindowsPath(name).drive:
        raise ValueError(f"Workspace archive contains a non-canonical member path: {name!r}")
    pure = PurePosixPath(name)
    if not name or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"Workspace archive contains an unsafe member path: {name!r}")
    return pure.as_posix()


def _read_archive_metadata(archive: zipfile.ZipFile) -> dict[str, Any]:
    try:
        payload = json.loads(archive.read("archive-metadata.json").decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Workspace archive is missing valid archive-metadata.json.") from exc
    if not isinstance(payload, dict) or payload.get("archive_schema_version") != ARCHIVE_SCHEMA_VERSION:
        raise ValueError("Unsupported workspace archive schema.")
    return payload


def restore_workspace_archive(archive_path: str | Path, output_directory: str | Path) -> SugarWorkspace:
    """Validate and restore an archive into a new workspace directory."""

    source = Path(archive_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    target = Path(output_directory).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"Restore destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.restore-", dir=target.parent))
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            members = archive.infolist()
            if len(members) > _MAX_MEMBERS:
                raise ValueError("Workspace archive contains too many files.")
            metadata = _read_archive_metadata(archive)
            total_size = 0
            seen: set[str] = set()
            declared_files = metadata.get("files")
            if not isinstance(declared_files, list) or not all(isinstance(name, str) for name in declared_files):
                raise ValueError("Workspace archive metadata has an invalid file manifest.")
            actual_files = sorted(
                member.filename
                for member in members
                if member.filename != "archive-metadata.json" and not member.is_dir()
            )
            if sorted(declared_files) != actual_files or metadata.get("file_count") != len(actual_files):
                raise ValueError("Workspace archive file manifest does not match its contents.")
            for member in members:
                name = _safe_member_name(member.filename)
                if name in seen:
                    raise ValueError(f"Workspace archive contains a duplicate member: {name}")
                seen.add(name)
                if member.is_dir():
                    continue
                total_size += max(0, member.file_size)
                if total_size > _MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("Workspace archive exceeds the uncompressed size limit.")
                destination = staging / name
                try:
                    destination.resolve().relative_to(staging.resolve())
                except ValueError as exc:
                    raise ValueError(f"Workspace archive member escapes the restore directory: {name!r}") from exc
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, mode="r") as source_stream, destination.open("wb") as target_stream:
                    shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)

        manifest = SugarWorkspace.open(staging)
        expected_project_id = str(metadata.get("project_id") or "")
        if expected_project_id and manifest.manifest.project_id != expected_project_id:
            raise ValueError("Workspace archive project identity does not match its restored manifest.")
        shutil.move(str(staging), str(target))
        staging = Path()
        return SugarWorkspace.open(target)
    finally:
        if staging != Path() and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
