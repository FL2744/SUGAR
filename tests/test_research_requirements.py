from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core.research_requirements import (
    BranchMetrics,
    ResearchRequirement,
    ResearchTimeframe,
    build_initial_search_plan,
    evaluate_branch,
    load_requirement,
    load_search_plan,
    save_requirement,
    save_search_plan,
)


def _requirement() -> ResearchRequirement:
    return ResearchRequirement(
        question="How are foreign educational opportunities reaching university students in Exampleland?",
        geographies=["Exampleland", "Exampleland"],
        timeframe=ResearchTimeframe("2026-01-01", "2026-09-17"),
        target_audiences=["University students"],
        languages=["auto", "Regional Language", "Examplean"],
        known_entities=["Public Engagement Center A", "Cultural Center B"],
    )


def test_requirement_round_trip_is_stable_and_deduplicated(tmp_path: Path):
    requirement = _requirement()
    path = Path(save_requirement(requirement, tmp_path / "requirement.json"))
    restored = load_requirement(path)
    assert restored.requirement_id == requirement.requirement_id
    assert restored.geographies == ["Exampleland"]
    assert restored.timeframe.start == "2026-01-01"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "1.0"


def test_initial_plan_is_bounded_auditable_and_persistable(tmp_path: Path):
    requirement = _requirement()
    plan = build_initial_search_plan(requirement)
    assert plan.requirement_id == requirement.requirement_id
    assert len(plan.branches) == 4
    assert all(branch.rationale for branch in plan.branches)
    assert all(branch.origin == "requirement" for branch in plan.branches)
    assert all(branch.hop_depth == 0 for branch in plan.branches)
    path = Path(save_search_plan(plan, tmp_path / "plan.json"))
    restored = load_search_plan(path)
    assert [branch.query for branch in restored.branches] == [branch.query for branch in plan.branches]


def test_discovered_branch_requires_evidence_and_obeys_hop_limit():
    plan = build_initial_search_plan(_requirement())
    parent = plan.branches[0]
    with pytest.raises(ValueError, match="evidence ID"):
        plan.add_discovered_branch(
            query="Education Advising Program A Capital City",
            rationale="Discovered co-occurring program.",
            parent_branch_id=parent.branch_id,
            evidence_ids=[],
        )
    child = plan.add_discovered_branch(
        query="Education Advising Program A Capital City",
        rationale="Discovered co-occurring program in relevant evidence.",
        parent_branch_id=parent.branch_id,
        evidence_ids=["obs_1", "obs_2"],
        parent_concept="Education Advising Program A",
    )
    grandchild = plan.add_discovered_branch(
        query="Education Advising Program A scholarship Capital City",
        rationale="Scholarship terminology recurred in evidence under the discovered program.",
        parent_branch_id=child.branch_id,
        evidence_ids=["obs_3"],
        parent_concept="scholarship",
    )
    with pytest.raises(ValueError, match="max_hops"):
        plan.add_discovered_branch(
            query="too far",
            rationale="Would drift beyond the bounded requirement graph.",
            parent_branch_id=grandchild.branch_id,
            evidence_ids=["obs_4"],
        )


def test_branch_controller_retires_saturated_low_value_branch():
    plan = build_initial_search_plan(_requirement())
    metrics = BranchMetrics(
        retrieved=100,
        relevance_assessed=100,
        relevant=4,
        unique=10,
        duplicates=90,
        new_concepts=0,
        distinct_sources=2,
        coverage_gain=0.0,
    )
    decision = evaluate_branch(metrics, plan.policy)
    assert decision.action == "retire"
    assert any("Duplicate rate" in reason for reason in decision.reasons)


def test_analyst_can_edit_and_control_branch_with_auditable_events():
    plan = build_initial_search_plan(_requirement())
    branch = plan.branches[0]
    original_id = branch.branch_id
    plan.edit_branch(
        branch.branch_id,
        query="Public Engagement Center A student advising",
        rationale="Analyst narrowed the branch to the target audience.",
        actor="Analyst A",
        reason="Initial seed was too broad.",
    )
    plan.set_status(
        branch.branch_id,
        "approved",
        actor="Analyst A",
        reason="Reviewed before collection.",
    )
    assert branch.branch_id == original_id
    assert branch.query == "Public Engagement Center A student advising"
    assert branch.status == "approved"
    edit_event = next(item for item in plan.events if item["type"] == "branch_edited")
    assert edit_event["branch_id"] == original_id
    assert edit_event["actor"] == "Analyst A"
    assert edit_event["changes"]["query"]["to"] == branch.query
    status_event = next(item for item in plan.events if item["type"] == "status_change")
    assert status_event["to"] == "approved"


def test_branch_edit_rejects_duplicate_query():
    plan = build_initial_search_plan(_requirement())
    with pytest.raises(ValueError, match="duplicates existing branch"):
        plan.edit_branch(plan.branches[0].branch_id, query=plan.branches[1].query)


def test_requirement_rejects_reversed_dates():
    with pytest.raises(ValueError, match="cannot be after"):
        ResearchTimeframe("2026-09-17", "2026-01-01")
