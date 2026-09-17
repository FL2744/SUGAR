from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_schema import AnalyticClaim, ReachMetrics, StateAssessment, SupportAssessment
from sugar_core.state_tradecraft import analytic_tensions, build_tradecraft_audit, source_adequacy_profile


def _observation(*, title="Case", verification_state="human_verified", evidence=None):
    return ResearchObservation(
        observation_type="program",
        title=title,
        summary=f"Evidence for {title}",
        observed_at="2026-08-01T12:00:00Z",
        country="Kyrgyzstan",
        city="Bishkek",
        evidence=evidence
        or [
            EvidenceReference(
                url="https://host.example/program",
                source_type="official_host_source",
                published_at="2026-08-01T12:00:00Z",
            )
        ],
        verification_state=verification_state,
        reviewer="analyst" if verification_state == "human_verified" else "",
    )


def test_source_adequacy_distinguishes_diverse_multi_source_from_single_identity():
    single = _observation()
    diverse = _observation(
        title="Diverse case",
        evidence=[
            EvidenceReference(url="https://host.example/program", source_type="official_host_source"),
            EvidenceReference(url="https://prc.example/notice", source_type="official_prc_source"),
            EvidenceReference(
                url="https://social.example/post", source_type="social_media", platform="weibo", native_id="123"
            ),
        ],
    )
    assert source_adequacy_profile(single)["adequacy"] == "single_evidence_identity"
    profile = source_adequacy_profile(diverse)
    assert profile["adequacy"] == "multi_source_diverse"
    assert profile["evidence_identities"] >= 3
    assert profile["distinct_source_channels"] >= 2


def test_confirmed_support_single_identity_and_coordination_without_verified_claim_are_high_tensions():
    observation = _observation()
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        narrative_tags=["china_russia_coordination"],
        prc_support=SupportAssessment(
            level="confirmed",
            bases=["official_host_source"],
            rationale="Host source explicitly attributes sponsorship.",
            evidence_refs=["https://host.example/program"],
            review_state="human_verified",
            reviewer="analyst",
        ),
        review_state="human_verified",
        reviewer="analyst",
    )
    tensions = analytic_tensions([observation], [assessment])
    types = {row["type"]: row for row in tensions}
    assert types["confirmed_support_single_evidence_identity"]["severity"] == "high"
    assert types["coordination_tag_without_verified_coordination_claim"]["severity"] == "high"


def test_reach_is_flagged_for_outcome_collection_not_treated_as_influence():
    observation = _observation()
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        reach=ReachMetrics(views=50000, likes=5000),
        observability_level="engagement_observed",
        review_state="human_verified",
        reviewer="analyst",
    )
    tensions = analytic_tensions([observation], [assessment])
    reach = next(row for row in tensions if row["type"] == "reach_without_outcome_evidence")
    assert reach["severity"] == "normal"
    assert "outcome collection" in reach["next_step"].casefold()


def test_tradecraft_audit_counts_epistemic_debt():
    observation = _observation(verification_state="unreviewed")
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        prc_support=SupportAssessment(
            level="probable",
            bases=["credible_secondary_reporting"],
            rationale="Probable pending human review.",
            evidence_refs=["https://host.example/program"],
            review_state="ai_triaged",
        ),
        claims=[
            AnalyticClaim(
                statement="A coordination relationship may exist.",
                claim_type="coordination",
                epistemic_status="hypothesis",
                evidence_refs=["https://host.example/program"],
                review_state="needs_followup",
            )
        ],
        analytic_priority="high",
        review_state="needs_followup",
    )
    audit = build_tradecraft_audit([observation], [assessment])
    debt = audit["epistemic_debt"]
    assert debt["possible_or_probable_support_pending"] == 1
    assert debt["high_priority_not_verified"] == 1
    assert debt["high_consequence_claims_not_verified"] == 1
    assert audit["guardrails"]
