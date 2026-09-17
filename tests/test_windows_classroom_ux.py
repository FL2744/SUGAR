from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_classroom_first_run_copy_and_defaults():
    app = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    assert "Start here — first time?" in app
    assert 'self.store.value("llm/provider", "arc")' in app
    assert 'self.search_sources.boxes["bilibili"].setChecked(True)' in app
    assert 'self.search_sources.boxes["weibo"].setChecked(True)' in app
    assert "Audit & Changes" in app
    assert "Compare assessment versions" in app
    assert "basic public Bilibili/Weibo collection" in app


def test_windows_theme_does_not_paint_every_widget_white():
    app = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    assert "QMainWindow, QWidget { background:" not in app
    assert "QLabel, QCheckBox { background: transparent; }" in app
    assert "QMenuBar { background: #ffffff" in app


def test_bundled_bridge_exposes_windows_cli_wrappers():
    bridge = (ROOT / "sugar_bridge.py").read_text(encoding="utf-8")
    build = (ROOT / "SUGAR-Windows" / "scripts" / "build.ps1").read_text(encoding="utf-8")
    assert '{"cli", "project", "state", "intel"}' in bridge
    for wrapper in ("sugar.cmd", "sugar-project.cmd", "sugar-state.cmd", "sugar-intel.cmd"):
        assert wrapper in build
    assert "CLASSROOM-QUICK-START.md" in build
