from __future__ import annotations

import json
import os

import pytest

from sugar_core.weibo_qualification import run_weibo_qualification


pytestmark = pytest.mark.skipif(
    os.environ.get("SUGAR_LIVE_WEIBO") != "1",
    reason="set SUGAR_LIVE_WEIBO=1 to run the bounded public Weibo qualification smoke",
)


def test_live_weibo_qualification_exercises_search_and_real_seed(tmp_path):
    """Bounded live smoke: one search page + one real post + first public comment page.

    This is intentionally not an industrial load test. It verifies that SUGAR truthfully records
    the current public search/access boundary while the known public seed/comment path still works.
    """
    config = {
        "sources": ["weibo"],
        "terms": ["孔子学院"],
        "output_directory": str(tmp_path),
        "weibo_hydrate_details": False,
        "harvest": {
            "target_records": None,
            "posts_per_task": 10,
            "pages_per_task": 1,
            "max_pages_per_query": 1,
            "max_retries": 0,
            "max_inline_wait_seconds": 1.0,
            "inter_task_delay_seconds": 0.0,
            "continue_on_error": True,
        },
        "qualification": {
            "name": "live_smoke",
            "replicates": 1,
            "seeds": ["5320265912291527"],
            "max_comments": 5,
            "comment_pages": 1,
            "max_reposts": 1,
            "repost_pages": 1,
            "author_posts": 1,
            "author_pages": 1,
            "audit_sample_size": 5,
            # Smoke thresholds validate plumbing/surface truthfulness, not industrial acceptance.
            "thresholds": {
                "minimum_unique_records": 0,
                "minimum_task_completion_rate": 0.0,
                "maximum_failed_task_rate": 1.0,
                "maximum_access_limited_task_rate": 1.0,
                "minimum_query_coverage": 0.0,
                "minimum_identity_coverage": 0.0,
                "minimum_provenance_coverage": 0.0,
                "minimum_timestamp_coverage": 0.0,
                "minimum_text_coverage": 0.0,
                "maximum_duplicate_fraction": 1.0,
                "minimum_seed_success_rate": 1.0,
                "minimum_comment_surface_success_rate": 1.0,
                "minimum_human_audit_labels": 0,
            },
        },
    }
    outputs = run_weibo_qualification(config, {"weibo_cookie": ""})
    report_path = tmp_path / "live_smoke.qualification.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["investigations"][0]["seed_surface"] == "ok"
    assert report["investigations"][0]["comment_surface"] == "ok"
    assert report["investigations"][0]["comments_retrieved"] > 0

    metrics = report["replicate_metrics"][0]
    assert metrics["planned_tasks"] == 1
    assert metrics["completed_tasks"] + metrics["failed_tasks"] + metrics["deferred_tasks"] == 1
    # If public search is gated, the campaign must classify the gate instead of reporting a silent
    # empty result. A genuine rate limit is also acceptable when explicitly recorded as such.
    if metrics["failed_tasks"] or metrics["deferred_tasks"]:
        assert metrics["access_limited_tasks"] >= 1 or metrics["rate_limit_events"] >= 1

    print("LIVE_WEIBO_QUALIFICATION_STATUS", report["status"])
    print("LIVE_WEIBO_QUALIFICATION_METRICS", metrics)
    print("LIVE_WEIBO_QUALIFICATION_INVESTIGATION", report["investigations"][0])
    print("LIVE_WEIBO_QUALIFICATION_OUTPUTS", outputs)
