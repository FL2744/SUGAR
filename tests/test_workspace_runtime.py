from pathlib import Path

from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_runtime import (
    choose_output_directory,
    latest_workspace_artifact_path,
    optional_workspace,
    register_workspace_outputs,
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
