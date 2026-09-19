from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend import BackendRunner
from widgets import Card, EnumCombo, LabeledRow, NumberField, OutputChip, PasswordField, PathField, SourceSelector, StatusPill

APP_NAME = "SUGAR"
APP_ORGANIZATION = "Virginia Tech Diplomacy Lab"
SOURCES = ("bilibili", "weibo", "x", "bluesky", "mastodon")

STYLE = """
QMainWindow { background: #f5f7fb; color: #172033; }
QDialog, QMessageBox { background: #ffffff; color: #172033; }
QMessageBox QLabel, QMessageBox QCheckBox { background: transparent; color: #172033; }
QToolTip { background: #ffffff; color: #172033; border: 1px solid #cfd8e6; padding: 4px; }
QAbstractItemView { background: #ffffff; color: #172033; selection-background-color: #e8f0fb; selection-color: #172033; }
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
QToolButton:hover { background: #eef3fa; }
QFrame#sidebar { background: #111b2e; border: none; }
QLabel#brand { color: white; font-size: 19pt; font-weight: 700; }
QLabel#brandSub { color: #aab8cf; font-size: 9pt; }
QListWidget#nav { background: transparent; border: none; color: #cfdaeb; outline: none; }
QListWidget#nav::item { padding: 11px 12px; margin: 2px 8px; border-radius: 7px; }
QListWidget#nav::item:selected { background: #275aa8; color: white; }
QListWidget#nav::item:hover:!selected { background: #1a2a45; }
QFrame#card { background: white; border: 1px solid #dfe5ef; border-radius: 9px; }
QLabel#pageTitle { font-size: 21pt; font-weight: 700; color: #172033; }
QLabel#pageSub { color: #637087; font-size: 10pt; }
QLabel#cardTitle { font-size: 12pt; font-weight: 650; color: #18243a; }
QLabel#fieldLabel { font-weight: 600; color: #33415a; }
QLabel#hint, QLabel#muted { color: #6e7b91; font-size: 9pt; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
  background: white; border: 1px solid #cfd8e6; border-radius: 6px; padding: 6px; selection-background-color: #2d6cc0;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #2d6cc0; }
QPushButton { background: #ffffff; border: 1px solid #cbd5e4; border-radius: 6px; padding: 7px 12px; }
QPushButton:hover { background: #eef3fa; }
QPushButton[primary="true"] { background: #235fa8; border-color: #235fa8; color: white; font-weight: 600; }
QPushButton[primary="true"]:hover { background: #194f91; }
QPushButton[danger="true"] { background: #fff6f5; color: #a8322d; border-color: #e5b8b5; }
QTabWidget::pane { border: 1px solid #dfe5ef; background: white; border-radius: 7px; }
QTabBar::tab { padding: 8px 14px; background: #edf1f7; margin-right: 2px; }
QTabBar::tab:selected { background: white; color: #235fa8; font-weight: 600; }
QProgressBar { border: 1px solid #cad4e2; border-radius: 5px; text-align: center; background: white; }
QProgressBar::chunk { background: #2d6cc0; border-radius: 4px; }
QLabel[tone="good"] { background: #e7f6ed; color: #1f6a3b; border-radius: 10px; padding: 4px 10px; font-weight: 600; }
QLabel[tone="warn"] { background: #fff4da; color: #805b00; border-radius: 10px; padding: 4px 10px; font-weight: 600; }
QLabel[tone="bad"] { background: #fde9e7; color: #9e302b; border-radius: 10px; padding: 4px 10px; font-weight: 600; }
QLabel[tone="neutral"] { background: #e9eef6; color: #43536e; border-radius: 10px; padding: 4px 10px; font-weight: 600; }
QDockWidget { font-weight: 600; }
"""


def apply_light_palette(app: QApplication) -> None:
    """Use a deterministic light palette instead of inheriting the OS dark palette."""
    palette = QPalette()
    normal = QPalette.ColorGroup.Normal
    disabled = QPalette.ColorGroup.Disabled
    role = QPalette.ColorRole

    colors = {
        role.Window: "#f5f7fb",
        role.WindowText: "#172033",
        role.Base: "#ffffff",
        role.AlternateBase: "#f5f7fb",
        role.ToolTipBase: "#ffffff",
        role.ToolTipText: "#172033",
        role.Text: "#172033",
        role.Button: "#ffffff",
        role.ButtonText: "#172033",
        role.BrightText: "#ffffff",
        role.Link: "#235fa8",
        role.Highlight: "#2d6cc0",
        role.HighlightedText: "#ffffff",
        role.PlaceholderText: "#6e7b91",
    }
    for color_role, value in colors.items():
        palette.setColor(normal, color_role, QColor(value))
        palette.setColor(QPalette.ColorGroup.Active, color_role, QColor(value))
        palette.setColor(QPalette.ColorGroup.Inactive, color_role, QColor(value))

    palette.setColor(disabled, role.Window, QColor("#f5f7fb"))
    palette.setColor(disabled, role.Base, QColor("#f2f4f8"))
    palette.setColor(disabled, role.Button, QColor("#eef1f5"))
    palette.setColor(disabled, role.WindowText, QColor("#7a8496"))
    palette.setColor(disabled, role.Text, QColor("#7a8496"))
    palette.setColor(disabled, role.ButtonText, QColor("#7a8496"))
    palette.setColor(disabled, role.PlaceholderText, QColor("#9098a7"))
    app.setPalette(palette)


