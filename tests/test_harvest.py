from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from sugar_core.harvest import (
    HarvestConfig,
    HarvestStore,
    build_harvest_tasks,
    rate_limit_wait_seconds,
    run_harvest,
)
from sugar_core.models import PostRecord


def _record(source: str, native_id: str, query: str) -> PostRecord:
    return PostRecord(
        platform=source,
        native_id=native_id,
        canonical_url=f"https://example.test/{source}/{native_id}",
        query=query,
        query_matches=[query],
        original_text=f"record {native_id}",
    )


def test_planner_time_shards_server_bound_sources_and_pages_numbered_sources():
    config = HarvestConfig(
        sources=("x", "bilibili"),
        terms=("one",),
        since="2026-01-01",
        until="2026-01-20",
        shard_days=7,
        pages_per_task=5,
        max_pages_per_query=12,
    )
    tasks = build_harvest_tasks(config)
    x_tasks = [task for task in tasks if task.source == "x"]
    bilibili_tasks = [task for task in tasks if task.source == "bilibili"]

    assert [(task.since, task.until) for task in x_tasks] == [
        ("2026-01-01", "2026-01-07"),
        ("2026-01-08", "2026-01-14"),
        ("2026-01-15", "2026-01-20"),
    ]
    assert [(task.page_start, task.page_count) for task in bilibili_tasks] == [
        (1, 5),
        (6, 5),
        (11, 2),
    ]
    assert all(task.since == "2026-01-01" and task.until == "2026-01-20" for task in bilibili_tasks)


def test_store_merges_duplicate_query_provenance(tmp_path: Path):
    path = tmp_path / "harvest.sqlite3"
    with HarvestStore(path) as store:
        inserted, updated = store.upsert_records([_record("bilibili", "BV1", "alpha")])
        assert (inserted, updated) == (1, 0)
        inserted, updated = store.upsert_records([_record("bilibili", "BV1", "beta")])
        assert (inserted, updated) == (0, 1)
        assert store.count_records() == 1
        record = store.records()[0]
        assert record.query_matches == ["alpha", "beta"]


def test_retry_after_header_is_honored():
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "7"
    error = requests.HTTPError("429 Too Many Requests", response=response)
    assert rate_limit_wait_seconds(error, "mastodon") == 7.0


