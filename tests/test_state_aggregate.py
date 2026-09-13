from pathlib import Path

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_aggregate import build_state_rollups, save_state_rollups
from sugar_core.state_schema import ReachMetrics, StateAssessment


def test_rollups_count_only_verified_metrics_as_verified_activity(tmp_path: Path):
    verified_obs = ResearchObservation(
        observation_type="event",
        title="Verified event",
        summary="Verified event evidence",
        country="Kenya",
        city="Nairobi",
        evidence=[EvidenceReference(url="https://example.org/verified")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    pending_obs = ResearchObservation(
        observation_type="event",
        title="Pending event",
        summary="Pending event evidence",
        country="Kenya",
        city="Nairobi",
        evidence=[EvidenceReference(url="https://example.org/pending")],
    )
    verified = StateAssessment(
        observation_id=verified_obs.observation_id,
        strategic_audiences=["students"],
        program_domains=["entrepreneurship"],
        narrative_tags=["economic_opportunity"],
        reach=ReachMetrics(attendance=100, views=1000),
        review_state="human_verified",
        reviewer="analyst",
    )
    pending = StateAssessment(
        observation_id=pending_obs.observation_id,
        strategic_audiences=["students"],
        program_domains=["entrepreneurship"],
        reach=ReachMetrics(attendance=900, views=9000),
        review_state="ai_triaged",
    )
    payload = build_state_rollups([verified_obs, pending_obs], [verified, pending])
    kenya = payload["countries"][0]
    assert kenya["observations_total"] == 2
    assert kenya["observations_verified"] == 1
    assert kenya["reported_attendance_verified"] == 100
    assert kenya["views_verified"] == 1000
    assert "not an influence index" in payload["guardrail"]

    outputs = save_state_rollups([verified_obs, pending_obs], [verified, pending], tmp_path, name="kenya")
    assert len(outputs) == 3
    assert all(Path(path).is_file() for path in outputs)
