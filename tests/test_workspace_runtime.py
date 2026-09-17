from pathlib import Path

import pytest

from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_runtime import (
    classify_workspace_output,
    choose_output_directory,
    latest_workspace_artifact_path,
    optional_workspace,
    register_workspace_outputs,
    workspace_from_config,
)


def test_workspace_runtime_routes_outputs_and_registers_artifacts(tmp_path: Path, monkeypatch):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    monkeypatch.chdir(workspace.path_for("state"))

    discovered = optional_workspace()
    assert discovered is not None
    assert discovered.root == workspace.root

    output_dir = choose_output_directory(None, discovered, "maps")
    output = output_dir / "state_map.html"
    output.write_text("<html></html>", encoding="utf-8")

    records = register_workspace_outputs(discovered, [output], operation="state-map", kind="map")

    assert len(records) == 1
    assert records[0].kind == "map"
    assert records[0].external is False
    assert latest_workspace_artifact_path(discovered, "map") == output.resolve()


def test_explicit_output_directory_overrides_workspace_default(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    explicit = tmp_path / "custom"

    result = choose_output_directory(explicit, workspace, "maps")

    assert result == explicit.resolve()
    assert result.is_dir()


def test_workspace_discovery_is_optional_but_explicit_paths_are_strict(tmp_path: Path):
    assert optional_workspace(discover_from=tmp_path) is None
    assert workspace_from_config({}, discover_from=tmp_path) is None

    with pytest.raises(FileNotFoundError):
        optional_workspace(tmp_path / "missing-project")

    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    assert optional_workspace(workspace.root).root == workspace.root
    assert workspace_from_config({"workspace": str(workspace.manifest_path)}).root == workspace.root


def test_output_directory_uses_workspace_then_fallback(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    assert choose_output_directory(None, workspace, "reports") == workspace.path_for("reports")

    fallback = tmp_path / "standalone" / "nested"
    result = choose_output_directory(None, None, "reports", fallback=fallback)
    assert result == fallback.resolve()
    assert result.is_dir()


def test_latest_artifact_skips_missing_newer_registration(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    existing = workspace.path_for("observations") / "existing.jsonl"
    existing.write_text("{}\n", encoding="utf-8")
    workspace.register_artifact("observations", existing)

    missing = workspace.path_for("observations") / "newer-but-missing.jsonl"
    workspace.register_artifact("observations", missing, require_exists=False)

    assert latest_workspace_artifact_path(workspace, "observations") == existing.resolve()
    assert latest_workspace_artifact_path(workspace, "observations", require_exists=False) == missing.resolve()
    assert latest_workspace_artifact_path(workspace, ["state_assessments", "observations"]) == existing.resolve()
    assert latest_workspace_artifact_path(None, "observations") is None


@pytest.mark.parametrize(
    ("path", "operation", "expected"),
    [
        ("state_map.html", "state-map", "map"),
        ("analysis.pdf", "analysis", "report"),
        ("analysis.docx", "analysis", "report"),
        ("case_observations.jsonl", "", "observations"),
        ("triaged.csv", "triage", "observations"),
        ("campaign.harvest.sqlite3", "", "harvest"),
        ("campaign.sqlite3", "harvest", "harvest"),
        ("search.csv", "search", "raw_collection"),
        ("seed.brief.md", "weibo-investigate", "raw_collection"),
        ("campaign.qualification.json", "weibo-qualify", "raw_collection"),
        ("packet.json", "intel-synthesis", "intelligence"),
        ("snapshot.json", "state-package", "state"),
        ("monitored_entities.csv", "", "reference"),
        ("other.zip", "", "export"),
    ],
)
def test_workspace_output_classification(path: str, operation: str, expected: str):
    assert classify_workspace_output(path, operation=operation) == expected


def test_register_outputs_classifies_existing_files_and_skips_missing(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    output = workspace.path_for("raw") / "seed.insights.json"
    output.write_text("{}", encoding="utf-8")
    missing = workspace.path_for("raw") / "missing.json"

    records = register_workspace_outputs(
        workspace,
        [output, missing],
        operation="weibo-investigate",
    )

    assert len(records) == 1
    assert records[0].kind == "raw_collection"
    assert records[0].metadata == {"operation": "weibo-investigate"}
    assert register_workspace_outputs(None, [output], operation="search") == []