def test_rate_limit_retries_after_conservative_wait(tmp_path: Path):
    calls = 0
    sleeps: list[float] = []

    def collector(source, request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("X rate limit reached (429).")
        return [_record(source, "1", request.search_terms[0])]

    outputs = run_harvest(
        {
            "sources": ["x"],
            "terms": ["test"],
            "output_directory": str(tmp_path),
            "harvest": {
                "name": "retry",
                "target_records": 1,
                "pages_per_task": 1,
                "posts_per_task": 10,
                "max_retries": 2,
                "max_inline_wait_seconds": 901,
                "inter_task_delay_seconds": 0,
            },
        },
        collector=collector,
        sleeper=sleeps.append,
    )

    assert calls == 2
    assert sleeps == [900.0]
    assert any(path.endswith("retry.csv") for path in outputs)
    with HarvestStore(tmp_path / "retry.harvest.sqlite3") as store:
        assert store.count_records() == 1
        assert store.event_count("rate_limit") == 1


def test_long_rate_limit_is_checkpointed_as_deferred_not_bypassed(tmp_path: Path):
    sleeps: list[float] = []

    def collector(source, request):
        raise RuntimeError("X rate limit reached (429).")

    run_harvest(
        {
            "sources": ["x"],
            "terms": ["test"],
            "output_directory": str(tmp_path),
            "harvest": {
                "name": "deferred",
                "pages_per_task": 1,
                "posts_per_task": 10,
                "max_retries": 3,
                "max_inline_wait_seconds": 60,
                "inter_task_delay_seconds": 0,
            },
        },
        collector=collector,
        sleeper=sleeps.append,
    )

    assert sleeps == []
    with HarvestStore(tmp_path / "deferred.harvest.sqlite3") as store:
        assert store.count_records() == 0
        assert store.task_counts() == {"deferred": 1}
        not_before = store.connection.execute("SELECT not_before FROM tasks").fetchone()[0]
        assert not_before.endswith("Z")


def test_numbered_page_ranges_are_durable_tasks_and_reach_collector(tmp_path: Path):
    ranges: list[tuple[int, int]] = []

    def collector(source, request):
        page_start = int(request.config["_harvest_page_start"])
        page_count = int(request.config["_harvest_page_count"])
        ranges.append((page_start, page_count))
        return [_record(source, f"page-{page_start}", request.search_terms[0])]

    run_harvest(
        {
            "sources": ["bilibili"],
            "terms": ["孔子学院"],
            "output_directory": str(tmp_path),
            "harvest": {
                "name": "page_shards",
                "target_records": 3,
                "posts_per_task": 50,
                "pages_per_task": 2,
                "max_pages_per_query": 6,
                "inter_task_delay_seconds": 0,
            },
        },
        collector=collector,
        sleeper=lambda _: None,
    )

    assert ranges == [(1, 2), (3, 2), (5, 2)]
    with HarvestStore(tmp_path / "page_shards.harvest.sqlite3") as store:
        assert store.count_records() == 3
        assert store.task_counts() == {"completed": 3}


def test_checkpoint_refuses_silent_plan_mixing(tmp_path: Path):
    def collector(source, request):
        return [_record(source, request.search_terms[0], request.search_terms[0])]

    base = {
        "sources": ["bilibili"],
        "terms": ["alpha"],
        "output_directory": str(tmp_path),
        "harvest": {
            "name": "fixed_plan",
            "target_records": 1,
            "pages_per_task": 1,
            "max_pages_per_query": 1,
            "inter_task_delay_seconds": 0,
        },
    }
    run_harvest(base, collector=collector, sleeper=lambda _: None)

    changed = dict(base)
    changed["terms"] = ["beta"]
    with pytest.raises(ValueError, match="different collection plan"):
        run_harvest(changed, collector=collector, sleeper=lambda _: None)


def test_full_harvest_scales_to_five_thousand_and_resumes_without_recollection(
    tmp_path: Path,
    monkeypatch,
):
    calls: list[str] = []

    def collector(source, request):
        shard = request.since or "all"
        calls.append(shard)
        query = request.search_terms[0]
        return [_record(source, f"{shard}-{index:04d}", query) for index in range(250)]

    # Keep the scale test focused on orchestration/checkpointing rather than openpyxl speed on six
    # CI environments. The real save_records path is covered elsewhere; JSONL/SQLite remain real.
    def lightweight_save(records, output_file, metadata=None):
        records = list(records)
        output_file = Path(output_file)
        output_file.write_text("records=" + str(len(records)), encoding="utf-8")
        output_file.with_suffix(".xlsx").write_text("test placeholder", encoding="utf-8")
        output_file.with_suffix(".metadata.json").write_text(
            json.dumps(metadata or {}, ensure_ascii=False), encoding="utf-8"
        )

    monkeypatch.setattr("sugar_core.harvest.save_records", lightweight_save)

    config = {
        "sources": ["x"],
        "terms": ["public diplomacy"],
        "since": "2026-01-01",
        "until": "2026-01-20",
        "output_directory": str(tmp_path),
        "harvest": {
            "name": "scale5000",
            "target_records": 5000,
            "shard_days": 1,
            "posts_per_task": 250,
            "pages_per_task": 5,
            "inter_task_delay_seconds": 0,
        },
    }
    outputs = run_harvest(config, collector=collector, sleeper=lambda _: None)

    assert len(calls) == 20
    assert any(path.endswith("scale5000.jsonl") for path in outputs)
    jsonl = tmp_path / "scale5000.jsonl"
    assert sum(1 for _ in jsonl.open("r", encoding="utf-8")) == 5000
    manifest = json.loads((tmp_path / "scale5000.harvest.json").read_text(encoding="utf-8"))
    assert manifest["unique_records"] == 5000
    assert manifest["task_counts"] == {"completed": 20}

    def should_not_run(source, request):
        raise AssertionError("completed harvest tasks should not be collected again")

    run_harvest(config, collector=should_not_run, sleeper=lambda _: None)
    with HarvestStore(tmp_path / "scale5000.harvest.sqlite3") as store:
        assert store.count_records() == 5000
        assert store.task_counts() == {"completed": 20}
