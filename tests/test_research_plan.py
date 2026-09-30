import pytest

from sugar_core.research_plan import (
    QuerySpec, ResearchPlanSpec, build_plan, interpretation_json_schema, normalize_platform,
    repair_plan_dict,
)


def test_defaults_are_documented_and_applied():
    plan = ResearchPlanSpec(topic="democracy", geography=["Middle East"])
    assert plan.depth == "standard"
    assert plan.limits["max_posts_per_query"] == 25
    assert plan.languages == ["auto"]
    assert plan.source_scope == "all_enabled"
    assert plan.dedup == {"enabled": True, "threshold": 0.9}
    assert plan.retry["max_attempts"] == 3
    assert plan.refresh["mode"] == "manual"
    rows = {r["label"]: r["value"] for r in plan.summary_rows()}
    assert rows["Research topic"] == "democracy"
    assert rows["Region"] == "Middle East"
    assert rows["Platforms"] == "All enabled platforms"
    assert rows["Languages"] == "Automatic"
    assert rows["Date range"] == "No restriction"
    assert rows["Collection depth"] == "Standard"


def test_round_trip_preserves_unknown_fields_in_extra():
    plan = ResearchPlanSpec.from_dict({"topic": "elections", "future_field": {"a": 1}})
    assert plan.extra == {"future_field": {"a": 1}}
    again = ResearchPlanSpec.from_dict(plan.to_dict())
    assert again.to_dict() == plan.to_dict()


def test_depth_presets_drive_limits_but_explicit_limits_win():
    assert ResearchPlanSpec(topic="x", depth="deep").limits["max_pages_per_query"] == 3
    plan = ResearchPlanSpec(topic="x", depth="quick", limits={"max_posts_per_query": 77})
    assert plan.limits["max_posts_per_query"] == 77
    assert plan.limits["query_count"] == 3


def test_invalid_values_raise_but_repair_makes_model_output_safe():
    with pytest.raises(ValueError):
        ResearchPlanSpec(topic="x", depth="bottomless")
    with pytest.raises(ValueError):
        ResearchPlanSpec(topic="x", timeframe={"start": "2024-05-01", "end": "2023-01-01"})
    repaired, issues = repair_plan_dict({
        "topic": "protests", "geography": "Iran, Iraq", "depth": "thorough", "platforms": ["Twitter", "Reddit", "Bluesky"],
        "timeframe": {"start": "2024-06-01", "end": "2023-01-01"}, "translation": {"policy": "yes"},
    })
    assert repaired["geography"] == ["Iran", "Iraq"]
    assert repaired["depth"] == "deep"
    assert repaired["platforms"] == ["x", "bluesky"]
    assert repaired["timeframe"]["start"] == "2023-01-01"     # reversed dates are swapped
    assert repaired["translation"]["policy"] == "always"
    assert any("Reddit" in i.message for i in issues)          # unsupported platform is reported, not silent
    assert ResearchPlanSpec.from_dict(repaired).source_scope == "selected"


def test_missing_topic_is_the_only_blocking_error():
    plan, issues = build_plan({"geography": ["Iran"]})
    assert plan is None
    assert [i.field for i in issues if i.severity == "error"] == ["topic"]
    plan, issues = build_plan({"topic": "  elections  "})
    assert plan is not None and plan.topic == "elections"
    assert plan.research_question == "What is being said about elections?"


def test_unparseable_date_is_cleared_with_a_warning_not_guessed():
    plan, issues = build_plan({"topic": "x", "timeframe": {"start": "sometime last spring", "end": ""}})
    assert plan is not None
    assert plan.timeframe["start"] == ""
    assert any(i.field == "timeframe.start" for i in issues)


def test_platform_normalization_and_all_platform_alias():
    assert normalize_platform("Twitter/X") == "x"
    assert normalize_platform("BSKY") == "bluesky"
    assert normalize_platform("unknown-site") == ""
    plan, _ = build_plan({"topic": "x", "platforms": ["all platforms"]})
    assert plan.source_scope == "all_enabled" and plan.platforms == []
    plan, _ = build_plan({"topic": "x", "platforms": ["mastodon"]}, available_platforms={"bluesky"})
    assert plan.platforms == [] and plan.source_scope == "all_enabled"


def test_fingerprint_ignores_ids_and_interpretation_notes():
    a = ResearchPlanSpec(topic="x", interpretation={"method": "llm"})
    b = ResearchPlanSpec(topic="x", interpretation={"method": "manual"})
    assert a.plan_id != b.plan_id
    assert a.fingerprint() == b.fingerprint()
    assert ResearchPlanSpec(topic="y").fingerprint() != a.fingerprint()


def test_query_specs_have_stable_ids_and_enabled_filter():
    q = QuerySpec(text="democracy Egypt", platform="Twitter")
    assert q.platform == "x" and q.id == QuerySpec(text="democracy Egypt", platform="x").id
    plan = ResearchPlanSpec(topic="x", queries=[{"text": "a"}, {"text": "b", "enabled": False}])
    assert [q.text for q in plan.enabled_queries()] == ["a"]


def test_interpretation_schema_is_strict_mode_compatible():
    schema = interpretation_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