def resource_path(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / name


def page_header(title: str, subtitle: str) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(3)
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    detail = QLabel(subtitle)
    detail.setObjectName("pageSub")
    detail.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(detail)
    return box


def scroll_page(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(content)
    return area


def split_terms(text: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for line in text.replace(",", "\n").splitlines():
        value = line.strip()
        key = value.casefold()
        if value and key not in seen:
            values.append(value)
            seen.add(key)
    return values


def primary_button(label: str, callback: Callable[[], None]) -> QPushButton:
    button = QPushButton(label)
    button.setProperty("primary", True)
    button.clicked.connect(callback)
    return button


class SettingsPage(QWidget):
    diagnostics_requested = Signal()
    arc_test_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.store = QSettings(APP_ORGANIZATION, APP_NAME)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(14)
        root.addWidget(page_header("Settings & Credentials", "Secrets are held in memory for this app session and are never written by the Windows UI."))

        llm = Card("Optional LLM provider", "Only AI-assisted workflows require this. OpenAI and custom OpenAI-compatible endpoints are deployment-neutral options; Virginia Tech ARC is a classroom/development convenience.")
        grid = QGridLayout()
        self.provider = EnumCombo((("OpenAI", "openai"), ("Virginia Tech ARC", "arc"), ("Custom OpenAI-compatible", "custom")))
        self.model = QComboBox()
        self.model.setEditable(True)
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("Only required for custom endpoints")
        self.llm_key = PasswordField("API key (session only)")
        grid.addWidget(LabeledRow("Provider", self.provider), 0, 0)
        grid.addWidget(LabeledRow("Model", self.model), 0, 1)
        grid.addWidget(LabeledRow("Base URL", self.base_url), 1, 0)
        grid.addWidget(LabeledRow("API key", self.llm_key, "If blank, SUGAR_LLM_API_KEY from the environment is used."), 1, 1)
        llm.layout.addLayout(grid)
        arc_help = QLabel(
            "Virginia Tech ARC quick setup — available to VT students, faculty, and staff without a separate ARC HPC account. "
            "1) Get a personal key from llm.arc.vt.edu (User profile → Settings → Account → API keys). "
            "2) Paste it above and choose Virginia Tech ARC. 3) Test the connection."
        )
        arc_help.setWordWrap(True)
        arc_help.setObjectName("muted")
        llm.layout.addWidget(arc_help)
        arc_row = QHBoxLayout()
        get_arc_key = QPushButton("1. Get ARC API Key")
        get_arc_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://llm.arc.vt.edu")))
        test_arc = QPushButton("3. Test ARC Connection")
        test_arc.clicked.connect(lambda: self.arc_test_requested.emit())
        self.arc_status = StatusPill("ARC not tested", "neutral")
        arc_row.addWidget(get_arc_key)
        arc_row.addWidget(test_arc)
        arc_row.addWidget(self.arc_status)
        arc_row.addStretch(1)
        llm.layout.addLayout(arc_row)
        root.addWidget(llm)

        sources = Card("Optional source credentials", "Bilibili Quick Search uses ordinary anonymous public access when Bilibili currently permits it. Weibo keyword search requires an existing authorized session. X requires its API token; Bluesky and Mastodon credentials are optional for their public modes. SUGAR never manufactures accounts or bypasses access controls.")
        source_grid = QGridLayout()
        self.x_token = PasswordField("X bearer token")
        self.bluesky_id = QLineEdit()
        self.bluesky_id.setPlaceholderText("Bluesky handle (optional)")
        self.bluesky_password = PasswordField("Bluesky app password")
        self.mastodon_token = PasswordField("Mastodon access token (optional)")
        self.weibo_cookie = PasswordField("Existing authorized Weibo cookie (optional)")
        source_grid.addWidget(LabeledRow("X bearer token", self.x_token), 0, 0)
        source_grid.addWidget(LabeledRow("Bluesky identifier", self.bluesky_id), 0, 1)
        source_grid.addWidget(LabeledRow("Bluesky app password", self.bluesky_password), 1, 0)
        source_grid.addWidget(LabeledRow("Mastodon token", self.mastodon_token), 1, 1)
        source_grid.addWidget(LabeledRow("Weibo session", self.weibo_cookie, "Required for Weibo keyword search. Use only a session you are authorized to use."), 2, 0, 1, 2)
        sources.layout.addLayout(source_grid)
        root.addWidget(sources)

        defaults = Card("Desktop defaults")
        self.output_root = PathField(mode="directory", placeholder="Default output folder")
        self.mastodon_url = QLineEdit()
        self.mastodon_url.setText("https://mastodon.social")
        defaults.layout.addWidget(LabeledRow("Default output folder", self.output_root))
        defaults.layout.addWidget(LabeledRow("Default Mastodon instance", self.mastodon_url))
        row = QHBoxLayout()
        save = primary_button("Save non-secret settings", self.save)
        clear = QPushButton("Clear session secrets")
        clear.clicked.connect(self.clear_secrets)
        diag = QPushButton("Run backend diagnostics")
        diag.clicked.connect(self.diagnostics_requested)
        row.addWidget(save)
        row.addWidget(clear)
        row.addWidget(diag)
        row.addStretch(1)
        defaults.layout.addLayout(row)
        root.addWidget(defaults)
        root.addStretch(1)

        self.provider.currentIndexChanged.connect(self._provider_changed)
        self._load()

    def _load(self) -> None:
        provider = str(self.store.value("llm/provider", "openai"))
        index = self.provider.findData(provider)
        self.provider.setCurrentIndex(max(0, index))
        self.base_url.setText(str(self.store.value("llm/base_url", "")))
        default_output = str(self.store.value("paths/output", str(Path.home() / "Documents" / "SUGAR")))
        self.output_root.setText(default_output)
        self.mastodon_url.setText(str(self.store.value("sources/mastodon_url", "https://mastodon.social")))
        self._provider_changed()
        saved_model = str(self.store.value("llm/model", "gpt-5.6-luna"))
        if provider == "arc":
            saved_model = {
                "DeepSeek-V4-Flash": "DeepSeek-V4.1-Flash",
                "GLM-5.2": "GLM-5.3",
            }.get(saved_model, saved_model)
        idx = self.model.findText(saved_model)
        if idx >= 0:
            self.model.setCurrentIndex(idx)
        elif provider == "arc":
            self.model.setCurrentIndex(0)
        else:
            self.model.setEditText(saved_model)

    def _provider_changed(self) -> None:
        current = self.model.currentText().strip()
        self.model.clear()
        provider = self.provider.value()
        if provider == "openai":
            models = ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"]
            default = "gpt-5.6-luna"
        elif provider == "arc":
            models = [
                "gpt-oss-120b",
                "gpt-oss-120b-thinking-low",
                "gpt-oss-120b-thinking-high",
                "DeepSeek-V4.1-Flash",
                "DeepSeek-V4.1-Flash-thinking-low",
                "DeepSeek-V4.1-Flash-thinking-max",
                "GLM-5.3",
                "GLM-5.3-thinking-high",
                "Kimi-K3",
                "Kimi-K3-thinking-low",
                "Kimi-K3-thinking-high",
            ]
            default = "gpt-oss-120b"
        else:
            models = []
            default = current
        self.model.addItems(models)
        if current and (provider == "custom" or current in models):
            self.model.setEditText(current)
        elif default:
            self.model.setEditText(default)
        if provider == "arc" and not self.base_url.text().strip():
            self.base_url.setPlaceholderText("Defaults to https://llm-api.arc.vt.edu/api/v1")
        elif provider == "custom":
            self.base_url.setPlaceholderText("https://example.org/v1")
        else:
            self.base_url.setPlaceholderText("Not required")

    def save(self) -> None:
        self.store.setValue("llm/provider", self.provider.value())
        self.store.setValue("llm/model", self.model.currentText().strip())
        self.store.setValue("llm/base_url", self.base_url.text().strip())
        self.store.setValue("paths/output", self.output_root.text())
        self.store.setValue("sources/mastodon_url", self.mastodon_url.text().strip())
        self.store.sync()

    def clear_secrets(self) -> None:
        for field in (self.llm_key, self.x_token, self.bluesky_password, self.mastodon_token, self.weibo_cookie):
            field.clear()
        self.bluesky_id.clear()

    def default_output(self) -> str:
        value = self.output_root.text().strip()
        return value or str(Path.home() / "Documents" / "SUGAR")

    def llm_config(self) -> dict[str, str]:
        return {
            "provider": self.provider.value(),
            "model": self.model.currentText().strip() or "gpt-5.6-luna",
            "base_url": self.base_url.text().strip(),
        }

    def secrets(self) -> dict[str, str]:
        def value(field: PasswordField, env: str) -> str:
            return field.text().strip() or os.environ.get(env, "").strip()

        return {
            "llm_api_key": value(self.llm_key, "SUGAR_LLM_API_KEY"),
            "x_bearer_token": value(self.x_token, "SUGAR_X_BEARER_TOKEN"),
            "bluesky_identifier": self.bluesky_id.text().strip() or os.environ.get("SUGAR_BLUESKY_IDENTIFIER", "").strip(),
            "bluesky_app_password": value(self.bluesky_password, "SUGAR_BLUESKY_APP_PASSWORD"),
            "mastodon_token": value(self.mastodon_token, "SUGAR_MASTODON_TOKEN"),
            "weibo_cookie": value(self.weibo_cookie, "SUGAR_WEIBO_COOKIE"),
        }


class HomePage(QWidget):
    navigate = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(14)
        root.addWidget(page_header("SUGAR Research Workbench", "Evidence-first collection, State Department research coding, macro/micro analytic intelligence, and reproducible briefing outputs."))

        start = Card(
            "Start here — first time?",
            "Recommended State/research path: create a portable Research Project, define the question, and build an inspectable plan. Core project, import, review, and export workflows do not require an LLM or Virginia Tech credentials.",
        )
        steps = QLabel(
            "1. Open State Workflow → Research Project and create or open a project folder.\n"
            "2. Enter the research question and constraints, then build and review the search plan. You can import an existing authorized dataset without configuring an LLM.\n"
            "3. Configure OpenAI, a custom OpenAI-compatible endpoint, or the optional Virginia Tech ARC classroom integration only if you need AI-assisted triage or enrichment."
        )
        steps.setWordWrap(True)
        start.layout.addWidget(steps)
        start_row = QHBoxLayout()
        setup_arc = QPushButton("Optional LLM settings")
        setup_arc.clicked.connect(lambda: self.navigate.emit("Settings"))
        collect_public = primary_button("1. Start Research Project", lambda: self.navigate.emit("State Workflow"))
        guide = QPushButton("Open 5-minute guide")
        guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(resource_path("CLASSROOM-QUICK-START.md")))))
        start_row.addWidget(setup_arc)
        start_row.addWidget(collect_public)
        start_row.addWidget(guide)
        start_row.addStretch(1)
        start.layout.addLayout(start_row)
        root.addWidget(start)

        summary = QHBoxLayout()
        self.backend_card = Card("Backend")
        self.backend_status = StatusPill("Checking…", "neutral")
        self.backend_detail = QLabel("Starting diagnostics")
        self.backend_detail.setObjectName("muted")
        self.backend_detail.setWordWrap(True)
        self.backend_card.layout.addWidget(self.backend_status)
        self.backend_card.layout.addWidget(self.backend_detail)
        summary.addWidget(self.backend_card)

        collectors = Card("Collectors")
        self.collector_status = QLabel("Waiting for backend capabilities")
        self.collector_status.setWordWrap(True)
        collectors.layout.addWidget(self.collector_status)
        summary.addWidget(collectors)

        research = Card("Research pipeline")
        text = QLabel("Collect → Normalize → Triage → Human Verify → State Assessment → Intelligence → Red Team → Brief")
        text.setWordWrap(True)
        research.layout.addWidget(text)
        summary.addWidget(research)
        root.addLayout(summary)

        quick = Card("Quick actions", "Use the full pages for advanced controls; these buttons jump directly to the relevant workflow.")
        actions = QHBoxLayout()
        for label, target in (("Collect data", "Collect"), ("Investigate Weibo", "Weibo"), ("Build State package", "State Workflow"), ("Run intelligence synthesis", "Intelligence")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=target: self.navigate.emit(value))
            actions.addWidget(button)
        actions.addStretch(1)
        quick.layout.addLayout(actions)
        root.addWidget(quick)

        guard = Card("Analytic guardrails")
        guard_text = QLabel(
            "SUGAR keeps presence, activity, reach, engagement, outcomes, and causal influence separate. "
            "AI can suggest classifications and analytic hypotheses, but it cannot self-verify evidence, invent source identities, or promote an uncited judgment into a confident finding."
        )
        guard_text.setWordWrap(True)
        guard.layout.addWidget(guard_text)
        root.addWidget(guard)
        root.addStretch(1)

    def update_diagnostics(self, payload: dict[str, Any]) -> None:
        self.backend_status.setText("Ready")
        self.backend_status.set_tone("good")
        deployment = payload.get("deployment") or {}
        credentials = payload.get("optional_credentials") or {}
        credential_labels = {
            "llm_api_key": "LLM",
            "x_bearer_token": "X",
            "bluesky_identifier": "Bluesky ID",
            "bluesky_app_password": "Bluesky password",
            "mastodon_token": "Mastodon",
            "weibo_cookie": "Weibo session",
        }
        configured = [
            credential_labels.get(key, key)
            for key, value in credentials.items()
            if bool(value)
        ]
        missing = [
            credential_labels.get(key, key)
            for key, value in credentials.items()
            if not bool(value)
        ]
        core_note = (
            "Core project/import/review/export workflows need no Virginia Tech service or LLM."
            if not deployment.get("virginia_tech_required", False)
            and not deployment.get("llm_required_for_core_workflows", False)
            else "Review deployment requirements before use."
        )
        credential_note = (
            f"Optional credentials configured: {', '.join(configured)}."
            if configured
            else "No optional credentials configured."
        )
        if missing:
            credential_note += f" Optional/not configured: {', '.join(missing)}."
        self.backend_detail.setText(
            f"SUGAR {payload.get('version', '?')} · {payload.get('runtime', '?')} · {payload.get('architecture', '?')} · bridge v{payload.get('bridge_protocol', '?')}\n"
            f"{core_note}\n{credential_note}"
        )
        collectors = payload.get("collectors") or {}
        labels: list[str] = []
        for name, capability in collectors.items():
            if not isinstance(capability, dict):
                labels.append(str(name))
                continue
            modes = []
            if capability.get("keyword_search"):
                modes.append("search")
            if capability.get("known_item"):
                modes.append("item")
            if capability.get("comments"):
                modes.append("comments")
            labels.append(f"{name}: {'/'.join(modes) if modes else 'registered'}")
        self.collector_status.setText(" · ".join(labels) if labels else "No collector capability data returned")

    def diagnostic_failure(self, message: str) -> None:
        self.backend_status.setText("Backend problem")
        self.backend_status.set_tone("bad")
        self.backend_detail.setText(message)


