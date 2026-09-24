from __future__ import annotations

import json
from pathlib import Path

from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_cli import main
from sugar_core.workspace_runtime import register_workspace_outputs
from sugar_core.workspace_pipeline import pipeline_report


def test_pipeline_reports_freshness_and_propagates_staleness(tmp_path: Path) -> None:
    workspace = SugarWorkspace.create(tmp_path / "project", name="Pipeline")
    source = workspace.path_for("raw") / "source.jsonl"
    first = workspace.path_for("state") / "first.json"
    second = workspace.path_for("intelligence") / "second.json"
    source.write_text('{"value": 1}\n', encoding="utf-8")
    first.write_text('{"result": 1}\n', encoding="utf-8")
    second.write_text('{"summary": 1}\n', encoding="utf-8")

    register_workspace_outputs(workspace, [source], operation="fixture", kind="evidence")
    register_workspace_outputs(workspace, [first], operation="fixture-transform", kind="state", inputs=[source])
    register_workspace_outputs(workspace, [second], operation="fixture-summarize", kind="intelligence", inputs=[first])

    initial = pipeline_report(workspace)
    assert initial["stale_count"] == 0
    assert {node["state"] for node in initial["nodes"]} == {"fresh"}

    source.write_text('{"value": 2}\n', encoding="utf-8")
    updated = pipeline_report(workspace)
    states = {node["path"]: node["state"] for node in updated["nodes"]}
    assert states["state/first.json"] == "stale"
    assert states["outputs/intelligence/second.json"] == "stale_upstream"
    assert updated["stale_count"] == 2
    assert len(updated["incremental_rebuild_order"]) == 2


def test_workspace_pipeline_cli_reports_derivation_state(tmp_path: Path, capsys) -> None:
    root = tmp_path / "project"
    workspace = SugarWorkspace.create(root, name="CLI pipeline")
    source = workspace.path_for("raw") / "source.csv"
    output = workspace.path_for("exports") / "report.json"
    source.write_text("id,value\n1,ok\n", encoding="utf-8")
    output.write_text(json.dumps({"ok": True}), encoding="utf-8")
    register_workspace_outputs(workspace, [output], operation="fixture", inputs=[source])

    assert main(["pipeline", str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["tracked_derivations"] == 1
    assert report["nodes"][0]["state"] == "fresh"
