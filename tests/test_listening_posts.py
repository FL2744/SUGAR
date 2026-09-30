from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from sugar_core import workspace_hub
from sugar_core.workspace import SugarWorkspace


def _hub(action: str, workspace: SugarWorkspace, *, secrets=None, **config):
    events: list[tuple[str, dict]] = []
    outputs = workspace_hub.run_workspace_hub(
        {"action": action, "workspace": str(workspace.root), **config},
        secrets=secrets or {},
        progress=lambda event, values: events.append((event, values)),
    )
    data = next((values["data"] for event, values in events if event == "workspace_hub_data"), None)
    return outputs, data, events


def test_due_listening_post_runs_search_and_feeds_review_queue(monkeypatch, tmp_path: Path):
    workspace = SugarWorkspace.create(tmp_path / "project", name="Monitoring project")
    _, monitor, _ = _hub(
        "monitor-save",
        workspace,
        name="Student program watch",
        terms=["student language program"],
        sources=["bluesky"],
        cadence_minutes=60,
        post_languages=["en", "es"],
        max_posts_per_query=12,
        max_pages_per_query=2,
    )
    assert monitor["status"] == "active"
    assert monitor["cadence_minutes"] == 60
    assert monitor["revision"] == 1

    monitor_file = workspace.internal_path / "listening-posts.json"
    saved_monitors = json.loads(monitor_file.read_text(encoding="utf-8"))
    saved_monitors[0]["next_due_at"] = "2000-01-01T00:00:00Z"
    monitor_file.write_text(json.dumps(saved_monitors), encoding="utf-8")

    calls: list[tuple[dict, dict]] = []

    def fake_search(config, secrets, *, progress=None):
        calls.append((dict(config), dict(secrets)))
        output_dir = Path(config["output_directory"])
        output_dir.mkdir(parents=True, exist_ok=True)
        records_file = output_dir / "sample.csv"
        pd.DataFrame([{
            "platform": "bluesky",
            "native_id": "post-1",
            "record_key": "bluesky:post-1",
            "canonical_url": "https://bsky.app/profile/example.test/post/post-1",
            "published_at": "2026-09-30T12:00:00Z",
            "author_handle": "example.test",
            "original_text": "A public student language program is accepting applications.",
        }]).to_csv(records_file, index=False)
        coverage_file = records_file.with_suffix(".coverage.json")
        coverage_file.write_text(json.dumps({"overall_status": "success", "sources": {
            "bluesky": {"status": "success", "records": 1},
        }}), encoding="utf-8")
        return [str(records_file), str(coverage_file)]

    monkeypatch.setattr(workspace_hub, "run_search", fake_search)
    secret_values = {"x_bearer_token": "test-secret-token"}
    _, result, events = _hub("monitor-run-due", workspace, secrets=secret_values, max_monitors=10)

    assert result["due_count"] == 1
    assert result["run_count"] == 1
    run = result["runs"][0]
    assert run["status"] == "succeeded"
    assert run["record_count"] == 1
    assert run["new_material"]["new"] == 1
    assert calls[0][0]["sources"] == ["bluesky"]
    assert calls[0][0]["terms"] == ["student language program"]
    assert calls[0][0]["post_languages"] == ["en", "es"]
    assert calls[0][0]["translate_posts"] is False
    assert calls[0][1] == secret_values
    assert any(event == "listening_post_run_start" for event, _ in events)

    _, feed, _ = _hub("monitor-feed", workspace, monitor_id=monitor["monitor_id"], review_state="unreviewed")
    assert feed["count"] == 1
    material_id = feed["material"][0]["material_id"]
    _, reviewed, _ = _hub(
        "monitor-review", workspace,
        material_id=material_id,
        review_state="human_verified",
        actor="Analyst One",
        note="Checked against the original public post.",
    )
    assert reviewed["review_state"] == "human_verified"
    assert reviewed["review_history"][-1]["actor"] == "Analyst One"

    saved_after_run = json.loads(monitor_file.read_text(encoding="utf-8"))[0]
    assert saved_after_run["last_run_status"] == "succeeded"
    assert saved_after_run["next_due_at"] > "2000-01-01T00:00:00Z"
