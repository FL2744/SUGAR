import json
from pathlib import Path

import pandas as pd

from sugar_core.observation_storage import save_observations
from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_cli import main
from sugar_core.state_schema import StateAssessment
from sugar_core.state_workflow import save_state_assessments
from sugar_core.workspace import SugarWorkspace


def test_state_cli_builds_complete_analyst_bundle(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="program",
        title="Verified education program",
        summary="Verified current program for students.",
        observed_at="2026-06-01T12:00:00Z",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.8746,
        longitude=74.5698,
        evidence=[
            EvidenceReference(
                url="https://example.org/program",
                published_at="2026-06-01T12:00:00Z",
                collected_at="2026-09-01T12:00:00Z",
            )
        ],
        verification_state="human_verified",
        reviewer="analyst",
    )
    observation_csv = tmp_path / "observations.csv"
    save_observations([observation], observation_csv)

    assessment = StateAssessment(
        observation_id=observation.observation_id,
        strategic_audiences=["students"],
        program_domains=["higher_education"],
        review_state="human_verified",
        reviewer="analyst",
    )
    assessment_file = tmp_path / "assessments.jsonl"
    save_state_assessments([assessment], assessment_file)

    us_sites = tmp_path / "us_sites.csv"
    pd.DataFrame(
        [
            {
                "name": "American Space Bishkek",
                "network": "american_space",
                "country": "Kyrgyzstan",
                "city": "Bishkek",
                "latitude": 42.87,
                "longitude": 74.59,
                "service_tags": "educationusa;higher_education",
                "source_url": "https://example.gov/space",
                "status": "active",
            }
        ]
    ).to_csv(us_sites, index=False)

    out_dir = tmp_path / "bundle"
    assert (
        main(
            [
                "package",
                str(observation_csv),
                "--assessments",
                str(assessment_file),
                "--us-sites",
                str(us_sites),
                "--output",
                str(out_dir),
                "--name",
                "state_smoke",
            ]
        )
        == 0
    )

    expected = [
        "state_smoke.audit.json",
        "state_smoke.brief.md",
        "state_smoke.map.geojson",
        "state_smoke.assessed.jsonl",
        "state_smoke.rollups.json",
        "state_smoke.countries.csv",
        "state_smoke.places.csv",
        "state_smoke.nodes.csv",
        "state_smoke.edges.csv",
        "state_smoke.network.json",
        "state_smoke.review.xlsx",
        "state_smoke.freshness.json",
    ]
    for filename in expected:
        assert (out_dir / filename).is_file(), filename

    audit = json.loads((out_dir / "state_smoke.audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "pass"
    geojson = json.loads((out_dir / "state_smoke.map.geojson").read_text(encoding="utf-8"))
    assert {row["properties"]["layer"] for row in geojson["features"]} == {"prc_observation", "us_presence"}
    network = json.loads((out_dir / "state_smoke.network.json").read_text(encoding="utf-8"))
    assert any(edge["relationship"] == "overlaps_us_public_diplomacy" for edge in network["edges"])


def test_state_cli_routes_map_into_workspace_and_registers_it(tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Project")
    observation = ResearchObservation(
        observation_type="event",
        title="Verified event",
        summary="Verified event with city-level coordinates.",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.8746,
        longitude=74.5698,
        location_basis="reported_city",
        location_confidence=0.8,
        evidence=[EvidenceReference(url="https://example.org/event")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    observation_csv = workspace.path_for("observations") / "observations.csv"
    save_observations([observation], observation_csv)
    assessment_file = workspace.path_for("state") / "assessments.jsonl"
    save_state_assessments(
        [
            StateAssessment(
                observation_id=observation.observation_id,
                review_state="human_verified",
                reviewer="analyst",
            )
        ],
        assessment_file,
    )

    assert (
        main(
            [
                "map",
                str(observation_csv),
                str(assessment_file),
                "--workspace",
                str(workspace.root),
            ]
        )
        == 0
    )

    map_path = workspace.path_for("maps") / "state_research.interactive_map.html"
    assert map_path.is_file()
    metadata = json.loads(map_path.with_suffix(".html.metadata.json").read_text(encoding="utf-8"))
    assert metadata["precision_counts"] == {"city": 1}
    assert workspace.latest_artifact("map") is not None
