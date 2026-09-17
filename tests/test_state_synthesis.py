from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_intelligence import build_intelligence_packet
from sugar_core.state_schema import StateAssessment
import json

import pytest

from sugar_core.llm import LLMConfig
from sugar_core.state_synthesis import (
    AgentTask,
    _call_integrator,
    _parallel_agents,
    _scope_label,
    _trim_packet,
    render_synthesis_markdown,
    run_agentic_synthesis,
    sanitize_agent_output,
    save_agentic_synthesis,
)


def _packet():
    observation = ResearchObservation(
        observation_type="program",
        title="Verified program",
        summary="A verified public program record.",
        observed_at="2026-08-01T12:00:00Z",
        country="example_host_country",
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


def test_alternative_consistency_is_case_insensitive_and_refs_are_allowlisted():
    packet, observation = _packet()
    result = sanitize_agent_output(
        {
            "alternatives": [
                {
                    "hypothesis": "A plausible alternative.",
                    "supporting_refs": [observation.observation_id, "invented"],
                    "contradicting_refs": ["invented"],
                    "consistency": "HIGH",
                    "discriminators": ["Indicator A"],
                    "collection_needed": ["Collect B"],
                }
            ]
        },
        packet,
        agent="test_agent",
    )

    alternative = result["alternatives"][0]
    assert alternative["consistency"] == "high"
    assert alternative["supporting_refs"] == [observation.observation_id]
    assert alternative["contradicting_refs"] == []


def test_trim_packet_limits_large_sections_without_mutating_input():
    packet = {
        "representative_cases": list(range(40)),
        "comparative_diagnostics": {"country_pair_comparability": list(range(80))},
        "network_patterns": {
            "recurrent_entities": list(range(50)),
            "cross_border_entities": list(range(50)),
            "digital_offline_coupling_candidates": list(range(50)),
            "archetype_clusters": list(range(50)),
        },
        "anomalies": list(range(40)),
    }

    result = _trim_packet(packet, max_cases=7)

    assert len(result["representative_cases"]) == 7
    assert len(result["comparative_diagnostics"]["country_pair_comparability"]) == 50
    assert all(len(result["network_patterns"][key]) == 30 for key in packet["network_patterns"])
    assert len(result["anomalies"]) == 25
    assert len(packet["representative_cases"]) == 40


def test_parallel_agents_preserves_task_order_and_fails_closed(monkeypatch):
    def fake_call_agent(client, llm, cache, task):
        if task.name == "broken":
            raise ValueError("bad agent")
        return {"agent": task.name, "summary": task.question}

    monkeypatch.setattr("sugar_core.state_synthesis._call_agent", fake_call_agent)
    tasks = [
        AgentTask("first", "role", "one", {}),
        AgentTask("broken", "role", "two", {}),
        AgentTask("third", "role", "three", {}),
    ]

    result = _parallel_agents(object(), LLMConfig(model="test"), None, tasks, max_workers=3)

    assert [row["agent"] for row in result] == ["first", "broken", "third"]
    assert result[1]["failed"] is True
    assert "ValueError" in result[1]["uncertainties"][0]


def test_integrator_sanitizes_refs_priorities_and_uncited_findings(monkeypatch):
    packet, observation = _packet()
    payload = {
        "executive_assessment": " Assessment. ",
        "key_judgments": [
            {
                "statement": "Supported judgment",
                "supporting_refs": [observation.observation_id, "invented"],
                "confidence": "HIGH",
                "likelihood": "LIKELY",
            }
        ],
        "macro_findings": [
            {"statement": "No real citation", "refs": ["invented"], "confidence": "high"}
        ],
        "micro_findings": [
            {"statement": "Cited", "refs": [observation.observation_id], "confidence": "moderate"}
        ],
        "alternatives": [{"hypothesis": "Alternative", "consistency": "Moderate"}],
        "indicators": [{"indicator": "Signal", "would_strengthen": "More", "would_weaken": "Less"}],
        "collection_priorities": [
            {"question": "Question?", "priority": "URGENT"},
            {"question": "Other?", "priority": "invalid"},
        ],
        "uncertainties": ["Gap"],
        "dissent": ["Dissent"],
        "tradecraft_note": "Caution",
    }
    monkeypatch.setattr("sugar_core.state_synthesis.cached_chat", lambda *args, **kwargs: json.dumps(payload))

    result = _call_integrator(
        object(), LLMConfig(model="test"), None, packet, [], stage="draft"
    )

    judgment = result["key_judgments"][0]
    assert judgment["supporting_refs"] == [observation.observation_id]
    assert judgment["confidence"] == "high"
    assert judgment["likelihood"] == "likely"
    assert result["macro_findings"][0]["status"] == "hypothesis"
    assert result["macro_findings"][0]["confidence"] == "low"
    assert result["micro_findings"][0]["status"] == "supported"
    assert result["alternatives"][0]["consistency"] == "moderate"
    assert [row["priority"] for row in result["collection_priorities"]] == ["urgent", "normal"]


@pytest.mark.parametrize(
    ("country", "observation_id", "expected"),
    [
        ("", "obs-1", "micro case obs-1"),
        ("example_host_country", "", "country assessment: example_host_country"),
        ("", "", "global comparative assessment"),
    ],
)
def test_scope_label(country, observation_id, expected):
    assert _scope_label(country, observation_id) == expected


def test_run_agentic_synthesis_quick_skips_red_team(monkeypatch):
    packet, _ = _packet()
    calls = {"integrator": []}
    monkeypatch.setattr("sugar_core.state_synthesis.build_intelligence_packet", lambda *args, **kwargs: packet)
    monkeypatch.setattr("sugar_core.state_synthesis.create_client", lambda llm: object())
    monkeypatch.setattr(
        "sugar_core.state_synthesis._parallel_agents",
        lambda client, llm, cache, tasks, max_workers: [{"agent": task.name} for task in tasks],
    )

    def fake_integrator(client, llm, cache, base_packet, agent_outputs, *, stage, critique=None):
        calls["integrator"].append((stage, critique))
        return {"executive_assessment": stage, "key_judgments": []}

    monkeypatch.setattr("sugar_core.state_synthesis._call_integrator", fake_integrator)
    monkeypatch.setattr("sugar_core.state_synthesis._red_team", lambda *args, **kwargs: pytest.fail("red team should not run"))

    result = run_agentic_synthesis([], [], llm=LLMConfig(model="test"), depth="quick")

    assert [agent["agent"] for agent in result["agents"]] == ["system_pattern_analyst", "methodologist"]
    assert calls["integrator"] == [("draft", None)]
    assert result["red_team"] is None
    assert result["final"] is result["draft"]


def test_run_agentic_synthesis_standard_red_teams_and_revises(monkeypatch):
    packet, _ = _packet()
    stages = []
    monkeypatch.setattr("sugar_core.state_synthesis.build_intelligence_packet", lambda *args, **kwargs: packet)
    monkeypatch.setattr("sugar_core.state_synthesis.create_client", lambda llm: object())
    monkeypatch.setattr(
        "sugar_core.state_synthesis._parallel_agents",
        lambda client, llm, cache, tasks, max_workers: [{"agent": task.name} for task in tasks],
    )
    monkeypatch.setattr("sugar_core.state_synthesis._red_team", lambda *args, **kwargs: {"summary": "critique"})

    def fake_integrator(client, llm, cache, base_packet, agent_outputs, *, stage, critique=None):
        stages.append((stage, critique))
        return {"executive_assessment": stage, "key_judgments": []}

    monkeypatch.setattr("sugar_core.state_synthesis._call_integrator", fake_integrator)

    result = run_agentic_synthesis(
        [], [], llm=LLMConfig(provider="arc", model="test"), country="example_host_country", depth="standard"
    )

    assert len(result["agents"]) == 5
    assert stages[0] == ("draft", None)
    assert stages[1] == ("revised", {"summary": "critique"})
    assert result["red_team"] == {"summary": "critique"}
    assert result["final"]["executive_assessment"] == "revised"
    assert result["llm"] == {"provider": "arc", "model": "test"}


def test_run_agentic_synthesis_rejects_unknown_depth_before_client_creation(monkeypatch):
    monkeypatch.setattr("sugar_core.state_synthesis.create_client", lambda llm: pytest.fail("client should not be created"))
    with pytest.raises(ValueError, match="quick, standard, or deep"):
        run_agentic_synthesis([], [], llm=LLMConfig(model="test"), depth="extreme")


def test_render_synthesis_markdown_includes_tradecraft_sections():
    markdown = render_synthesis_markdown(
        {
            "final": {
                "executive_assessment": "BLUF text",
                "key_judgments": [
                    {
                        "statement": "Judgment",
                        "likelihood": "likely",
                        "confidence": "moderate",
                        "status": "analytic_assessment",
                        "basis": "Evidence",
                        "supporting_refs": ["obs-1"],
                        "contrary_refs": [],
                    }
                ],
                "macro_findings": [],
                "micro_findings": [],
                "alternatives": [],
                "indicators": [],
                "collection_priorities": [],
                "uncertainties": ["Coverage gap"],
                "dissent": ["Alternative reading"],
                "tradecraft_note": "Do not overclaim.",
            }
        }
    )

    assert "## BLUF" in markdown
    assert "Likelihood: `likely` | Confidence: `moderate`" in markdown
    assert "Uncertainty: Coverage gap" in markdown
    assert "Dissent/tension: Alternative reading" in markdown
    assert "## Analytic Guardrail" in markdown


def test_save_agentic_synthesis_writes_manifest_and_agent_stream(monkeypatch, tmp_path):
    payload = {
        "generated_at": "2026-09-17T00:00:00Z",
        "synthesis_version": "1.0",
        "scope": {"country": "example_host_country"},
        "depth": "standard",
        "agents": [{"agent": "a"}, {"agent": "b"}],
        "red_team": {"agent": "red_team"},
        "final": {"executive_assessment": "Assessment", "key_judgments": []},
    }
    monkeypatch.setattr("sugar_core.state_synthesis.run_agentic_synthesis", lambda *args, **kwargs: payload)

    outputs = save_agentic_synthesis(
        [], [], tmp_path, llm=LLMConfig(provider="arc", model="test-model"), name="My Assessment"
    )

    assert len(outputs) == 4
    manifest = json.loads((tmp_path / "My_Assessment.manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "arc"
    assert manifest["model"] == "test-model"
    assert manifest["human_verification_mutated"] is False
    agent_lines = (tmp_path / "My_Assessment.agents.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["agent"] for line in agent_lines] == ["a", "b", "red_team"]
