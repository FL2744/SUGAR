from __future__ import annotations

import pytest

from sugar_core.observations import ResearchObservation
from sugar_core.state_location import ResolvedLocation
from sugar_core.state_proximity import nearest_us_presence
from sugar_core.state_schema import StateAssessment, USOverlapAssessment, USPresenceSite


def test_language_education_is_first_class_without_implying_english():
    assessment = StateAssessment(
        observation_id="obs-language",
        program_domains=["language_education"],
    )
    assert assessment.program_domains == ["language_education"]


def test_direct_service_overlap_cannot_be_manufactured_from_audience_similarity():
    overlap = USOverlapAssessment(
        audience_overlap=["students"],
        thematic_overlap=["higher_education"],
        service_overlap=["educationusa", "english_language"],
    )
    assert overlap.audience_overlap == ["students"]
    assert overlap.thematic_overlap == ["higher_education"]
    assert overlap.service_overlap == ["educationusa"]


def test_service_overlap_fails_closed_without_programmatic_thematic_overlap():
    overlap = USOverlapAssessment(
        audience_overlap=["students"],
        thematic_overlap=[],
        service_overlap=["educationusa", "english_language"],
    )
    assert overlap.service_overlap == []
    assert overlap.audience_overlap == ["students"]


def test_us_presence_supports_virtual_national_service_without_fake_point():
    site = USPresenceSite(
        name="EducationUSA Example",
        network="educationusa",
        country="Example Country",
        service_tags=["educationusa", "higher_education"],
        delivery_mode="virtual",
        coverage_scope="country",
        location_basis="official_service_directory_nonspatial",
    )
    assert site.delivery_mode == "virtual"
    assert site.coverage_scope == "country"
    assert not site.is_spatial
    assert site.latitude is None and site.longitude is None


def test_us_presence_rejects_partial_coordinate_pairs():
    with pytest.raises(ValueError, match="both latitude and longitude"):
        USPresenceSite(
            name="Broken point",
            network="american_space",
            country="Example Country",
            latitude=1.0,
            longitude=None,
        )


def test_nearest_us_presence_uses_site_specific_uncertainty_and_ignores_virtual_points():
    observation = ResearchObservation(
        observation_type="event",
        title="Example activity",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.8746,
        longitude=74.5698,
    )
    location = ResolvedLocation(
        observation_id=observation.observation_id,
        latitude=42.8746,
        longitude=74.5698,
        precision="site",
        confidence=0.90,
        basis="source_named_site",
        label="Example activity",
        source="recorded",
        uncertainty_km=0.5,
    )
    virtual = USPresenceSite(
        name="Virtual service with incidental coordinates",
        network="educationusa",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.8747,
        longitude=74.5699,
        delivery_mode="virtual",
        coverage_scope="country",
        location_precision="site",
        location_uncertainty_km=0.1,
    )
    physical = USPresenceSite(
        name="Physical American Space",
        network="american_space",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.88,
        longitude=74.60,
        delivery_mode="physical",
        coverage_scope="site",
        location_precision="city",
        location_confidence=0.75,
        location_uncertainty_km=12.0,
        location_basis="city_centroid_reference_not_building",
    )

    proximity = nearest_us_presence(
        observation,
        location,
        [virtual, physical],
        threshold_km=50.0,
        site_uncertainty_km=0.75,
    )
    assert proximity is not None
    assert proximity.site_id == physical.site_id
    assert proximity.site_precision == "city"
    assert proximity.site_confidence == 0.75
    assert proximity.site_uncertainty_km == 12.0
    assert proximity.site_location_basis == "city_centroid_reference_not_building"


def test_site_precision_supplies_default_uncertainty_when_explicit_value_missing():
    site = USPresenceSite(
        name="Site-precise American Space",
        network="american_space",
        country="Example Country",
        latitude=10.0,
        longitude=20.0,
        location_precision="site",
    )
    assert site.effective_location_uncertainty_km(99.0) == 0.75
