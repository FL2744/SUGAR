from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core.llm import LLMConfig
from sugar_core.requirement_compiler import (
    RESEARCH_STRATEGY_WORKFLOW,
    CompiledResearchStrategy,
    SourceSpan,
    StrategyConcept,
    build_search_plan_from_strategy,
    compile_requirement_deterministically,
    enrich_strategy_with_llm,
    load_research_strategy,
    save_research_strategy,
)
from sugar_core.research_requirements import ResearchRequirement


QUESTION = "How are foreign educational institutions reaching university students in Exampleland?"


def requirement() -> ResearchRequirement:
    return ResearchRequirement(question=QUESTION, collection_mode="standard")


def test_deterministic_compiler_extracts_question_structure_without_ai():
    strategy = compile_requirement_deterministically(requirement())
    assert strategy.review_state == "draft"
    assert strategy.analytic_task == "mechanism_assessment"

    explicit = {(item.kind, item.value) for item in strategy.concepts if item.origin == "explicit"}
    assert ("subject", "foreign educational institutions") in explicit
    assert ("activity", "reaching") in explicit
    assert ("target_audience", "university students") in explicit
    assert ("geography", "Exampleland") in explicit
    for concept in strategy.concepts:
        if concept.origin == "explicit":
            assert concept.source_span is not None
            assert QUESTION[concept.source_span.start:concept.source_span.end] == concept.source_span.text

    dimension_names = {item.name for item in strategy.dimensions}
    assert {"presence", "program_activity", "audience_reach", "engagement_mechanism"} <= dimension_names
    missing = {item.field for item in strategy.missing_dimensions}
    assert "timeframe" in missing
    assert "languages" in missing


def test_explicit_concept_rejects_fake_source_span():
    with pytest.raises(ValueError, match="does not exactly match"):
        CompiledResearchStrategy(
            requirement_id="rq_test",
            original_question=QUESTION,
            analytic_task="mechanism_assessment",
            concepts=[
                StrategyConcept(
                    kind="entity",
                    value="Public Engagement Center",
                    origin="explicit",
                    source_span=SourceSpan(text="Public Engagement Center", start=0, end=19),
                )
            ],
        )


def test_hypothesis_cannot_masquerade_as_explicit_source_span():
    with pytest.raises(ValueError, match="cannot masquerade"):
        StrategyConcept(
            kind="entity",
            value="Public Engagement Center",
            origin="hypothesis",
            source_span=SourceSpan(text="How", start=0, end=3),
        )


def test_ai_compile_accepts_only_exact_explicit_spans_and_separates_hypotheses(tmp_path: Path):
    req = requirement()
    strategy = compile_requirement_deterministically(req)

    class FakeClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(**kwargs):
                    payload = {
                        "analytic_task": "mechanism_assessment",
                        "explicit_concepts": [
                            {
                                "kind": "actor_class",
                                "value": "foreign educational institutions",
                                "source_text": "foreign educational institutions",
                                "start": QUESTION.index("foreign educational institutions"),
                                "end": QUESTION.index("foreign educational institutions") + len("foreign educational institutions"),
                                "confidence": 0.99,
                                "rationale": "Exact source phrase.",
                            },
                            {
                                "kind": "entity",
                                "value": "Public Engagement Center",
                                "source_text": "Public Engagement Center",
                                "start": 0,
                                "end": len("Public Engagement Center"),
                                "confidence": 0.9,
                                "rationale": "Invalid fabricated span.",
                            },
                        ],
                        "interpreted_concepts": [
                            {
                                "kind": "activity",
                                "value": "audience outreach",
                                "confidence": 0.88,
                                "rationale": "Semantic interpretation of reaching.",
                            }
                        ],
                        "search_hypotheses": [
                            {
                                "kind": "entity",
                                "value": "Public Engagement Center",
                                "confidence": 0.72,
                                "rationale": "Plausible institution class to investigate, not asserted.",
                            }
                        ],
                        "research_dimensions": [
                            {
                                "name": "mechanisms",
                                "question": "Through what observable mechanisms does engagement occur?",
                                "indicators": ["scholarship", "event", "language program"],
                                "source_families": ["universities", "official institutions"],
                                "rationale": "Operationalizes how.",
                            }
                        ],
                    }

                    class Message:
                        content = json.dumps(payload)

                    class Choice:
                        message = Message()

                    class Response:
                        choices = [Choice()]

                    return Response()

            completions = Completions()

        chat = Chat()

    enriched = enrich_strategy_with_llm(
        req,
        strategy,
        llm=LLMConfig(provider="custom", model="compiler-test", api_key="x", base_url="https://example.test/v1"),
        cache_dir=tmp_path,
        client=FakeClient(),
    )
    assert enriched.ai_provider == "custom"
    assert enriched.ai_model == "compiler-test"
    assert enriched.ai_workflow == RESEARCH_STRATEGY_WORKFLOW
    assert any(
        item.origin == "hypothesis" and item.value == "Public Engagement Center"
        for item in enriched.concepts
    )
    assert not any(
        item.origin == "explicit" and item.value == "Public Engagement Center"
        for item in enriched.concepts
    )
    assert any(
        item.origin == "explicit" and item.value == "foreign educational institutions"
        for item in enriched.concepts
    )


