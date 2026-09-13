import pytest

from sugar_core.state_schema import AnalyticClaim, StateAssessment, SupportAssessment


def test_confirmed_prc_support_requires_evidence_and_human_review():
    with pytest.raises(ValueError, match="explicit evidence"):
        SupportAssessment(level="confirmed", review_state="human_verified", reviewer="analyst")

    with pytest.raises(ValueError, match="human verification"):
        SupportAssessment(
            level="confirmed",
            bases=["official_prc_source"],
            evidence_refs=["https://example.org/source"],
            review_state="ai_triaged",
        )

    support = SupportAssessment(
        level="confirmed",
        bases=["official_prc_source"],
        evidence_refs=["https://example.org/source"],
        review_state="human_verified",
        reviewer="analyst",
    )
    assert support.level == "confirmed"


def test_influence_cannot_be_encoded_as_simple_observed_fact():
    with pytest.raises(ValueError, match="simple observed fact"):
        AnalyticClaim(
            statement="The program influenced participants.",
            claim_type="influence",
            epistemic_status="observed_fact",
            evidence_refs=["https://example.org/source"],
        )


def test_high_consequence_claims_require_evidence_references():
    for claim_type in ("support_relationship", "coordination", "influence"):
        with pytest.raises(ValueError, match="explicit evidence"):
            AnalyticClaim(
                statement=f"Test {claim_type}",
                claim_type=claim_type,
                epistemic_status="analytic_assessment",
            )


def test_state_assessment_is_not_brief_eligible_until_human_verified():
    assessment = StateAssessment(observation_id="obs_123", review_state="ai_triaged")
    assert not assessment.brief_eligible

    verified = StateAssessment(
        observation_id="obs_456",
        review_state="human_verified",
        reviewer="analyst",
    )
    assert verified.brief_eligible
