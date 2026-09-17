from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Iterable, Iterator

WORKSPACE_SCHEMA_VERSION = "1.0"
DATABASE_SCHEMA_VERSION = 1
MANIFEST_FILENAME = "sugar-project.json"
INTERNAL_DIRECTORY = ".sugar"
DATABASE_FILENAME = "workspace.sqlite3"
CATALOG_FILENAME = "sugar-artifacts.json"
CATALOG_SCHEMA_VERSION = "1.0"

DEFAULT_LAYOUT: dict[str, str] = {
    "raw": "data/raw",
    "observations": "data/observations",
    "references": "references",
    "state": "state",
    "maps": "outputs/maps",
    "reports": "outputs/reports",
    "intelligence": "outputs/intelligence",
    "exports": "outputs/exports",
    "cache": ".sugar/cache",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _software_version() -> str:
    try:
        return package_version("sugar-osint")
    except PackageNotFoundError:
        return "unknown"


@dataclass(frozen=True)
class WorkspaceManifest:
    schema_version: str
    project_id: str
    name: str
    description: str
    created_at: str
    updated_at: str
    layout: dict[str, str]


@dataclass(frozen=True)
class ArtifactRecord:
    id: int
    kind: str
    path: str
    label: str
    registered_at: str
    updated_at: str
    metadata: dict[str, Any]
    external: bool
    exists: bool


class SugarWorkspace:
    """Persistent, portable project workspace for SUGAR research.

    The JSON manifest defines portable project identity and directory layout.
    SQLite stores mutable local artifact metadata. Secrets are never stored in either.
    """

    def __init__(self, root: Path, manifest: WorkspaceManifest) -> None:
        self.root = root.resolve()
        self.manifest = manifest

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_FILENAME

    @property
    def internal_path(self) -> Path:
        return self.root / INTERNAL_DIRECTORY

    @property
    def database_path(self) -> Path:
        return self.internal_path / DATABASE_FILENAME

    @property
    def catalog_path(self) -> Path:
        return self.root / CATALOG_FILENAME

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        name: str,
        description: str = "",
        project_id: str | None = None,
        exist_ok: bool = False,
    ) -> "SugarWorkspace":
        target = Path(root).expanduser().resolve()
        manifest_path = target / MANIFEST_FILENAME
        if manifest_path.exists():
            if exist_ok:
                return cls.open(target)
            raise FileExistsError(f"SUGAR workspace already exists: {manifest_path}")

        target.mkdir(parents=True, exist_ok=True)
        now = _utc_now()
        manifest = WorkspaceManifest(
            schema_version=WORKSPACE_SCHEMA_VERSION,
            project_id=project_id or str(uuid.uuid4()),
            name=str(name).strip() or target.name,
            description=str(description).strip(),
            created_at=now,
            updated_at=now,
            layout=dict(DEFAULT_LAYOUT),
        )
        workspace = cls(target, manifest)
        workspace._validate_layout()
        workspace._ensure_layout()
        workspace._write_manifest(manifest)
        workspace._initialize_database()
        workspace._write_catalog()
        return workspace

    @classmethod
    def open(cls, path: str | Path) -> "SugarWorkspace":
        candidate = Path(path).expanduser()
        if candidate.name == MANIFEST_FILENAME:
            manifest_path = candidate.resolve()
        elif candidate.is_file():
            raise ValueError(f"Expected {MANIFEST_FILENAME}, got {candidate.name}")
        else:
            manifest_path = candidate.resolve() / MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise FileNotFoundError(manifest_path)

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Workspace manifest must contain a JSON object.")
        schema_version = str(payload.get("schema_version") or "")
        if schema_version != WORKSPACE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported workspace schema {schema_version!r}; expected {WORKSPACE_SCHEMA_VERSION!r}."
            )
        layout = payload.get("layout") or {}
        if not isinstance(layout, dict):
            raise ValueError("Workspace manifest layout must be a JSON object.")

        manifest = WorkspaceManifest(
            schema_version=schema_version,
            project_id=str(payload.get("project_id") or ""),
            name=str(payload.get("name") or manifest_path.parent.name),
            description=str(payload.get("description") or ""),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            layout={str(key): str(value) for key, value in layout.items()},
        )
        if not manifest.project_id:
            raise ValueError("Workspace manifest is missing project_id.")
        workspace = cls(manifest_path.parent, manifest)
        workspace._validate_layout()
        workspace._ensure_layout()
        database_existed = workspace.database_path.is_file()
        workspace._initialize_database()
        if not database_existed and workspace.catalog_path.is_file():
            workspace._restore_catalog()
        elif not workspace.catalog_path.is_file():
            workspace._write_catalog()
        return workspace

    @classmethod
    def discover(cls, start: str | Path = ".") -> "SugarWorkspace":
        candidate = Path(start).expanduser().resolve()
        if candidate.is_file():
            candidate = candidate.parent
        for directory in (candidate, *candidate.parents):
            manifest_path = directory / MANIFEST_FILENAME
            if manifest_path.is_file():
                return cls.open(directory)
        raise FileNotFoundError(f"No {MANIFEST_FILENAME} found from {candidate} upward.")

    def path_for(self, key: str) -> Path:
        try:
            relative = self.manifest.layout[key]
        except KeyError as exc:
            known = ", ".join(sorted(self.manifest.layout))
            raise KeyError(f"Unknown workspace path {key!r}. Known paths: {known}") from exc
        return self._safe_layout_path(relative)

    def register_artifact(
        self,
        kind: str,
        path: str | Path,
        *,
        label: str = "",
        metadata: dict[str, Any] | None = None,
        require_exists: bool = True,
    ) -> ArtifactRecord:
        kind = str(kind).strip().casefold().replace(" ", "_")
        if not kind:
            raise ValueError("Artifact kind cannot be empty.")
        resolved = self._resolve_artifact_path(path)
        if require_exists and not resolved.exists():
            raise FileNotFoundError(resolved)
        stored_path, external = self._portable_path(resolved)
        now = _utc_now()
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO artifacts(kind, path, label, registered_at, updated_at, metadata_json, external)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kind, path) DO UPDATE SET
                    label = excluded.label,
                    updated_at = excluded.updated_at,
                    metadata_json = excluded.metadata_json,
                    external = excluded.external
                """,
                (kind, stored_path, str(label).strip(), now, now, metadata_json, int(external)),
            )
            connection.commit()
            row = connection.execute(
                "SELECT id, kind, path, label, registered_at, updated_at, metadata_json, external "
                "FROM artifacts WHERE kind = ? AND path = ?",
                (kind, stored_path),
            ).fetchone()
        assert row is not None
        artifact = self._artifact_from_row(row)
        self._write_catalog()
        return artifact

    def register_outputs(
        self,
        paths: Iterable[str | Path],
        *,
        kind: str,
        operation: str = "",
    ) -> list[ArtifactRecord]:
        records: list[ArtifactRecord] = []
        for path in paths:
            records.append(
                self.register_artifact(
                    kind,
                    path,
                    metadata={"operation": operation} if operation else {},
                )
            )
        return records

    def list_artifacts(self, kind: str | None = None) -> list[ArtifactRecord]:
        select = "SELECT id, kind, path, label, registered_at, updated_at, metadata_json, external FROM artifacts"
        with self._connect() as connection:
            if kind:
                rows = connection.execute(
                    select + " WHERE kind = ? ORDER BY id DESC",
                    (str(kind).strip().casefold().replace(" ", "_"),),
                ).fetchall()
            else:
                rows = connection.execute(select + " ORDER BY id DESC").fetchall()
        return [self._artifact_from_row(row) for row in rows]

    def latest_artifact(self, kind: str) -> ArtifactRecord | None:
        records = self.list_artifacts(kind)
        return records[0] if records else None

    def status(self) -> dict[str, Any]:
        artifacts = self.list_artifacts()
        counts: dict[str, int] = {}
        missing = 0
        external = 0
        for artifact in artifacts:
            counts[artifact.kind] = counts.get(artifact.kind, 0) + 1
            missing += int(not artifact.exists)
            external += int(artifact.external)
        return {
            "schema_version": self.manifest.schema_version,
            "database_schema_version": DATABASE_SCHEMA_VERSION,
            "project_id": self.manifest.project_id,
            "name": self.manifest.name,
            "description": self.manifest.description,
            "root": str(self.root),
            "manifest": str(self.manifest_path),
            "database": str(self.database_path),
            "catalog": str(self.catalog_path),
            "catalog_schema_version": CATALOG_SCHEMA_VERSION,
            "software_version": _software_version(),
            "layout": {key: str(self.path_for(key)) for key in sorted(self.manifest.layout)},
            "artifact_count": len(artifacts),
            "artifact_counts": dict(sorted(counts.items())),
            "missing_artifacts": missing,
            "external_artifacts": external,
        }

    def artifact_absolute_path(self, artifact: ArtifactRecord) -> Path:
        stored = Path(artifact.path)
        if artifact.external:
            return stored.expanduser().resolve()
        return (self.root / stored).resolve()

    def _safe_layout_path(self, relative: str) -> Path:
        raw = Path(str(relative))
        if raw.is_absolute():
            raise ValueError(f"Workspace layout paths must be relative: {relative!r}")
        resolved = (self.root / raw).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Workspace layout path escapes project root: {relative!r}") from exc
        return resolved

    def _validate_layout(self) -> None:
        missing = sorted(set(DEFAULT_LAYOUT) - set(self.manifest.layout))
        if missing:
            raise ValueError(f"Workspace manifest is missing required layout keys: {', '.join(missing)}")
        for key, relative in self.manifest.layout.items():
            if not str(key).strip():
                raise ValueError("Workspace layout keys cannot be empty.")
            self._safe_layout_path(relative)

    def _resolve_artifact_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (self.root / candidate).resolve()

    def _portable_path(self, path: Path) -> tuple[str, bool]:
        try:
            return path.relative_to(self.root).as_posix(), False
        except ValueError:
            return str(path), True

    def _artifact_from_row(self, row: sqlite3.Row) -> ArtifactRecord:
        stored = str(row["path"])
        external = bool(row["external"])
        path_obj = Path(stored)
        absolute = path_obj.expanduser().resolve() if external else (self.root / path_obj).resolve()
        raw_metadata = str(row["metadata_json"] or "{}")
        try:
            metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            metadata = {"_invalid_metadata": raw_metadata}
        if not isinstance(metadata, dict):
            metadata = {"value": metadata}
        return ArtifactRecord(
            id=int(row["id"]),
            kind=str(row["kind"]),
            path=stored,
            label=str(row["label"] or ""),
            registered_at=str(row["registered_at"]),
            updated_at=str(row["updated_at"]),
            metadata=metadata,
            external=external,
            exists=absolute.exists(),
        )

    def _ensure_layout(self) -> None:
        for key in self.manifest.layout:
            self.path_for(key).mkdir(parents=True, exist_ok=True)
        self.internal_path.mkdir(parents=True, exist_ok=True)

    def _write_manifest(self, manifest: WorkspaceManifest) -> None:
        payload = asdict(manifest)
        temporary = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.manifest_path)

    def export_catalog(self) -> dict[str, Any]:
        artifacts = self.list_artifacts()
        return {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "project_id": self.manifest.project_id,
            "workspace_schema_version": self.manifest.schema_version,
            "database_schema_version": DATABASE_SCHEMA_VERSION,
            "software": {"name": "SUGAR", "version": _software_version()},
            "artifacts": [
                {
                    "kind": artifact.kind,
                    "path": artifact.path,
                    "label": artifact.label,
                    "registered_at": artifact.registered_at,
                    "updated_at": artifact.updated_at,
                    "metadata": artifact.metadata,
                    "external": artifact.external,
                }
                for artifact in artifacts
            ],
        }

    def _write_catalog(self) -> None:
        payload = self.export_catalog()
        temporary = self.catalog_path.with_suffix(self.catalog_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.catalog_path)

    def _validate_catalog_artifact_path(self, stored_path: str, *, external: bool) -> None:
        raw = Path(stored_path)
        if external:
            if not raw.is_absolute():
                raise ValueError(f"External catalog artifact paths must be absolute: {stored_path!r}")
            return
        if raw.is_absolute():
            raise ValueError(f"Project catalog artifact paths must be relative: {stored_path!r}")
        resolved = (self.root / raw).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"Catalog artifact path escapes project root: {stored_path!r}") from exc

    def _restore_catalog(self) -> None:
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Workspace artifact catalog must contain a JSON object.")
        schema_version = str(payload.get("schema_version") or "")
        if schema_version != CATALOG_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported workspace artifact catalog schema {schema_version!r}; "
                f"expected {CATALOG_SCHEMA_VERSION!r}."
            )
        if str(payload.get("project_id") or "") != self.manifest.project_id:
            raise ValueError("Workspace artifact catalog project_id does not match sugar-project.json.")
        artifacts = payload.get("artifacts") or []
        if not isinstance(artifacts, list):
            raise ValueError("Workspace artifact catalog artifacts must be a JSON array.")

        with self._connect() as connection:
            for raw in artifacts:
                if not isinstance(raw, dict):
                    raise ValueError("Workspace artifact catalog entries must be JSON objects.")
                kind = str(raw.get("kind") or "").strip().casefold().replace(" ", "_")
                stored_path = str(raw.get("path") or "").strip()
                external = bool(raw.get("external", False))
                if not kind or not stored_path:
                    raise ValueError("Workspace artifact catalog entries require kind and path.")
                self._validate_catalog_artifact_path(stored_path, external=external)
                metadata = raw.get("metadata") or {}
                if not isinstance(metadata, dict):
                    raise ValueError("Workspace artifact catalog metadata must be a JSON object.")
                registered_at = str(raw.get("registered_at") or _utc_now())
                updated_at = str(raw.get("updated_at") or registered_at)
                connection.execute(
                    """
                    INSERT INTO artifacts(kind, path, label, registered_at, updated_at, metadata_json, external)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(kind, path) DO UPDATE SET
                        label = excluded.label,
                        registered_at = excluded.registered_at,
                        updated_at = excluded.updated_at,
                        metadata_json = excluded.metadata_json,
                        external = excluded.external
                    """,
                    (
                        kind,
                        stored_path,
                        str(raw.get("label") or "").strip(),
                        registered_at,
                        updated_at,
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                        int(external),
                    ),
                )
            connection.commit()
        self._write_catalog()

    def _initialize_database(self) -> None:
        self.internal_path.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version > DATABASE_SCHEMA_VERSION:
                raise ValueError(
                    f"Unsupported workspace database schema {current_version}; "
                    f"maximum supported version is {DATABASE_SCHEMA_VERSION}."
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    registered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    external INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(kind, path)
                )
                """
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(artifacts)").fetchall()}
            if "external" not in columns:
                connection.execute("ALTER TABLE artifacts ADD COLUMN external INTEGER NOT NULL DEFAULT 0")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_artifacts_kind_id ON artifacts(kind, id DESC)"
            )
            if current_version < DATABASE_SCHEMA_VERSION:
                connection.execute(f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}")
            connection.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def open_workspace(path: str | Path = ".", *, discover: bool = False) -> SugarWorkspace:
    return SugarWorkspace.discover(path) if discover else SugarWorkspace.open(path)