def test_analyst_can_edit_interpretation_but_not_explicit_source_text():
    strategy = compile_requirement_deterministically(requirement())
    explicit = next(item for item in strategy.concepts if item.kind == "subject")
    with pytest.raises(ValueError, match="immutable"):
        strategy.update_concept(explicit.concept_id, value="Something else", actor="Analyst")

    added = strategy.add_analyst_concept(
        kind="entity",
        value="Public Engagement Center",
        origin="hypothesis",
        rationale="Analyst wants this investigated.",
        actor="Analyst",
    )
    strategy.update_concept(added.concept_id, value="Public Engagement Center Exampleland", actor="Analyst")
    assert strategy.concept(added.concept_id).value == "Public Engagement Center Exampleland"
    assert any(event["type"] == "concept_added" for event in strategy.events)
    assert any(event["type"] == "concept_updated" for event in strategy.events)


def test_analyst_can_edit_or_exclude_research_dimensions_and_reapproval_is_required():
    strategy = compile_requirement_deterministically(requirement())
    strategy.approve(reviewer="Analyst One")
    dimension = next(item for item in strategy.dimensions if item.name == "program_activity")
    strategy.update_dimension(
        dimension.dimension_id,
        question="Which educational programs are publicly documented?",
        indicators=["scholarship", "language course"],
        source_families=["universities", "official institutions"],
        included=False,
        analyst_note="Exclude from this narrow run.",
        actor="Analyst One",
    )
    assert strategy.review_state == "draft"
    assert strategy.reviewer == ""
    updated = strategy.dimension(dimension.dimension_id)
    assert updated.included is False
    assert updated.question == "Which educational programs are publicly documented?"
    assert updated.indicators == ["scholarship", "language course"]
    assert any(event["type"] == "dimension_updated" for event in strategy.events)


def test_planner_refuses_unapproved_strategy_then_uses_approved_strategy():
    req = requirement()
    strategy = compile_requirement_deterministically(req)
    strategy.add_analyst_concept(
        kind="entity",
        value="Public Engagement Center Exampleland",
        origin="hypothesis",
        rationale="Analyst-approved discovery hypothesis.",
    )
    with pytest.raises(ValueError, match="analyst-approved"):
        build_search_plan_from_strategy(req, strategy)

    strategy.approve(reviewer="Analyst One", note="Interpretation checked.")
    plan = build_search_plan_from_strategy(req, strategy)
    queries = {branch.query for branch in plan.branches}
    assert "foreign educational institutions Exampleland" in queries
    assert "foreign educational institutions university students" in queries
    assert "Public Engagement Center Exampleland" in queries
    hypothesis_branch = next(
        branch for branch in plan.branches if branch.query == "Public Engagement Center Exampleland"
    )
    assert "not an asserted fact" in hypothesis_branch.rationale
    assert any(event["type"] == "compiled_strategy_plan" for event in plan.events)


def test_strategy_planner_does_not_use_excluded_dimension_indicators():
    req = requirement()
    strategy = compile_requirement_deterministically(req)
    dimension = next(item for item in strategy.dimensions if item.name == "program_activity")
    unique_indicator = "special-program-indicator"
    strategy.update_dimension(
        dimension.dimension_id,
        indicators=[unique_indicator],
        included=False,
        actor="Analyst",
    )
    strategy.approve(reviewer="Analyst")
    plan = build_search_plan_from_strategy(req, strategy)
    assert not any(unique_indicator in branch.query for branch in plan.branches)


def test_strategy_round_trip_preserves_review_and_provenance(tmp_path: Path):
    strategy = compile_requirement_deterministically(requirement())
    strategy.ai_provider = "openai"
    strategy.ai_model = "gpt-test"
    strategy.ai_workflow = RESEARCH_STRATEGY_WORKFLOW
    strategy.approve(reviewer="Analyst One")
    path = Path(save_research_strategy(strategy, tmp_path / "strategy.json"))
    restored = load_research_strategy(path)
    assert restored.approved
    assert restored.reviewer == "Analyst One"
    assert restored.ai_provider == "openai"
    assert restored.concepts[0].concept_id == strategy.concepts[0].concept_id
