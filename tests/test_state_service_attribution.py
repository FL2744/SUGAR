from __future__ import annotations

from dataclasses import asdict

import pytest

from sugar_core.observations import ResearchObservation
from sugar_core.state_schema import (
    StateAssessment,
    USOverlapAssessment,
    USPresenceSite,
    USServiceSourceAttribution,
)
from sugar_core.state_workflow import (
    assess_us_overlap,
    build_review_queue,
    compare_state_snapshots,
    load_state_assessments,
    save_state_assessments,
    state_geojson,
)


def observation() -> ResearchObservation:
    return ResearchObservation(
        observation_type="program",
        title="University advising activity",
        summary="Public reporting describes a university-facing activity.",
        country="Kyrgyzstan",
        city="Bishkek",
        latitude=42.8746,
        longitude=74.5698,
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
        source_url="https://americanspaces.example/bishkek",
        delivery_mode="physical",
        coverage_scope="site",
        location_precision="site",
    )


def virtual_educationusa() -> USPresenceSite:
    return USPresenceSite(
        name="EducationUSA Kyrgyzstan",
        network="educationusa",
        country="Kyrgyzstan",
        service_tags=["educationusa", "study_in_the_us", "higher_education"],
        source_url="https://educationusa.example/kyrgyzstan",
        delivery_mode="virtual",
        coverage_scope="country",
    )


def assessed_overlap() -> tuple[ResearchObservation, StateAssessment]:
    obs = observation()
    assessment = StateAssessment(
        observation_id=obs.observation_id,
        strategic_audiences=["students"],
        program_domains=["higher_education"],
    )
    assessment.us_overlap = assess_us_overlap(
        obs,
        assessment,
        [physical_space(), virtual_educationusa()],
    )
    return obs, assessment


def test_service_sources_separate_program_matches_from_audience_matches():
    _, assessment = assessed_overlap()
    overlap = assessment.us_overlap
    sources = {source.name: source for source in overlap.service_sources}

    assert set(sources) == {"American Space Bishkek", "EducationUSA Kyrgyzstan"}
    assert overlap.service_overlap == ["educationusa", "higher_education", "study_in_the_us"]

    american_space = sources["American Space Bishkek"]
    assert american_space.program_service_matches == []
    assert american_space.audience_service_matches == ["english_language"]
    assert "english_language" not in overlap.service_overlap

    educationusa = sources["EducationUSA Kyrgyzstan"]
    assert educationusa.program_service_matches == ["educationusa", "higher_education", "study_in_the_us"]
    assert educationusa.audience_service_matches == ["educationusa"]
    assert educationusa.delivery_mode == "virtual"
    assert educationusa.coverage_scope == "country"
    assert educationusa.source_url == "https://educationusa.example/kyrgyzstan"


def test_service_source_attribution_round_trips_through_state_jsonl(tmp_path):
    _, assessment = assessed_overlap()
    path = tmp_path / "state.jsonl"

    save_state_assessments([assessment], path)
    restored = load_state_assessments(path)[0]

    assert restored.schema_version == "1.2"
    assert restored.us_overlap.service_source_ids == assessment.us_overlap.service_source_ids
    assert [asdict(source) for source in restored.us_overlap.service_sources] == [
        asdict(source) for source in assessment.us_overlap.service_sources
    ]
    assert restored.fingerprint() == assessment.fingerprint()


def test_review_queue_exposes_service_source_ids_and_names_without_parsing_note():
    obs, assessment = assessed_overlap()
    row = build_review_queue([obs], [assessment])[0]

    assert row["us_service_source_ids"] == "; ".join(assessment.us_overlap.service_source_ids)
    assert row["us_service_source_names"] == "American Space Bishkek; EducationUSA Kyrgyzstan"


def test_geojson_carries_structured_service_source_attribution():
    obs, assessment = assessed_overlap()
    geojson = state_geojson([obs], [assessment], verified_only=False)
    observation_feature = next(
        feature for feature in geojson["features"] if feature["properties"]["layer"] == "prc_observation"
    )

    sources = observation_feature["properties"]["us_service_sources"]
    assert {source["name"] for source in sources} == {"American Space Bishkek", "EducationUSA Kyrgyzstan"}
    assert next(source for source in sources if source["name"] == "American Space Bishkek")[
        "program_service_matches"
    ] == []


def test_snapshot_change_detection_marks_service_provenance_as_us_overlap():
    source = USServiceSourceAttribution(
        site_id="us_service_1",
        name="EducationUSA Kyrgyzstan",
        network="educationusa",
        delivery_mode="virtual",
        coverage_scope="country",
        source_url="https://example.gov/old",
        program_service_matches=["educationusa"],
    )
    left = StateAssessment(
        observation_id="obs_same",
        us_overlap=USOverlapAssessment(
            thematic_overlap=["higher_education"],
            service_overlap=["educationusa"],
            service_sources=[source],
        ),
    )
    right = StateAssessment(
        observation_id="obs_same",
        us_overlap=USOverlapAssessment(
            thematic_overlap=["higher_education"],
            service_overlap=["educationusa"],
            service_sources=[
                USServiceSourceAttribution(
                    site_id="us_service_1",
                    name="EducationUSA Kyrgyzstan",
                    network="educationusa",
                    delivery_mode="virtual",
                    coverage_scope="country",
                    source_url="https://example.gov/current",
                    program_service_matches=["educationusa"],
                )
            ],
        ),
    )

    changed = compare_state_snapshots([left], [right])["changed"]
    assert changed == [{"observation_id": "obs_same", "changed_fields": ["us_overlap"]}]


def test_program_source_matches_cannot_exceed_direct_service_overlap():
    with pytest.raises(ValueError, match="must also appear in direct service_overlap"):
        USOverlapAssessment(
            thematic_overlap=["higher_education"],
            service_overlap=["educationusa"],
            service_sources=[
                USServiceSourceAttribution(
                    site_id="us_service_1",
                    name="EducationUSA Kyrgyzstan",
                    network="educationusa",
                    delivery_mode="virtual",
                    coverage_scope="country",
                    program_service_matches=["higher_education"],
                )
            ],
        )


def test_service_source_attribution_requires_a_real_contribution():
    with pytest.raises(ValueError, match="requires a program or audience service match"):
        USServiceSourceAttribution(
            site_id="us_service_1",
            name="EducationUSA Kyrgyzstan",
            network="educationusa",
            delivery_mode="virtual",
            coverage_scope="country",
        )
