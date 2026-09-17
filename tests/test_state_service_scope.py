from __future__ import annotations

import csv
from pathlib import Path

from sugar_core.observations import ObservationLocation, ResearchObservation
from sugar_core.state_schema import StateAssessment, USPresenceSite
from sugar_core.state_workflow import (
    assess_us_overlap,
    load_us_presence_sites,
    state_geojson,
    write_us_presence_template,
)


def observation(
    *,
    country: str = "Kyrgyzstan",
    city: str = "Bishkek",
    lat: float = 42.8746,
    lon: float = 74.5698,
    locations: list[ObservationLocation] | None = None,
) -> ResearchObservation:
    return ResearchObservation(
        observation_type="program",
        title="University advising activity",
        summary="Public reporting describes a university-facing activity.",
        country=country,
        city=city,
        latitude=lat,
        longitude=lon,
        locations=locations or [],
    )


def physical_space() -> USPresenceSite:
    return USPresenceSite(
        name="American Space Bishkek",
        network="american_space",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.88,
        longitude=74.60,
        service_tags=["culture", "english_language"],
        delivery_mode="physical",
        coverage_scope="site",
        location_precision="site",
        location_uncertainty_km=0.5,
    )


def virtual_educationusa() -> USPresenceSite:
    return USPresenceSite(
        name="EducationUSA Kyrgyzstan",
        network="educationusa",
        country="Kyrgyzstan",
        service_tags=["educationusa", "study_in_the_us", "higher_education"],
        delivery_mode="virtual",
        coverage_scope="country",
        location_basis="official_service_directory_nonspatial",
    )


def test_country_virtual_service_contributes_without_becoming_nearest_site():
    obs = observation()
    assessment = StateAssessment(
        observation_id=obs.observation_id,
        strategic_audiences=["students"],
        program_domains=["higher_education"],
    )
    overlap = assess_us_overlap(obs, assessment, [physical_space(), virtual_educationusa()])

    assert overlap.nearest_site_name == "American Space Bishkek"
    assert overlap.distance_km is not None
    assert "higher_education" in overlap.thematic_overlap
    assert "educationusa" in overlap.service_overlap
    assert "students" in overlap.audience_overlap
    assert "EducationUSA Kyrgyzstan [virtual/country]" in overlap.note


def test_country_virtual_service_does_not_leak_across_countries():
    obs = observation(country="Kazakhstan", city="Almaty", lat=43.2389, lon=76.8897)
    assessment = StateAssessment(observation_id=obs.observation_id, program_domains=["higher_education"])
    overlap = assess_us_overlap(obs, assessment, [virtual_educationusa()])

    assert overlap.nearest_site_id == ""
    assert overlap.service_overlap == []
    assert overlap.thematic_overlap == []


def test_global_virtual_service_applies_across_countries():
    obs = observation(country="Kazakhstan", city="Almaty", lat=43.2389, lon=76.8897)
    assessment = StateAssessment(observation_id=obs.observation_id, program_domains=["higher_education"])
    global_service = USPresenceSite(
        name="Global EducationUSA service",
        network="educationusa",
        country="United States",
        service_tags=["educationusa", "higher_education"],
        delivery_mode="virtual",
        coverage_scope="global",
    )
    overlap = assess_us_overlap(obs, assessment, [global_service])

    assert overlap.nearest_site_id == ""
    assert overlap.service_overlap == ["educationusa", "higher_education"]
    assert overlap.thematic_overlap == ["higher_education"]
    assert "Global EducationUSA service [virtual/global]" in overlap.note


def test_city_and_site_scopes_fail_closed_when_not_geographically_applicable():
    obs = observation(city="Bishkek")
    assessment = StateAssessment(observation_id=obs.observation_id, program_domains=["entrepreneurship"])
    city_service = USPresenceSite(
        name="Osh city entrepreneurship service",
        network="american_space",
        country="Kyrgyzstan",
        city="Osh",
        service_tags=["entrepreneurship"],
        delivery_mode="virtual",
        coverage_scope="city",
    )
    distant_site = USPresenceSite(
        name="Distant site program",
        network="american_space",
        country="Kyrgyzstan",
        city="Osh",
        latitude=40.5140,
        longitude=72.8161,
        service_tags=["entrepreneurship"],
        delivery_mode="physical",
        coverage_scope="site",
    )
    overlap = assess_us_overlap(obs, assessment, [city_service, distant_site], nearby_km=50.0)

    assert overlap.service_overlap == []
    assert overlap.thematic_overlap == []


def test_structured_locations_supersede_stale_summary_city_for_service_scope():
    obs = observation(
        city="Bishkek",
        locations=[
            ObservationLocation(
                label="Osh venue",
                country="Kyrgyzstan",
                city="Osh",
                precision="city",
                basis="source_stated",
            )
        ],
    )
    assessment = StateAssessment(observation_id=obs.observation_id, program_domains=["entrepreneurship"])
    bishkek_service = USPresenceSite(
        name="Bishkek city entrepreneurship service",
        network="american_space",
        country="Kyrgyzstan",
        city="Bishkek",
        service_tags=["entrepreneurship"],
        delivery_mode="virtual",
        coverage_scope="city",
    )
    osh_service = USPresenceSite(
        name="Osh city entrepreneurship service",
        network="american_space",
        country="Kyrgyzstan",
        city="Osh",
        service_tags=["entrepreneurship"],
        delivery_mode="virtual",
        coverage_scope="city",
    )

    overlap = assess_us_overlap(obs, assessment, [bishkek_service, osh_service])

    assert overlap.service_overlap == ["entrepreneurship"]
    assert "Osh city entrepreneurship service [virtual/city]" in overlap.note
    assert "Bishkek city entrepreneurship service" not in overlap.note


