from sugar_core.state_agentic import _integration_packet
from sugar_core.state_synthesis import AgentTask


def _case(index):
    return {
        "observation_id": f"obs_{index}",
        "assessment_id": f"state_{index}",
        "source_refs": [f"https://example.org/{index}"],
        "high_consequence_claims": [],
        "comparables": [],
    }


def test_integrator_context_is_bounded_and_includes_specialist_cited_country_case_and_tensions():
    base_packet = {
        "representative_cases": [_case(i) for i in range(100)],
        "scope": {"mode": "global"},
        "guardrails": [],
        "corpus": {},
        "macro_structure": {},
        "comparative_diagnostics": {},
        "network_patterns": {},
        "collection_questions": [],
        "tradecraft_audit": {
            "high_severity_tensions": [
                {
                    "type": "confirmed_support_single_evidence_identity",
                    "explanation": "Confirmed support has only one evidence identity.",
                    "observation_id": "obs_1",
                    "next_step": "Seek independent corroboration.",
                }
            ]
        },
    }
    country_case = {
        "observation_id": "obs_country_special",
        "assessment_id": "state_country_special",
        "source_refs": ["https://example.org/country-special"],
        "high_consequence_claims": [],
        "comparables": [],
    }
    country_packet = {**base_packet, "representative_cases": [country_case]}
    tasks = [
        AgentTask(name="system_pattern_analyst", role="system_pattern_analyst", question="q", packet=base_packet),
        AgentTask(name="country:Test", role="country_analyst", question="q", packet=country_packet),
    ]
    outputs = [
        {"agent": "system_pattern_analyst", "judgments": [], "findings": [], "alternatives": []},
        {
            "agent": "country:Test",
            "judgments": [{"supporting_refs": ["obs_country_special"], "contrary_refs": []}],
            "findings": [],
            "alternatives": [],
        },
    ]
    packet = _integration_packet(base_packet, tasks, outputs, baseline_cases=10, max_cases=20)
    ids = {row["observation_id"] for row in packet["representative_cases"]}
    assert "obs_country_special" in ids
    assert len(packet["representative_cases"]) <= 20
    assert packet["integration_context"]["strategy"] == (
        "high-priority baseline plus specialist-cited cases plus deterministic tradecraft tensions"
    )
    assert packet["integration_context"]["high_severity_tensions_injected"] == 1
    assert any(
        "confirmed_support_single_evidence_identity" in row["question"] for row in packet["collection_questions"]
    )
    assert any("high-severity analytic tension" in value for value in packet["guardrails"])
