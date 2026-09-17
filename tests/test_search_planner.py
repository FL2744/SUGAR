from __future__ import annotations

import json

from sugar_core.llm import LLMConfig
from sugar_core.research_requirements import ResearchRequirement, build_initial_search_plan
from sugar_core.search_planner import EvidenceExcerpt, expand_branch_from_evidence, expand_initial_plan_with_llm


def _requirement() -> ResearchRequirement:
    return ResearchRequirement(
        question="How are educational programs reaching university students in Exampleland?",
        geographies=["Exampleland"],
        languages=["Examplean", "Regional Language"],
        known_entities=["Public Engagement Center A"],
        excluded_topics=["casino"],
    )


def test_llm_initial_expansion_is_bounded_sanitized_and_attributed(monkeypatch):
    requirement = _requirement()
    plan = build_initial_search_plan(requirement)
    response = {
        "queries": [
            {
                "query": "Американский уголок Кыргызстан",
                "rationale": "Regional Language alias for the known institution in scope.",
                "search_family": "alias",
                "language": "Regional Language",
                "concept": "Public Engagement Center A",
            },
            {
                "query": "Public Engagement Center A",
                "rationale": "Duplicate existing query.",
                "search_family": "entity",
                "language": "English",
                "concept": "Public Engagement Center A",
            },
            {
                "query": "casino Exampleland",
                "rationale": "Explicitly excluded topic.",
                "search_family": "discovery",
                "language": "English",
                "concept": "casino",
            },
        ]
    }
    monkeypatch.setattr("sugar_core.search_planner.cached_chat", lambda *args, **kwargs: json.dumps(response))

    expanded = expand_initial_plan_with_llm(
        requirement,
        plan,
        llm=LLMConfig(provider="custom", model="planner-test", api_key="x", base_url="https://invalid.test/v1"),
        client=object(),
        max_candidates=3,
    )

    added = [branch for branch in expanded.branches if branch.origin == "generated"]
    assert len(added) == 1
    assert added[0].query == "Американский уголок Кыргызстан"
    assert added[0].search_family == "alias"
    assert added[0].generator == "custom:planner-test"
    assert expanded.events[-1]["type"] == "llm_initial_expansion"
    assert expanded.events[-1]["accepted"] == 1


def test_evidence_expansion_rejects_invented_evidence_ids(monkeypatch):
    requirement = _requirement()
    plan = build_initial_search_plan(requirement)
    parent = plan.branches[0]
    response = {
        "queries": [
            {
                "query": "Education Advising Program A Capital City",
                "rationale": "Program name appears in the supplied source excerpt.",
                "search_family": "relationship",
                "language": "English",
                "concept": "Education Advising Program A",
                "evidence_ids": ["obs_real"],
            },
            {
                "query": "Invented thing",
                "rationale": "Claims support that was not supplied.",
                "search_family": "discovery",
                "language": "English",
                "concept": "invented",
                "evidence_ids": ["obs_fake"],
            },
        ]
    }
    monkeypatch.setattr("sugar_core.search_planner.cached_chat", lambda *args, **kwargs: json.dumps(response))

    expanded = expand_branch_from_evidence(
        requirement,
        plan,
        parent_branch_id=parent.branch_id,
        evidence=[EvidenceExcerpt("obs_real", "Students discussed Education Advising Program A Capital City scholarship advising.")],
        llm=LLMConfig(provider="openai", model="planner-test", api_key="x"),
        client=object(),
        max_candidates=4,
    )

    children = [branch for branch in expanded.branches if branch.parent_branch_id == parent.branch_id]
    assert len(children) == 1
    assert children[0].evidence_ids == ["obs_real"]
    assert children[0].hop_depth == 1
    assert expanded.events[-1]["accepted"] == 1
    assert expanded.events[-1]["rejected"] == 1
