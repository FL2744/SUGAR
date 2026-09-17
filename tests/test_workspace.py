from __future__ import annotations

import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from sugar_core.workspace import (
    DEFAULT_LAYOUT,
    MANIFEST_FILENAME,
    SugarWorkspace,
)
from sugar_core.workspace_archive import _safe_member_name, create_workspace_archive, restore_workspace_archive


def test_workspace_create_builds_manifest_layout_and_database(tmp_path: Path) -> None:
    root = tmp_path / "team4"
    workspace = SugarWorkspace.create(root, name="Team 4 Research", description="Diplomacy Lab")

    assert workspace.root == root.resolve()
    assert workspace.manifest_path.is_file()
    assert workspace.database_path.is_file()
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert payload["name"] == "Team 4 Research"
    assert payload["description"] == "Diplomacy Lab"
    assert payload["project_id"]
    assert payload["layout"] == DEFAULT_LAYOUT
    for key in DEFAULT_LAYOUT:
        assert workspace.path_for(key).is_dir()


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


def test_two_workspace_handles_can_write_through_sqlite_busy_timeout(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    first = SugarWorkspace.open(workspace.root)
    second = SugarWorkspace.open(workspace.root)
    first_file = workspace.path_for("references") / "first.txt"
    second_file = workspace.path_for("references") / "second.txt"
    first_file.write_text("first", encoding="utf-8")
    second_file.write_text("second", encoding="utf-8")

    first.register_artifact("reference", first_file)
    second.register_artifact("reference", second_file)

    assert {item.path for item in workspace.list_artifacts("reference")} == {
        "references/first.txt",
        "references/second.txt",
    }


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


def test_workspace_migrates_legacy_artifact_registry(tmp_path: Path) -> None:
    root = tmp_path / "legacy-project"
    root.mkdir()
    (root / MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": "legacy-project",
                "name": "Legacy Project",
                "description": "Legacy fixture",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "layout": DEFAULT_LAYOUT,
            }
        ),
        encoding="utf-8",
    )
    internal = root / ".sugar"
    internal.mkdir()
    with closing(sqlite3.connect(internal / "workspace.sqlite3")) as connection:
        connection.execute(
            """
            CREATE TABLE artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                registered_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(kind, path)
            )
            """
        )

    workspace = SugarWorkspace.open(root)
    assert workspace.status()["database_schema_version"] == 1
    backups = sorted((internal / "migration-backups").glob("*.sqlite3"))
    assert len(backups) == 1
    with closing(sqlite3.connect(backups[0])) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(artifacts)").fetchall()}
    assert "external" not in columns
    fixture = workspace.path_for("references") / "legacy.txt"
    fixture.write_text("legacy", encoding="utf-8")
    artifact = workspace.register_artifact("reference", fixture)
    assert artifact.external is False


def test_workspace_reports_corrupted_database_as_actionable_error(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "corrupted", name="Corrupted")
    workspace.database_path.write_bytes(b"not a sqlite database")

    with pytest.raises(ValueError, match="corrupt or unreadable"):
        SugarWorkspace.open(workspace.root)


def test_workspace_archive_round_trips_project_files_and_external_references(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Portable Project")
    artifact_path = workspace.path_for("observations") / "observations.jsonl"
    artifact_path.write_text('{"ok": true}\n', encoding="utf-8")
    external_path = tmp_path / "external.csv"
    external_path.write_text("id\nexternal\n", encoding="utf-8")
    workspace.register_artifact("observations", artifact_path)
    workspace.register_artifact("reference", external_path)

    archive_path = create_workspace_archive(workspace, tmp_path / "portable.sugar.zip")
    restored = restore_workspace_archive(archive_path, tmp_path / "restored")

    assert restored.manifest.project_id == workspace.manifest.project_id
    assert (restored.root / "data" / "observations" / "observations.jsonl").read_text(
        encoding="utf-8"
    ) == '{"ok": true}\n'
    restored_artifacts = restored.list_artifacts()
    assert any(item.path == "data/observations/observations.jsonl" and item.exists for item in restored_artifacts)
    assert any(item.external and not item.path.startswith("data/") for item in restored_artifacts)


def test_workspace_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    metadata = {
        "archive_schema_version": "1",
        "project_id": "project",
        "file_count": 1,
        "files": ["../escape.txt"],
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("archive-metadata.json", json.dumps(metadata))
        archive.writestr("../escape.txt", "no")

    with pytest.raises(ValueError, match="unsafe member path"):
        restore_workspace_archive(archive_path, tmp_path / "restored")


def test_workspace_archive_rejects_windows_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-canonical member path"):
        _safe_member_name(r"..\escape.txt")
    with pytest.raises(ValueError, match="non-canonical member path"):
        _safe_member_name("C:/escape.txt")
