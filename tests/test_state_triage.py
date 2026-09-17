from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_triage import assessment_from_triage_payload


def observation() -> ResearchObservation:
    return ResearchObservation(
        observation_type="program",
        title="Technology workshop",
        summary="A public source describes a technology workshop for university students.",
        country="example_host_country",
        city="Bishkek",
        evidence=[
            EvidenceReference(
                url="https://example.org/program",
                source_type="official_host_source",
                published_at="2026-09-01T12:00:00Z",
            )
        ],
        verification_state="human_verified",
        reviewer="analyst",
    )


def test_ai_confirmed_support_is_downgraded_and_bogus_taxonomy_is_dropped():
    obs = observation()
    assessment = assessment_from_triage_payload(
        obs,
        {
            "strategic_audiences": ["students", "invented_audience"],
            "program_domains": ["stem_technology", "invented_domain"],
            "narrative_tags": ["technology_innovation", "invented_narrative"],
            "sponsor_support": {
                "level": "confirmed",
                "bases": ["official_sponsor_source", "invented_basis"],
                "rationale": "The source identifies official sponsorship.",
                "confidence": 0.9,
                "evidence_refs": ["https://example.org/program", "https://invented.invalid"],
            },
            "observability_level": "reach_observed",
            "reach": {"views": "500", "likes": "bad-value"},
            "claims": [],
            "analytic_priority": "high",
        },
        model="test-model",
    )
    assert assessment.sponsor_support.level == "probable"
    assert assessment.sponsor_support.evidence_refs == ["https://example.org/program"]
    assert assessment.sponsor_support.bases == ["official_sponsor_source"]
    assert assessment.strategic_audiences == ["students"]
    assert assessment.program_domains == ["stem_technology"]
    assert assessment.narrative_tags == ["technology_innovation"]
    assert assessment.reach.views == 500
    assert assessment.reach.likes is None
    assert assessment.review_state == "ai_triaged"


def test_ai_probable_support_without_attached_evidence_is_downgraded():
    obs = observation()
    assessment = assessment_from_triage_payload(
        obs,
        {
            "sponsor_support": {
                "level": "probable",
                "bases": ["branding"],
                "confidence": 0.7,
                "evidence_refs": ["https://invented.invalid"],
            }
        },
    )
    assert assessment.sponsor_support.level == "possible"
    assert assessment.sponsor_support.evidence_refs == []


def test_ai_influence_language_becomes_followup_hypothesis_not_finding():
    obs = observation()
    assessment = assessment_from_triage_payload(
        obs,
        {
            "observability_level": "causal_influence_evidence",
            "claims": [
                {
                    "statement": "The workshop changed participant attitudes.",
                    "claim_type": "influence",
                    "epistemic_status": "observed_fact",
                    "confidence": 0.8,
                    "evidence_refs": ["https://example.org/program"],
                }
            ],
        },
    )
    assert assessment.observability_level == "outcome_evidence"
    assert assessment.review_state == "needs_followup"
    assert assessment.claims[0].epistemic_status == "hypothesis"
    assert assessment.claims[0].review_state == "needs_followup"
    assert not assessment.brief_eligible
