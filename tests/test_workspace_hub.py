from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sugar_core.workspace import SugarWorkspace
from sugar_core.workspace_hub import run_workspace_hub


def _hub(action: str, workspace: SugarWorkspace, **config):
    events: list[tuple[str, dict]] = []
    outputs = run_workspace_hub(
        {"action": action, "workspace": str(workspace.root), **config},
        progress=lambda event, values: events.append((event, values)),
    )
    data = next((values["data"] for event, values in events if event == "workspace_hub_data"), None)
    return outputs, data


def test_project_profile_persists_notes_and_non_authoritative_member_roster(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Profile project")
    _, saved = _hub(
        "project-profile-update",
        workspace,
        notes="Use public sources and record translation decisions.",
        members=[
            {"name": "Analyst One", "email": "one@example.test", "role": "Lead analyst"},
            {"name": "Reviewer Two", "email": "two@example.test", "role": "Reviewer"},
        ],
    )
    assert saved == {
        "notes": "Use public sources and record translation decisions.",
        "members": [
            {"name": "Analyst One", "email": "one@example.test", "role": "Lead analyst"},
            {"name": "Reviewer Two", "email": "two@example.test", "role": "Reviewer"},
        ],
        "access_control": False,
    }
    profile_path = workspace.internal_path / "project-profile.json"
    assert json.loads(profile_path.read_text(encoding="utf-8"))["members"] == saved["members"]

    _, loaded = _hub("project-profile", workspace)
    assert loaded == saved
    _, dashboard = _hub("dashboard", workspace)
    assert dashboard["project_profile"] == saved
    artifact = workspace.latest_artifact("project_profile")
    assert artifact is not None
    assert artifact.metadata == {"access_control": False, "member_count": 2}


@pytest.mark.parametrize(
    "members,match",
    [
        ([{"name": "", "email": "", "role": "analyst"}], "requires a name"),
        ([{"name": "A", "email": "not-an-email", "role": "analyst"}], "invalid email"),
        ([{"name": "A", "email": "a@example.test", "role": "analyst"}, {"name": "B", "email": "A@example.test", "role": "reviewer"}], "must be unique"),
    ],
)
def test_project_profile_rejects_invalid_members(tmp_path: Path, members, match: str):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Profile project")
    with pytest.raises(ValueError, match=match):
        _hub("project-profile-update", workspace, notes="", members=members)


def test_dataset_virtual_file_references_are_project_scoped(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Path project")
    source = workspace.path_for("raw") / "records.csv"
    source.write_text("id,country,city,latitude,longitude\n1,Exampleland,North City,12.3,45.6\n", encoding="utf-8")

    _, preview = _hub(
        "dataset-browse",
        workspace,
        source_file=f"sugar-workspace://{workspace.manifest.project_id}/data/raw/records.csv",
    )
    assert preview["row_count"] == 1

    with pytest.raises(ValueError, match="leave the selected workspace"):
        _hub(
            "dataset-browse",
            workspace,
            source_file=f"sugar-workspace://{workspace.manifest.project_id}/%2e%2e/secret.csv",
        )
    with pytest.raises(ValueError, match="does not belong"):
        _hub("dataset-browse", workspace, source_file="sugar-workspace://other-project/data/raw/records.csv")


def test_manual_geography_annotations_are_provenanced_and_comparable(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Geography review")
    left = workspace.path_for("raw") / "left.csv"
    right = workspace.path_for("raw") / "right.csv"
    pd.DataFrame([
        {"record_id": "a", "country": "Exampleland", "region": "Unverified", "city": "Harbor"},
        {"record_id": "b", "country": "Exampleland", "region": "South", "city": "Lake"},
    ]).to_csv(left, index=False)
    pd.DataFrame([
        {"record_id": "c", "country": "Exampleland", "region": "North", "city": "Harbor"},
        {"record_id": "d", "country": "Sample State", "region": "South", "city": "Lake"},
    ]).to_csv(right, index=False)

    _, annotation = _hub(
        "dataset-geography-assign", workspace, source_file=str(left), row_number=0,
        country="Exampleland", region="North", city="Harbor", note="Verified in the source register", actor="Reviewer A",
    )
    assert annotation["provenance"] == "analyst_manual"
    assert annotation["assigned_by"] == "Reviewer A"

    _, preview = _hub("dataset-browse", workspace, source_file=str(left), max_rows=5)
    assert preview["rows"][0]["_sugar_row_number"] == 0
    assert preview["rows"][0]["analyst_region"] == "North"
    assert preview["rows"][0]["location_provenance"] == "analyst_manual"

    _, summary = _hub("dataset-geography-summary", workspace, source_file=str(left), group_by="region")
    assert summary["groups"][0]["label"] == "North"

    _, comparison = _hub(
        "dataset-region-compare", workspace, source_file=str(left), comparison_file=str(right), group_by="region",
    )
    by_name = {row["label"]: row for row in comparison["groups"]}
    assert by_name["North"]["left_records"] == 1
    assert by_name["North"]["right_records"] == 1
    assert by_name["South"]["share_difference"] == 0.0
    assert "does not establish" in comparison["guardrail"]

    left.write_text(left.read_text(encoding="utf-8").replace("Unverified", "West"), encoding="utf-8")
    _, changed_summary = _hub("dataset-geography-summary", workspace, source_file=str(left), group_by="region")
    assert "West" in {group["label"] for group in changed_summary["groups"]}


def test_project_comments_and_reusable_research_templates(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Reusable project")
    _, starter = _hub("research-template-list", workspace)
    assert len(starter["templates"]) >= 3
    _, saved = _hub(
        "research-template-save", workspace, name="Annual scan",
        fields={"question": "What services changed this year?", "languages": ["en", "es"], "preferred_sources": ["x"]},
    )
    assert saved["template_id"] == "custom-annual-scan"
    _, templates = _hub("research-template-list", workspace)
    assert next(item for item in templates["templates"] if item["template_id"] == saved["template_id"])["question"] == "What services changed this year?"

    _, comment = _hub("project-comment-add", workspace, body="Check the date range before collection.", actor="Analyst One")
    _, comments = _hub("project-comment-list", workspace)
    assert comments["comments"] == [comment]
    assert comment["actor"] == "Analyst One"


@pytest.mark.parametrize("export_format", ["csv", "xlsx", "jsonl", "json", "geojson"])
def test_dataset_export_formats_and_geographic_grouping(tmp_path: Path, export_format: str):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Export project")
    source = workspace.path_for("raw") / "records.csv"
    pd.DataFrame(
        [
            {"record_id": "one", "country": "Exampleland", "region": "North", "city": "Harbor", "latitude": 12.34, "longitude": 45.67},
            {"record_id": "two", "country": "Sample State", "region": "South", "city": "Lake", "latitude": "", "longitude": ""},
            {"record_id": "three", "country": "Exampleland", "region": "North", "city": "Harbor", "latitude": 12.34, "longitude": 45.67},
        ],
    ).to_csv(source, index=False)

    _, summary = _hub(
        "dataset-geography-summary",
        workspace,
        source_file=str(source),
        group_by="auto",
    )
    assert summary["total_rows"] == 3
    assert summary["located_rows"] == 3
    assert summary["groups"][0]["label"] == "Exampleland / North / Harbor"
    assert "do not establish influence" in summary["guardrail"]

    outputs, result = _hub(
        "dataset-export",
        workspace,
        source_file=str(source),
        format=export_format,
        file_name=f"records.{export_format}",
    )
    target = Path(outputs[-1])
    assert target.is_file()
    assert target.suffix == f".{export_format}"
    if export_format == "json":
        assert isinstance(json.loads(target.read_text(encoding="utf-8")), list)
    elif export_format == "geojson":
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["type"] == "FeatureCollection"
        assert data["features"][0]["geometry"]["coordinates"] == [45.67, 12.34]
    elif export_format == "jsonl":
        assert json.loads(target.read_text(encoding="utf-8").splitlines()[0])["record_id"] == "one"
    assert result["matching_rows"] == 3
