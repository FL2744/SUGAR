from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from sugar_core.workspace import (
    CATALOG_FILENAME,
    CATALOG_SCHEMA_VERSION,
    DEFAULT_LAYOUT,
    MANIFEST_FILENAME,
    SugarWorkspace,
)


def test_workspace_create_builds_manifest_layout_and_database(tmp_path: Path) -> None:
    root = tmp_path / "team4"
    workspace = SugarWorkspace.create(root, name="Team 4 Research", description="Diplomacy Lab")

    assert workspace.root == root.resolve()
    assert workspace.manifest_path.is_file()
    assert workspace.database_path.is_file()
    assert workspace.catalog_path.is_file()
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert payload["name"] == "Team 4 Research"
    assert payload["description"] == "Diplomacy Lab"
    assert payload["project_id"]
    assert payload["layout"] == DEFAULT_LAYOUT
    for key in DEFAULT_LAYOUT:
        assert workspace.path_for(key).is_dir()
    catalog = json.loads(workspace.catalog_path.read_text(encoding="utf-8"))
    assert catalog["schema_version"] == CATALOG_SCHEMA_VERSION
    assert catalog["project_id"] == workspace.manifest.project_id
    assert catalog["software"]["name"] == "SUGAR"
    assert catalog["artifacts"] == []


def test_workspace_database_context_closes_connection(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")

    with workspace._connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_workspace_open_and_discover_from_nested_directory(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    nested = workspace.path_for("state") / "review" / "round-1"
    nested.mkdir(parents=True)

    opened = SugarWorkspace.open(workspace.root)
    discovered = SugarWorkspace.discover(nested)

    assert opened.manifest.project_id == workspace.manifest.project_id
    assert discovered.root == workspace.root
    assert discovered.manifest_path.name == MANIFEST_FILENAME


def test_workspace_registers_internal_artifacts_portably(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    output = workspace.path_for("observations") / "observations.xlsx"
    output.write_text("fixture", encoding="utf-8")

    artifact = workspace.register_artifact(
        "observations",
        output,
        label="Reviewed observations",
        metadata={"operation": "triage"},
    )

    assert artifact.kind == "observations"
    assert artifact.path == "data/observations/observations.xlsx"
    assert artifact.external is False
    assert artifact.exists is True
    assert artifact.metadata == {"operation": "triage"}
    assert workspace.latest_artifact("observations") == artifact
    catalog = json.loads(workspace.catalog_path.read_text(encoding="utf-8"))
    assert catalog["artifacts"][0]["path"] == "data/observations/observations.xlsx"
    assert catalog["artifacts"][0]["external"] is False


def test_workspace_registration_is_idempotent_and_updates_metadata(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    report = workspace.path_for("reports") / "brief.pdf"
    report.write_bytes(b"pdf")

    first = workspace.register_artifact("report", report, metadata={"revision": 1})
    second = workspace.register_artifact("report", report, label="Current brief", metadata={"revision": 2})

    assert first.id == second.id
    assert len(workspace.list_artifacts("report")) == 1
    assert second.label == "Current brief"
    assert second.metadata == {"revision": 2}


def test_workspace_tracks_external_and_missing_artifacts(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    external = tmp_path / "american-spaces.csv"
    external.write_text("name,latitude,longitude\n", encoding="utf-8")
    workspace.register_artifact("reference", external)

    missing = workspace.root / "references" / "future.csv"
    workspace.register_artifact("reference", missing, require_exists=False)

    status = workspace.status()
    assert status["artifact_count"] == 2
    assert status["artifact_counts"] == {"reference": 2}
    assert status["external_artifacts"] == 1
    assert status["missing_artifacts"] == 1
    assert status["database_schema_version"] == 1
    assert status["catalog_schema_version"] == CATALOG_SCHEMA_VERSION
    assert Path(status["catalog"]).name == CATALOG_FILENAME


def test_workspace_rebuilds_sqlite_registry_from_portable_catalog_after_move(tmp_path: Path) -> None:
    original = SugarWorkspace.create(tmp_path / "original", name="Portable Project")
    evidence = original.path_for("observations") / "observations.jsonl"
    evidence.write_text("{}\n", encoding="utf-8")
    original.register_artifact("observations", evidence, metadata={"schema_version": "1.2"})
    missing = original.path_for("state") / "future-review.jsonl"
    original.register_artifact("state_assessments", missing, require_exists=False)

    moved_root = tmp_path / "moved"
    shutil.copytree(original.root, moved_root)
    moved_database = moved_root / ".sugar" / "workspace.sqlite3"
    moved_database.unlink()

    moved = SugarWorkspace.open(moved_root)
    artifacts = moved.list_artifacts()
    assert len(artifacts) == 2
    restored_evidence = next(item for item in artifacts if item.kind == "observations")
    restored_missing = next(item for item in artifacts if item.kind == "state_assessments")
    assert restored_evidence.external is False
    assert restored_evidence.exists is True
    assert moved.artifact_absolute_path(restored_evidence) == moved_root / "data" / "observations" / "observations.jsonl"
    assert restored_missing.exists is False
    assert moved.status()["missing_artifacts"] == 1


def test_workspace_catalog_restore_rejects_project_path_escape(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    catalog = json.loads(workspace.catalog_path.read_text(encoding="utf-8"))
    catalog["artifacts"] = [{
        "kind": "observations",
        "path": "../outside.jsonl",
        "label": "",
        "registered_at": "2026-09-17T00:00:00Z",
        "updated_at": "2026-09-17T00:00:00Z",
        "metadata": {},
        "external": False,
    }]
    workspace.catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    workspace.database_path.unlink()

    with pytest.raises(ValueError, match="escapes project root"):
        SugarWorkspace.open(workspace.root)


def test_workspace_rejects_duplicate_creation_without_exist_ok(tmp_path: Path) -> None:
    root = tmp_path / "project"
    workspace = SugarWorkspace.create(root, name="Project")
    with pytest.raises(FileExistsError):
        SugarWorkspace.create(root, name="Again")

    reopened = SugarWorkspace.create(root, name="Ignored", exist_ok=True)
    assert reopened.manifest.project_id == workspace.manifest.project_id
    assert reopened.manifest.name == "Project"


def test_workspace_rejects_unknown_schema_version(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "999"
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported workspace schema"):
        SugarWorkspace.open(workspace.root)


def test_workspace_rejects_layout_path_escape(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload["layout"]["reports"] = "../../outside"
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes project root"):
        SugarWorkspace.open(workspace.root)


def test_workspace_rejects_missing_required_layout_key(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload["layout"].pop("state")
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required layout keys"):
        SugarWorkspace.open(workspace.root)
