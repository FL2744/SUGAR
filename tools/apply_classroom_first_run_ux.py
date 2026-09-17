from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "SUGAR-Windows" / "app.py"
BUILD = ROOT / "SUGAR-Windows" / "scripts" / "build.ps1"
BRIDGE = ROOT / "sugar_bridge.py"
GUIDE = ROOT / "docs" / "classroom-quick-start.md"
TEST = ROOT / "tests" / "test_windows_classroom_ux.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


app = APP.read_text(encoding="utf-8")
app = replace_once(
    app,
    'SOURCES = ("x", "bluesky", "mastodon", "bilibili", "weibo")',
    'SOURCES = ("bilibili", "weibo", "x", "bluesky", "mastodon")',
    "source ordering",
)
app = replace_once(
    app,
    'QMainWindow, QWidget { background: #f5f7fb; color: #172033; font-family: "Segoe UI"; font-size: 10pt; }',
    '''QMainWindow { background: #f5f7fb; color: #172033; }
QWidget { color: #172033; font-family: "Segoe UI"; font-size: 10pt; }
QStackedWidget, QScrollArea { background: #f5f7fb; border: none; }
QScrollArea > QWidget > QWidget { background: #f5f7fb; }
QLabel, QCheckBox { background: transparent; }
QMenuBar { background: #ffffff; color: #172033; border-bottom: 1px solid #dfe5ef; }
QMenuBar::item { background: transparent; padding: 5px 8px; }
QMenuBar::item:selected { background: #eef3fa; }
QMenu { background: #ffffff; color: #172033; border: 1px solid #cfd8e6; }
QMenu::item:selected { background: #e8f0fb; }
QToolButton { background: #ffffff; color: #172033; border: 1px solid #cbd5e4; border-radius: 6px; padding: 6px 9px; }
QToolButton:hover { background: #eef3fa; }''',
    "light-theme base",
)
app = replace_once(
    app,
    '        sources = Card("Source credentials", "Only use legitimate credentials or sessions you are authorized to use. SUGAR does not automate login or manufacture browser/session identities.")',
    '        sources = Card("Optional source credentials", "For the core classroom Bilibili/Weibo workflow, leave this section blank unless a specific task requires an authenticated source. X, Bluesky, Mastodon, and an authorized Weibo session are optional extensions; SUGAR never manufactures accounts or bypasses access controls.")',
    "credential explanation",
)
app = replace_once(app, 'provider = str(self.store.value("llm/provider", "openai"))', 'provider = str(self.store.value("llm/provider", "arc"))', "default provider")
app = replace_once(app, 'saved_model = str(self.store.value("llm/model", "gpt-5.6-luna"))', 'saved_model = str(self.store.value("llm/model", "gpt-oss-120b"))', "default model")

