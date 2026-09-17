import csv
import json
from pathlib import Path

import pytest

import sugar_core.weibo_qualification as qualification
from sugar_core.harvest import HarvestStore, HarvestTask
from sugar_core.models import PostRecord
from sugar_core.weibo_investigation import WeiboInvestigation
from sugar_core.weibo_qualification import (
    QualificationResult,
    QualificationThresholds,
    _aggregate_runs,
    _deterministic_audit_sample,
    _investigation_summary,
    _looks_access_limited,
    _markdown_report,
    _safe_ratio,
    compare_replicates,
    evaluate_qualification,
    inspect_weibo_checkpoint,
    read_human_audit,
    run_weibo_qualification,
    write_human_audit_sample,
)


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
    first = HarvestTask(source="weibo", query="文化交流", page_start=1, page_count=1)
    second = HarvestTask(source="weibo", query="技术培训", page_start=2, page_count=1)
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
    assert metrics["productive_task_rate"] == 1.0
    assert metrics["zero_yield_task_rate"] == 0.0
    assert metrics["mean_records_per_completed_task"] == 2.0
    assert metrics["query_coverage"] == 1.0
    assert metrics["identity_coverage"] == 1.0
    assert metrics["provenance_coverage"] == 1.0
    assert len(metrics["task_yield"]) == 2


def test_access_gate_is_not_false_zero(tmp_path: Path):
    path = tmp_path / "gated.sqlite3"
    task = HarvestTask(source="weibo", query="文化交流", page_start=1, page_count=1)
    with HarvestStore(path) as store:
        store.register_tasks([task])
        store.start_task(task)
        store.fail_task(task, "Weibo keyword search requires authorization")
    metrics = inspect_weibo_checkpoint(path, expected_terms=[task.query])
    assert metrics["failed_task_rate"] == 1.0
    assert metrics["access_limited_task_rate"] == 1.0
    assert metrics["query_coverage"] == 0.0
    assert metrics["zero_yield_queries"] == [task.query]


def test_replicate_jaccard():
    result = compare_replicates([
        {"record_keys": ["weibo:1", "weibo:2", "weibo:3"]},
        {"record_keys": ["weibo:2", "weibo:3", "weibo:4"]},
    ])
    assert result["minimum_jaccard"] == 0.5


def test_empty_replicates_are_not_perfect_reproducibility():
    result = compare_replicates([
        {"record_keys": []},
        {"record_keys": []},
    ])
    assert result["pairwise_jaccard"][0]["jaccard"] is None
    assert result["minimum_jaccard"] is None
    assert result["mean_jaccard"] is None


def test_threshold_mapping_ignores_unknown_fields_and_overrides_known_values():
    thresholds = QualificationThresholds.from_mapping(
        {"minimum_unique_records": 25, "minimum_query_coverage": 0.5, "not_a_threshold": 999}
    )
    assert thresholds.minimum_unique_records == 25
    assert thresholds.minimum_query_coverage == 0.5
    assert not hasattr(thresholds, "not_a_threshold")


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(1, 4, 0.25), (1, 0, None), (1, -1, None)],
)
def test_safe_ratio_handles_empty_denominators(numerator, denominator, expected):
    assert _safe_ratio(numerator, denominator) == expected


@pytest.mark.parametrize(
    "message",
    [
        "authorization required",
        "Risk-Control triggered",
        "需要登录",
        "访问频次过高",
    ],
)
def test_access_limit_detection_covers_common_gates(message):
    assert _looks_access_limited(message)


def test_access_limit_detection_does_not_classify_generic_failure():
    assert not _looks_access_limited("temporary upstream timeout")


def test_single_replicate_has_no_reproducibility_score():
    result = compare_replicates([{"record_keys": ["weibo:1"]}])
    assert result == {
        "replicates": 1,
        "pairwise_jaccard": [],
        "minimum_jaccard": None,
        "mean_jaccard": None,
    }