class CollectPage(QWidget):
    def __init__(self, run: Callable[[str, dict[str, Any], bool], None], settings: SettingsPage) -> None:
        super().__init__()
        self.run_operation = run
        self.settings = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.addWidget(page_header("Collection", "Run bounded interactive searches or durable, checkpointed high-volume harvest campaigns."))
        tabs = QTabWidget()
        tabs.addTab(self._search_tab(), "Quick Search")
        tabs.addTab(self._ingest_tab(), "Public URL")
        tabs.addTab(self._harvest_tab(), "Resumable Harvest")
        root.addWidget(tabs, 1)

    def _search_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        self.search_sources = SourceSelector(SOURCES)
        self.search_sources.boxes["bilibili"].setChecked(True)
        self.search_terms = QTextEdit()
        self.search_terms.setPlaceholderText("One search term per line\nCultural exchange Institute\nTechnical training Workshop")
        self.search_terms.setMaximumHeight(120)
        self.term_languages = QLineEdit()
        self.term_languages.setPlaceholderText("Optional translated query languages, comma separated")
        self.post_languages = QLineEdit()
        self.since = QLineEdit()
        self.since.setPlaceholderText("YYYY-MM-DD")
        self.until = QLineEdit()
        self.until.setPlaceholderText("YYYY-MM-DD")
        self.max_posts = NumberField(1, 5000, 20)
        self.max_pages = NumberField(1, 500, 1)
        self.x_mode = EnumCombo((("Recent", "recent"), ("Full archive (authorized X access)", "all")))
        self.translate_posts = QCheckBox("Translate posts")
        self.translate_posts.setChecked(False)
        self.infer_locations = QCheckBox("Infer broad locations")
        self.infer_locations.setChecked(False)
        self.include_reposts = QCheckBox("Include reposts/retweets")
        self.search_output = PathField(mode="directory")
        self.search_output.setText(self.settings.default_output())

        form = QGridLayout()
        form.addWidget(LabeledRow("Sources", self.search_sources, "Bilibili: anonymous public access when available. Weibo: authorized session required for keyword search."), 0, 0, 1, 2)
        form.addWidget(LabeledRow("Search terms", self.search_terms), 1, 0, 1, 2)
        form.addWidget(LabeledRow("Translate terms into", self.term_languages, "Example: Spanish, Russian. Leave blank to use only original terms."), 2, 0)
        form.addWidget(LabeledRow("Post language filters", self.post_languages, "BCP-47 codes; currently most relevant to X."), 2, 1)
        form.addWidget(LabeledRow("Since", self.since), 3, 0)
        form.addWidget(LabeledRow("Until", self.until), 3, 1)
        form.addWidget(LabeledRow("Posts per query", self.max_posts), 4, 0)
        form.addWidget(LabeledRow("Pages per query", self.max_pages), 4, 1)
        form.addWidget(LabeledRow("X options (ignored unless X is selected)", self.x_mode), 5, 0)
        toggles = QWidget()
        toggle_layout = QHBoxLayout(toggles)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        for box in (self.translate_posts, self.infer_locations, self.include_reposts):
            toggle_layout.addWidget(box)
        toggle_layout.addStretch(1)
        form.addWidget(LabeledRow("Enrichment", toggles), 5, 1)
        form.addWidget(LabeledRow("Output folder", self.search_output), 6, 0, 1, 2)
        layout.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(primary_button("Run Search", self._run_search))
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _run_search(self) -> None:
        terms = split_terms(self.search_terms.toPlainText())
        sources = self.search_sources.selected()
        if not sources or not terms:
            QMessageBox.warning(self, "Missing input", "Select at least one source and enter at least one search term.")
            return
        config = {
            "sources": sources,
            "terms": terms,
            "translate_term_languages": split_terms(self.term_languages.text()),
            "post_languages": split_terms(self.post_languages.text()),
            "x_search_mode": self.x_mode.value(),
            "since": self.since.text().strip(),
            "until": self.until.text().strip(),
            "max_posts_per_query": self.max_posts.value(),
            "max_pages_per_query": self.max_pages.value(),
            "translate_posts": self.translate_posts.isChecked(),
            "infer_locations": self.infer_locations.isChecked(),
            "include_retweets": self.include_reposts.isChecked(),
            "target_language": "English",
            "bilibili_hydrate_details": False,
            "output_directory": self.search_output.text() or self.settings.default_output(),
            "mastodon_url": self.settings.mastodon_url.text().strip() or "https://mastodon.social",
            "llm": self.settings.llm_config(),
        }
        need_llm = bool(config["translate_posts"] or config["infer_locations"] or config["translate_term_languages"])
        self.run_operation("search", config, need_llm)

    def _ingest_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        self.ingest_source = EnumCombo((
            ("WeChat Official Account article", "wechat"),
            ("Bilibili video", "bilibili"),
            ("Weibo post", "weibo"),
        ))
        self.ingest_identifier = QLineEdit()
        self.ingest_identifier.setPlaceholderText("Paste a public URL or supported native item ID")
        self.ingest_query = QLineEdit()
        self.ingest_query.setPlaceholderText("Optional research query/provenance label")
        self.ingest_output = PathField(mode="directory")
        self.ingest_output.setText(self.settings.default_output())

        form = QGridLayout()
        form.addWidget(LabeledRow("Source", self.ingest_source), 0, 0)
        form.addWidget(LabeledRow("Public URL or item ID", self.ingest_identifier), 0, 1)
        form.addWidget(LabeledRow("Research query", self.ingest_query, "Optional. Stored as query provenance on the imported item."), 1, 0)
        form.addWidget(LabeledRow("Output folder", self.ingest_output), 1, 1)
        layout.addLayout(form)
        note = QLabel(
            "Use this for a specific public item you already know about. WeChat currently supports public "
            "mp.weixin.qq.com Official Account articles; SUGAR does not search private WeChat, manufacture "
            "login state, solve challenges, or bypass access controls."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(primary_button("Import Public Item", self._run_ingest))
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _run_ingest(self) -> None:
        identifier = self.ingest_identifier.text().strip()
        if not identifier:
            QMessageBox.warning(self, "Missing public item", "Paste a public URL or supported native item ID.")
            return
        self.run_operation(
            "ingest",
            {
                "source": self.ingest_source.value(),
                "identifier": identifier,
                "query": self.ingest_query.text().strip(),
                "output_directory": self.ingest_output.text() or self.settings.default_output(),
            },
            False,
        )

    def _harvest_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        self.harvest_sources = SourceSelector(SOURCES)
        self.harvest_sources.boxes["weibo"].setChecked(True)
        self.harvest_terms = QTextEdit()
        self.harvest_terms.setPlaceholderText("One query per line. Use a reproducible research matrix rather than a single deep query.")
        self.harvest_terms.setMaximumHeight(120)
        self.harvest_since = QLineEdit()
        self.harvest_until = QLineEdit()
        self.harvest_since.setPlaceholderText("YYYY-MM-DD")
        self.harvest_until.setPlaceholderText("YYYY-MM-DD")
        self.harvest_target = NumberField(0, 1_000_000, 10000)
        self.harvest_target.setSpecialValueText("No early stop")
        self.shard_days = NumberField(1, 365, 7)
        self.posts_task = NumberField(1, 10000, 500)
        self.pages_task = NumberField(1, 100, 5)
        self.max_pages_query = NumberField(1, 5000, 100)
        self.task_delay = QDoubleSpinBox()
        self.task_delay.setRange(0, 60)
        self.task_delay.setValue(1.0)
        self.task_delay.setSuffix(" s")
        self.harvest_name = QLineEdit("state_weibo_campaign")
        self.harvest_output = PathField(mode="directory")
        self.harvest_output.setText(self.settings.default_output())

        form = QGridLayout()
        form.addWidget(LabeledRow("Sources", self.harvest_sources), 0, 0, 1, 2)
        form.addWidget(LabeledRow("Query plan", self.harvest_terms), 1, 0, 1, 2)
        form.addWidget(LabeledRow("Since", self.harvest_since), 2, 0)
        form.addWidget(LabeledRow("Until", self.harvest_until), 2, 1)
        form.addWidget(LabeledRow("Unique-record target", self.harvest_target, "0 runs the entire bounded plan; otherwise collection stops after reaching the target."), 3, 0)
        form.addWidget(LabeledRow("Date shard size", self.shard_days), 3, 1)
        form.addWidget(LabeledRow("Posts per task", self.posts_task), 4, 0)
        form.addWidget(LabeledRow("Pages per durable task", self.pages_task), 4, 1)
        form.addWidget(LabeledRow("Maximum pages per query", self.max_pages_query), 5, 0)
        form.addWidget(LabeledRow("Inter-task delay", self.task_delay), 5, 1)
        form.addWidget(LabeledRow("Campaign name", self.harvest_name), 6, 0)
        form.addWidget(LabeledRow("Output/checkpoint folder", self.harvest_output), 6, 1)
        layout.addLayout(form)
        note = QLabel("Rate limits remain authoritative. Harvest scales through durable sharding, checkpoint/resume, deduplication and backoff—not proxy/account rotation or access-control evasion.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(primary_button("Start / Resume Harvest", self._run_harvest))
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _run_harvest(self) -> None:
        terms = split_terms(self.harvest_terms.toPlainText())
        sources = self.harvest_sources.selected()
        if not sources or not terms:
            QMessageBox.warning(self, "Missing input", "Select at least one source and enter a query plan.")
            return
        target = self.harvest_target.value()
        config = {
            "sources": sources,
            "terms": terms,
            "since": self.harvest_since.text().strip(),
            "until": self.harvest_until.text().strip(),
            "output_directory": self.harvest_output.text() or self.settings.default_output(),
            "mastodon_url": self.settings.mastodon_url.text().strip() or "https://mastodon.social",
            "harvest": {
                "name": self.harvest_name.text().strip() or "sugar_harvest",
                "target_records": target if target > 0 else None,
                "shard_days": self.shard_days.value(),
                "posts_per_task": self.posts_task.value(),
                "pages_per_task": self.pages_task.value(),
                "max_pages_per_query": self.max_pages_query.value(),
                "inter_task_delay_seconds": self.task_delay.value(),
                "continue_on_error": True,
            },
        }
        self.run_operation("harvest", config, False)


class WeiboPage(QWidget):
    def __init__(self, run: Callable[[str, dict[str, Any], bool], None], settings: SettingsPage) -> None:
        super().__init__()
        self.run_operation = run
        self.settings = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.addWidget(page_header("Weibo Research", "Investigate real public posts at micro level or qualify a repeatable campaign against explicit State-facing research thresholds."))
        tabs = QTabWidget()
        tabs.addTab(self._investigate_tab(), "Post Investigation")
        tabs.addTab(self._qualification_tab(), "Industrial Qualification")
        root.addWidget(tabs, 1)

    def _investigate_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        self.seed = QLineEdit()
        self.seed.setPlaceholderText("Public Weibo URL or status ID")
        self.weibo_comments = NumberField(0, 10000, 100)
        self.weibo_comment_pages = NumberField(0, 100, 5)
        self.weibo_reposts = NumberField(0, 10000, 100)
        self.weibo_repost_pages = NumberField(0, 100, 5)
        self.weibo_author_posts = NumberField(0, 10000, 40)
        self.weibo_author_pages = NumberField(0, 100, 2)
        self.weibo_name = QLineEdit("weibo_investigation")
        self.weibo_output = PathField(mode="directory")
        self.weibo_output.setText(self.settings.default_output())
        grid = QGridLayout()
        grid.addWidget(LabeledRow("Seed post", self.seed), 0, 0, 1, 2)
        grid.addWidget(LabeledRow("Max comments", self.weibo_comments), 1, 0)
        grid.addWidget(LabeledRow("Comment pages", self.weibo_comment_pages), 1, 1)
        grid.addWidget(LabeledRow("Max reposts", self.weibo_reposts), 2, 0)
        grid.addWidget(LabeledRow("Repost pages", self.weibo_repost_pages), 2, 1)
        grid.addWidget(LabeledRow("Recent author posts", self.weibo_author_posts), 3, 0)
        grid.addWidget(LabeledRow("Author pages", self.weibo_author_pages), 3, 1)
        grid.addWidget(LabeledRow("Investigation name", self.weibo_name), 4, 0)
        grid.addWidget(LabeledRow("Output folder", self.weibo_output), 4, 1)
        layout.addLayout(grid)
        note = QLabel("Every surface is reported independently. Access-limited repost/timeline surfaces are not converted into observed zeroes.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Investigate Post", self._run_investigation)); layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _run_investigation(self) -> None:
        if not self.seed.text().strip():
            QMessageBox.warning(self, "Missing seed", "Enter a public Weibo post URL or status ID.")
            return
        config = {
            "seed": self.seed.text().strip(),
            "max_comments": self.weibo_comments.value(),
            "comment_pages": self.weibo_comment_pages.value(),
            "max_reposts": self.weibo_reposts.value(),
            "repost_pages": self.weibo_repost_pages.value(),
            "author_posts": self.weibo_author_posts.value(),
            "author_pages": self.weibo_author_pages.value(),
            "name": self.weibo_name.text().strip() or "weibo_investigation",
            "output_directory": self.weibo_output.text() or self.settings.default_output(),
        }
        self.run_operation("weibo-investigate", config, False)

    def _qualification_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        self.qual_terms = QTextEdit()
        self.qual_terms.setMaximumHeight(100)
        self.qual_terms.setPlaceholderText("One Weibo query per line")
        self.qual_seeds = QTextEdit()
        self.qual_seeds.setMaximumHeight(90)
        self.qual_seeds.setPlaceholderText("Known public Weibo post URLs/IDs, one per line")
        self.qual_replicates = NumberField(1, 10, 2)
        self.qual_pages_task = NumberField(1, 50, 5)
        self.qual_max_pages = NumberField(1, 500, 25)
        self.qual_delay = QDoubleSpinBox(); self.qual_delay.setRange(0, 60); self.qual_delay.setValue(1.0); self.qual_delay.setSuffix(" s")
        self.qual_audit_size = NumberField(0, 10000, 100)
        self.qual_audit_file = PathField(mode="file", extensions=("csv",))
        self.qual_name = QLineEdit("weibo_state_qualification")
        self.qual_output = PathField(mode="directory"); self.qual_output.setText(self.settings.default_output())
        grid = QGridLayout()
        grid.addWidget(LabeledRow("Query plan", self.qual_terms), 0, 0)
        grid.addWidget(LabeledRow("Real-post validation seeds", self.qual_seeds), 0, 1)
        grid.addWidget(LabeledRow("Replicates", self.qual_replicates), 1, 0)
        grid.addWidget(LabeledRow("Pages per durable task", self.qual_pages_task), 1, 1)
        grid.addWidget(LabeledRow("Maximum pages per query", self.qual_max_pages), 2, 0)
        grid.addWidget(LabeledRow("Inter-task delay", self.qual_delay), 2, 1)
        grid.addWidget(LabeledRow("Human audit sample size", self.qual_audit_size), 3, 0)
        grid.addWidget(LabeledRow("Completed human audit CSV", self.qual_audit_file, "Optional on first run. A deterministic audit sample is generated for labeling."), 3, 1)
        grid.addWidget(LabeledRow("Qualification name", self.qual_name), 4, 0)
        grid.addWidget(LabeledRow("Output folder", self.qual_output), 4, 1)
        layout.addLayout(grid)
        note = QLabel("Qualification runs the complete bounded query plan. It measures coverage, failures, access limits, provenance, duplicates, repeatability and real-post/comment access; it is not an official State certification or ATO.")
        note.setObjectName("hint"); note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Run Qualification", self._run_qualification)); layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _run_qualification(self) -> None:
        terms = split_terms(self.qual_terms.toPlainText())
        if not terms:
            QMessageBox.warning(self, "Missing query plan", "Enter at least one Weibo query.")
            return
        config = {
            "sources": ["weibo"],
            "terms": terms,
            "output_directory": self.qual_output.text() or self.settings.default_output(),
            "harvest": {
                "pages_per_task": self.qual_pages_task.value(),
                "max_pages_per_query": self.qual_max_pages.value(),
                "inter_task_delay_seconds": self.qual_delay.value(),
                "continue_on_error": True,
            },
            "qualification": {
                "name": self.qual_name.text().strip() or "weibo_qualification",
                "seeds": split_terms(self.qual_seeds.toPlainText()),
                "replicates": self.qual_replicates.value(),
                "audit_sample_size": self.qual_audit_size.value(),
                "audit_file": self.qual_audit_file.text() or None,
                "max_comments": 50,
                "comment_pages": 3,
                "max_reposts": 25,
                "repost_pages": 2,
                "author_posts": 20,
                "author_pages": 1,
            },
        }
        self.run_operation("weibo-qualify", config, False)


class StatePage(QWidget):
    def __init__(self, run: Callable[[str, dict[str, Any], bool], None], settings: SettingsPage) -> None:
        super().__init__()
        self.run_operation = run
        self.settings = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.addWidget(page_header("State Department Workflow", "Start with the research question, keep collection limits visible, review evidence, and export a portable auditable handoff. Expert assessment and monitoring tools remain available in the later tabs."))
        tabs = QTabWidget()
        tabs.addTab(self._research_project_tab(), "Research Project")
        tabs.addTab(self._package_tab(), "State Package")
        tabs.addTab(self._triage_tab(), "AI Triage")
        tabs.addTab(self._review_tab(), "Human Review")
        tabs.addTab(self._audit_tab(), "Audit & Changes")
        tabs.addTab(self._templates_tab(), "Monitoring Templates")
        root.addWidget(tabs, 1)

    def _research_project_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(16,16,16,16); layout.setSpacing(14)

        project = Card("1. Project workspace", "One portable project folder keeps the question, search plan, evidence, review artifacts and handoff together. You can copy the folder to another machine and rebuild its artifact index.")
        self.research_workspace = PathField(mode="directory", placeholder="Choose or create a SUGAR project folder")
        self.research_project_name = QLineEdit("State Research Project")
        project_grid = QGridLayout(); project_grid.addWidget(LabeledRow("Project folder", self.research_workspace),0,0,1,2); project_grid.addWidget(LabeledRow("Project name", self.research_project_name),1,0)
        project.layout.addLayout(project_grid)
        project_actions = QHBoxLayout(); project_actions.addWidget(primary_button("Create / Open Project", self._research_workspace_open)); project_actions.addStretch(1); project.layout.addLayout(project_actions)
        layout.addWidget(project)

        question = Card("2. Research question", "Define what you are trying to answer before collecting. SUGAR turns this into a versioned requirement and an inspectable bounded search plan.")
        self.research_question = QTextEdit(); self.research_question.setPlaceholderText("Example: How are public-facing cultural and educational programs expanding across the target geography, and what evidence supports that assessment?"); self.research_question.setMaximumHeight(92)
        self.research_geographies = QLineEdit(); self.research_geographies.setPlaceholderText("Comma separated, e.g. Country A, Capital City")
        self.research_entities = QLineEdit(); self.research_entities.setPlaceholderText("Known institutions, programs, organizations…")
        self.research_audiences = QLineEdit(); self.research_audiences.setPlaceholderText("Target audiences, communities, or stakeholder groups")
        self.research_languages = QLineEdit("auto")
        self.research_since = QLineEdit(); self.research_since.setPlaceholderText("YYYY-MM-DD (optional)")
        self.research_until = QLineEdit(); self.research_until.setPlaceholderText("YYYY-MM-DD (optional)")
        self.research_mode = EnumCombo((("Quick reconnaissance","quick"),("Standard research","standard"),("Deep bounded research","deep"))); self.research_mode.setCurrentIndex(1)
        self.research_sources = SourceSelector(SOURCES); self.research_sources.boxes["bilibili"].setChecked(True)
        qgrid=QGridLayout(); qgrid.addWidget(LabeledRow("Research question",self.research_question),0,0,1,2); qgrid.addWidget(LabeledRow("Geographies",self.research_geographies),1,0); qgrid.addWidget(LabeledRow("Known entities",self.research_entities),1,1); qgrid.addWidget(LabeledRow("Target audiences",self.research_audiences),2,0); qgrid.addWidget(LabeledRow("Languages",self.research_languages),2,1); qgrid.addWidget(LabeledRow("Depth",self.research_mode),3,0); qgrid.addWidget(LabeledRow("Since",self.research_since),3,1); qgrid.addWidget(LabeledRow("Until",self.research_until),4,1); qgrid.addWidget(LabeledRow("Preferred searchable sources",self.research_sources,"These are preferences, not proof of coverage. Source failures and zero-result searches are recorded separately."),5,0,1,2)
        question.layout.addLayout(qgrid)
        qactions=QHBoxLayout(); qactions.addWidget(primary_button("Save Research Question",self._research_requirement)); qactions.addStretch(1); question.layout.addLayout(qactions)
        layout.addWidget(question)

        strategy_review = Card(
            "2b. Interpret and approve the research strategy",
            "SUGAR compiles the sentence into explicit source-span concepts, semantic interpretations, search hypotheses, missing dimensions, and operational research dimensions. AI enrichment is optional; it may propose interpretations/hypotheses but cannot turn them into analyst-stated facts.",
        )
        strategy_actions = QHBoxLayout()
        strategy_actions.addWidget(primary_button("Compile Deterministically", self._research_compile))
        strategy_actions.addWidget(QPushButton("Compile + AI", clicked=self._research_compile_ai))
        strategy_actions.addWidget(QPushButton("Refresh Interpretation", clicked=self._research_strategy_refresh))
        strategy_actions.addStretch(1)
        strategy_review.layout.addLayout(strategy_actions)
        self.research_strategy_task = QLineEdit()
        self.research_strategy_task.setPlaceholderText("Compiled analytic task, e.g. mechanism_assessment")
        strategy_review.layout.addWidget(LabeledRow("Analytic task", self.research_strategy_task))
        self.research_strategy_table = QTableWidget(0, 7)
        self.research_strategy_table.setHorizontalHeaderLabels(
            ["Concept ID", "Class", "Kind", "Value", "Confidence", "Use", "Rationale"]
        )
        self.research_strategy_table.setMinimumHeight(260)
        self.research_strategy_table.setColumnWidth(0, 150)
        self.research_strategy_table.setColumnWidth(1, 90)
        self.research_strategy_table.setColumnWidth(2, 110)
        self.research_strategy_table.setColumnWidth(3, 250)
        self.research_strategy_table.setColumnWidth(4, 80)
        self.research_strategy_table.setColumnWidth(5, 55)
        self.research_strategy_table.setColumnWidth(6, 360)
        strategy_review.layout.addWidget(self.research_strategy_table)
        self.research_strategy_dimensions = QTableWidget(0, 7)
        self.research_strategy_dimensions.setHorizontalHeaderLabels(
            ["Dimension ID", "Use", "Name", "Question", "Indicators", "Source families", "Rationale"]
        )
        self.research_strategy_dimensions.setMinimumHeight(220)
        self.research_strategy_dimensions.setColumnWidth(0, 145)
        self.research_strategy_dimensions.setColumnWidth(1, 50)
        self.research_strategy_dimensions.setColumnWidth(2, 125)
        self.research_strategy_dimensions.setColumnWidth(3, 320)
        self.research_strategy_dimensions.setColumnWidth(4, 260)
        self.research_strategy_dimensions.setColumnWidth(5, 240)
        self.research_strategy_dimensions.setColumnWidth(6, 300)
        strategy_review.layout.addWidget(
            LabeledRow(
                "Research dimensions",
                self.research_strategy_dimensions,
                "Edit the operational questions/indicators or exclude a dimension before approval.",
            )
        )
        self.research_strategy_missing = QPlainTextEdit()
        self.research_strategy_missing.setReadOnly(True)
        self.research_strategy_missing.setMaximumHeight(105)
        strategy_review.layout.addWidget(
            LabeledRow(
                "Missing / confirm",
                self.research_strategy_missing,
                "Missing fields are not silently guessed. Update the research requirement and recompile when they matter.",
            )
        )
        self.research_strategy_reviewer = QLineEdit()
        self.research_strategy_reviewer.setPlaceholderText("Named analyst required for approval")
        self.research_strategy_note = QLineEdit()
        self.research_strategy_note.setPlaceholderText("Optional review note")
        strategy_meta = QGridLayout()
        strategy_meta.addWidget(LabeledRow("Reviewer", self.research_strategy_reviewer), 0, 0)
        strategy_meta.addWidget(LabeledRow("Review note", self.research_strategy_note), 0, 1)
        strategy_review.layout.addLayout(strategy_meta)
        strategy_review_actions = QHBoxLayout()
        strategy_review_actions.addWidget(QPushButton("Save Interpretation Edits", clicked=self._research_strategy_save))
        strategy_review_actions.addWidget(primary_button("Approve Research Strategy", self._research_strategy_approve))
        strategy_review_actions.addWidget(QPushButton("Build Search Plan from Approved Strategy", clicked=self._research_plan))
        strategy_review_actions.addStretch(1)
        strategy_review.layout.addLayout(strategy_review_actions)
        layout.addWidget(strategy_review)

        plan_review = Card(
            "2c. Review search branches",
            "Review the generated plan before collection. Query and rationale cells are editable; approvals, pauses, and exclusions are preserved in the plan audit history.",
        )
        self.research_plan_table = QTableWidget(0, 5)
        self.research_plan_table.setHorizontalHeaderLabels(
            ["Branch ID", "Query", "Rationale", "Origin", "Status"]
        )
        self.research_plan_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.research_plan_table.setSelectionMode(QTableWidget.SingleSelection)
        self.research_plan_table.setMinimumHeight(220)
        self.research_plan_table.setColumnWidth(0, 155)
        self.research_plan_table.setColumnWidth(1, 260)
        self.research_plan_table.setColumnWidth(2, 360)
        self.research_plan_table.setColumnWidth(3, 95)
        self.research_plan_table.setColumnWidth(4, 95)
        plan_review.layout.addWidget(self.research_plan_table)
        self.research_plan_reason = QLineEdit()
        self.research_plan_reason.setPlaceholderText("Optional analyst reason for this edit/status change")
        plan_review.layout.addWidget(LabeledRow("Reason", self.research_plan_reason))
        plan_actions = QHBoxLayout()
        plan_actions.addWidget(QPushButton("Refresh Plan", clicked=self._research_plan_refresh))
        plan_actions.addWidget(QPushButton("Save Edits", clicked=self._research_plan_save_edits))
        plan_actions.addWidget(QPushButton("Approve", clicked=lambda: self._research_plan_set_status("approved")))
        plan_actions.addWidget(QPushButton("Pause", clicked=lambda: self._research_plan_set_status("paused")))
        plan_actions.addWidget(QPushButton("Exclude", clicked=lambda: self._research_plan_set_status("excluded")))
        plan_actions.addStretch(1)
        plan_review.layout.addLayout(plan_actions)
        layout.addWidget(plan_review)

        evidence = Card("3. Gather evidence", "Either execute the approved search plan or import an existing partner/Department export. Both routes normalize into the same evidence model with provenance.")
        self.research_import_file = PathField(mode="file", extensions=("csv","jsonl"))
        self.research_import_system = QLineEdit("external")
        self.research_posts = NumberField(1,1000,20); self.research_pages = NumberField(1,100,1)
        egrid=QGridLayout(); egrid.addWidget(LabeledRow("Existing CSV / JSONL",self.research_import_file,"Optional. Import lets SUGAR start from data collected in another authorized system without recollecting it."),0,0,1,2); egrid.addWidget(LabeledRow("Source system",self.research_import_system),1,0); egrid.addWidget(LabeledRow("Posts per query",self.research_posts),1,1); egrid.addWidget(LabeledRow("Pages per query",self.research_pages),2,1); evidence.layout.addLayout(egrid)
        eactions=QHBoxLayout(); eactions.addWidget(primary_button("Run Search Plan",self._research_collect)); eactions.addWidget(QPushButton("Import Existing Dataset",clicked=self._research_import)); eactions.addWidget(QPushButton("Triage into ResearchObservations",clicked=self._research_triage)); eactions.addStretch(1); evidence.layout.addLayout(eactions)
        layout.addWidget(evidence)

        finish = Card("4. Human review and handoff", "AI triage and State assessments remain suggestions until a named analyst reviews the underlying observation and any analytic claims. The review workbook applies those decisions through SUGAR's verification gates before handoff.")
        review_actions=QHBoxLayout()
        review_actions.addWidget(QPushButton("Prepare State Assessment Suggestions",clicked=self._research_state_triage))
        review_actions.addWidget(QPushButton("Export Human Review Workbook",clicked=self._research_review_export))
        review_actions.addStretch(1)
        finish.layout.addLayout(review_actions)
        self.research_review_book=PathField(mode="file",extensions=("xlsx",))
        finish.layout.addWidget(LabeledRow("Completed human review workbook (optional override)",self.research_review_book,"Leave blank to reuse the project's latest exported review workbook after you edit and save it. The workbook contains observation, assessment, claim, sponsor-support, and source-conflict review fields when available."))
        apply_review_actions=QHBoxLayout()
        apply_review_actions.addWidget(primary_button("Apply Human Review",self._research_review_apply))
        apply_review_actions.addStretch(1)
        finish.layout.addLayout(apply_review_actions)
        self.research_handoff_name = QLineEdit("sugar-handoff")
        self.research_handoff_output = PathField(mode="directory", placeholder="Optional; defaults to the project exports folder")
        finish.layout.addWidget(LabeledRow("Handoff name",self.research_handoff_name))
        finish.layout.addWidget(LabeledRow("Handoff parent folder",self.research_handoff_output))
        factions=QHBoxLayout(); factions.addWidget(QPushButton("Apply Evidence Feedback to Plan",clicked=self._research_feedback)); factions.addWidget(primary_button("Export Verified Handoff",self._research_handoff)); factions.addStretch(1); finish.layout.addLayout(factions)
        layout.addWidget(finish); layout.addStretch(1)
        return page

    def _research_workspace_value(self) -> str:
        return self.research_workspace.text().strip()

    def _require_research_workspace(self) -> str | None:
        workspace = self._research_workspace_value()
        if not workspace:
            QMessageBox.warning(self,"Missing project","Choose a project workspace folder first.")
            return None
        return workspace

    def _research_workspace_open(self) -> None:
        workspace = self._require_research_workspace()
        if not workspace: return
        manifest = Path(workspace).expanduser() / "sugar-project.json"
        if manifest.is_file():
            self.run_operation("workspace-status",{"workspace":workspace},False)
        else:
            self.run_operation("workspace-init",{"workspace":workspace,"name":self.research_project_name.text().strip() or "State Research Project","exist_ok":True},False)

    def _research_requirement(self) -> None:
        workspace = self._require_research_workspace()
        if not workspace: return
        question = self.research_question.toPlainText().strip()
        if not question:
            QMessageBox.warning(self,"Missing question","Write the research question before creating the requirement.")
            return
        self.run_operation("research-requirement",{
            "workspace":workspace,"question":question,"geographies":self.research_geographies.text(),"known_entities":self.research_entities.text(),
            "target_audiences":self.research_audiences.text(),
            "languages":self.research_languages.text(),"since":self.research_since.text().strip(),"until":self.research_until.text().strip(),
            "collection_mode":self.research_mode.value(),"preferred_sources":self.research_sources.selected(),
        },False)

    def _research_plan(self) -> None:
        workspace = self._require_research_workspace()
        if workspace: self.run_operation("research-plan",{"workspace":workspace},False)

    def _research_compile(self) -> None:
        workspace = self._require_research_workspace()
        if workspace:
            self.run_operation("research-compile", {"workspace": workspace, "ai_expand": False}, False)

    def _research_compile_ai(self) -> None:
        workspace = self._require_research_workspace()
        if workspace:
            self.run_operation(
                "research-compile",
                {
                    "workspace": workspace,
                    "ai_expand": True,
                    "llm": self.settings.llm_config(),
                },
                True,
            )

    def _research_strategy_refresh(self) -> None:
        workspace = self._require_research_workspace()
        if workspace:
            self.run_operation("research-strategy-review", {"workspace": workspace}, False)

    def _research_strategy_updates(self) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        for row in range(self.research_strategy_table.rowCount()):
            concept_id = self.research_strategy_table.item(row, 0)
            origin = self.research_strategy_table.item(row, 1)
            value = self.research_strategy_table.item(row, 3)
            included = self.research_strategy_table.item(row, 5)
            rationale = self.research_strategy_table.item(row, 6)
            if concept_id is None or origin is None or value is None or included is None:
                continue
            update: dict[str, Any] = {
                "concept_id": concept_id.text(),
                "included": included.checkState() == Qt.CheckState.Checked,
            }
            if origin.text().casefold() != "explicit":
                update["value"] = value.text()
            if rationale is not None:
                update["rationale"] = rationale.text()
            updates.append(update)
        return updates

    def _research_strategy_dimension_updates(self) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        for row in range(self.research_strategy_dimensions.rowCount()):
            dimension_id = self.research_strategy_dimensions.item(row, 0)
            included = self.research_strategy_dimensions.item(row, 1)
            question = self.research_strategy_dimensions.item(row, 3)
            indicators = self.research_strategy_dimensions.item(row, 4)
            sources = self.research_strategy_dimensions.item(row, 5)
            rationale = self.research_strategy_dimensions.item(row, 6)
            if dimension_id is None or included is None or question is None:
                continue
            updates.append(
                {
                    "dimension_id": dimension_id.text(),
                    "included": included.checkState() == Qt.CheckState.Checked,
                    "question": question.text(),
                    "indicators": split_terms(indicators.text()) if indicators is not None else [],
                    "source_families": split_terms(sources.text()) if sources is not None else [],
                    "rationale": rationale.text() if rationale is not None else "",
                }
            )
        return updates

    def _research_strategy_save(self, *, decision: str = "") -> None:
        workspace = self._require_research_workspace()
        if not workspace:
            return
        config: dict[str, Any] = {
            "workspace": workspace,
            "actor": self.research_strategy_reviewer.text().strip() or "desktop analyst",
            "analytic_task": self.research_strategy_task.text().strip(),
            "concept_updates": self._research_strategy_updates(),
            "dimension_updates": self._research_strategy_dimension_updates(),
        }
        if decision:
            config.update(
                {
                    "decision": decision,
                    "reviewer": self.research_strategy_reviewer.text().strip(),
                    "review_note": self.research_strategy_note.text().strip(),
                }
            )
        self.run_operation("research-strategy-update", config, False)

    def _research_strategy_approve(self) -> None:
        if not self.research_strategy_reviewer.text().strip():
            QMessageBox.warning(
                self,
                "Reviewer required",
                "Enter the name of the analyst approving the compiled research strategy.",
            )
            return
        self._research_strategy_save(decision="approved")

    def _research_plan_refresh(self) -> None:
        workspace = self._require_research_workspace()
        if workspace:
            self.run_operation("research-plan-review", {"workspace": workspace}, False)

    def _selected_research_plan_row(self) -> tuple[str, str, str] | None:
        row = self.research_plan_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Choose a branch",
                "Select one search-plan row first.",
            )
            return None
        branch_item = self.research_plan_table.item(row, 0)
        query_item = self.research_plan_table.item(row, 1)
        rationale_item = self.research_plan_table.item(row, 2)
        if branch_item is None or query_item is None or rationale_item is None:
            return None
        return branch_item.text(), query_item.text(), rationale_item.text()

    def _research_plan_update(self, status: str = "") -> None:
        workspace = self._require_research_workspace()
        if not workspace:
            return
        selected = self._selected_research_plan_row()
        if selected is None:
            return
        branch_id, query, rationale = selected
        config = {
            "workspace": workspace,
            "branch_id": branch_id,
            "query": query,
            "rationale": rationale,
            "actor": "desktop analyst",
            "reason": self.research_plan_reason.text().strip(),
        }
        if status:
            config["status"] = status
        self.run_operation("research-plan-update", config, False)

    def _research_plan_save_edits(self) -> None:
        self._research_plan_update()

    def _research_plan_set_status(self, status: str) -> None:
        self._research_plan_update(status)

    def handle_backend_event(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        if event == "strategy-review":
            self.research_strategy_task.setText(str(payload.get("analytic_task") or ""))
            concepts = payload.get("concepts") or []
            self.research_strategy_table.setRowCount(0)
            for concept in concepts:
                if not isinstance(concept, dict):
                    continue
                row = self.research_strategy_table.rowCount()
                self.research_strategy_table.insertRow(row)
                confidence = concept.get("confidence")
                values = (
                    str(concept.get("concept_id") or ""),
                    str(concept.get("origin") or ""),
                    str(concept.get("kind") or ""),
                    str(concept.get("value") or ""),
                    f"{float(confidence):.2f}" if isinstance(confidence, (int, float)) else "",
                    "",
                    str(concept.get("rationale") or ""),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column in {0, 1, 2, 4}:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if column == 3 and str(concept.get("origin") or "").casefold() == "explicit":
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if column == 5:
                        item.setFlags(
                            (item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable
                        )
                        item.setCheckState(
                            Qt.CheckState.Checked
                            if bool(concept.get("included", True))
                            else Qt.CheckState.Unchecked
                        )
                    self.research_strategy_table.setItem(row, column, item)
            dimensions = payload.get("dimensions") or []
            self.research_strategy_dimensions.setRowCount(0)
            for dimension in dimensions:
                if not isinstance(dimension, dict):
                    continue
                row = self.research_strategy_dimensions.rowCount()
                self.research_strategy_dimensions.insertRow(row)
                values = (
                    str(dimension.get("dimension_id") or ""),
                    "",
                    str(dimension.get("name") or ""),
                    str(dimension.get("question") or ""),
                    ", ".join(str(value) for value in dimension.get("indicators") or []),
                    ", ".join(str(value) for value in dimension.get("source_families") or []),
                    str(dimension.get("rationale") or ""),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column in {0, 2}:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    if column == 1:
                        item.setFlags(
                            (item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEditable
                        )
                        item.setCheckState(
                            Qt.CheckState.Checked
                            if bool(dimension.get("included", True))
                            else Qt.CheckState.Unchecked
                        )
                    self.research_strategy_dimensions.setItem(row, column, item)
            lines: list[str] = []
            missing = payload.get("missing_dimensions") or []
            if missing:
                lines.append("Missing / analyst confirmation needed:")
                for item in missing:
                    if isinstance(item, dict):
                        lines.append(f"- {item.get('field', '')}: {item.get('reason', '')}")
            state = str(payload.get("review_state") or "draft")
            reviewer = str(payload.get("reviewer") or "")
            lines.append(f"Strategy review state: {state}" + (f" by {reviewer}" if reviewer else ""))
            self.research_strategy_missing.setPlainText("\n".join(lines))
            return
        if event != "plan-review":
            return
        branches = payload.get("branches") or []
        if not isinstance(branches, list):
            return
        self.research_plan_table.setRowCount(0)
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            row = self.research_plan_table.rowCount()
            self.research_plan_table.insertRow(row)
            values = (
                str(branch.get("branch_id") or ""),
                str(branch.get("query") or ""),
                str(branch.get("rationale") or ""),
                str(branch.get("origin") or ""),
                str(branch.get("status") or ""),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {0, 3, 4}:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.research_plan_table.setItem(row, column, item)

    def _research_collect(self) -> None:
        workspace = self._require_research_workspace()
        if not workspace: return
        sources=self.research_sources.selected()
        if not sources:
            QMessageBox.warning(self,"Missing sources","Select at least one searchable source.")
            return
        self.run_operation("research-collect",{"workspace":workspace,"sources":sources,"max_posts_per_query":self.research_posts.value(),"max_pages_per_query":self.research_pages.value(),"continue_on_source_error":True},False)

    def _research_import(self) -> None:
        workspace = self._require_research_workspace()
        if not workspace: return
        if not self.research_import_file.text():
            QMessageBox.warning(self,"Missing dataset","Choose an existing CSV or JSONL dataset to import.")
            return
        self.run_operation("research-import",{"workspace":workspace,"source_file":self.research_import_file.text(),"source_system":self.research_import_system.text().strip() or "external"},False)

    def _research_triage(self) -> None:
        workspace = self._require_research_workspace()
        if workspace: self.run_operation("research-triage",{"workspace":workspace,"llm":self.settings.llm_config()},True)

    def _research_feedback(self) -> None:
        workspace = self._require_research_workspace()
        if workspace: self.run_operation("research-feedback",{"workspace":workspace},False)

    def _research_state_triage(self) -> None:
        workspace = self._require_research_workspace()
        if workspace:
            self.run_operation(
                "state-triage",
                {"workspace": workspace, "llm": self.settings.llm_config()},
                True,
            )

    def _research_review_export(self) -> None:
        workspace = self._require_research_workspace()
        if workspace:
            self.run_operation("state-review-export", {"workspace": workspace}, False)

    def _research_review_apply(self) -> None:
        workspace = self._require_research_workspace()
        if not workspace:
            return
        config={"workspace":workspace}
        if self.research_review_book.text():
            config["workbook"]=self.research_review_book.text()
        self.run_operation("state-review-apply",config,False)

    def _research_handoff(self) -> None:
        workspace = self._require_research_workspace()
        if not workspace: return
        config={"workspace":workspace,"name":self.research_handoff_name.text().strip() or "sugar-handoff","create_zip":True}
        if self.research_handoff_output.text(): config["output_directory"]=self.research_handoff_output.text()
        self.run_operation("research-handoff",config,False)

    def _package_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(16,16,16,16)
        self.state_obs = PathField(mode="file", extensions=("csv","xlsx","jsonl"))
        self.state_assess = PathField(mode="file", extensions=("jsonl",))
        self.state_us = PathField(mode="file", extensions=("csv","xlsx"))
        self.state_entities = PathField(mode="file", extensions=("csv","xlsx"))
        self.state_previous = PathField(mode="file", extensions=("jsonl",))
        self.state_output = PathField(mode="directory"); self.state_output.setText(self.settings.default_output())
        self.state_name = QLineEdit("state_research")
        self.state_title = QLineEdit("State-Supported Public Engagement Research Update")
        self.current_start = QLineEdit("2024-01-01")
        self.stale_days = NumberField(1, 3650, 90)
        grid=QGridLayout()
        grid.addWidget(LabeledRow("Research observations",self.state_obs),0,0,1,2)
        grid.addWidget(LabeledRow("State assessments",self.state_assess,"Optional. Blank assessments are created when omitted."),1,0)
        grid.addWidget(LabeledRow("American Spaces / EducationUSA / U.S. sites",self.state_us),1,1)
        grid.addWidget(LabeledRow("Monitored entity registry",self.state_entities),2,0)
        grid.addWidget(LabeledRow("Previous assessment snapshot",self.state_previous),2,1)
        grid.addWidget(LabeledRow("Package name",self.state_name),3,0)
        grid.addWidget(LabeledRow("Brief title",self.state_title),3,1)
        grid.addWidget(LabeledRow("Current activity starts",self.current_start),4,0)
        grid.addWidget(LabeledRow("Collection stale after",self.stale_days),4,1)
        grid.addWidget(LabeledRow("Output folder",self.state_output),5,0,1,2)
        layout.addLayout(grid)
        note=QLabel("The package defaults to verified-only State-facing outputs and keeps attendance/views/likes/comments/shares separate rather than manufacturing an influence score.")
        note.setObjectName("hint"); note.setWordWrap(True); layout.addWidget(note)
        row=QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Build Complete State Package",self._run_package)); layout.addLayout(row); layout.addStretch(1)
        return page

    def _run_package(self)->None:
        if not self.state_obs.text(): QMessageBox.warning(self,"Missing observations","Choose a ResearchObservation dataset."); return
        self.run_operation("state-package",{
            "observations":self.state_obs.text(),"assessments":self.state_assess.text(),"us_sites":self.state_us.text(),"entities":self.state_entities.text(),"previous_assessments":self.state_previous.text(),
            "output_directory":self.state_output.text() or self.settings.default_output(),"name":self.state_name.text().strip() or "state_research","title":self.state_title.text().strip(),
            "current_start":self.current_start.text().strip() or "2024-01-01","stale_days":self.stale_days.value(),
        },False)

    def _triage_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16)
        self.triage_obs=PathField(mode="file",extensions=("csv","xlsx","jsonl"))
        self.triage_out=PathField(mode="save",save_extension="jsonl")
        self.triage_limit=NumberField(0,1_000_000,0); self.triage_limit.setSpecialValueText("All observations")
        layout.addWidget(LabeledRow("Research observations",self.triage_obs))
        layout.addWidget(LabeledRow("Output assessments JSONL",self.triage_out))
        layout.addWidget(LabeledRow("Limit",self.triage_limit,"0 processes the entire dataset. AI suggestions remain unverified until an analyst reviews them."))
        row=QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Run Guarded AI Triage",self._run_triage)); layout.addLayout(row); layout.addStretch(1)
        return page

    def _run_triage(self)->None:
        if not self.triage_obs.text(): QMessageBox.warning(self,"Missing observations","Choose a ResearchObservation dataset."); return
        target=self.triage_out.text() or str(Path(self.settings.default_output())/"state_triage.jsonl")
        self.run_operation("state-triage",{"observations":self.triage_obs.text(),"output_file":target,"limit":self.triage_limit.value() or None,"llm":self.settings.llm_config()},True)

    def _review_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16)
        export=Card("Export analyst review workbook","Creates an Excel workbook containing assessment and claim decisions without allowing AI to self-verify them.")
        self.review_obs=PathField(mode="file",extensions=("csv","xlsx","jsonl")); self.review_assess=PathField(mode="file",extensions=("jsonl",)); self.review_book=PathField(mode="save",save_extension="xlsx")
        export.layout.addWidget(LabeledRow("Observations",self.review_obs)); export.layout.addWidget(LabeledRow("Assessments",self.review_assess)); export.layout.addWidget(LabeledRow("Review workbook",self.review_book)); export.layout.addWidget(primary_button("Export Review Workbook",self._review_export))
        layout.addWidget(export)
        apply=Card("Apply analyst decisions","Imports reviewed decisions back through the same evidence and verification constraints.")
        self.apply_obs=PathField(mode="file",extensions=("csv","xlsx","jsonl"))
        self.apply_assess=PathField(mode="file",extensions=("jsonl",)); self.apply_book=PathField(mode="file",extensions=("xlsx",)); self.apply_out=PathField(mode="save",save_extension="jsonl")
        self.apply_obs_out=PathField(mode="save",save_extension="csv")
        apply.layout.addWidget(LabeledRow("Original observations",self.apply_obs,"Required to apply observation verification decisions from the workbook."))
        apply.layout.addWidget(LabeledRow("Original assessments",self.apply_assess)); apply.layout.addWidget(LabeledRow("Completed review workbook",self.apply_book)); apply.layout.addWidget(LabeledRow("Reviewed observations",self.apply_obs_out)); apply.layout.addWidget(LabeledRow("Reviewed assessments",self.apply_out)); apply.layout.addWidget(primary_button("Apply Human Review",self._review_apply))
        layout.addWidget(apply); layout.addStretch(1); return page

    def _review_export(self)->None:
        if not self.review_obs.text() or not self.review_assess.text(): QMessageBox.warning(self,"Missing files","Choose observations and assessments."); return
        out=self.review_book.text() or str(Path(self.settings.default_output())/"state_review.xlsx")
        self.run_operation("state-review-export",{"observations":self.review_obs.text(),"assessments":self.review_assess.text(),"output_file":out},False)

    def _review_apply(self)->None:
        if not self.apply_obs.text() or not self.apply_assess.text() or not self.apply_book.text(): QMessageBox.warning(self,"Missing files","Choose observations, assessments, and a completed review workbook."); return
        out=self.apply_out.text() or str(Path(self.settings.default_output())/"state_reviewed.jsonl")
        obs_out=self.apply_obs_out.text() or str(Path(self.settings.default_output())/"observations_reviewed.csv")
        self.run_operation("state-review-apply",{"observations":self.apply_obs.text(),"assessments":self.apply_assess.text(),"workbook":self.apply_book.text(),"observations_output_file":obs_out,"output_file":out},False)

    def _audit_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16)
        audit=Card("Evidence / verification audit")
        self.audit_obs=PathField(mode="file",extensions=("csv","xlsx","jsonl")); self.audit_assess=PathField(mode="file",extensions=("jsonl",)); self.audit_out=PathField(mode="save",save_extension="json")
        audit.layout.addWidget(LabeledRow("Observations",self.audit_obs)); audit.layout.addWidget(LabeledRow("Assessments",self.audit_assess)); audit.layout.addWidget(LabeledRow("Audit JSON",self.audit_out)); audit.layout.addWidget(primary_button("Run Audit",self._audit)); layout.addWidget(audit)
        diff=Card("Compare assessment versions","Shows what changed between a previous and current assessment snapshot.")
        self.diff_prev=PathField(mode="file",extensions=("jsonl",)); self.diff_cur=PathField(mode="file",extensions=("jsonl",)); self.diff_out=PathField(mode="save",save_extension="json")
        diff.layout.addWidget(LabeledRow("Previous assessments",self.diff_prev)); diff.layout.addWidget(LabeledRow("Current assessments",self.diff_cur)); diff.layout.addWidget(LabeledRow("Change report JSON",self.diff_out)); diff.layout.addWidget(primary_button("Compare Snapshots",self._diff)); layout.addWidget(diff); layout.addStretch(1); return page

    def _audit(self)->None:
        if not self.audit_obs.text() or not self.audit_assess.text(): QMessageBox.warning(self,"Missing files","Choose observations and assessments."); return
        out=self.audit_out.text() or str(Path(self.settings.default_output())/"state_audit.json")
        self.run_operation("state-audit",{"observations":self.audit_obs.text(),"assessments":self.audit_assess.text(),"output_file":out},False)

    def _diff(self)->None:
        if not self.diff_prev.text() or not self.diff_cur.text(): QMessageBox.warning(self,"Missing files","Choose both assessment snapshots."); return
        out=self.diff_out.text() or str(Path(self.settings.default_output())/"state_diff.json")
        self.run_operation("state-diff",{"previous":self.diff_prev.text(),"current":self.diff_cur.text(),"output_file":out},False)

    def _templates_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16)
        us=Card("U.S. public-diplomacy presence template"); self.us_template=PathField(mode="save",save_extension="csv"); us.layout.addWidget(LabeledRow("Output CSV",self.us_template)); us.layout.addWidget(primary_button("Create U.S. Sites Template",lambda:self._template("state-template-us-sites",self.us_template,"us_presence.csv"))); layout.addWidget(us)
        ent=Card("Monitored entity / alias registry"); self.entity_template=PathField(mode="save",save_extension="csv"); ent.layout.addWidget(LabeledRow("Output CSV",self.entity_template)); ent.layout.addWidget(primary_button("Create Entity Template",lambda:self._template("state-template-entities",self.entity_template,"monitored_entities.csv"))); layout.addWidget(ent)
        plan=Card("Generate watch-query plan from entity registry"); self.plan_entities=PathField(mode="file",extensions=("csv","xlsx")); self.plan_out=PathField(mode="save",save_extension="txt"); plan.layout.addWidget(LabeledRow("Entity registry",self.plan_entities)); plan.layout.addWidget(LabeledRow("Query plan",self.plan_out)); plan.layout.addWidget(primary_button("Generate Query Plan",self._query_plan)); layout.addWidget(plan); layout.addStretch(1); return page

    def _template(self,operation:str,field:PathField,name:str)->None:
        out=field.text() or str(Path(self.settings.default_output())/name); self.run_operation(operation,{"output_file":out},False)
    def _query_plan(self)->None:
        if not self.plan_entities.text(): QMessageBox.warning(self,"Missing registry","Choose an entity registry."); return
        out=self.plan_out.text() or str(Path(self.settings.default_output())/"query_plan.txt"); self.run_operation("state-query-plan",{"entities":self.plan_entities.text(),"output_file":out},False)


class IntelligencePage(QWidget):
    def __init__(self,run:Callable[[str,dict[str,Any],bool],None],settings:SettingsPage)->None:
        super().__init__(); self.run_operation=run; self.settings=settings
        root=QVBoxLayout(self); root.setContentsMargins(24,20,24,24); root.addWidget(page_header("Analytic Intelligence","Measure the corpus first, audit epistemic debt, then run bounded specialist agents, evidence-neighborhood refinement, integration, red-team critique and longitudinal comparison."))
        tabs=QTabWidget(); tabs.addTab(self._deterministic_tab(),"Packet & Tradecraft"); tabs.addTab(self._synthesis_tab(),"Agentic Synthesis"); tabs.addTab(self._hypothesis_tab(),"Competing Hypotheses"); tabs.addTab(self._compare_tab(),"Longitudinal"); root.addWidget(tabs,1)

    def _base_inputs(self):
        obs=PathField(mode="file",extensions=("csv","xlsx","jsonl")); assessments=PathField(mode="file",extensions=("jsonl",)); return obs,assessments

    def _deterministic_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16); self.intel_obs,self.intel_assess=self._base_inputs(); self.intel_country=QLineEdit(); self.intel_case=QLineEdit(); self.case_limit=NumberField(1,500,20); self.packet_out=PathField(mode="save",save_extension="json"); self.trade_out=PathField(mode="save",save_extension="json")
        grid=QGridLayout(); grid.addWidget(LabeledRow("Observations",self.intel_obs),0,0); grid.addWidget(LabeledRow("State assessments",self.intel_assess),0,1); grid.addWidget(LabeledRow("Country scope",self.intel_country,"Optional"),1,0); grid.addWidget(LabeledRow("Observation ID",self.intel_case,"Optional micro-case scope; takes precedence over country."),1,1); grid.addWidget(LabeledRow("Representative case limit",self.case_limit),2,0); grid.addWidget(LabeledRow("Packet output",self.packet_out),2,1); layout.addLayout(grid)
        row=QHBoxLayout(); row.addWidget(primary_button("Build Intelligence Packet",self._packet)); row.addWidget(QPushButton("Run Tradecraft Audit",clicked=self._tradecraft)); row.addStretch(1); layout.addLayout(row); layout.addWidget(LabeledRow("Tradecraft audit output",self.trade_out)); note=QLabel("These operations require no LLM. Use them to inspect concentration/diversity, comparability, source adequacy, analytic tensions and epistemic debt before synthesis."); note.setObjectName("hint"); note.setWordWrap(True); layout.addWidget(note); layout.addStretch(1); return page

    def _require_base(self,obs:PathField,assess:PathField)->bool:
        if not obs.text() or not assess.text(): QMessageBox.warning(self,"Missing files","Choose observations and State assessments."); return False
        return True
    def _packet(self)->None:
        if not self._require_base(self.intel_obs,self.intel_assess): return
        out=self.packet_out.text() or str(Path(self.settings.default_output())/"intelligence_packet.json"); self.run_operation("intel-packet",{"observations":self.intel_obs.text(),"assessments":self.intel_assess.text(),"output_file":out,"country":self.intel_country.text().strip(),"observation_id":self.intel_case.text().strip(),"case_limit":self.case_limit.value()},False)
    def _tradecraft(self)->None:
        if not self._require_base(self.intel_obs,self.intel_assess): return
        out=self.trade_out.text() or str(Path(self.settings.default_output())/"tradecraft_audit.json"); self.run_operation("intel-tradecraft",{"observations":self.intel_obs.text(),"assessments":self.intel_assess.text(),"output_file":out},False)

    def _synthesis_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16); self.syn_obs,self.syn_assess=self._base_inputs(); self.syn_country=QLineEdit(); self.syn_case=QLineEdit(); self.syn_depth=EnumCombo((("Quick","quick"),("Standard","standard"),("Deep iterative","deep"))); self.syn_depth.setCurrentIndex(1); self.syn_workers=NumberField(1,16,4); self.syn_name=QLineEdit("analytic_intelligence"); self.syn_output=PathField(mode="directory"); self.syn_output.setText(self.settings.default_output())
        grid=QGridLayout(); grid.addWidget(LabeledRow("Observations",self.syn_obs),0,0); grid.addWidget(LabeledRow("State assessments",self.syn_assess),0,1); grid.addWidget(LabeledRow("Country scope",self.syn_country,"Optional"),1,0); grid.addWidget(LabeledRow("Observation ID",self.syn_case,"Optional micro-case scope"),1,1); grid.addWidget(LabeledRow("Depth",self.syn_depth),2,0); grid.addWidget(LabeledRow("Parallel workers",self.syn_workers),2,1); grid.addWidget(LabeledRow("Synthesis name",self.syn_name),3,0); grid.addWidget(LabeledRow("Output folder",self.syn_output),3,1); layout.addLayout(grid)
        note=QLabel("Deep mode runs first-pass specialists, retrieves cited and comparable evidence, forces specialist reassessment, then integrates, red-teams, and revises. Multiple agents are functional decomposition—not independent corroboration."); note.setObjectName("hint"); note.setWordWrap(True); layout.addWidget(note); row=QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Run Synthesis",self._synthesize)); layout.addLayout(row); layout.addStretch(1); return page
    def _synthesize(self)->None:
        if not self._require_base(self.syn_obs,self.syn_assess): return
        self.run_operation("intel-synthesize",{"observations":self.syn_obs.text(),"assessments":self.syn_assess.text(),"output_directory":self.syn_output.text() or self.settings.default_output(),"name":self.syn_name.text().strip() or "analytic_intelligence","country":self.syn_country.text().strip(),"observation_id":self.syn_case.text().strip(),"depth":self.syn_depth.value(),"workers":self.syn_workers.value(),"llm":self.settings.llm_config()},True)

    def _hypothesis_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16); self.hyp_syn=PathField(mode="file",extensions=("json",)); self.hyp_output=PathField(mode="directory"); self.hyp_output.setText(self.settings.default_output()); self.hyp_name=QLineEdit("analytic_intelligence"); layout.addWidget(LabeledRow("Synthesis JSON",self.hyp_syn)); layout.addWidget(LabeledRow("Output folder",self.hyp_output)); layout.addWidget(LabeledRow("Output name",self.hyp_name)); note=QLabel("Creates a support/contradiction/discrimination matrix and a least-inconsistent ordering. It does not numerically score truth or convert missing collection into negative evidence."); note.setObjectName("hint"); note.setWordWrap(True); layout.addWidget(note); row=QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Build Hypothesis Matrix",self._hypotheses)); layout.addLayout(row); layout.addStretch(1); return page
    def _hypotheses(self)->None:
        if not self.hyp_syn.text(): QMessageBox.warning(self,"Missing synthesis","Choose a synthesis JSON file."); return
        self.run_operation("intel-hypotheses",{"synthesis":self.hyp_syn.text(),"output_directory":self.hyp_output.text() or self.settings.default_output(),"name":self.hyp_name.text().strip() or "analytic_intelligence"},False)

    def _compare_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16); self.comp_prev=PathField(mode="file",extensions=("json",)); self.comp_cur=PathField(mode="file",extensions=("json",)); self.comp_kind=EnumCombo((("Agentic synthesis","synthesis"),("Deterministic packet","packet"))); self.comp_out=PathField(mode="save",save_extension="json"); layout.addWidget(LabeledRow("Previous reporting cycle",self.comp_prev)); layout.addWidget(LabeledRow("Current reporting cycle",self.comp_cur)); layout.addWidget(LabeledRow("Artifact type",self.comp_kind)); layout.addWidget(LabeledRow("Comparison output",self.comp_out)); row=QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Compare Reporting Cycles",self._compare)); layout.addLayout(row); layout.addStretch(1); return page
    def _compare(self)->None:
        if not self.comp_prev.text() or not self.comp_cur.text(): QMessageBox.warning(self,"Missing files","Choose previous and current intelligence artifacts."); return
        out=self.comp_out.text() or str(Path(self.settings.default_output())/"intelligence_comparison.json"); self.run_operation("intel-compare",{"previous":self.comp_prev.text(),"current":self.comp_cur.text(),"kind":self.comp_kind.value(),"output_file":out},False)