home_header = '        root.addWidget(page_header("SUGAR Research Workbench", "Evidence-first collection, State Department research coding, macro/micro analytic intelligence, and reproducible briefing outputs."))\n'
home_insert = home_header + '''\n        start = Card(
            "Start here — first time?",
            "Recommended classroom path: connect Virginia Tech ARC once, collect a small public-source sample, inspect the outputs, then move into the advanced workflow pages only when you need them.",
        )
        steps = QLabel(
            "1. Settings → Virginia Tech ARC → Get ARC API Key → paste the key → Test ARC Connection.\\n"
            "2. Collect → Quick Search → use Bilibili and/or Weibo → enter a few search terms → Run Search.\\n"
            "3. Open the generated files from Activity & Outputs. Basic public Bilibili/Weibo collection does not require source credentials."
        )
        steps.setWordWrap(True)
        start.layout.addWidget(steps)
        start_row = QHBoxLayout()
        setup_arc = primary_button("1. Set up Virginia Tech ARC", lambda: self.navigate.emit("Settings"))
        collect_public = QPushButton("2. Start public collection")
        collect_public.clicked.connect(lambda: self.navigate.emit("Collect"))
        guide = QPushButton("Open 5-minute guide")
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(resource_path("CLASSROOM-QUICK-START.md")))))
        start_row.addWidget(setup_arc)
        start_row.addWidget(collect_public)
        start_row.addWidget(guide)
        start_row.addStretch(1)
        start.layout.addLayout(start_row)
        root.addWidget(start)
'''
app = replace_once(app, home_header, home_insert, "home start card")
app = replace_once(
    app,
    '        self.search_sources.boxes["x"].setChecked(True)',
    '        self.search_sources.boxes["bilibili"].setChecked(True)\n        self.search_sources.boxes["weibo"].setChecked(True)',
    "public-source defaults",
)
app = replace_once(app, 'LabeledRow("X mode", self.x_mode)', 'LabeledRow("X options (ignored unless X is selected)", self.x_mode)', "x mode wording")
app = replace_once(app, 'tabs.addTab(self._audit_tab(), "Audit & Diff")', 'tabs.addTab(self._audit_tab(), "Audit & Changes")', "audit tab wording")
app = replace_once(app, 'diff=Card("Assessment snapshot diff")', 'diff=Card("Compare assessment versions","Shows what changed between a previous and current assessment snapshot.")', "diff card wording")
app = replace_once(app, 'LabeledRow("Diff JSON",self.diff_out)', 'LabeledRow("Change report JSON",self.diff_out)', "diff output wording")
app = replace_once(
    app,
    '        if not smoke: QTimer.singleShot(150,self._diagnostics_run)',
    '        if not smoke:\n            QTimer.singleShot(150,self._diagnostics_run)\n            QTimer.singleShot(450,self._show_getting_started)',
    "first-run timer",
)
app = replace_once(
    app,
    '        tools=bar.addMenu("Tools"); diag=QAction("Backend diagnostics",self); diag.triggered.connect(self._diagnostics_run); tools.addAction(diag); cancel=QAction("Cancel current operation",self); cancel.triggered.connect(self.runner.cancel); tools.addAction(cancel)\n\n    def navigate(self,name:str)->None:',
    '''        tools=bar.addMenu("Tools"); diag=QAction("Backend diagnostics",self); diag.triggered.connect(self._diagnostics_run); tools.addAction(diag); cancel=QAction("Cancel current operation",self); cancel.triggered.connect(self.runner.cancel); tools.addAction(cancel)
        help_menu=bar.addMenu("Help"); getting_started=QAction("Getting Started",self); getting_started.triggered.connect(lambda: self._show_getting_started(True)); help_menu.addAction(getting_started)

    def _show_getting_started(self, force: bool = False)->None:
        store=QSettings(APP_ORGANIZATION,APP_NAME)
        if not force and store.value("ux/getting_started_seen",False,type=bool):
            return
        box=QMessageBox(self)
        box.setWindowTitle("Getting started with SUGAR")
        box.setIcon(QMessageBox.Information)
        box.setTextFormat(Qt.RichText)
        box.setText(
            "<b>Recommended first run</b><br><br>"
            "<b>1.</b> Open <b>Settings</b>, choose <b>Virginia Tech ARC</b>, click <b>Get ARC API Key</b>, paste the key, and test the connection.<br><br>"
            "<b>2.</b> Open <b>Collect → Quick Search</b>. Bilibili and Weibo are selected by default; enter a few terms and run a small search.<br><br>"
            "<b>3.</b> Inspect the generated files under <b>Activity & Outputs</b>. The State Workflow, Intelligence, and reporting pages are advanced follow-on tools.<br><br>"
            "<b>Source credentials are optional:</b> basic public Bilibili/Weibo collection does not require X, Bluesky, Mastodon, or Weibo credentials."
        )
        check=QCheckBox("Don't show this automatically again")
        check.setChecked(True)
        box.setCheckBox(check)
        box.exec()
        if check.isChecked():
            store.setValue("ux/getting_started_seen",True)
            store.sync()

    def navigate(self,name:str)->None:''',
    "help and first-run dialog",
)
APP.write_text(app, encoding="utf-8")

bridge = BRIDGE.read_text(encoding="utf-8")
bridge = replace_once(
    bridge,
    'def main(argv=None) -> int:\n    parser = argparse.ArgumentParser()',
    '''def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"cli", "project", "state", "intel"}:
        mode = argv.pop(0)
        if mode == "cli":
            from sugar_core.cli import main as command_main
        elif mode == "project":
            from sugar_core.workspace_cli import main as command_main
        elif mode == "state":
            from sugar_core.state_cli import main as command_main
        else:
            from sugar_core.state_intel_cli import main as command_main
        return int(command_main(argv) or 0)

    parser = argparse.ArgumentParser()''',
    "windows cli bridge routing",
)
BRIDGE.write_text(bridge, encoding="utf-8")

