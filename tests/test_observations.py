from __future__ import annotations

import json

import pytest

from sugar_core.models import PostRecord
from sugar_core.observation_storage import load_observations, observations_to_frame, save_observations
from sugar_core.observations import EvidenceReference, ResearchObservation, observation_from_post


def test_post_conversion_preserves_source_and_location_provenance():
    post = PostRecord(
        platform="bluesky",
        native_id="abc123",
        canonical_url="https://bsky.app/profile/example/post/abc123",
        query="confucius institute",
        query_matches=["confucius institute"],
        published_at="2026-09-10T12:00:00Z",
        author_handle="example.bsky.social",
        author_name="Example Institution",
        original_text="Public event announcement",
        translated_text="Public event announcement",
        inferred_location="Bishkek, Kyrgyzstan",
        location_confidence=0.82,
        location_source="explicit place mention",
        latitude=42.8746,
        longitude=74.5698,
    )

    observation = observation_from_post(post)

    assert observation.observation_type == "digital_post"
    assert observation.location_label == "Bishkek, Kyrgyzstan"
    assert observation.location_basis == "ai_inferred"
    assert observation.location_confidence == pytest.approx(0.82)
    assert observation.source_record_keys == ["bluesky:abc123"]
    assert observation.primary_source_url == post.canonical_url
    assert observation.evidence[0].platform == "bluesky"
    assert observation.evidence[0].native_id == "abc123"


def test_observation_id_is_stable_for_same_evidence():
    evidence = EvidenceReference(
        url="https://example.org/program/1",
        source_type="official",
        published_at="2026-09-01",
    )
    first = ResearchObservation(
        observation_type="program",
        summary="Program activity observed.",
        program_name="Example Program",
        evidence=[evidence],
    )
    second = ResearchObservation(
        observation_type="program",
        summary="Program activity observed.",
        program_name="Example Program",
        evidence=[evidence],
    )
    assert first.observation_id == second.observation_id


def test_human_verification_requires_reviewer_and_can_be_reopened():
    observation = ResearchObservation(
        observation_type="event",
        summary="A public event was advertised.",
        evidence=[EvidenceReference(url="https://example.org/event")],
    )

    observation.set_ai_triage(labels=["education", "students"], confidence=0.77, model="test-model")
    assert observation.verification_state == "ai_triaged"
    assert observation.triage_labels == ["education", "students"]

    with pytest.raises(ValueError, match="requires a reviewer"):
        observation.transition_verification("human_verified")

    observation.transition_verification("human_verified", reviewer="Analyst A", notes="Confirmed in source.")
    assert observation.verification_state == "human_verified"
    assert observation.reviewer == "Analyst A"
    assert observation.reviewed_at

    observation.transition_verification("needs_followup", reviewer="Analyst B", notes="New contradictory source.")
    assert observation.verification_state == "needs_followup"


def test_invalid_confidence_and_transition_are_rejected():
    with pytest.raises(ValueError, match="between 0 and 1"):
        ResearchObservation(
            observation_type="institution",
            summary="Institution observed.",
            ai_confidence=1.2,
        )

    observation = ResearchObservation(observation_type="institution", summary="Institution observed.")
    observation.transition_verification("human_verified", reviewer="Analyst")
    with pytest.raises(ValueError, match="Invalid verification transition"):
        observation.transition_verification("rejected", reviewer="Analyst")


def test_observation_frame_keeps_numeric_confidence_and_coordinates():
    observation = ResearchObservation(
        observation_type="institution",
        summary="Institution observed.",
        location_label="Bishkek, Kyrgyzstan",
        latitude=42.8746,
        longitude=74.5698,
        location_confidence=0.91,
        ai_confidence=0.73,
    )
    frame = observations_to_frame([observation])
    assert frame.loc[0, "latitude"] == pytest.approx(42.8746)
    assert frame.loc[0, "longitude"] == pytest.approx(74.5698)
    assert frame.loc[0, "location_confidence"] == pytest.approx(0.91)
    assert frame.loc[0, "ai_confidence"] == pytest.approx(0.73)


def test_observation_storage_round_trip(tmp_path):
    observation = ResearchObservation(
        observation_type="program",
        summary="Technical training program advertised to university students.",
        title="Example technical program",
        country="Kyrgyzstan",
        city="Bishkek",
        institution_name="Example Center",
        program_name="Technical Training",
        actors=["Example Center", "Partner University"],
        audiences=["university students"],
        themes=["technology", "education"],
        us_overlap=["EducationUSA"],
        evidence=[EvidenceReference(url="https://example.org/program", source_type="official")],
    )
    observation.set_ai_triage(labels=["strategic_audience"], confidence=0.8, model="test-model")
    observation.transition_verification("human_verified", reviewer="Analyst", notes="Source reviewed.")

    target = tmp_path / "observations.csv"
    save_observations([observation], target, metadata={"project": "test"})
    loaded = load_observations(target)

    assert len(loaded) == 1
    restored = loaded[0]
    assert restored.observation_id == observation.observation_id
    assert restored.actors == ["Example Center", "Partner University"]
    assert restored.audiences == ["university students"]
    assert restored.themes == ["technology", "education"]
    assert restored.us_overlap == ["EducationUSA"]
    assert restored.verification_state == "human_verified"
    assert restored.reviewer == "Analyst"
    assert restored.evidence[0].url == "https://example.org/program"

    metadata = json.loads(target.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert metadata["dataset_type"] == "research_observations"
    assert metadata["project"] == "test"
