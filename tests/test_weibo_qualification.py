from __future__ import annotations

import csv
import json
from pathlib import Path

from sugar_core.harvest import HarvestStore, HarvestTask
from sugar_core.models import PostRecord
from sugar_core.weibo_investigation import WeiboInvestigation
from sugar_core.weibo_qualification import (
    QualificationThresholds,
    compare_replicates,
    evaluate_qualification,
    inspect_weibo_checkpoint,
    read_human_audit,
    run_weibo_qualification,
)


def _record(native_id: str, query: str = "孔子学院") -> PostRecord:
    return PostRecord(
        platform="weibo",
        native_id=native_id,
        canonical_url=f"https://m.weibo.cn/detail/{native_id}",
        query=query,
        query_matches=[query],
        source_mode="weibo_public_search",
        source_host="m.weibo.cn",
        source_url=f"https://m.weibo.cn/api/container/getIndex?q={query}",
        published_at="2026-09-01T12:00:00Z",
        author_handle=f"u{native_id}",
        author_name=f"User {native_id}",
        original_text=f"Relevant public post {native_id}",
        engagement={"likes": 1, "replies": 1, "reposts": 0},
    )


def _write_checkpoint(path: Path, ids: list[str], terms: list[str]) -> None:
    tasks = [HarvestTask(source="weibo", query=term, page_start=index + 1, page_count=1) for index, term in enumerate(terms)]
    with HarvestStore(path) as store:
        store.register_tasks(tasks)
        for index, task in enumerate(tasks):
            store.start_task(task)
            rows = [_record(ids[index % len(ids)], task.query)]
            # Give every term at least one unique record and add extra records on the first query.
            if index == 0:
                rows.extend(_record(native_id, task.query) for native_id in ids[1:])
            store.upsert_records(rows)
            store.complete_task(task, len(rows))
            store.add_event("task_completed", source="weibo", task_id=task.task_id, returned=len(rows))


def test_checkpoint_metrics_cover_identity_provenance_queries_and_duplicates(tmp_path):
    checkpoint = tmp_path / "run.sqlite3"
    _write_checkpoint(checkpoint, ["1", "2", "3"], ["孔子学院", "鲁班工坊"])
    metrics = inspect_weibo_checkpoint(checkpoint, expected_terms=["孔子学院", "鲁班工坊"])
    assert metrics["unique_records"] == 4
    assert metrics["task_completion_rate"] == 1.0
    assert metrics["query_coverage"] == 1.0
    assert metrics["identity_coverage"] == 1.0
    assert metrics["provenance_coverage"] == 1.0
    assert metrics["timestamp_coverage"] == 1.0
    assert metrics["text_coverage"] == 1.0
    assert metrics["maximum_completed_page"] == 2


def test_access_limited_tasks_are_measured_separately(tmp_path):
    checkpoint = tmp_path / "gated.sqlite3"
    task = HarvestTask(source="weibo", query="孔子学院", page_start=1, page_count=1)
    with HarvestStore(checkpoint) as store:
        store.register_tasks([task])
        store.start_task(task)
        store.fail_task(task, "Weibo keyword search requires a logged-in/authorized session")
    metrics = inspect_weibo_checkpoint(checkpoint, expected_terms=["孔子学院"])
    assert metrics["failed_task_rate"] == 1.0
    assert metrics["access_limited_task_rate"] == 1.0
    assert metrics["query_coverage"] == 0.0


def test_replicate_jaccard_detects_snapshot_stability():
    metrics = [
        {"record_keys": ["weibo:1", "weibo:2", "weibo:3"]},
        {"record_keys": ["weibo:2", "weibo:3", "weibo:4"]},
    ]
    result = compare_replicates(metrics)
    assert result["minimum_jaccard"] == 0.5
    assert result["mean_jaccard"] == 0.5