class ReportsPage(QWidget):
    def __init__(self,run:Callable[[str,dict[str,Any],bool],None],settings:SettingsPage)->None:
        super().__init__(); self.run_operation=run; self.settings=settings; root=QVBoxLayout(self); root.setContentsMargins(24,20,24,24); root.addWidget(page_header("Maps & Reports","Create standalone maps and Word/PDF reports from existing normalized result files.")); tabs=QTabWidget(); tabs.addTab(self._map_tab(),"Map"); tabs.addTab(self._report_tab(),"Report"); root.addWidget(tabs,1)
    def _map_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16); self.map_source=PathField(mode="file",extensions=("csv","xlsx")); self.map_out=PathField(mode="save",save_extension="html"); layout.addWidget(LabeledRow("Existing results",self.map_source)); layout.addWidget(LabeledRow("HTML map",self.map_out)); row=QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Create Map",self._map)); layout.addLayout(row); layout.addStretch(1); return page
    def _map(self)->None:
        if not self.map_source.text(): QMessageBox.warning(self,"Missing file","Choose a normalized results file."); return
        out=self.map_out.text() or str(Path(self.map_source.text()).with_name(Path(self.map_source.text()).stem+"_map.html")); self.run_operation("map",{"source_file":self.map_source.text(),"output_file":out},False)
    def _report_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16); self.report_source=PathField(mode="file",extensions=("csv","xlsx")); self.report_stem=PathField(mode="save",save_extension="pdf"); self.report_format=EnumCombo((("PDF","pdf"),("Word","docx"),("PDF + Word","both"))); layout.addWidget(LabeledRow("Existing results",self.report_source)); layout.addWidget(LabeledRow("Output path",self.report_stem,"Extension is ignored for combined output.")); layout.addWidget(LabeledRow("Format",self.report_format)); row=QHBoxLayout(); row.addStretch(1); row.addWidget(primary_button("Create Report",self._report)); layout.addLayout(row); layout.addStretch(1); return page
    def _report(self)->None:
        if not self.report_source.text(): QMessageBox.warning(self,"Missing file","Choose a normalized results file."); return
        raw=self.report_stem.text() or str(Path(self.report_source.text()).with_name(Path(self.report_source.text()).stem+"_analysis")); stem=str(Path(raw).with_suffix("")); self.run_operation("analysis",{"source_file":self.report_source.text(),"output_stem":stem,"output_format":self.report_format.value()},False)


