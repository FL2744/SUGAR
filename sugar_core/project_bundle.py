from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from datetime import datetime, timezone

from .workspace import MANIFEST_FILENAME, SugarWorkspace


_EXCLUDED_DIRECTORY_NAMES = {".git", "__pycache__", "cache", "caches", "node_modules"}
_SECRET_PATH_PARTS = {".env", "credentials", "secrets", "tokens", "cookies", "keychain", "auth"}
_SECRET_JSON_KEYS = {"api_key", "password", "cookie", "authorization", "secret", "bearer_token", "app_password"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _secret_path(path: Path) -> bool:
    return any(part.casefold() in _SECRET_PATH_PARTS or part.casefold().startswith(".env") for part in path.parts)


def _secret_fields(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in _SECRET_JSON_KEYS or normalized.endswith("_api_key"):
                paths.append(str(key))
            else:
                paths.extend(f"{key}.{item}" for item in _secret_fields(child))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(f"[{index}].{item}" for item in _secret_fields(child))
    return paths


def _copy_external_catalog_files(stage: Path, workspace: SugarWorkspace) -> tuple[list[str], dict[str, str]]:
    catalog_path = stage / "sugar-artifacts.json"
    if not catalog_path.is_file():
        return [], {}
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    omissions: list[str] = []
    portable_paths: dict[str, str] = {}
    for artifact in payload.get("artifacts", []):
        if not artifact.get("external"):
            continue
        source = Path(str(artifact.get("path") or "")).expanduser()
        if not source.is_file():
            omissions.append(f"Missing external artifact: {source}")
            continue
        if _secret_path(source):
            omissions.append(f"Excluded secret-path artifact: {source.name}")
            continue
        digest = _sha256(source)
        relative = Path("references") / "external" / f"{digest[:12]}_{source.name}"
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        artifact["path"] = relative.as_posix()
        artifact["external"] = False
        portable_paths[str(source.resolve())] = relative.as_posix()
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return omissions, portable_paths


_PATH_KEYS = {
    "workspace", "root", "path", "file", "source_file", "source_path", "source_paths",
    "output_directory", "output_file", "outputs", "last_run_outputs", "artifact_path",
    "bundle", "bundle_path", "destination", "reference_files", "external_files",
}


def _portable_reference(value: Any, workspace: SugarWorkspace, external_paths: dict[str, str], key: str = "") -> Any:
    if isinstance(value, dict):
        return {str(child_key): _portable_reference(child, workspace, external_paths, str(child_key))
                for child_key, child in value.items()}
    if isinstance(value, list):
        return [_portable_reference(child, workspace, external_paths, key) for child in value]
    normalized_key = key.casefold().replace("-", "_")
    if normalized_key not in _PATH_KEYS or not isinstance(value, str) or not value:
        return value
    try:
        source = Path(value).expanduser()
        if not source.is_absolute():
            return value
        resolved = source.resolve()
        if str(resolved) in external_paths:
            return external_paths[str(resolved)]
        try:
            relative = resolved.relative_to(workspace.root)
            return "." if key == "workspace" else relative.as_posix()
        except ValueError:
            return value
    except (OSError, RuntimeError, ValueError):
        return value


def _rewrite_project_history(stage: Path, workspace: SugarWorkspace, external_paths: dict[str, str]) -> None:
    for path in stage.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in {".json", ".jsonl", ".ndjson"}:
            continue
        if path.name in {"sugar-project.json", "sugar-artifacts.json", "sugar-bundle.json", "dataset_manifest.json"}:
            continue
        try:
            if path.suffix.casefold() in {".jsonl", ".ndjson"}:
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
                updated = [_portable_reference(row, workspace, external_paths) for row in rows]
                text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in updated)
            else:
                value = json.loads(path.read_text(encoding="utf-8-sig"))
                updated = _portable_reference(value, workspace, external_paths)
                text = json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            path.write_text(text, encoding="utf-8")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue


def export_project_bundle(workspace: SugarWorkspace, output: str | Path) -> dict[str, Any]:
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    omissions: list[str] = []
    with tempfile.TemporaryDirectory(prefix="sugar-project-export-") as temporary:
        stage = Path(temporary) / "project"
        stage.mkdir()
        for current, directories, files in os.walk(workspace.root, followlinks=False):
            current_path = Path(current)
            directories[:] = [name for name in directories if name not in _EXCLUDED_DIRECTORY_NAMES and not _secret_path(Path(name))]
            for name in files:
                source = current_path / name
                relative = source.relative_to(workspace.root)
                if source.resolve() == target or _secret_path(relative):
                    omissions.append(f"Excluded secret-named path: {relative.as_posix()}")
                    continue
                if relative.parts[:2] == (".sugar", "workspace.sqlite3"):
                    continue
                if source.suffix.casefold() in {".zip", ".7z", ".rar"}:
                    continue
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        external_omissions, external_paths = _copy_external_catalog_files(stage, workspace)
        omissions.extend(external_omissions)
        _rewrite_project_history(stage, workspace, external_paths)
        inventory: list[dict[str, Any]] = []
        for path in sorted(item for item in stage.rglob("*") if item.is_file()):
            if path.name == "sugar-bundle.json":
                continue
            if path.suffix.casefold() in {".json", ".jsonl", ".ndjson"}:
                try:
                    text = path.read_text(encoding="utf-8-sig")
                    documents = [json.loads(line) for line in text.splitlines() if line.strip()] if path.suffix.casefold() in {".jsonl", ".ndjson"} else [json.loads(text)]
                    fields = [field for document in documents for field in _secret_fields(document)]
                    if fields:
                        omissions.append(f"Excluded file with credential fields: {path.relative_to(stage).as_posix()}")
                        path.unlink()
                        continue
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            inventory.append({"path": path.relative_to(stage).as_posix(), "sha256": _sha256(path), "bytes": path.stat().st_size})
        manifest = {
            "schema_version": "1.0", "project_id": workspace.manifest.project_id,
            "project_name": workspace.manifest.name,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "files": inventory, "omissions": omissions,
            "security_note": "Credential-named paths and JSON credential fields are excluded. Credentials are not part of portable project settings.",
        }
        (stage / "sugar-bundle.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary_zip = target.with_name(target.name + ".tmp")
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(item for item in stage.rglob("*") if item.is_file()):
                archive.write(path, path.relative_to(stage).as_posix())
        temporary_zip.replace(target)
    workspace.register_artifact("project_bundle", target, label="Portable SUGAR project bundle", metadata={"sha256": _sha256(target)})
    return {"bundle": str(target), "project_id": workspace.manifest.project_id,
            "file_count": len(inventory), "omissions": omissions, "sha256": _sha256(target)}


def import_project_bundle(
    bundle: str | Path,
    destination: str | Path,
    *,
    maximum_uncompressed_bytes: int = 2_000_000_000,
) -> dict[str, Any]:
    source = Path(bundle).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.is_file():
        raise FileExistsError(f"Project import destination must be a new directory: {target}")
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Project import destination must be empty: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.sugar-import-", dir=target.parent)).resolve()
    try:
        staging.relative_to(target.parent.resolve())
    except ValueError as exc:
        raise ValueError("Temporary import directory escaped the selected destination parent.") from exc
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            if sum(info.file_size for info in infos) > maximum_uncompressed_bytes:
                raise ValueError("Project bundle exceeds the permitted uncompressed size.")
            names: set[str] = set()
            for info in infos:
                name = info.filename.replace("\\", "/")
                relative = PurePosixPath(name)
                mode = info.external_attr >> 16
                if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts) or (len(name) >= 2 and name[1] == ":"):
                    raise ValueError(f"Unsafe path in project bundle: {name!r}")
                if stat.S_ISLNK(mode):
                    raise ValueError(f"Symbolic links are not allowed in project bundles: {name!r}")
                if name in names:
                    raise ValueError(f"Duplicate path in project bundle: {name!r}")
                names.add(name)
            if "sugar-bundle.json" not in names or MANIFEST_FILENAME not in names:
                raise ValueError("Bundle is missing its integrity manifest or project manifest.")
            manifest = json.loads(archive.read("sugar-bundle.json").decode("utf-8"))
            if manifest.get("schema_version") != "1.0" or not isinstance(manifest.get("files"), list):
                raise ValueError("Unsupported project bundle manifest.")
            listed = {row.get("path"): row for row in manifest["files"]}
            for name, expected in listed.items():
                if name not in names:
                    raise ValueError(f"Project bundle is missing listed file {name!r}.")
                digest = hashlib.sha256(archive.read(name)).hexdigest()
                if digest != expected.get("sha256"):
                    raise ValueError(f"Project bundle integrity check failed for {name!r}.")
            for info in infos:
                if info.is_dir() or info.filename == "sugar-bundle.json":
                    continue
                if info.filename not in listed:
                    raise ValueError(f"Project bundle contains an unmanifested file {info.filename!r}.")
                destination_path = (staging / PurePosixPath(info.filename)).resolve()
                try:
                    destination_path.relative_to(staging.resolve())
                except ValueError as exc:
                    raise ValueError(f"Project bundle path escapes import destination: {info.filename!r}") from exc
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as input_stream, destination_path.open("wb") as output_stream:
                    shutil.copyfileobj(input_stream, output_stream)
        imported = SugarWorkspace.open(staging)
        if imported.manifest.project_id != manifest.get("project_id"):
            raise ValueError("Project ID in bundle manifest does not match sugar-project.json.")
        if target.exists():
            target.rmdir()
        staging.replace(target)
        opened = SugarWorkspace.open(target)
        return {"destination": str(target), "project_id": opened.manifest.project_id,
                "name": opened.manifest.name, "file_count": len(manifest["files"]),
                "omissions": manifest.get("omissions", [])}
    except Exception:
        try:
            staging.resolve().relative_to(target.parent.resolve())
        except ValueError:
            raise RuntimeError("Refusing to remove an import staging directory outside the selected destination parent.")
        shutil.rmtree(staging, ignore_errors=True)
        raise