build = BUILD.read_text(encoding="utf-8")
build = replace_once(
    build,
    '    --add-data "$(Join-Path $RepoRoot \'sugar-logo.png\');." `\n',
    '    --add-data "$(Join-Path $RepoRoot \'sugar-logo.png\');." `\n    --add-data "$(Join-Path $RepoRoot \'docs\\classroom-quick-start.md\');." `\n',
    "bundle quick-start guide",
)
build = replace_once(
    build,
    'Copy-Item -Force $BridgeExe (Join-Path $AppDir "sugar-bridge.exe")\n\nCopy-Item -Force (Join-Path $WindowsDir "README.md") (Join-Path $AppDir "README-Windows.md")',
    '''Copy-Item -Force $BridgeExe (Join-Path $AppDir "sugar-bridge.exe")

$CliWrappers = @{
    "sugar.cmd" = "cli"
    "sugar-project.cmd" = "project"
    "sugar-state.cmd" = "state"
    "sugar-intel.cmd" = "intel"
}
foreach ($wrapper in $CliWrappers.GetEnumerator()) {
    $wrapperText = "@echo off`r`n`\"%~dp0sugar-bridge.exe`\" $($wrapper.Value) %*`r`n"
    Set-Content -Encoding ASCII -Path (Join-Path $AppDir $wrapper.Key) -Value $wrapperText
}

Copy-Item -Force (Join-Path $WindowsDir "README.md") (Join-Path $AppDir "README-Windows.md")
Copy-Item -Force (Join-Path $RepoRoot "docs\\classroom-quick-start.md") (Join-Path $AppDir "CLASSROOM-QUICK-START.md")''',
    "cli wrappers and guide copy",
)
BUILD.write_text(build, encoding="utf-8")

GUIDE.parent.mkdir(parents=True, exist_ok=True)
GUIDE.write_text('''# SUGAR Classroom Quick Start

This guide is for a first-time user who wants to get useful results without learning every SUGAR feature first.

## The 5-minute path

1. **Open Settings.** Choose **Virginia Tech ARC**. Click **Get ARC API Key**, sign in with your VT account, create a personal key, paste it into SUGAR, and click **Test ARC Connection**.
2. **Open Collect → Quick Search.** Start with **Bilibili** and/or **Weibo**. Enter a few search terms, one per line.
3. Leave **Source credentials** blank unless your specific task requires an authenticated source. Basic public Bilibili/Weibo work is designed to operate without X, Bluesky, or Mastodon credentials.
4. Keep the first search small. Run it and watch **Activity & Outputs** at the bottom of the window.
5. Open the generated CSV/XLSX/JSONL outputs before moving on to advanced analysis.

## What the pages are for

- **Home** — status, workflow map, and first-run shortcuts.
- **Collect** — normal keyword collection and resumable larger harvests.
- **Weibo** — investigate a known public Weibo post or run repeatable Weibo qualification/coverage checks.
- **State Workflow** — turn normalized observations into reviewable assessments, change reports, templates, and briefing packages.
- **Intelligence** — deterministic tradecraft checks and optional LLM-assisted synthesis. Use this after you have a real corpus.
- **Maps & Reports** — turn existing results into maps, PDF, or Word outputs.
- **Settings** — ARC/model connection, optional source credentials, and output defaults.

## Credentials: what is actually required?

**Virginia Tech ARC API key:** recommended for classroom use when you want translation, location inference, AI triage, or synthesis.

**Bilibili:** no source credential is required for the supported public collection path.

**Weibo:** supported public surfaces can be used without a saved session. An authorized existing Weibo session is optional and may improve access to surfaces that are otherwise limited.

**X / Bluesky / Mastodon:** optional general-source adapters. Only configure their credentials if you intentionally plan to use those sources.

SUGAR does not create accounts, bypass authentication, rotate identities, or defeat platform access controls.

## A sensible first exercise

Search one or two narrow terms on Bilibili/Weibo with a small page limit. Inspect what was actually collected. Then decide whether you need translation/inference, a larger resumable harvest, a post-level Weibo investigation, or downstream analysis. Do not begin with every source and every enrichment option enabled.

## Windows command line

The portable Windows folder also includes command wrappers backed by the same bundled SUGAR engine:

```bat
sugar.cmd --help
sugar-project.cmd --help
sugar-state.cmd --help
sugar-intel.cmd --help
```

This does **not** require a separate Python installation. The GUI is best for discovery and classroom use; the CLI is useful for reproducible or scripted workflows.

## Terminology

- **Audit** means checking whether evidence/verification rules were followed.
- **Compare assessment versions** means showing what changed between two saved assessment snapshots (the operation is often called a “diff” in developer tools).
- **Qualification** means measuring collector coverage, failures, access limits, provenance, duplicates, and repeatability. It is not an official certification or authority-to-operate.
- **Observation** is collected evidence. **Assessment** is an analytic judgment linked to evidence. SUGAR deliberately keeps those separate.
''', encoding="utf-8")

TEST.write_text('''from pathlib import Path

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
''', encoding="utf-8")

print("Applied classroom first-run UX patch.")