class ActivityDock(QDockWidget):
    cancel_requested=Signal()
    def __init__(self,parent:QWidget|None=None)->None:
        super().__init__("Activity & Outputs",parent); self.setObjectName("activityDock"); shell=QWidget(); root=QVBoxLayout(shell); root.setContentsMargins(10,8,10,8); root.setSpacing(6)
        top=QHBoxLayout(); self.status=QLabel("Ready"); self.status.setObjectName("muted"); self.progress=QProgressBar(); self.progress.setRange(0,1); self.progress.setValue(0); self.progress.setMaximumWidth(240); self.cancel=QPushButton("Cancel"); self.cancel.setProperty("danger",True); self.cancel.setEnabled(False); self.cancel.clicked.connect(self.cancel_requested); self.copy=QPushButton("Copy log"); self.clear=QPushButton("Clear"); top.addWidget(self.status); top.addStretch(1); top.addWidget(self.progress); top.addWidget(self.cancel); top.addWidget(self.copy); top.addWidget(self.clear); root.addLayout(top)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(5000); self.log.setMinimumHeight(105); root.addWidget(self.log,1)
        self.output_host=QWidget(); self.output_layout=QHBoxLayout(self.output_host); self.output_layout.setContentsMargins(0,0,0,0); self.output_layout.addWidget(QLabel("Outputs:")); self.output_layout.addStretch(1); root.addWidget(self.output_host)
        self.setWidget(shell); self.copy.clicked.connect(self._copy); self.clear.clicked.connect(self.log.clear)
    def _copy(self)->None: QApplication.clipboard().setText(self.log.toPlainText())
    def set_running(self,running:bool)->None:
        self.cancel.setEnabled(running); self.status.setText("Running…" if running else "Ready"); self.progress.setRange(0,0 if running else 1); self.progress.setValue(0 if running else 1)
    def set_progress(self,current:int,total:int)->None:
        if total>0: self.progress.setRange(0,total); self.progress.setValue(min(current,total))
    def append_event(self,payload:dict[str,Any])->None:
        event=str(payload.get("event") or "event")
        if event in {"backend","diagnostics"}: return
        if event=="complete": message="Completed successfully."
        elif event=="error": message=f"ERROR: {payload.get('message','Unknown error')}"
        elif event=="backend_stderr": message=f"backend: {payload.get('message','')}"
        else:
            details=[]
            for key in ("operation","source","query","stage","status","records","returned","inserted","unique_records","current","total","replicate","seed","comments","wait_seconds"):
                if key in payload and payload[key] not in (None,""): details.append(f"{key}={payload[key]}")
            message=event.replace("_"," ") + (" · " + " · ".join(details) if details else "")
        self.log.appendPlainText(message)
        if isinstance(payload.get("current"),int) and isinstance(payload.get("total"),int): self.set_progress(int(payload["current"]),int(payload["total"]))
        elif isinstance(payload.get("index"),int) and isinstance(payload.get("total"),int): self.set_progress(int(payload["index"]),int(payload["total"]))
    def set_outputs(self,paths:list[str])->None:
        while self.output_layout.count()>0:
            item=self.output_layout.takeAt(0); widget=item.widget();
            if widget: widget.deleteLater()
        self.output_layout.addWidget(QLabel("Outputs:"))
        for path in paths[:12]: self.output_layout.addWidget(OutputChip(path))
        if len(paths)>12: self.output_layout.addWidget(QLabel(f"+{len(paths)-12} more"))
        self.output_layout.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(self,*,smoke:bool=False)->None:
        super().__init__(); self.setWindowTitle("SUGAR — State Research Workbench"); self.resize(1380,900); self.setMinimumSize(1080,720); icon=resource_path("sugar-logo.png");
        if icon.is_file(): self.setWindowIcon(QIcon(str(icon)))
        self.runner=BackendRunner(self); self._diagnostics:dict[str,Any]={}; self.pages:dict[str,int]={}
        self.settings_page=SettingsPage(); self.home=HomePage()
        self.state_page=StatePage(self.run_operation,self.settings_page)
        central=QWidget(); outer=QHBoxLayout(central); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(210); side=QVBoxLayout(sidebar); side.setContentsMargins(8,16,8,12); brand=QLabel("SUGAR"); brand.setObjectName("brand"); sub=QLabel("State Research Workbench"); sub.setObjectName("brandSub"); side.addWidget(brand); side.addWidget(sub); side.addSpacing(12); self.nav=QListWidget(); self.nav.setObjectName("nav"); side.addWidget(self.nav,1); version=QLabel("Evidence-first OSINT + analysis"); version.setObjectName("brandSub"); version.setWordWrap(True); side.addWidget(version); outer.addWidget(sidebar)
        self.stack=QStackedWidget(); outer.addWidget(self.stack,1); self.setCentralWidget(central)
        page_defs=[("Home",self.home),("Collect",CollectPage(self.run_operation,self.settings_page)),("Weibo",WeiboPage(self.run_operation,self.settings_page)),("State Workflow",self.state_page),("Intelligence",IntelligencePage(self.run_operation,self.settings_page)),("Maps & Reports",ReportsPage(self.run_operation,self.settings_page)),("Settings",self.settings_page)]
        for name,page in page_defs:
            self.pages[name]=self.stack.count(); self.nav.addItem(QListWidgetItem(name)); self.stack.addWidget(scroll_page(page))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); self.nav.setCurrentRow(0); self.home.navigate.connect(self.navigate)
        self.activity=ActivityDock(self); self.addDockWidget(Qt.BottomDockWidgetArea,self.activity); self.activity.cancel_requested.connect(self.runner.cancel)
        self.runner.event.connect(self._event); self.runner.event.connect(self.state_page.handle_backend_event); self.runner.outputs_changed.connect(self.activity.set_outputs); self.runner.error.connect(self._error); self.runner.running_changed.connect(self.activity.set_running); self.settings_page.diagnostics_requested.connect(self._diagnostics_run); self.settings_page.arc_test_requested.connect(self._arc_test_run)
        self._build_menu()
        if not smoke:
            QTimer.singleShot(150,self._diagnostics_run)
            QTimer.singleShot(450,self._show_getting_started)

    def _build_menu(self)->None:
        bar=self.menuBar(); file_menu=bar.addMenu("File"); open_output=QAction("Open default output folder",self); open_output.triggered.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(self.settings_page.default_output()))); file_menu.addAction(open_output); file_menu.addSeparator(); quit_action=QAction("Exit",self); quit_action.triggered.connect(self.close); file_menu.addAction(quit_action)
        tools=bar.addMenu("Tools"); diag=QAction("Backend diagnostics",self); diag.triggered.connect(self._diagnostics_run); tools.addAction(diag); cancel=QAction("Cancel current operation",self); cancel.triggered.connect(self.runner.cancel); tools.addAction(cancel)
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
            "<b>1.</b> Open <b>State Workflow → Research Project</b> and create or open a portable project.<br><br>"
            "<b>2.</b> Save the research question and build the inspectable search plan. Import, project inspection, human review, and export work without any LLM or Virginia Tech credentials.<br><br>"
            "<b>3.</b> Configure an LLM only if you need AI assistance. OpenAI and custom OpenAI-compatible providers are supported; Virginia Tech ARC is an optional classroom/development integration.<br><br>"
            "<b>Source credentials:</b> only configure a source credential when you intentionally use that source and are authorized to do so."
        )
        check=QCheckBox("Don't show this automatically again")
        check.setChecked(True)
        box.setCheckBox(check)
        box.exec()
        if check.isChecked():
            store.setValue("ux/getting_started_seen",True)
            store.sync()

    def navigate(self,name:str)->None:
        if name in self.pages: self.nav.setCurrentRow(self.pages[name])

    def run_operation(self,command:str,config:dict[str,Any],requires_llm:bool=False)->None:
        if self.runner.is_running: QMessageBox.information(self,"SUGAR is busy","Cancel or finish the current operation before starting another."); return
        secrets=self.settings_page.secrets()
        if requires_llm and not secrets.get("llm_api_key"):
            QMessageBox.warning(self,"LLM key required","This operation needs an LLM API key. Add one in Settings or set SUGAR_LLM_API_KEY in the environment."); self.navigate("Settings"); return
        if "llm" not in config and requires_llm: config["llm"]=self.settings_page.llm_config()
        try:
            self.activity.log.appendPlainText(f"\n=== {command} ===")
            self.runner.run(command,config,secrets)
        except Exception as exc: self._error(str(exc))

    def _arc_test_run(self)->None:
        if self.runner.is_running: return
        arc_index=self.settings_page.provider.findData("arc")
        if arc_index>=0: self.settings_page.provider.setCurrentIndex(arc_index)
        secrets=self.settings_page.secrets()
        if not secrets.get("llm_api_key"):
            QMessageBox.warning(self,"ARC API key required","Click 'Get ARC API Key', create your personal key, paste it into the API key field, then test again.")
            return
        self.settings_page.arc_status.setText("Testing ARC…"); self.settings_page.arc_status.set_tone("neutral")
        model=self.settings_page.model.currentText().strip() or "gpt-oss-120b"
        try:
            self.runner.run("llm-check",{"llm":{"provider":"arc","model":model,"base_url":""}},secrets)
        except Exception as exc:
            self.settings_page.arc_status.setText("ARC test failed"); self.settings_page.arc_status.set_tone("bad"); self._error(str(exc))

    def _diagnostics_run(self)->None:
        if self.runner.is_running: return
        try: self.runner.diagnostics()
        except Exception as exc: self.home.diagnostic_failure(str(exc))

    def _event(self,payload:dict[str,Any])->None:
        event=payload.get("event");
        if event in {"diagnostics","backend"}:
            diagnostic_payload=dict(payload)
            backend_credentials=dict(payload.get("optional_credentials") or {})
            session_secrets=self.settings_page.secrets()
            backend_credentials.update({
                "llm_api_key": bool(session_secrets.get("llm_api_key")),
                "x_bearer_token": bool(session_secrets.get("x_bearer_token")),
                "bluesky_identifier": bool(session_secrets.get("bluesky_identifier")),
                "bluesky_app_password": bool(session_secrets.get("bluesky_app_password")),
                "mastodon_token": bool(session_secrets.get("mastodon_token")),
                "weibo_cookie": bool(session_secrets.get("weibo_cookie")),
            })
            diagnostic_payload["optional_credentials"]=backend_credentials
            self._diagnostics=diagnostic_payload; self.home.update_diagnostics(diagnostic_payload)
        if event=="llm_connection":
            available=bool(payload.get("selected_model_available",True)); model=str(payload.get("model") or "ARC model")
            self.settings_page.arc_status.setText("ARC connected" if available else "ARC connected · model unavailable"); self.settings_page.arc_status.set_tone("good" if available else "warn")
            message=f"Connected to Virginia Tech ARC. {model} is available." if available else f"Connected to Virginia Tech ARC, but {model} was not listed by the service. Choose another ARC model."
            QMessageBox.information(self,"ARC connection",message) if available else QMessageBox.warning(self,"ARC connection",message)
        self.activity.append_event(payload)

    def _error(self,message:str)->None:
        self.home.diagnostic_failure(message) if not self._diagnostics else None
        QMessageBox.critical(self,"SUGAR operation failed",message)

    def closeEvent(self,event)->None:
        if self.runner.is_running:
            choice=QMessageBox.question(self,"Operation running","A SUGAR operation is still running. Cancel it and exit?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
            if choice!=QMessageBox.Yes: event.ignore(); return
            self.runner.cancel()
        self.settings_page.save(); event.accept()

    def smoke_check(self)->None:
        assert len(self.pages)==7
        assert "Intelligence" in self.pages and "State Workflow" in self.pages
        assert self.runner is not None


def main()->int:
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setOrganizationName(APP_ORGANIZATION); app.setStyle("Fusion"); apply_light_palette(app); app.setStyleSheet(STYLE)
    smoke="--smoke-test" in sys.argv
    window=MainWindow(smoke=smoke)
    if smoke:
        window.smoke_check(); return 0
    window.show(); return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
