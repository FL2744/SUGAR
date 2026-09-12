from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from sugar_core.mapping import _normalize_rows, _popup_html, create_map
from sugar_core.observation_storage import observations_to_frame
from sugar_core.observations import ResearchObservation, SpatialMatch


def _spatial_observation() -> ResearchObservation:
    return ResearchObservation(
        observation_id="obs_spatial",
        observation_type="program",
        title="Technology workshop",
        summary="Public workshop activity.",
        city="Bishkek",
        country="Kyrgyzstan",
        latitude=42.8746,
        longitude=74.5698,
        location_basis="source_stated",
        location_confidence=0.96,
        us_overlap=["Analyst-reviewed shared audience"],
        overlap_note="Human-reviewed overlap judgment.",
        spatial_matches=[
            SpatialMatch(
                reference_layer="American Spaces",
                reference_id="as_bishkek",
                reference_name="American Space Bishkek",
                reference_category="American Space",
                distance_km=2.71,
                distance_band="0–5 km",
                same_city=True,
                same_country=True,
                latitude=42.876,
                longitude=74.603,
                source_url="https://example.test/american-space",
            )
        ],
    )


def test_mapping_normalizes_structured_spatial_matches():
    frame = observations_to_frame([_spatial_observation()])
    normalized, dataset_type = _normalize_rows(frame)

    assert dataset_type == "research_observations"
    matches = normalized.iloc[0]["_spatial_matches"]
    assert len(matches) == 1
    assert matches[0]["reference_layer"] == "American Spaces"
    assert matches[0]["reference_id"] == "as_bishkek"
    assert matches[0]["distance_km"] == 2.71


def test_popup_keeps_computed_proximity_separate_from_human_overlap():
    normalized, _ = _normalize_rows(observations_to_frame([_spatial_observation()]))
    popup = _popup_html(normalized.iloc[0], 2200)

    assert "U.S. overlap:" in popup
    assert "Analyst-reviewed shared audience" in popup
    assert "Computed proximity:" in popup
    assert "American Spaces: American Space Bishkek" in popup
    assert "2.7 km" in popup
    assert "0–5 km" in popup
    assert "same city" in popup


def test_map_surfaces_computed_proximity_without_relabeling_it_as_overlap(tmp_path: Path):
    frame = observations_to_frame([_spatial_observation()])
    output = tmp_path / "spatial_map.html"

    create_map(frame, output)

    text = output.read_text(encoding="utf-8")
    assert "observations with computed reference proximity" in text
    assert "Computed proximity:" in text
    assert "Computed proximity only" in text
    assert "not a strategic-overlap finding" in text


def test_export_upgrades_legacy_schema_rows_to_current_schema():
    observation = _spatial_observation()
    observation.schema_version = "1.0"

    frame = observations_to_frame([observation])

    assert frame.iloc[0]["schema_version"] == "1.1"
    stored = json.loads(frame.iloc[0]["spatial_matches"])
    assert stored[0]["reference_id"] == "as_bishkek"
