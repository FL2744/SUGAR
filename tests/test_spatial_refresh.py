from __future__ import annotations

import pandas as pd

from sugar_core.observations import ResearchObservation, SpatialMatch
from sugar_core.spatial import SpatialOverlapConfig, analyze_spatial_overlap


def test_spatial_refresh_clears_stale_match_when_reference_moves_out_of_range():
    observation = ResearchObservation(
        observation_id="obs_refresh",
        observation_type="program",
        title="Program",
        summary="Public activity.",
        latitude=42.8746,
        longitude=74.5698,
        spatial_matches=[
            SpatialMatch(
                reference_layer="American Spaces",
                reference_id="old_ref",
                reference_name="Old nearby reference",
                distance_km=2.0,
                latitude=42.88,
                longitude=74.59,
            )
        ],
    )
    previous_updated_at = observation.updated_at
    far_reference = pd.DataFrame(
        [
            {
                "id": "far_ref",
                "name": "Far reference",
                "latitude": 35.0,
                "longitude": 105.0,
            }
        ]
    )

    enriched, matches, summary = analyze_spatial_overlap(
        [observation],
        [("American Spaces", far_reference)],
        config=SpatialOverlapConfig(max_distance_km=25),
    )

    assert enriched[0].spatial_matches == []
    assert matches.empty
    assert summary["observations_matched"] == 0
    assert enriched[0].schema_version == "1.1"
    assert enriched[0].updated_at >= previous_updated_at
