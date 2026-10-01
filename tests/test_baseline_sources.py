from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core import baseline_sources as bs
from sugar_core.reference_registry import list_entities
from sugar_core.workspace import SugarWorkspace

SPEC = {
    "key": "demo-dir", "network": "Demo Network", "role": "reference", "endpoint": "https://directory.example.org/api/list",
    "rows_path": "data", "id_field": "id", "id_prefix": "demo:",
    "fields": {"name": "title", "country": "country", "city": "city", "latitude": "lat", "longitude": "lon"},
    "exclude": [{"field": "title", "equals": "root"}],
    "status": {"field": "state", "map": {"Open": "active", "Closed": "closed"}, "default": "unknown"},
    "detail_url": "https://directory.example.org/place/{id}",
    "description": [{"field": "state", "label": "Directory status"}],
}
ROWS = [
    {"id": 1, "title": "Alpha Hub", "country": "Exampleland", "city": "Town", "lat": "1.5", "lon": "2.5", "state": "Open"},
    {"id": 2, "title": "Beta Hub", "country": "Exampleland", "city": "Village", "lat": "", "lon": "", "state": "Temporarily Paused"},
    {"id": 3, "title": "root"},
]


def test_validate_spec_rejects_bad_input():
    with pytest.raises(ValueError):
        bs.validate_spec({**SPEC, "endpoint": "http://insecure.example.org"})
    with pytest.raises(ValueError):
        bs.validate_spec({**SPEC, "status": {"map": {"x": "thriving"}}})
    with pytest.raises(ValueError):
        bs.parse_pack([])


def test_normalize_keeps_native_status_and_leaves_uncertain_unknown():
    rows = bs.normalize(bs.validate_spec(SPEC), ROWS)
    assert [r["entity_id"] for r in rows] == ["demo:1", "demo:2"]
    assert rows[0]["status"] == "active"
    assert rows[1]["status"] == "unknown" and rows[1]["source_native_status"] == "Temporarily Paused"
    assert rows[0]["source_url"] == "https://directory.example.org/place/1"


def test_sync_is_idempotent_and_writes_snapshot(tmp_path):
    ws = SugarWorkspace.create(tmp_path / "ws", name="Demo")
    specs = {"demo-dir": bs.validate_spec(SPEC)}
    fetcher = lambda spec, **_: ROWS  # noqa: E731
    first = bs.sync_baselines(ws, specs, None, fetcher=fetcher)
    bs.sync_baselines(ws, specs, ["demo_dir"], fetcher=fetcher)
    assert first["sources"]["demo-dir"]["normalized_rows"] == 2
    assert len(list_entities(ws)) == 2
    assert json.loads(Path(first["manifest"]).read_text(encoding="utf-8"))["sources"]["demo-dir"]["raw_rows"] == 3


def test_packs_load_from_project_and_missing_pack_is_explained(tmp_path):
    ws = SugarWorkspace.create(tmp_path / "ws", name="Demo")
    with pytest.raises(ValueError, match="No baseline pack"):
        bs.sync_baselines(ws, {}, None)
    bs.store_pack(ws, {"sources": [SPEC]}, name="demo")
    assert "demo-dir" in bs.load_specs(ws)
