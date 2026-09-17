from __future__ import annotations

from pathlib import Path

from sugar_core.models import PostRecord
from sugar_core.plan_execution import execute_search_plan
from sugar_core.research_requirements import ResearchRequirement, build_initial_search_plan


def test_execute_search_plan_reuses_collection_service_and_records_observable_metrics(monkeypatch, tmp_path: Path):
    requirement = ResearchRequirement(
        question="What is happening around Public Engagement Center A in Exampleland?",
        geographies=["Exampleland"],
        known_entities=["Public Engagement Center A"],
        preferred_sources=["bilibili"],
    )
    plan = build_initial_search_plan(requirement)
    first_query = plan.branches[0].query
    second_query = plan.branches[1].query
    csv_path = tmp_path / "collected.csv"
    csv_path.write_text("placeholder", encoding="utf-8")
    observed_config = {}

    def fake_run_search(config, secrets, progress=None):
        observed_config.update(config)
        return [str(csv_path), str(tmp_path / "collected.xlsx"), str(tmp_path / "collected.metadata.json")]

    records = [
        PostRecord(
            platform="bilibili",
            native_id="1",
            canonical_url="https://example.test/1",
            query=first_query,
            query_matches=[first_query],
        ),
        PostRecord(
            platform="bilibili",
            native_id="2",
            canonical_url="https://example.test/2",
            query=second_query,
            query_matches=[first_query, second_query],
        ),
    ]
    monkeypatch.setattr("sugar_core.plan_execution.run_search", fake_run_search)
    monkeypatch.setattr("sugar_core.plan_execution.load_post_records", lambda path: records)

    result = execute_search_plan(
        requirement,
        plan,
        config={"sources": ["bilibili"], "output_directory": str(tmp_path)},
    )

    assert observed_config["terms"] == [first_query, second_query]
    assert observed_config["translate_posts"] is False
    assert observed_config["infer_locations"] is False
    assert result.records == 2
    assert plan.branches[0].metrics.retrieved == 2
    assert plan.branches[1].metrics.retrieved == 1
    assert plan.branches[0].metrics.relevance_assessed == 0
    assert all(branch.status == "completed" for branch in plan.branches)
    assert plan.events[-1]["type"] == "collection_run"
    assert plan.events[-1]["relevance_assessed"] is False
