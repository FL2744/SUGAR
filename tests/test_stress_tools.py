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
    assert all((tmp_path / f"records-{count}" / "stress-report.json").is_file() for count in (5, 3))
    assert parse_scales("1000, 1000, 5000") == [1000, 5000]
