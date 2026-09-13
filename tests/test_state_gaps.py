from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_entities import EntityRegistry, MonitoredEntity
from sugar_core.state_gaps import build_gap_report
from sugar_core.state_schema import StateAssessment, USPresenceSite


def test_gap_report_never_treats_missing_observation_as_no_activity():
    observation = ResearchObservation(
        observation_type="program",
        title="Known current program",
        summary="Known current program",
        observed_at="2026-06-01T12:00:00Z",
        country="Kyrgyzstan",
        city="Bishkek",
        evidence=[EvidenceReference(url="https://example.org/source", collected_at="2026-09-01T12:00:00Z")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        review_state="human_verified",
        reviewer="analyst",
    )
    registry = EntityRegistry(
        [
            MonitoredEntity(
                canonical_name="Unobserved Priority Institution",
                aliases=["UPI"],
                country="Kyrgyzstan",
                city="Osh",
                priority="high",
            )
        ]
    )
    site = USPresenceSite(
        name="American Space Osh",
        network="american_space",
        country="Kyrgyzstan",
        city="Osh",
    )
    report = build_gap_report([observation], [assessment], entities=registry, us_sites=[site])
    categories = {row["category"] for row in report["gaps"]}
    assert "entity_monitoring_gap" in categories
    assert "us_presence_comparison_gap" in categories
    assert "must never be reported as evidence that no activity exists" in report["guardrail"]
    assert any("not evidence that the entity is inactive" in row["reason"] for row in report["gaps"])
