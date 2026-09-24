from __future__ import annotations

import json
from pathlib import Path

from sugar_core.reference_map import create_reference_workspace_map, load_reference_features
from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_share import (
    export_project_share,
    import_project_share,
    verify_project_share,
)


def test_reference_layer_map_keeps_closed_institutions(tmp_path: Path) -> None:
    source = tmp_path / "institutions.csv"
    source.write_text(
        "entity_id,canonical_name,latitude,longitude,lifecycle_status,source_refs\n"
        "a,Active Center,38.9,-77.0,active,https://example.org/a\n"
        "b,Closed Center,40.7,-74.0,closed,https://example.org/b\n",
        encoding="utf-8",
    )

    features = load_reference_features(source, layer_name="Centers")
    assert [feature.status for feature in features] == ["active", "closed"]

    target = tmp_path / "map.html"
    output = create_reference_workspace_map([("Centers", source, None)], target)
    metadata = json.loads(Path(output + ".metadata.json").read_text(encoding="utf-8"))

    assert Path(output).is_file()
    assert metadata["feature_count"] == 2
    assert metadata["layers"][0]["status_counts"] == {"active": 1, "closed": 1}
    html = Path(output).read_text(encoding="utf-8")
    assert "Closed Center" in html
    assert "☠" in html


def test_whole_project_share_round_trip(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Shared Project")
    evidence = workspace.path_for("raw") / "evidence.txt"
    evidence.write_text("evidence", encoding="utf-8")
    workspace.register_artifact("raw", evidence)

    share = export_project_share(workspace.root, tmp_path / "shared-project.zip")
    verification = verify_project_share(share)

    assert verification["valid"] is True
    assert verification["project_id"] == workspace.manifest.project_id

    imported = Path(import_project_share(share, tmp_path / "imports"))
    reopened = SugarWorkspace.open(imported)

    assert reopened.manifest.project_id == workspace.manifest.project_id
    assert (imported / "sugar-research.json").is_file()
    assert (imported / "data" / "raw" / "evidence.txt").read_text(encoding="utf-8") == "evidence"


def test_project_share_detects_tampering(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Shared Project")
    share = Path(export_project_share(workspace.root, tmp_path / "shared-project.zip"))

    import zipfile

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(share, "r") as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith("/sugar-project.json"):
                data = data + b" "
            target.writestr(info, data)

    verification = verify_project_share(tampered)
    assert verification["valid"] is False
    assert any("Hash mismatch" in error for error in verification["errors"])