def test_deterministic_audit_sample_is_repeatable_and_query_stratified():
    records = [
        record("1", "alpha"),
        record("2", "alpha"),
        record("3", "alpha"),
        record("4", "beta"),
        record("5", "beta"),
        record("6", "beta"),
    ]

    first = _deterministic_audit_sample(records, 4)
    second = _deterministic_audit_sample(list(reversed(records)), 4)

    assert [row.record_key for row in first] == [row.record_key for row in second]
    queries = {row.query for row in first}
    assert queries == {"alpha", "beta"}
    assert _deterministic_audit_sample(records, 0) == []


def test_write_and_read_human_audit_round_trip(tmp_path: Path):
    path = Path(write_human_audit_sample([record("1", "alpha"), record("2", "beta")], tmp_path / "audit.csv", size=2))
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    rows[0]["human_relevant"] = "yes"
    rows[0]["human_provenance_ok"] = "ok"
    rows[1]["human_relevant"] = "irrelevant"
    rows[1]["human_provenance_ok"] = "bad"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    audit = read_human_audit(path)
    assert audit["provided"] is True
    assert audit["labeled"] == 2
    assert audit["provenance_labeled"] == 2
    assert audit["relevance_rate"] == 0.5
    assert audit["provenance_ok_rate"] == 0.5
    assert read_human_audit(None)["provided"] is False


def test_read_human_audit_rejects_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_human_audit(tmp_path / "missing.csv")


def test_aggregate_runs_uses_worst_case_acceptance_metrics():
    aggregate = _aggregate_runs(
        [
            {
                "unique_records": 100,
                "task_completion_rate": 1.0,
                "productive_task_rate": 0.9,
                "query_coverage": 1.0,
                "identity_coverage": 1.0,
                "provenance_coverage": 1.0,
                "timestamp_coverage": 1.0,
                "text_coverage": 1.0,
                "failed_task_rate": 0.0,
                "access_limited_task_rate": 0.1,
                "zero_yield_task_rate": 0.1,
                "estimated_duplicate_fraction": 0.2,
                "rate_limit_events": 1,
            },
            {
                "unique_records": 80,
                "task_completion_rate": 0.95,
                "productive_task_rate": 0.8,
                "query_coverage": 0.75,
                "identity_coverage": 0.99,
                "provenance_coverage": 0.98,
                "timestamp_coverage": 0.9,
                "text_coverage": 0.95,
                "failed_task_rate": 0.05,
                "access_limited_task_rate": 0.2,
                "zero_yield_task_rate": 0.25,
                "estimated_duplicate_fraction": 0.4,
                "rate_limit_events": 3,
            },
        ]
    )
    assert aggregate["replicate_count"] == 2
    assert aggregate["unique_records"] == 80
    assert aggregate["query_coverage"] == 0.75
    assert aggregate["failed_task_rate"] == 0.05
    assert aggregate["estimated_duplicate_fraction"] == 0.4
    assert aggregate["rate_limit_events"] == 3
    assert _aggregate_runs([]) == {}


def _passing_aggregate() -> dict:
    return {
        "unique_records": 1500,
        "task_completion_rate": 1.0,
        "failed_task_rate": 0.0,
        "access_limited_task_rate": 0.0,
        "query_coverage": 1.0,
        "identity_coverage": 1.0,
        "provenance_coverage": 1.0,
        "timestamp_coverage": 1.0,
        "text_coverage": 1.0,
        "estimated_duplicate_fraction": 0.1,
    }


def _passing_investigations() -> list[dict]:
    return [
        {
            "status": "ok",
            "seed_surface": "ok",
            "reported_comments": 2,
            "comment_surface": "ok",
            "comments_retrieved": 2,
        }
    ]


def _passing_audit() -> dict:
    return {
        "provided": True,
        "labeled": 50,
        "provenance_labeled": 50,
        "relevance_rate": 0.8,
        "provenance_ok_rate": 0.98,
    }


