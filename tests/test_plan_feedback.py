from __future__ import annotations

from sugar_core.models import PostRecord
from sugar_core.observations import ResearchObservation
from sugar_core.plan_feedback import apply_triage_feedback, evidence_excerpts_for_branch
from sugar_core.research_requirements import ResearchRequirement, SearchPolicy, build_initial_search_plan


def _record(native_id: str, query: str, text: str = "source text") -> PostRecord:
    return PostRecord(
        platform="example",
        native_id=native_id,
        canonical_url=f"https://example.test/{native_id}",
        query=query,
        query_matches=[query],
        original_text=text,
    )


def _observation(record: PostRecord, relevance: str) -> ResearchObservation:
    return ResearchObservation(
        observation_type="digital_post",
        summary=record.original_text,
        source_record_keys=[record.record_key],
        relevance=relevance,
    )


def test_uncertain_triage_does_not_count_as_negative_relevance_evidence():
    requirement = ResearchRequirement(question="Question", known_entities=["entity"])
    plan = build_initial_search_plan(requirement)
    plan.policy = SearchPolicy(min_sample=2, min_relevance_rate=0.5, min_novelty_rate=0.1)
    query = plan.branches[0].query
    records = [_record("1", query), _record("2", query), _record("3", query)]
    observations = [
        _observation(records[0], "relevant"),
        _observation(records[1], "uncertain"),
        _observation(records[2], "uncertain"),
    ]

    result = apply_triage_feedback(plan, records, observations)[0]

    assert plan.branches[0].metrics.relevance_assessed == 1
    assert plan.branches[0].metrics.relevant == 1
    assert plan.branches[0].metrics.uncertain == 2
    assert result.decision.action == "continue"
    assert plan.branches[0].status != "retired"


def test_decisive_low_relevance_can_retire_branch_after_minimum_sample():
    requirement = ResearchRequirement(question="Question", known_entities=["entity"])
    plan = build_initial_search_plan(requirement)
    plan.policy = SearchPolicy(min_sample=3, min_relevance_rate=0.5, min_novelty_rate=0.1)
    query = plan.branches[0].query
    records = [_record(str(index), query) for index in range(4)]
    observations = [
        _observation(records[0], "relevant"),
        *[_observation(record, "not_relevant") for record in records[1:]],
    ]

    result = apply_triage_feedback(plan, records, observations)[0]

    assert result.decision.action == "retire"
    assert plan.branches[0].status == "retired"
    assert any(event["type"] == "branch_evaluation" for event in plan.events)


def test_evidence_excerpts_use_original_source_text_and_real_observation_ids():
    requirement = ResearchRequirement(question="Question", known_entities=["entity"])
    plan = build_initial_search_plan(requirement)
    query = plan.branches[0].query
    record = _record("1", query, "Кыргызча original source term")
    observation = _observation(record, "relevant")

    excerpts = evidence_excerpts_for_branch(plan, plan.branches[0].branch_id, [record], [observation])

    assert len(excerpts) == 1
    assert excerpts[0].evidence_id == observation.observation_id
    assert excerpts[0].text == "Кыргызча original source term"
