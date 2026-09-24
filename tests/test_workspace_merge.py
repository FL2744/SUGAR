from __future__ import annotations

import json
from pathlib import Path

from sugar_core.models import PostRecord
from sugar_core.state_schema import StateAssessment
from sugar_core.state_workflow import save_state_assessments
from sugar_core.storage import save_records
from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_cli import main
from sugar_core.triage_io import load_post_records


def _analyst_project(root: Path, reviewer: str, decision: str) -> SugarWorkspace:
    workspace = SugarWorkspace.create(root, name=reviewer)
    evidence = workspace.path_for("raw") / "records.csv"
    save_records([PostRecord(
        platform="website",
        native_id="shared-1",
        canonical_url="https://example.org/program",
        query="program",
        original_text="Shared public program evidence.",
    )], evidence)
    workspace.register_artifact("evidence", evidence)
    assessments = workspace.path_for("state") / "assessments.jsonl"
    save_state_assessments([
        StateAssessment(
            observation_id="obs_shared",
            review_state=decision,
            reviewer=reviewer,
            review_note=f"Reviewed by {reviewer}.",
        )], assessments)
    workspace.register_artifact("state_assessments", assessments)
    return workspace


def test_project_merge_deduplicates_records_and_preserves_review_conflicts(tmp_path: Path, capsys) -> None:
    first = _analyst_project(tmp_path / "analyst-a", "Analyst A", "human_verified")
    second = _analyst_project(tmp_path / "analyst-b", "Analyst B", "rejected")
    destination = tmp_path / "merged"

    assert main(["merge", str(destination), str(first.root), str(second.root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["canonical_evidence"]["unique_record_keys"] == 1
    assert len(report["human_review_conflicts"]) == 1
    assert report["compatibility"] == "review_required"
    merged = SugarWorkspace.open(destination)
    merged_records = load_post_records(merged.path_for("raw") / "merged_evidence.csv")
    assert len(merged_records) == 1
    assert merged_records[0].raw_stats["project_merge"]["contributors"] == ["Analyst A", "Analyst B"]
    assert not (merged.path_for("state") / "merged_assessments.jsonl").exists()
    assert len(merged.list_artifacts("state_assessments")) == 2
