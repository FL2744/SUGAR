from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
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
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from backend import BackendRunner
from widgets import Card, EnumCombo, LabeledRow, NumberField, OutputChip, PasswordField, PathField, SourceSelector, StatusPill

APP_NAME = "SUGAR"
APP_ORGANIZATION = "Virginia Tech Diplomacy Lab"
SOURCES = ("x", "bluesky", "mastodon", "bilibili", "weibo")

STYLE = """
QMainWindow, QWidget { background: #f5f7fb; color: #172033; font-family: "Segoe UI"; font-size: 10pt; }
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

    def __init__(self) -> None:
        super().__init__()
        self.store = QSettings(APP_ORGANIZATION, APP_NAME)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(14)
        root.addWidget(page_header("Settings & Credentials", "Secrets are held in memory for this app session and are never written by the Windows UI."))

        llm = Card("LLM provider", "Used for translation, State triage, and agentic intelligence. Virginia Tech ARC uses its OpenAI-compatible endpoint.")
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
        root.addWidget(llm)

        sources = Card("Source credentials", "Only use legitimate credentials or sessions you are authorized to use. SUGAR does not automate login or manufacture browser/session identities.")
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
        source_grid.addWidget(LabeledRow("Weibo session", self.weibo_cookie, "Optional. Anonymous public surfaces remain the default when this is blank."), 2, 0, 1, 2)
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
        idx = self.model.findText(saved_model)
        if idx >= 0:
            self.model.setCurrentIndex(idx)
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
            models = ["gpt-oss-120b", "DeepSeek-V4-Flash", "GLM-5.2", "Kimi-K3"]
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

        summary = QHBoxLayout()
        self.backend_card = Card("Backend")
        self.backend_status = StatusPill("Checking…", "neutral")
        self.backend_detail = QLabel("Starting diagnostics")
        self.backend_detail.setObjectName("muted")
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
        self.backend_detail.setText(
            f"SUGAR {payload.get('version', '?')} · {payload.get('runtime', '?')} · {payload.get('architecture', '?')} · bridge v{payload.get('bridge_protocol', '?')}"
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
        tabs.addTab(self._harvest_tab(), "Resumable Harvest")
        root.addWidget(tabs, 1)

    def _search_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        self.search_sources = SourceSelector(SOURCES)
        self.search_sources.boxes["x"].setChecked(True)
        self.search_terms = QTextEdit()
        self.search_terms.setPlaceholderText("One search term per line\nCultural exchange Institute\nTechnical training Workshop")
        self.search_terms.setMaximumHeight(120)
        self.term_languages = QLineEdit()
        self.term_languages.setPlaceholderText("Optional translated query languages, comma separated")
        self.post_languages = QLineEdit("en")
        self.since = QLineEdit()
        self.since.setPlaceholderText("YYYY-MM-DD")
        self.until = QLineEdit()
        self.until.setPlaceholderText("YYYY-MM-DD")
        self.max_posts = NumberField(1, 5000, 100)
        self.max_pages = NumberField(1, 500, 5)
        self.x_mode = EnumCombo((("Recent", "recent"), ("Full archive (authorized X access)", "all")))
        self.translate_posts = QCheckBox("Translate posts")
        self.translate_posts.setChecked(True)
        self.infer_locations = QCheckBox("Infer broad locations")
        self.infer_locations.setChecked(True)
        self.include_reposts = QCheckBox("Include reposts/retweets")
        self.search_output = PathField(mode="directory")
        self.search_output.setText(self.settings.default_output())

        form = QGridLayout()
        form.addWidget(LabeledRow("Sources", self.search_sources), 0, 0, 1, 2)
        form.addWidget(LabeledRow("Search terms", self.search_terms), 1, 0, 1, 2)
        form.addWidget(LabeledRow("Translate terms into", self.term_languages, "Example: Spanish, Russian. Leave blank to use only original terms."), 2, 0)
        form.addWidget(LabeledRow("Post language filters", self.post_languages, "BCP-47 codes; currently most relevant to X."), 2, 1)
        form.addWidget(LabeledRow("Since", self.since), 3, 0)
        form.addWidget(LabeledRow("Until", self.until), 3, 1)
        form.addWidget(LabeledRow("Posts per query", self.max_posts), 4, 0)
        form.addWidget(LabeledRow("Pages per query", self.max_pages), 4, 1)
        form.addWidget(LabeledRow("X mode", self.x_mode), 5, 0)
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
            "output_directory": self.search_output.text() or self.settings.default_output(),
            "mastodon_url": self.settings.mastodon_url.text().strip() or "https://mastodon.social",
            "llm": self.settings.llm_config(),
        }
        need_llm = bool(config["translate_posts"] or config["infer_locations"] or config["translate_term_languages"])
        self.run_operation("search", config, need_llm)

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
        root.addWidget(page_header("State Department Workflow", "Turn ResearchObservations into auditable assessments, human review artifacts, American Spaces/EducationUSA comparisons, maps, networks and briefing outputs."))
        tabs = QTabWidget()
        tabs.addTab(self._package_tab(), "State Package")
        tabs.addTab(self._triage_tab(), "AI Triage")
        tabs.addTab(self._review_tab(), "Human Review")
        tabs.addTab(self._audit_tab(), "Audit & Diff")
        tabs.addTab(self._templates_tab(), "Monitoring Templates")
        root.addWidget(tabs, 1)

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
        self.apply_assess=PathField(mode="file",extensions=("jsonl",)); self.apply_book=PathField(mode="file",extensions=("xlsx",)); self.apply_out=PathField(mode="save",save_extension="jsonl")
        apply.layout.addWidget(LabeledRow("Original assessments",self.apply_assess)); apply.layout.addWidget(LabeledRow("Completed review workbook",self.apply_book)); apply.layout.addWidget(LabeledRow("Reviewed assessments",self.apply_out)); apply.layout.addWidget(primary_button("Apply Human Review",self._review_apply))
        layout.addWidget(apply); layout.addStretch(1); return page

    def _review_export(self)->None:
        if not self.review_obs.text() or not self.review_assess.text(): QMessageBox.warning(self,"Missing files","Choose observations and assessments."); return
        out=self.review_book.text() or str(Path(self.settings.default_output())/"state_review.xlsx")
        self.run_operation("state-review-export",{"observations":self.review_obs.text(),"assessments":self.review_assess.text(),"output_file":out},False)

    def _review_apply(self)->None:
        if not self.apply_assess.text() or not self.apply_book.text(): QMessageBox.warning(self,"Missing files","Choose assessments and a completed review workbook."); return
        out=self.apply_out.text() or str(Path(self.settings.default_output())/"state_reviewed.jsonl")
        self.run_operation("state-review-apply",{"assessments":self.apply_assess.text(),"workbook":self.apply_book.text(),"output_file":out},False)

    def _audit_tab(self)->QWidget:
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(16,16,16,16)
        audit=Card("Evidence / verification audit")
        self.audit_obs=PathField(mode="file",extensions=("csv","xlsx","jsonl")); self.audit_assess=PathField(mode="file",extensions=("jsonl",)); self.audit_out=PathField(mode="save",save_extension="json")
        audit.layout.addWidget(LabeledRow("Observations",self.audit_obs)); audit.layout.addWidget(LabeledRow("Assessments",self.audit_assess)); audit.layout.addWidget(LabeledRow("Audit JSON",self.audit_out)); audit.layout.addWidget(primary_button("Run Audit",self._audit)); layout.addWidget(audit)
        diff=Card("Assessment snapshot diff")
        self.diff_prev=PathField(mode="file",extensions=("jsonl",)); self.diff_cur=PathField(mode="file",extensions=("jsonl",)); self.diff_out=PathField(mode="save",save_extension="json")
        diff.layout.addWidget(LabeledRow("Previous assessments",self.diff_prev)); diff.layout.addWidget(LabeledRow("Current assessments",self.diff_cur)); diff.layout.addWidget(LabeledRow("Diff JSON",self.diff_out)); diff.layout.addWidget(primary_button("Compare Snapshots",self._diff)); layout.addWidget(diff); layout.addStretch(1); return page

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
        central=QWidget(); outer=QHBoxLayout(central); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(210); side=QVBoxLayout(sidebar); side.setContentsMargins(8,16,8,12); brand=QLabel("SUGAR"); brand.setObjectName("brand"); sub=QLabel("State Research Workbench"); sub.setObjectName("brandSub"); side.addWidget(brand); side.addWidget(sub); side.addSpacing(12); self.nav=QListWidget(); self.nav.setObjectName("nav"); side.addWidget(self.nav,1); version=QLabel("Evidence-first OSINT + analysis"); version.setObjectName("brandSub"); version.setWordWrap(True); side.addWidget(version); outer.addWidget(sidebar)
        self.stack=QStackedWidget(); outer.addWidget(self.stack,1); self.setCentralWidget(central)
        page_defs=[("Home",self.home),("Collect",CollectPage(self.run_operation,self.settings_page)),("Weibo",WeiboPage(self.run_operation,self.settings_page)),("State Workflow",StatePage(self.run_operation,self.settings_page)),("Intelligence",IntelligencePage(self.run_operation,self.settings_page)),("Maps & Reports",ReportsPage(self.run_operation,self.settings_page)),("Settings",self.settings_page)]
        for name,page in page_defs:
            self.pages[name]=self.stack.count(); self.nav.addItem(QListWidgetItem(name)); self.stack.addWidget(scroll_page(page))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); self.nav.setCurrentRow(0); self.home.navigate.connect(self.navigate)
        self.activity=ActivityDock(self); self.addDockWidget(Qt.BottomDockWidgetArea,self.activity); self.activity.cancel_requested.connect(self.runner.cancel)
        self.runner.event.connect(self._event); self.runner.outputs_changed.connect(self.activity.set_outputs); self.runner.error.connect(self._error); self.runner.running_changed.connect(self.activity.set_running); self.settings_page.diagnostics_requested.connect(self._diagnostics_run)
        self._build_menu()
        if not smoke: QTimer.singleShot(150,self._diagnostics_run)

    def _build_menu(self)->None:
        bar=self.menuBar(); file_menu=bar.addMenu("File"); open_output=QAction("Open default output folder",self); open_output.triggered.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(self.settings_page.default_output()))); file_menu.addAction(open_output); file_menu.addSeparator(); quit_action=QAction("Exit",self); quit_action.triggered.connect(self.close); file_menu.addAction(quit_action)
        tools=bar.addMenu("Tools"); diag=QAction("Backend diagnostics",self); diag.triggered.connect(self._diagnostics_run); tools.addAction(diag); cancel=QAction("Cancel current operation",self); cancel.triggered.connect(self.runner.cancel); tools.addAction(cancel)

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

    def _diagnostics_run(self)->None:
        if self.runner.is_running: return
        try: self.runner.diagnostics()
        except Exception as exc: self.home.diagnostic_failure(str(exc))

    def _event(self,payload:dict[str,Any])->None:
        event=payload.get("event");
        if event in {"diagnostics","backend"}:
            self._diagnostics=payload; self.home.update_diagnostics(payload)
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
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME); app.setOrganizationName(APP_ORGANIZATION); app.setStyle("Fusion"); app.setStyleSheet(STYLE)
    smoke="--smoke-test" in sys.argv
    window=MainWindow(smoke=smoke)
    if smoke:
        window.smoke_check(); return 0
    window.show(); return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
