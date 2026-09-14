from pathlib import Path

from sugar_core.observations import ResearchObservation
from sugar_core.state_location import resolve_observation_location
from sugar_core.utils import JsonCache


def test_recorded_coordinates_preserve_location_but_expose_precision():
    observation = ResearchObservation(
        observation_type="event",
        summary="Event at a recorded campus location.",
        city="Bishkek",
        country="Kyrgyzstan",
        latitude=42.875,
        longitude=74.612,
        location_basis="institution_site",
        location_confidence=0.91,
    )

    resolved = resolve_observation_location(observation)

    assert resolved.resolved is True
    assert resolved.precision == "site"
    assert resolved.source == "recorded_coordinates"
    assert resolved.confidence == 0.91
    assert resolved.density_eligible is True


def test_missing_city_coordinates_can_be_resolved_without_false_site_precision(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="program",
        summary="Program reported in Bishkek.",
        city="Bishkek",
        country="Kyrgyzstan",
        location_basis="reported_city",
        location_confidence=0.8,
    )
    queries = []

    def fake_geocoder(query, cache):
        queries.append(query)
        return {
            "latitude": 42.8746,
            "longitude": 74.5698,
            "display_name": "Bishkek, Kyrgyzstan",
            "boundingbox": [42.75, 43.0, 74.4, 74.75],
            "type": "city",
            "addresstype": "city",
            "category": "place",
        }

    resolved = resolve_observation_location(
        observation,
        cache=JsonCache(tmp_path / "geo.json"),
        geocoder=fake_geocoder,
        resolve_missing=True,
    )

    assert queries == ["Bishkek, Kyrgyzstan"]
    assert resolved.resolved is True
    assert resolved.precision == "city"
    assert resolved.derived is True
    assert resolved.source == "geocoded_city"
    assert resolved.uncertainty_km > 1
    assert resolved.density_eligible is True


def test_site_query_is_downgraded_when_provider_only_returns_city(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="event",
        summary="Event reported at a named venue.",
        location_label="Example Cultural Center",
        city="Nairobi",
        country="Kenya",
        location_basis="venue",
        location_confidence=0.9,
    )

    def fake_geocoder(query, cache):
        return {
            "latitude": -1.2864,
            "longitude": 36.8172,
            "display_name": "Nairobi, Kenya",
            "type": "city",
            "addresstype": "city",
            "category": "place",
        }

    resolved = resolve_observation_location(
        observation,
        cache=JsonCache(tmp_path / "geo.json"),
        geocoder=fake_geocoder,
        resolve_missing=True,
    )

    assert resolved.resolved is True
    assert resolved.query.startswith("Example Cultural Center")
    assert resolved.precision == "city"
    assert resolved.confidence <= 0.75
    assert resolved.provider_type == "city"


def test_country_level_provider_result_is_rejected_for_city_query(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="program",
        summary="Program reported in a city.",
        city="Ambiguous Place",
        country="Kenya",
        location_basis="reported_city",
    )

    def fake_geocoder(query, cache):
        return {
            "latitude": 0.0236,
            "longitude": 37.9062,
            "display_name": "Kenya",
            "type": "country",
            "addresstype": "country",
            "category": "boundary",
        }

    resolved = resolve_observation_location(
        observation,
        cache=JsonCache(tmp_path / "geo.json"),
        geocoder=fake_geocoder,
        resolve_missing=True,
    )

    assert resolved.resolved is False
    assert resolved.source == "geocode_no_match"


def test_institution_name_is_not_used_as_venue_without_location_basis(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="event",
        summary="An event involving a university, with only city-level location evidence.",
        institution_name="Example University",
        city="Nairobi",
        country="Kenya",
        location_basis="reported_city",
    )
    queries = []

    def fake_geocoder(query, cache):
        queries.append(query)
        return {"latitude": -1.2864, "longitude": 36.8172, "display_name": "Nairobi, Kenya"}

    resolved = resolve_observation_location(
        observation,
        cache=JsonCache(tmp_path / "geo.json"),
        geocoder=fake_geocoder,
        resolve_missing=True,
    )

    assert queries == ["Nairobi, Kenya"]
    assert "Example University" not in resolved.query
    assert resolved.precision == "city"


def test_country_only_location_is_not_mapped_to_false_centroid(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="program",
        summary="Country-level program with no subnational location evidence.",
        country="Kenya",
        location_basis="country",
    )
    calls = []

    def fake_geocoder(query, cache):
        calls.append(query)
        raise AssertionError("country-only records should not be geocoded to a centroid")

    resolved = resolve_observation_location(
        observation,
        cache=JsonCache(tmp_path / "geo.json"),
        geocoder=fake_geocoder,
        resolve_missing=True,
    )

    assert resolved.resolved is False
    assert calls == []
    assert "national centroid" in resolved.unresolved_reason


def test_partial_coordinate_pair_fails_closed():
    observation = ResearchObservation(
        observation_type="event",
        summary="Malformed coordinate record.",
        city="Nairobi",
        country="Kenya",
        latitude=-1.2864,
        longitude=None,
    )

    resolved = resolve_observation_location(observation)

    assert resolved.resolved is False
    assert resolved.source == "invalid_coordinates"
    assert "Only one coordinate" in resolved.unresolved_reason
