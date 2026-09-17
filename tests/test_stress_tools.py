from __future__ import annotations

from tools.soak_test import run_soak
from tools.stress_matrix import parse_scales, run_matrix


def test_offline_soak_is_bounded_and_records_checkpoint_samples():
    report = run_soak(25, iterations=2, duration_seconds=0, max_samples=1)

    assert report["network"] is False
    assert report["iterations_requested"] == 2
    assert report["iterations_completed"] == 2
    assert len(report["samples"]) == 1
    assert report["samples"][0]["iteration"] == 2
    assert report["samples"][0]["probe_results"]


def test_offline_stress_matrix_writes_isolated_reports(tmp_path):
    report = run_matrix([5, 3, 5], tmp_path, export=False, map_output=False)

    assert report["network"] is False
    assert [run["records"] for run in report["runs"]] == [5, 3]
    assert all(run["peak_python_bytes"] > 0 for run in report["runs"])
    assert all(run["disk_bytes"] > 0 for run in report["runs"])
    assert all(run["artifact_sizes_bytes"] for run in report["runs"])
    assert all((tmp_path / f"records-{count}" / "stress-report.json").is_file() for count in (5, 3))
    assert parse_scales("1000, 1000, 5000") == [1000, 5000]


def test_stress_probe_streams_storage_and_bounds_in_memory_sample(tmp_path):
    from tools.stress_test import run_probes

    report = run_probes(25, 5, tmp_path, export=False, map_output=False, in_memory_sample=7)

    assert report["records"] == 25
    assert report["materialized_records"] == 7
    assert report["in_memory_sample_limit"] == 7
    assert next(item for item in report["results"] if item["name"] == "harvest_store_upsert")["records"] == 25
    read = next(item for item in report["results"] if item["name"] == "harvest_store_read")
    assert read["records"] == 25
    assert read["sample_records"] == 7


def test_stress_budgets_report_wall_time_disk_and_peak_failures():
    from tools.stress_test import evaluate_budgets

    report = {
        "results": [{"name": "storage", "seconds": 2.0}],
        "disk_bytes": 20,
        "peak_python_bytes": 30,
    }
    failures = evaluate_budgets(report, max_seconds=1, max_disk_bytes=10, max_peak_python_bytes=15)

    assert failures == [
        "storage exceeded 1s (2.000000s)",
        "disk usage exceeded 10 bytes (20 bytes)",
        "peak Python allocation exceeded 15 bytes (30 bytes)",
    ]