def test_multi_country_structured_locations_union_applicable_service_sources():
    obs = observation(
        locations=[
            ObservationLocation(
                label="Bishkek venue",
                country="Kyrgyzstan",
                city="Bishkek",
                precision="city",
                basis="source_stated",
            ),
            ObservationLocation(
                label="Almaty venue",
                country="Kazakhstan",
                city="Almaty",
                precision="city",
                basis="source_stated",
            ),
        ]
    )
    assessment = StateAssessment(
        observation_id=obs.observation_id,
        program_domains=["higher_education", "entrepreneurship"],
    )
    kg_service = USPresenceSite(
        name="EducationUSA Kyrgyzstan",
        network="educationusa",
        country="Kyrgyzstan",
        service_tags=["educationusa"],
        delivery_mode="virtual",
        coverage_scope="country",
    )
    kz_service = USPresenceSite(
        name="Almaty entrepreneurship service",
        network="american_space",
        country="Kazakhstan",
        city="Almaty",
        service_tags=["entrepreneurship"],
        delivery_mode="virtual",
        coverage_scope="city",
    )

    overlap = assess_us_overlap(obs, assessment, [kg_service, kz_service])

    assert overlap.service_overlap == ["educationusa", "entrepreneurship"]
    assert "EducationUSA Kyrgyzstan [virtual/country]" in overlap.note
    assert "Almaty entrepreneurship service [virtual/city]" in overlap.note
    assert "2 structured activity locations" in overlap.note


def test_nearest_physical_site_uses_structured_location_coordinates_not_summary_point():
    obs = observation(
        locations=[
            ObservationLocation(
                label="Osh venue",
                country="Kyrgyzstan",
                city="Osh",
                latitude=40.53347,
                longitude=72.792545,
                precision="site",
                basis="source_stated",
            )
        ]
    )
    osh_space = USPresenceSite(
        name="American Corner Osh",
        network="american_space",
        country="Kyrgyzstan",
        city="Osh",
        latitude=40.53347,
        longitude=72.792545,
        service_tags=["culture"],
        delivery_mode="physical",
        coverage_scope="site",
        location_precision="site",
    )

    overlap = assess_us_overlap(obs, StateAssessment(observation_id=obs.observation_id), [physical_space(), osh_space])

    assert overlap.nearest_site_name == "American Corner Osh"
    assert overlap.distance_km == 0.0


def test_site_scope_distance_does_not_borrow_coordinates_from_other_country_location():
    obs = observation(
        locations=[
            ObservationLocation(
                label="Osh venue",
                country="Kyrgyzstan",
                city="Osh",
                precision="city",
                basis="source_stated",
            ),
            ObservationLocation(
                label="Korday venue",
                country="Kazakhstan",
                city="Korday",
                latitude=43.0339,
                longitude=74.7129,
                precision="site",
                basis="source_stated",
            ),
        ]
    )
    assessment = StateAssessment(observation_id=obs.observation_id, program_domains=["entrepreneurship"])
    bishkek_site_service = USPresenceSite(
        name="Bishkek site entrepreneurship service",
        network="american_space",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.88,
        longitude=74.60,
        service_tags=["entrepreneurship"],
        delivery_mode="physical",
        coverage_scope="site",
        location_precision="site",
    )

    overlap = assess_us_overlap(obs, assessment, [bishkek_site_service], nearby_km=50.0)

    assert overlap.service_overlap == []
    assert overlap.thematic_overlap == []


def test_virtual_service_with_incidental_coordinate_is_not_emitted_as_geojson_point():
    obs = observation()
    assessment = StateAssessment(observation_id=obs.observation_id, review_state="ai_triaged")
    virtual = virtual_educationusa()
    virtual.latitude = 42.87
    virtual.longitude = 74.60
    geojson = state_geojson([obs], [assessment], [virtual], verified_only=False)
    assert [feature["properties"]["layer"] for feature in geojson["features"]] == ["prc_observation"]


def test_us_presence_loader_reads_scope_and_precision_fields(tmp_path: Path):
    path = tmp_path / "us-presence.csv"
    fields = [
        "name",
        "network",
        "country",
        "city",
        "latitude",
        "longitude",
        "service_tags",
        "delivery_mode",
        "coverage_scope",
        "location_precision",
        "location_confidence",
        "location_uncertainty_km",
        "location_basis",
        "source_url",
        "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "name": "EducationUSA Kyrgyzstan",
                "network": "educationusa",
                "country": "Kyrgyzstan",
                "city": "",
                "latitude": "",
                "longitude": "",
                "service_tags": "educationusa;higher_education",
                "delivery_mode": "virtual",
                "coverage_scope": "country",
                "location_precision": "unknown",
                "location_confidence": "",
                "location_uncertainty_km": "",
                "location_basis": "official_service_directory_nonspatial",
                "source_url": "https://example.gov/edu",
                "status": "active",
            }
        )
    sites = load_us_presence_sites(path)
    assert len(sites) == 1
    site = sites[0]
    assert site.delivery_mode == "virtual"
    assert site.coverage_scope == "country"
    assert not site.is_spatial
    assert site.location_basis == "official_service_directory_nonspatial"


def test_us_presence_template_exposes_scope_and_precision_columns(tmp_path: Path):
    path = Path(write_us_presence_template(tmp_path / "us-presence.csv"))
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert {row["delivery_mode"] for row in rows} == {"physical", "virtual"}
    assert {row["coverage_scope"] for row in rows} == {"site", "country"}
    assert "location_uncertainty_km" in rows[0]
