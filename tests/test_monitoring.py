import time
from datetime import datetime, timedelta, timezone

import pytest

from sugar_core import monitoring as mon
from sugar_core.reference_registry import upsert_entity
from test_workbench import bench, prepare, project as make_project   # noqa: F401


def add(p, name, **values):
    return upsert_entity(p.workspace, {"name": name, **values}, evidence_refs=[{"source_url": f"https://src.example/{name.replace(' ', '-')}"}])


def test_registry_diff_names_every_kind_of_change():
    before = {"a": {"name": "Harbor Room", "status": "active", "city": "Harbor", "country": "X", "network": "n", "programs": [], "audiences": [], "sources": 1},
              "b": {"name": "Old Center", "status": "active", "city": "Old", "country": "X", "network": "n", "programs": [], "audiences": [], "sources": 1},
              "gone": {"name": "Merged", "status": "active", "city": "", "country": "", "network": "n", "programs": [], "audiences": [], "sources": 1}}
    after = {"a": {"name": "Harbor Hall", "status": "active", "city": "Port", "country": "X", "network": "n", "programs": ["steam"], "audiences": ["educators"], "sources": 2},
             "b": {"name": "Old Center", "status": "closed", "city": "Old", "country": "X", "network": "n", "programs": [], "audiences": [], "sources": 1},
             "c": {"name": "Fresh Space", "status": "active", "city": "New", "country": "Y", "network": "n", "programs": [], "audiences": [], "sources": 1}}
    kinds = sorted((c["name"], c["kind"]) for c in mon.diff_registry(before, after))
    assert ("Harbor Hall", "renamed") in kinds and ("Harbor Hall", "moved") in kinds and ("Harbor Hall", "activity") in kinds
    assert ("Old Center", "closed") in kinds and ("Fresh Space", "new") in kinds and ("Merged", "removed") in kinds
    assert mon.diff_registry(after, after) == []


def test_monitor_settings_are_validated(tmp_path):
    wb, proj = bench(tmp_path), make_project(tmp_path)
    with pytest.raises(ValueError, match="no research plan"):
        mon.save_monitor(proj, name="Weekly", cadence_hours=168)
    prepare(wb, proj)
    saved = mon.save_monitor(proj, name="  Weekly   check ", cadence_hours=168)
    assert saved["name"] == "Weekly check" and saved["enabled"] and mon.list_monitors(proj)[0]["id"] == saved["id"]
    for bad in (0, 5, 100000):
        with pytest.raises(ValueError, match="how often"):
            mon.save_monitor(proj, name="x", cadence_hours=bad)
    with pytest.raises(ValueError, match="name"):
        mon.save_monitor(proj, name=" ", cadence_hours=24)
    assert mon.save_monitor(proj, name="Renamed", cadence_hours=24, monitor_id=saved["id"])["cadence_hours"] == 24 and len(mon.list_monitors(proj)) == 1
    mon.delete_monitor(proj, saved["id"])
    assert mon.list_monitors(proj) == []


def test_digest_baselines_then_reports_institution_changes(tmp_path):
    proj = make_project(tmp_path)
    harbor = add(proj, "Harbor Room", status="active", city="Harbor", country="Exampleland")
    first = mon.build_digest(proj, trigger="manual")
    assert first["first_pass"] and "Baseline" in first["summary"] and first["counts"]["institution_changes"] == 0
    add(proj, "Harbor Room", entity_id=harbor["entity_id"], status="closed")
    add(proj, "Fresh Space", status="active", city="Port", country="Exampleland")
    second = mon.build_digest(proj, trigger="manual")
    assert not second["first_pass"] and any(c["kind"] == "new" and c["name"] == "Fresh Space" for c in second["institution_changes"])
    assert "1 new institution" in second["summary"]
    assert any(c["name"] == "Harbor Room" and c["kind"] == "status" for c in second["institution_changes"])        # two sources now disagree, so status is unresolved
    third = mon.build_digest(proj, trigger="manual")
    assert third["summary"] == "Nothing changed since the last check." and [d["id"] for d in mon.list_digests(proj)] == [third["id"], second["id"], first["id"]]


def test_scheduler_runs_due_monitors_defers_conflicts_and_digests_finished_passes(tmp_path):
    wb, proj = bench(tmp_path), make_project(tmp_path)
    prepare(wb, proj)
    saved = mon.save_monitor(proj, name="Daily", cadence_hours=24)
    clock = {"now": datetime.now(timezone.utc)}
    scheduler = mon.MonitorScheduler(lambda: [proj], lambda: wb, clock=lambda: clock["now"])
    first = scheduler.tick()
    assert first == {"started": 1, "digests": 0}
    monitor = mon.list_monitors(proj)[0]
    assert monitor["last_status"] == "running" and monitor["next_due_at"] > clock["now"].strftime("%Y-%m-%dT%H:%M:%SZ")
    for _ in range(200):                                       # wait for the pass to finish
        row = proj.get_run(monitor["last_run_id"])
        if row and row.status in mon.TERMINAL:
            break
        time.sleep(0.1)
    clock["now"] += timedelta(hours=1)
    second = scheduler.tick()
    assert second == {"started": 0, "digests": 1}              # finished pass becomes a digest; the monitor is not due again yet
    digest = mon.list_digests(proj)[0]
    assert digest["trigger"] == "schedule" and digest["run_id"] == monitor["last_run_id"] and digest["first_pass"] and digest["counts"]["new_items"] >= 1
    clock["now"] += timedelta(days=2)
    assert scheduler.tick()["started"] == 1                    # now it refreshes sources instead of repeating the first run
    assert proj.get_run(mon.list_monitors(proj)[0]["last_run_id"]).kind == "refresh_sources"
    # a running project defers rather than failing or hammering
    clock["now"] += timedelta(days=2)
    conflicted = scheduler.tick()
    assert conflicted["started"] == 0 and mon.list_monitors(proj)[0]["last_status"].startswith("deferred")
    assert saved["id"] == mon.list_monitors(proj)[0]["id"]


def test_disabled_monitors_never_run(tmp_path):
    wb, proj = bench(tmp_path), make_project(tmp_path)
    prepare(wb, proj)
    mon.save_monitor(proj, name="Paused", cadence_hours=6, enabled=False)
    assert mon.due_monitors(proj) == [] and mon.MonitorScheduler(lambda: [proj], lambda: wb).tick() == {"started": 0, "digests": 0}
