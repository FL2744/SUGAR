from datetime import datetime, timezone

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_freshness import build_freshness_report
from sugar_core.state_schema import StateAssessment


def test_freshness_separates_current_activity_from_background_and_collection_age():
    current = ResearchObservation(
        observation_type="program",
        title="Current program",
        summary="Current evidence",
        observed_at="2026-06-01T12:00:00Z",
        evidence=[EvidenceReference(url="https://example.org/current", collected_at="2026-08-01T12:00:00Z")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    historical = ResearchObservation(
        observation_type="institution",
        title="Historical relationship",
        summary="Historical evidence",
        observed_at="2022-01-01T12:00:00Z",
        evidence=[EvidenceReference(url="https://example.org/history", collected_at="2025-01-01T12:00:00Z")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    current_assessment = StateAssessment(
        observation_id=current.observation_id,
        review_state="human_verified",
        reviewer="analyst",
    )
    historical_assessment = StateAssessment(
        observation_id=historical.observation_id,
        review_state="human_verified",
        reviewer="analyst",
    )
    report = build_freshness_report(
        [current, historical],
        [current_assessment, historical_assessment],
        now=datetime(2026, 9, 13, tzinfo=timezone.utc),
        collection_stale_days=90,
    )
    assert report["current_period_verified"] == 1
    assert report["pre_period_observations"] == 1
    assert report["stale_collection_observations"] == 1
    assert "do not invalidate older evidence" in report["guardrail"]
