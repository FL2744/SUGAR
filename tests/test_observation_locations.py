import json

import pytest

from sugar_core.observation_storage import load_observations, observations_to_frame, save_observations
from sugar_core.observations import EvidenceReference, ObservationLocation, ResearchObservation


def _multi_site_observation() -> ResearchObservation:
    return ResearchObservation(
        observation_type="event",
        title="Two-venue activity",
        summary="One activity was reported at two locations.",
        country="example_host_country",
        city="Bishkek",
        evidence=[EvidenceReference(url="https://example.org/activity")],
        locations=[
            ObservationLocation(
                label="Venue A",
                country="example_host_country",
                city="Bishkek",
                latitude=42.85,
                longitude=74.58,
                precision="site",
                confidence=0.9,
                uncertainty_km=0.75,
                basis="official_address",
                source_ref="https://example.org/a",
            ),
            ObservationLocation(
                label="Venue B campus unresolved",
                country="example_host_country",
                city="Bishkek",
                latitude=42.8746,
                longitude=74.5698,
                precision="city",
                confidence=0.75,
                uncertainty_km=12,
                basis="campus_unresolved_city_centroid",
                source_ref="https://example.org/activity",
            ),
        ],
    )


def test_observation_location_requires_complete_coordinates():
    with pytest.raises(ValueError, match="both latitude and longitude"):
        ObservationLocation(label="Broken", latitude=42.0)


def test_observation_location_ids_are_stable_and_deduplicated():
    first = ObservationLocation(label="Venue", city="Bishkek", country="example_host_country", latitude=42.85, longitude=74.58)
    second = ObservationLocation(label="Venue", city="Bishkek", country="example_host_country", latitude=42.85, longitude=74.58)
    observation = ResearchObservation(
        observation_type="event",
        summary="Duplicate location inputs.",
        locations=[first, second],
    )
    assert first.location_id == second.location_id
    assert len(observation.locations) == 1


def test_locations_export_as_structured_json_column():
    observation = _multi_site_observation()
    frame = observations_to_frame([observation])
    assert "locations" in frame.columns
    payload = json.loads(frame.loc[0, "locations"])
    assert len(payload) == 2
    assert payload[0]["precision"] == "site"
    assert payload[1]["precision"] == "city"
    assert payload[0]["source_ref"] == "https://example.org/a"


def test_multi_site_locations_round_trip_through_csv_and_xlsx(tmp_path):
    observation = _multi_site_observation()
    target = tmp_path / "observations.csv"
    save_observations([observation], target)

    csv_restored = load_observations(target)[0]
    xlsx_restored = load_observations(target.with_suffix(".xlsx"))[0]
    for restored in (csv_restored, xlsx_restored):
        assert restored.observation_id == observation.observation_id
        assert restored.schema_version == "1.4"
        assert len(restored.locations) == 2
        assert [item.location_id for item in restored.locations] == [
            item.location_id for item in observation.locations
        ]
        assert restored.locations[0].precision == "site"
        assert restored.locations[1].uncertainty_km == 12
