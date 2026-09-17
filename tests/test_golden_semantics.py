from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from sugar_core.observations import ResearchObservation
from sugar_core.spatial import SpatialOverlapConfig, analyze_spatial_overlap
from sugar_core.state_aggregate import build_state_rollups
from sugar_core.state_freshness import build_freshness_report
from sugar_core.state_schema import StateAssessment

FIXTURE = Path(__file__).parent / "fixtures" / "golden" / "state_semantics.json"


def test_golden_state_semantics_fixture_locks_cross_module_contract() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == 1

    observations = [ResearchObservation(**row) for row in fixture["observations"]]
    assessments = [StateAssessment(**row) for row in fixture["assessments"]]
    expected = fixture["expectations"]

    rollups = build_state_rollups(observations, assessments)
    country = rollups["countries"][0]
    for key, value in expected["rollup_country"].items():
        assert country[key] == value

    freshness = build_freshness_report(
        observations,
        assessments,
        now=datetime(2026, 9, 13, tzinfo=timezone.utc),
        collection_stale_days=90,
    )
    for key, value in expected["freshness"].items():
        assert freshness[key] == value

    references = pd.DataFrame(fixture["references"])
    enriched, matches, spatial = analyze_spatial_overlap(
        observations,
        [("Golden references", references)],
        config=SpatialOverlapConfig(max_distance_km=5, stored_matches_per_observation=1),
    )
    for key, value in expected["spatial"].items():
        if key.startswith("nearest_"):
            continue
        assert spatial[key] == value
    nearest = next(row.nearest_spatial_match for row in enriched if row.spatial_matches)
    assert nearest is not None
    assert nearest.reference_id == expected["spatial"]["nearest_reference_id"]
    assert nearest.distance_band == expected["spatial"]["nearest_distance_band"]
    assert len(matches) == expected["spatial"]["retained_pair_matches"]
