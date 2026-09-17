from __future__ import annotations

from tools.soak_test import run_soak


def test_offline_soak_is_bounded_and_records_checkpoint_samples():
    report = run_soak(25, iterations=2, duration_seconds=0, max_samples=1)

    assert report["network"] is False
    assert report["iterations_requested"] == 2
    assert report["iterations_completed"] == 2
    assert len(report["samples"]) == 1
    assert report["samples"][0]["iteration"] == 2
    assert report["samples"][0]["probe_results"]
