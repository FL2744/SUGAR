from pathlib import Path
import uuid

import pytest

import sugar_api
from sugar_core.workspace import SugarWorkspace


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    identifier = str(uuid.uuid4())
    root = tmp_path / identifier
    SugarWorkspace.create(root, name="API boundary test")
    monkeypatch.setattr(sugar_api, "_workspace_root", tmp_path)
    return identifier, root


def test_browser_project_references_resolve_inside_the_workspace(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    source = root / "data" / "raw" / "records.jsonl"
    source.write_text("{}\n", encoding="utf-8")

    config = sugar_api._rewrite_config(
        {
            "workspace": f"sugar-workspace://{identifier}",
            "records_file": f"sugar-file://{identifier}/data/raw/records.jsonl",
            "output_directory": f"sugar-workspace://{identifier}/outputs/exports",
        },
        workspace_id=identifier,
    )

    assert config["workspace"] == str(root.resolve())
    assert config["records_file"] == str(source.resolve())
    assert config["output_directory"] == str((root / "outputs" / "exports").resolve())


def test_browser_handoff_directory_reference_accepts_a_project_folder(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    bundle = root / "outputs" / "exports" / "handoff"
    bundle.mkdir(parents=True)

    config = sugar_api._rewrite_config(
        {"bundle_directory": f"sugar-workspace://{identifier}/outputs/exports/handoff"},
        workspace_id=identifier,
    )

    assert config["bundle_directory"] == str(bundle.resolve())


def test_browser_handoff_directory_reference_rejects_a_file(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    bundle_file = root / "outputs" / "exports" / "handoff.zip"
    bundle_file.parent.mkdir(parents=True, exist_ok=True)
    bundle_file.write_bytes(b"zip")

    with pytest.raises(sugar_api.ApiError, match="Project directory was not found"):
        sugar_api._rewrite_config(
            {"bundle_directory": f"sugar-workspace://{identifier}/outputs/exports/handoff.zip"},
            workspace_id=identifier,
        )


def test_browser_project_references_reject_traversal_and_cross_project_access(tmp_path, monkeypatch):
    identifier, _ = _workspace(tmp_path, monkeypatch)
    other_id = str(uuid.uuid4())

    with pytest.raises(sugar_api.ApiError, match="escapes"):
        sugar_api._rewrite_config(
            {"workspace": f"sugar-workspace://{identifier}/../../outside"},
            workspace_id=identifier,
        )
    with pytest.raises(sugar_api.ApiError, match="another project"):
        sugar_api._rewrite_config(
            {"workspace": f"sugar-workspace://{other_id}"},
            workspace_id=identifier,
        )
    with pytest.raises(sugar_api.ApiError, match="must reference a file"):
        sugar_api._rewrite_config({"source_file": "C:/private/records.csv"}, workspace_id=identifier)


def test_api_outputs_use_portable_forward_slash_project_references(tmp_path, monkeypatch):
    identifier, root = _workspace(tmp_path, monkeypatch)
    backend_path = str(root / "data" / "raw" / "records.jsonl")

    mapped = sugar_api._map_paths(
        {"outputs": [backend_path], "message": f"saved {backend_path}"},
        root=root,
        identifier=identifier,
    )

    expected = f"sugar-workspace://{identifier}/data/raw/records.jsonl"
    assert mapped["outputs"] == [expected]
    assert mapped["message"] == f"saved {expected}"
