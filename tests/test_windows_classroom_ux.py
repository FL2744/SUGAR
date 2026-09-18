from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_classroom_first_run_copy_and_defaults():
    app = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    assert "Start here — first time?" in app
    assert 'self.store.value("llm/provider", "arc")' in app
    assert 'self.search_sources.boxes["bilibili"].setChecked(True)' in app
    assert 'self.search_sources.boxes["weibo"].setChecked(True)' not in app
    assert "Audit & Changes" in app
    assert "Compare assessment versions" in app
    assert "Weibo keyword search requires an authorized Weibo session" in app


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

def test_windows_ui_uses_deterministic_light_palette() -> None:
    source = Path("SUGAR-Windows/app.py").read_text(encoding="utf-8")
    assert "def apply_light_palette(" in source
    assert "QPalette.ColorRole.WindowText" not in source  # roles are intentionally aliased locally
    assert 'role.WindowText: "#172033"' in source
    assert 'role.Window: "#f5f7fb"' in source
    assert "QDialog, QMessageBox { background: #ffffff; color: #172033; }" in source
    assert "apply_light_palette(app)" in source

def test_classroom_quick_search_is_bounded_and_credential_honest() -> None:
    app = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    assert "NumberField(1, 5000, 20)" in app
    assert "NumberField(1, 500, 1)" in app
    assert '"bilibili_hydrate_details": False' in app
    assert "Weibo keyword search requires an authorized Weibo session" in app
    assert '"DeepSeek-V4-Flash": "DeepSeek-V4.1-Flash"' in app
    assert "DeepSeek-V4.1-Flash-thinking-max" in app
    assert "gpt-oss-120b-thinking-high" in app


def test_windows_exposes_generic_public_item_ingestion_without_fake_wechat_search() -> None:
    app = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    assert 'tabs.addTab(self._ingest_tab(), "Public URL")' in app
    assert '("WeChat Official Account article", "wechat")' in app
    assert 'self.run_operation(\n            "ingest"' in app
    assert "mp.weixin.qq.com" in app
    assert 'SourceSelector(SOURCES)' in app


def test_windows_state_workflow_starts_with_research_question_and_portable_handoff() -> None:
    app = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    assert 'tabs.addTab(self._research_project_tab(), "Research Project")' in app
    assert 'Card("1. Project workspace"' in app
    assert 'Card("2. Research question"' in app
    assert 'Card("3. Gather evidence"' in app
    assert 'Card("4. Review and hand off"' in app
    assert 'LabeledRow("Target audiences",self.research_audiences)' in app
    assert '"target_audiences":self.research_audiences.text()' in app
    for operation in (
        "research-requirement",
        "research-plan",
        "research-import",
        "research-collect",
        "research-triage",
        "research-feedback",
        "research-handoff",
    ):
        assert f'"{operation}"' in app
