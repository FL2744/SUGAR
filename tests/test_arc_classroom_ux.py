from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_frontend_uses_one_shared_map_and_backend_boundary():
    bridge = (ROOT / "SUGAR-Desktop" / "src" / "bridge.ts").read_text(encoding="utf-8")
    map_view = (ROOT / "SUGAR-Desktop" / "src" / "map-view.tsx").read_text(encoding="utf-8")
    shell = (ROOT / "SUGAR-Desktop" / "src" / "shell.tsx").read_text(encoding="utf-8")

    assert "isTauri()" in bridge
    assert '"run_backend"' in bridge
    assert '"/api/run"' in bridge
    assert "maxZoom: 18" in map_view
    assert "Institutions, on the map." in shell
    assert "Research API" in shell


def test_bridge_exposes_llm_connection_check():
    import sugar_bridge

    assert "llm-check" in sugar_bridge.ALL_OPERATIONS


def test_arc_check_emits_live_model_catalog() -> None:
    bridge = (ROOT / "sugar_bridge.py").read_text(encoding="utf-8")
    assert "available_models=model_ids" in bridge