def test_qualification_passes_when_all_automated_and_human_gates_pass():
    status, checks, limitations = evaluate_qualification(
        _passing_aggregate(),
        _passing_investigations(),
        {"replicates": 2, "minimum_jaccard": 0.8},
        _passing_audit(),
        QualificationThresholds(),
    )
    assert status == "pass"
    assert all(check.passed for check in checks)
    assert limitations


def test_single_replicate_is_conditional_instead_of_silently_skipping_reproducibility():
    status, checks, _ = evaluate_qualification(
        _passing_aggregate(),
        _passing_investigations(),
        {"replicates": 1, "minimum_jaccard": None},
        _passing_audit(),
        QualificationThresholds(),
    )
    reproducibility = next(check for check in checks if check.name == "replicate_minimum_jaccard")
    assert status == "conditional"
    assert reproducibility.severity == "advisory"
    assert reproducibility.passed is False
    assert "At least two" in reproducibility.note


def test_missing_human_audit_is_conditional_when_required_automated_gates_pass():
    status, _, _ = evaluate_qualification(
        _passing_aggregate(),
        _passing_investigations(),
        {"replicates": 2, "minimum_jaccard": 0.8},
        {"provided": False, "labeled": 0, "provenance_labeled": 0},
        QualificationThresholds(),
    )
    assert status == "conditional"


def test_required_failure_takes_precedence_over_advisory_or_human_gates():
    aggregate = _passing_aggregate()
    aggregate["unique_records"] = 10
    status, checks, _ = evaluate_qualification(
        aggregate,
        [],
        {"replicates": 1, "minimum_jaccard": None},
        {"provided": False, "labeled": 0, "provenance_labeled": 0},
        QualificationThresholds(),
    )
    assert status == "fail"
    assert any(check.name == "unique_records" and not check.passed for check in checks)
    assert any(check.name == "seed_investigation_success_rate" and not check.passed for check in checks)


def test_investigation_summary_reports_success_and_failure():
    seed = record("seed", "alpha")
    seed.engagement = {"replies": 4, "reposts": 2}
    investigation = WeiboInvestigation(
        seed=seed,
        comments=[record("comment", "alpha")],
        reposts=[record("repost", "alpha")],
        author_posts=[record("author", "alpha")],
        original=None,
        surface_status={
            "seed": {"status": "ok"},
            "comments": {"status": "ok"},
            "reposts": {"status": "access_limited"},
            "author_timeline": {"status": "ok"},
        },
        insights={
            "retrieval": {"comment_retrieved_to_reported_ratio": 0.25},
            "response_context": {"top_public_responses": list(range(10))},
        },
    )
    summary = _investigation_summary("seed-url", investigation)
    assert summary["status"] == "ok"
    assert summary["reported_comments"] == 4
    assert summary["comment_capture_ratio"] == 0.25
    assert len(summary["top_responses"]) == 5

    failed = _investigation_summary("seed-url", None, RuntimeError("blocked"))
    assert failed["status"] == "failed"
    assert failed["error"] == "RuntimeError: blocked"


def test_markdown_report_renders_checks_investigations_and_limitations():
    result = QualificationResult(
        status="conditional",
        generated_at="2026-09-17T00:00:00Z",
        thresholds={},
        aggregate_metrics={"unique_records": 12},
        investigations=[
            {
                "seed": "123",
                "status": "ok",
                "comments_retrieved": 2,
                "seed_surface": "ok",
                "comment_surface": "ok",
                "repost_surface": "access_limited",
                "author_timeline_surface": "ok",
            }
        ],
        checks=[
            {
                "name": "query_coverage",
                "value": 0.8,
                "threshold": 0.75,
                "passed": True,
                "severity": "required",
                "note": "",
            }
        ],
        limitations=["Human review remains required."],
    )
    markdown = _markdown_report(result)
    assert "**Status:** CONDITIONAL" in markdown
    assert "| query_coverage | 0.8 | 0.75 | PASS | required |" in markdown
    assert "`123` — ok — comments 2" in markdown
    assert "Human review remains required." in markdown


