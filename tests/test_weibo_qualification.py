from pathlib import Path

from sugar_core.harvest import HarvestStore, HarvestTask
from sugar_core.models import PostRecord
from sugar_core.weibo_qualification import compare_replicates, inspect_weibo_checkpoint


def record(native_id: str, query: str) -> PostRecord:
    return PostRecord(
        platform="weibo",
        native_id=native_id,
        canonical_url=f"https://m.weibo.cn/detail/{native_id}",
        query=query,
        query_matches=[query],
        source_mode="weibo_public_search",
        source_url="https://m.weibo.cn/api/container/getIndex",
        published_at="2026-09-01T12:00:00Z",
        author_name="tester",
        original_text="relevant public post",
    )


def test_checkpoint_metrics(tmp_path: Path):
    path = tmp_path / "run.sqlite3"
    first = HarvestTask(source="weibo", query="孔子学院", page_start=1, page_count=1)
    second = HarvestTask(source="weibo", query="鲁班工坊", page_start=2, page_count=1)
    with HarvestStore(path) as store:
        store.register_tasks([first, second])
        store.start_task(first)
        store.upsert_records([record("1", first.query), record("2", first.query), record("3", first.query)])
        store.complete_task(first, 3)
        store.start_task(second)
        store.upsert_records([record("2", second.query)])
        store.complete_task(second, 1)
    metrics = inspect_weibo_checkpoint(path, expected_terms=[first.query, second.query])
    assert metrics["unique_records"] == 3
    assert metrics["raw_records_returned"] == 4
    assert metrics["estimated_duplicate_fraction"] == 0.25
    assert metrics["task_completion_rate"] == 1.0
    assert metrics["query_coverage"] == 1.0
    assert metrics["identity_coverage"] == 1.0
    assert metrics["provenance_coverage"] == 1.0


def test_access_gate_is_not_false_zero(tmp_path: Path):
    path = tmp_path / "gated.sqlite3"
    task = HarvestTask(source="weibo", query="孔子学院", page_start=1, page_count=1)
    with HarvestStore(path) as store:
        store.register_tasks([task])
        store.start_task(task)
        store.fail_task(task, "Weibo keyword search requires authorization")
    metrics = inspect_weibo_checkpoint(path, expected_terms=[task.query])
    assert metrics["failed_task_rate"] == 1.0
    assert metrics["access_limited_task_rate"] == 1.0
    assert metrics["query_coverage"] == 0.0


def test_replicate_jaccard():
    result = compare_replicates([
        {"record_keys": ["weibo:1", "weibo:2", "weibo:3"]},
        {"record_keys": ["weibo:2", "weibo:3", "weibo:4"]},
    ])
    assert result["minimum_jaccard"] == 0.5
