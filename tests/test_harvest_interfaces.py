from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core.cli import _merge_terms
from sugar_core.service import run_harvest


def test_terms_file_supports_comments_bom_and_deduplication(tmp_path: Path):
    first = tmp_path / "terms_a.txt"
    second = tmp_path / "terms_b.txt"
    first.write_text("\ufeff# project terms\n孔子学院\n\n鲁班工坊\n", encoding="utf-8")
    second.write_text("鲁班工坊\n中国文化中心\n# ignored\n", encoding="utf-8")

    assert _merge_terms(["汉语桥", "孔子学院"], [str(first), str(second)]) == [
        "汉语桥",
        "孔子学院",
        "鲁班工坊",
        "中国文化中心",
    ]


def test_service_guard_records_access_mode_without_credentials(tmp_path: Path, monkeypatch):
    captured = []

    def fake_run(config, secrets, progress=None):
        captured.append(dict(secrets))
        manifest = tmp_path / "guarded.harvest.json"
        manifest.write_text(json.dumps({"unique_records": 0}), encoding="utf-8")
        return [str(manifest)]

    monkeypatch.setattr("sugar_core.service._run_harvest", fake_run)
    config = {
        "sources": ["weibo", "bilibili"],
        "terms": ["孔子学院"],
        "output_directory": str(tmp_path),
        "harvest": {"name": "guarded"},
    }

    outputs = run_harvest(config, {"weibo_cookie": "SUB=secret-session-value"})
    marker = tmp_path / "guarded.harvest.access.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "guarded.harvest.json").read_text(encoding="utf-8"))

    assert payload["access_modes"] == {"bilibili": "anonymous_public", "weibo": "session"}
    assert manifest["access_modes"] == payload["access_modes"]
    assert "secret-session-value" not in marker.read_text(encoding="utf-8")
    assert "secret-session-value" not in (tmp_path / "guarded.harvest.json").read_text(encoding="utf-8")
    assert str(marker.resolve()) in outputs
    assert captured[0]["weibo_cookie"] == "SUB=secret-session-value"


def test_service_guard_refuses_anonymous_session_mixing(tmp_path: Path, monkeypatch):
    def fake_run(config, secrets, progress=None):
        return []

    monkeypatch.setattr("sugar_core.service._run_harvest", fake_run)
    config = {
        "sources": ["weibo"],
        "terms": ["孔子学院"],
        "output_directory": str(tmp_path),
        "harvest": {"name": "same_name"},
    }

    run_harvest(config, {})
    with pytest.raises(ValueError, match="different source access modes"):
        run_harvest(config, {"weibo_cookie": "SUB=legitimate-session"})