def test_run_qualification_requires_terms(tmp_path: Path):
    with pytest.raises(ValueError, match="at least one keyword"):
        run_weibo_qualification({"output_directory": str(tmp_path), "qualification": {}})


def test_run_qualification_registers_investigation_outputs_and_passes_offline(monkeypatch, tmp_path: Path):
    progress = []

    def harvest_runner(config, secrets, progress=None):
        checkpoint = Path(config["output_directory"]) / f"{config['harvest']['name']}.harvest.sqlite3"
        tasks = [HarvestTask(source="weibo", query=term, page_start=1, page_count=1) for term in config["terms"]]
        with HarvestStore(checkpoint) as store:
            store.register_tasks(tasks)
            for index, task in enumerate(tasks, 1):
                store.start_task(task)
                row = record(str(index), task.query)
                row.query_matches = [task.query]
                store.upsert_records([row])
                store.complete_task(task, 1)
        return [str(checkpoint)]

    def investigator(seed, **kwargs):
        seed_record = record("seed-1", "alpha")
        seed_record.engagement = {"replies": 1, "reposts": 0}
        return WeiboInvestigation(
            seed=seed_record,
            comments=[record("comment-1", "alpha")],
            reposts=[],
            author_posts=[],
            original=None,
            surface_status={
                "seed": {"status": "ok"},
                "comments": {"status": "ok"},
                "reposts": {"status": "ok"},
                "author_timeline": {"status": "ok"},
            },
            insights={"retrieval": {}, "response_context": {}},
        )

    def fake_save(result, output_directory, *, name):
        path = Path(output_directory) / f"{name}.brief.md"
        path.write_text("investigation", encoding="utf-8")
        return [str(path)]

    monkeypatch.setattr(qualification, "save_weibo_investigation", fake_save)
    config = {
        "terms": ["alpha", "beta"],
        "output_directory": str(tmp_path),
        "qualification": {
            "name": "acceptance",
            "replicates": 2,
            "seeds": ["seed-url"],
            "audit_sample_size": 2,
            "thresholds": {
                "minimum_unique_records": 2,
                "minimum_query_coverage": 1.0,
                "minimum_identity_coverage": 1.0,
                "minimum_provenance_coverage": 1.0,
                "minimum_timestamp_coverage": 1.0,
                "minimum_text_coverage": 1.0,
                "minimum_seed_success_rate": 1.0,
                "minimum_comment_surface_success_rate": 1.0,
                "minimum_replicate_jaccard": 1.0,
                "minimum_human_audit_labels": 0,
            },
        },
    }

    outputs = run_weibo_qualification(
        config,
        {"weibo_cookie": "session=value"},
        progress=lambda event, values: progress.append((event, values)),
        harvest_runner=harvest_runner,
        investigator=investigator,
    )

    investigation_output = tmp_path / "acceptance.investigations" / "seed_1_seed-1.brief.md"
    assert str(investigation_output.resolve()) in outputs
    assert investigation_output.is_file()
    assert len([path for path in outputs if path.endswith(".harvest.sqlite3")]) == 2
    payload = json.loads((tmp_path / "acceptance.qualification.json").read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert str(investigation_output.resolve()) in payload["outputs"]
    assert (tmp_path / "acceptance.human_audit.csv").is_file()
    assert "**Status:** PASS" in (tmp_path / "acceptance.qualification.md").read_text(encoding="utf-8")
    events = [event for event, _ in progress]
    assert events[0] == "qualification_start"
    assert events.count("qualification_replicate_complete") == 2
    assert "qualification_seed_complete" in events
    assert events[-1] == "qualification_complete"
