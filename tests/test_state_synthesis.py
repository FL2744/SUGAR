from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_intelligence import build_intelligence_packet
from sugar_core.state_schema import StateAssessment
from sugar_core.state_synthesis import sanitize_agent_output


def _packet():
    observation = ResearchObservation(
        observation_type="program",
        title="Verified program",
        summary="A verified public program record.",
        observed_at="2026-08-01T12:00:00Z",
        country="Kyrgyzstan",
        city="Bishkek",
        evidence=[EvidenceReference(url="https://example.org/source", source_type="official_host_source")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        program_domains=["stem_technology"],
        strategic_audiences=["students"],
        review_state="human_verified",
        reviewer="analyst",
    )
    return build_intelligence_packet([observation], [assessment]), observation


def test_agent_output_discards_invented_refs_and_downgrades_uncited_judgment():
    packet, observation = _packet()
    result = sanitize_agent_output(
        {
            "summary": "Test",
            "judgments": [
                {
                    "statement": "Supported pattern.",
                    "judgment_type": "descriptive_pattern",
                    "status": "analytic_assessment",
                    "likelihood": "likely",
                    "confidence": "high",
                    "supporting_refs": [observation.observation_id, "invented:ref"],
                },
                {
                    "statement": "Uncited strategic intent claim.",
                    "judgment_type": "mechanism_assessment",
                    "status": "analytic_assessment",
                    "likelihood": "very_likely",
                    "confidence": "high",
                    "supporting_refs": ["invented:only"],
                },
            ],
            "findings": [
                {"statement": "Invented citation finding", "refs": ["invented:url"], "confidence": "high"}
            ],
        },
        packet,
        agent="test_agent",
    )
    assert result["judgments"][0]["supporting_refs"] == [observation.observation_id]
    assert result["judgments"][0]["confidence"] == "high"
    uncited = result["judgments"][1]
    assert uncited["supporting_refs"] == []
    assert uncited["status"] == "hypothesis"
    assert uncited["confidence"] == "low"
    assert result["findings"][0]["refs"] == []
    assert result["findings"][0]["status"] == "hypothesis"
    assert result["findings"][0]["confidence"] == "low"


def test_likelihood_and_confidence_remain_separate_dimensions():
    packet, observation = _packet()
    result = sanitize_agent_output(
        {
            "judgments": [
                {
                    "statement": "The pattern is likely but confidence is low because coverage is thin.",
                    "judgment_type": "trajectory_assessment",
                    "likelihood": "likely",
                    "confidence": "low",
                    "supporting_refs": [observation.observation_id],
                    "assumptions": ["Observed records reflect at least some current activity."],
                }
            ]
        },
        packet,
        agent="test_agent",
    )
    judgment = result["judgments"][0]
    assert judgment["likelihood"] == "likely"
    assert judgment["confidence"] == "low"
    assert judgment["assumptions"]
