from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sugar_core.observation_storage import load_observations, save_observations
from sugar_core.observations import ResearchObservation, SpatialMatch
from sugar_core.service import run_overlap
from sugar_core.spatial import (
    SpatialOverlapConfig,
    analyze_spatial_overlap,
    distance_band,
    haversine_km,
    reference_points_from_frame,
)


def _observation(
    observation_id: str,
    latitude: float | None,
    longitude: float | None,
    *,
    city: str = "Bishkek",
    country: str = "Kyrgyzstan",
    verification_state: str = "unreviewed",
    reviewer: str = "",
) -> ResearchObservation:
    return ResearchObservation(
        observation_id=observation_id,
        observation_type="program",
        title=f"Program {observation_id}",
        summary="Public program activity.",
        city=city,
        country=country,
        latitude=latitude,
        longitude=longitude,
        location_basis="source_stated",
        location_confidence=0.95 if latitude is not None else None,
        us_overlap=["manual analyst tag"],
        verification_state=verification_state,
        reviewer=reviewer,
    )


def _references() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": "as_bishkek",
                "name": "American Space Bishkek",
                "category": "American Space",
                "city": "Bishkek",
                "country": "Kyrgyzstan",
                "latitude": 42.876,
                "longitude": 74.603,
                "url": "https://example.test/bishkek",
            },
            {
                "id": "edu_osh",
                "name": "EducationUSA Osh",
                "category": "EducationUSA",
                "city": "Osh",
                "country": "Kyrgyzstan",
                "latitude": 40.514,
                "longitude": 72.816,
                "url": "https://example.test/osh",
            },
        ]
    )


def test_haversine_is_symmetric_and_reasonable():
    distance = haversine_km(42.8746, 74.5698, 42.876, 74.603)
    reverse = haversine_km(42.876, 74.603, 42.8746, 74.5698)
    assert distance == pytest.approx(reverse, rel=1e-12)
    assert distance == pytest.approx(2.71, abs=0.15)
    assert haversine_km(42.0, 74.0, 42.0, 74.0) == pytest.approx(0.0)


def test_distance_bands_are_boundary_inclusive():
    bands = (5, 25, 100, 250)
    assert distance_band(0, bands) == "0–5 km"
    assert distance_band(5, bands) == "0–5 km"
    assert distance_band(5.001, bands) == "5–25 km"
    assert distance_band(250, bands) == "100–250 km"
    assert distance_band(251, bands) == ">250 km"


def test_reference_normalization_filters_bad_coordinates_and_deduplicates():
    frame = _references()
    frame.loc[len(frame)] = {
        "id": "bad",
        "name": "Bad point",
        "latitude": 200,
        "longitude": 400,
    }
    frame.loc[len(frame)] = frame.iloc[0].to_dict()
    points = reference_points_from_frame(frame, "American Spaces")
    assert len(points) == 2
    assert points[0].layer == "American Spaces"
    assert points[0].reference_id == "as_bishkek"


def test_spatial_analysis_keeps_computed_proximity_separate_from_manual_overlap():
    observations = [
        _observation("obs_a", 42.8746, 74.5698),
        _observation("obs_unmapped", None, None),
        _observation(
            "obs_rejected",
            42.8746,
            74.5698,
            verification_state="rejected",
            reviewer="Analyst",
        ),
    ]
    enriched, matches, summary = analyze_spatial_overlap(
        observations,
        [("U.S. Public Diplomacy", _references())],
        config=SpatialOverlapConfig(distance_bands_km=(5, 25, 100, 250), stored_matches_per_observation=2),
    )

    first = enriched[0]
    assert first.us_overlap == ["manual analyst tag"]
    assert first.spatial_matches
    nearest = first.spatial_matches[0]
    assert nearest.reference_name == "American Space Bishkek"
    assert nearest.distance_km == pytest.approx(2.71, abs=0.2)
    assert nearest.distance_band == "0–5 km"
    assert nearest.same_city is True
    assert nearest.same_country is True
    assert summary["observations_total"] == 3
    assert summary["observations_analyzed"] == 1
    assert summary["observations_matched"] == 1
    assert summary["observations_unmapped"] == 1
    assert summary["rejected_skipped"] == 1
    assert summary["nearest_band_counts"]["0–5 km"] == 1
    assert set(matches["observation_id"]) == {"obs_a"}


def test_full_match_table_can_exceed_portable_top_k():
    references = pd.DataFrame(
        [
            {"id": f"r{i}", "name": f"Reference {i}", "latitude": 42.8746, "longitude": 74.5698 + i * 0.001}
            for i in range(1, 7)
        ]
    )
    observations = [_observation("obs_a", 42.8746, 74.5698)]
    enriched, matches, summary = analyze_spatial_overlap(
        observations,
        [("Reference Network", references)],
        config=SpatialOverlapConfig(max_distance_km=25, stored_matches_per_observation=2),
    )
    assert len(matches) == 6
    assert len(enriched[0].spatial_matches) == 2
    assert summary["retained_pair_matches"] == 6


def test_spatial_match_round_trip_through_observation_storage(tmp_path: Path):
    observation = _observation("obs_a", 42.8746, 74.5698)
    observation.spatial_matches = [
        SpatialMatch(
            reference_layer="American Spaces",
            reference_id="as_bishkek",
            reference_name="American Space Bishkek",
            reference_category="American Space",
            distance_km=2.7,
            distance_band="0–5 km",
            same_city=True,
            same_country=True,
            latitude=42.876,
            longitude=74.603,
            source_url="https://example.test/bishkek",
        )
    ]
    output = tmp_path / "observations.csv"
    save_observations([observation], output)
    loaded = load_observations(output)
    assert loaded[0].nearest_spatial_match is not None
    assert loaded[0].nearest_spatial_match.reference_id == "as_bishkek"
    assert loaded[0].nearest_spatial_match.distance_km == pytest.approx(2.7)
    assert loaded[0].schema_version == "1.1"


def test_run_overlap_writes_enriched_dataset_match_table_summary_and_map(tmp_path: Path):
    source = tmp_path / "observations.csv"
    references = tmp_path / "american_spaces.csv"
    output = tmp_path / "observations_spatial.csv"
    save_observations([_observation("obs_a", 42.8746, 74.5698)], source)
    _references().to_csv(references, index=False)

    outputs = run_overlap(
        {
            "source_file": str(source),
            "output_file": str(output),
            "spatial": {
                "reference_layers": [{"name": "American Spaces", "file": str(references)}],
                "distance_bands_km": [5, 25, 100, 250],
                "stored_matches_per_observation": 3,
                "create_map": True,
            },
        }
    )

    expected = {
        str(output.resolve()),
        str(output.with_suffix(".xlsx").resolve()),
        str(output.with_suffix(".metadata.json").resolve()),
        str(tmp_path / "observations_spatial_matches.csv"),
        str(tmp_path / "observations_spatial_matches.xlsx"),
        str(tmp_path / "observations_spatial_summary.json"),
        str(tmp_path / "observations_spatial_map.html"),
    }
    assert set(outputs) == expected
    for path in expected:
        assert Path(path).exists()

    enriched = load_observations(output)
    assert enriched[0].nearest_spatial_match.reference_name == "American Space Bishkek"
    summary = json.loads((tmp_path / "observations_spatial_summary.json").read_text(encoding="utf-8"))
    assert summary["observations_matched"] == 1
    assert "not evidence" in summary["interpretation"].casefold()