def _fake_investigation(seed: str, **kwargs) -> WeiboInvestigation:
    seed_record = _record("5320265912291527", "seed")
    seed_record.engagement = {"likes": 125, "replies": 49, "reposts": 26}
    comment = _record("5320678784111166", "seed")
    comment.content_type = "comment"
    comment.original_text = "中西方文化crossover"
    comment.parent_record_key = seed_record.record_key
    comment.thread_root_key = seed_record.record_key
    return WeiboInvestigation(
        seed=seed_record,
        comments=[comment],
        reposts=[],
        author_posts=[],
        original=None,
        surface_status={
            "seed": {"status": "ok", "mode": "pwa_json"},
            "comments": {"status": "ok", "records": "1"},
            "reposts": {"status": "access_limited"},
            "author_timeline": {"status": "access_limited"},
        },
        insights={
            "retrieval": {"comment_retrieved_to_reported_ratio": 1 / 49},
            "response_context": {"top_public_responses": [{"text": "中西方文化crossover"}]},
        },
    )


def test_full_qualification_stays_conditional_until_human_audit(tmp_path):
    call = {"count": 0}

    def fake_harvest(config, secrets, progress=None):
        call["count"] += 1
        name = config["harvest"]["name"]
        checkpoint = Path(config["output_directory"]) / f"{name}.harvest.sqlite3"
        ids = ["1", "2", "3"] if call["count"] == 1 else ["1", "2", "3"]
        _write_checkpoint(checkpoint, ids, list(config["terms"]))
        return [str(checkpoint)]

    config = {
        "terms": ["孔子学院", "鲁班工坊"],
        "output_directory": str(tmp_path),
        "harvest": {"target_records": 3},
        "qualification": {
            "name": "industrial",
            "replicates": 2,
            "seeds": ["5320265912291527"],
            "audit_sample_size": 3,
            "thresholds": {
                "minimum_unique_records": 3,
                "minimum_human_audit_labels": 2,
                "minimum_human_relevance_rate": 0.5,
            },
        },
    }
    outputs = run_weibo_qualification(config, {}, harvest_runner=fake_harvest, investigator=_fake_investigation)
    report = json.loads((tmp_path / "industrial.qualification.json").read_text(encoding="utf-8"))
    assert report["status"] == "conditional"
    assert report["aggregate_metrics"]["reproducibility"]["minimum_jaccard"] == 1.0
    assert (tmp_path / "industrial.human_audit.csv").is_file()
    assert any(path.endswith("industrial.qualification.md") for path in outputs)


def test_completed_human_audit_can_pass_qualification(tmp_path):
    audit = tmp_path / "audit.csv"
    with audit.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["human_relevant", "human_provenance_ok"])
        writer.writeheader()
        writer.writerow({"human_relevant": "yes", "human_provenance_ok": "yes"})
        writer.writerow({"human_relevant": "yes", "human_provenance_ok": "yes"})
    audit_metrics = read_human_audit(audit)
    thresholds = QualificationThresholds(
        minimum_unique_records=3,
        minimum_human_audit_labels=2,
        minimum_human_relevance_rate=0.5,
    )
    aggregate = {
        "unique_records": 3,
        "task_completion_rate": 1.0,
        "failed_task_rate": 0.0,
        "access_limited_task_rate": 0.0,
        "query_coverage": 1.0,
        "identity_coverage": 1.0,
        "provenance_coverage": 1.0,
        "timestamp_coverage": 1.0,
        "text_coverage": 1.0,
        "estimated_duplicate_fraction": 0.0,
    }
    investigations = [{
        "status": "ok",
        "seed_surface": "ok",
        "comment_surface": "ok",
        "comments_retrieved": 1,
        "reported_comments": 1,
    }]
    status, checks, _ = evaluate_qualification(
        aggregate,
        investigations,
        {"replicates": 2, "minimum_jaccard": 1.0},
        audit_metrics,
        thresholds,
    )
    assert status == "pass"
    assert all(check.passed for check in checks if check.severity in {"required", "human"})
