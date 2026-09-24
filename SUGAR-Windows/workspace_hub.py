from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from widgets import Card, LabeledRow, PathField


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ";").split(";") if item.strip()]


class DatasetDropTarget(QLabel):
    files_dropped = Signal(list)

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(58)
        self.setWordWrap(True)
        self.setStyleSheet("border: 2px dashed #8da2bf; border-radius: 8px; padding: 10px; color: #42536d; background: #f8fafc")
        self.setToolTip("Drop CSV, TSV, XLSX, XLS, JSON, or GeoJSON files here.")

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        accepted = [path for path in paths if Path(path).suffix.casefold() in {".csv", ".tsv", ".xlsx", ".xls", ".json", ".geojson", ".jsonl", ".ndjson"}]
        if accepted:
            self.files_dropped.emit(accepted)
            event.acceptProposedAction()
        else:
            event.ignore()


class WorkspaceHubPage(QWidget):
    """Persistent project, registry, map, monitoring, and conversation workspace."""

    def __init__(self, run: Callable[[str, dict[str, Any], bool], None], activate_workspace: Callable[[str], None], default_workspace: str = "") -> None:
        super().__init__()
        self.run_operation = run
        self.activate_workspace_callback = activate_workspace
        self.workspace = default_workspace
        self.project_rows: list[dict[str, Any]] = []
        self.entity_rows: list[dict[str, Any]] = []
        self.monitor_rows: list[dict[str, Any]] = []
        self.history_rows: list[dict[str, Any]] = []
        self.material_rows: list[dict[str, Any]] = []
        self.preview: dict[str, Any] = {}
        store = QSettings("Virginia Tech Diplomacy Lab", "SUGAR")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        title = QLabel("Research Workspace")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Persistent projects, source-backed institutions, map layers, saved monitoring, evidence review, and reproducible history.")
        subtitle.setObjectName("pageSub")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        active = Card("Active project", "Project context is shared with the State Workflow page. History and bundles travel with the project.")
        active_row = QHBoxLayout()
        self.workspace_field = PathField(mode="directory", placeholder="Choose or create a SUGAR project folder")
        self.workspace_field.setText(default_workspace)
        self.project_name = QLineEdit("State Research Project")
        self.project_name.setPlaceholderText("New project name")
        self.analyst_name = QLineEdit(str(store.value("workspace/analyst_name", "analyst")))
        self.analyst_name.setPlaceholderText("Analyst name for review history")
        self.analyst_name.setMaximumWidth(190)
        self.analyst_name.editingFinished.connect(lambda: store.setValue("workspace/analyst_name", self.analyst_name.text().strip() or "analyst"))
        self.open_project_button = QPushButton("Create / open")
        self.open_project_button.clicked.connect(self._open_or_create_project)
        active_row.addWidget(self.workspace_field, 3)
        active_row.addWidget(self.project_name, 1)
        active_row.addWidget(self.analyst_name)
        active_row.addWidget(self.open_project_button)
        active.layout.addLayout(active_row)
        self.project_summary = QLabel("Choose a project to load its dashboard.")
        self.project_summary.setWordWrap(True)
        self.project_summary.setObjectName("muted")
        active.layout.addWidget(self.project_summary)
        root.addWidget(active)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_projects_tab()
        self._build_registry_tab()
        self._build_data_tab()
        self._build_maps_tab()
        self._build_monitoring_tab()
        self._build_conversation_help_tab()

    def _table(self, headers: list[str], *, height: int = 220) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(height)
        return table

    def _button(self, label: str, callback: Callable[[], None], *, primary: bool = False) -> QPushButton:
        button = QPushButton(label)
        if primary:
            button.setProperty("primary", "true")
        button.clicked.connect(callback)
        return button

    def _build_projects_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.projects_root = PathField(mode="directory", placeholder="Folder containing projects")
        if self.workspace:
            self.projects_root.setText(str(Path(self.workspace).parent))
        row.addWidget(LabeledRow("Project folder", self.projects_root), 1)
        row.addWidget(self._button("Refresh projects", self.refresh_projects, primary=True))
        row.addWidget(self._button("Use selected project", self.use_selected_project))
        layout.addLayout(row)
        self.projects_table = self._table(["Project", "Activity", "Artifacts", "Review", "Subprojects", "Project folder"])
        self.projects_table.cellDoubleClicked.connect(lambda *_: self.use_selected_project())
        layout.addWidget(self.projects_table)
        self.project_history_table = self._table(["Time", "Type", "Command", "Status", "Summary"], height=190)
        self.project_history_table.itemSelectionChanged.connect(self._show_history_detail)
        layout.addWidget(QLabel("Project activity and searches"))
        layout.addWidget(self.project_history_table)
        detail_row = QHBoxLayout()
        self.history_detail = QPlainTextEdit()
        self.history_detail.setReadOnly(True)
        self.history_detail.setPlaceholderText("Select an activity row to inspect query terms, platforms, filters, coverage, and outputs.")
        self.history_detail.setMaximumHeight(120)
        detail_row.addWidget(self.history_detail, 1)
        history_buttons = QVBoxLayout()
        history_buttons.addWidget(self._button("Load project history", self.load_history))
        history_buttons.addWidget(self._button("Rerun selected search", self.rerun_selected_search, primary=True))
        history_buttons.addWidget(self._button("Create subproject", self.create_subproject))
        history_buttons.addStretch(1)
        detail_row.addLayout(history_buttons)
        layout.addLayout(detail_row)

        exchange = Card("Share or import a project", "Portable bundles include evidence, reference data, search history, annotations, maps, settings, and provenance. Credentials are excluded.")
        exchange_row = QGridLayout()
        self.bundle_output = PathField(mode="save", save_extension="sugar.zip", placeholder="Bundle output path")
        self.bundle_input = PathField(mode="file", extensions=("zip",), placeholder="Shared .sugar.zip bundle")
        self.import_destination = QLineEdit()
        self.import_destination.setPlaceholderText("New destination folder for imported project")
        self.link_imported_child = QCheckBox("Link imported project as a subproject of the active project")
        exchange_row.addWidget(LabeledRow("Export bundle", self.bundle_output), 0, 0)
        exchange_row.addWidget(self._button("Export project", self.export_project), 0, 1)
        exchange_row.addWidget(LabeledRow("Import bundle", self.bundle_input), 1, 0)
        exchange_row.addWidget(self.import_destination, 1, 1)
        exchange.layout.addLayout(exchange_row)
        exchange.layout.addWidget(self.link_imported_child)
        exchange.layout.addWidget(self._button("Import project", self.import_project))
        layout.addWidget(exchange)
        self.tabs.addTab(page, "Projects & history")

    def _build_registry_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        filters = QHBoxLayout()
        self.registry_filter = QLineEdit()
        self.registry_filter.setPlaceholderText("Search institution, alias, city, or country")
        self.registry_network_filter = QLineEdit()
        self.registry_network_filter.setPlaceholderText("Network")
        self.registry_status_filter = QComboBox()
        self.registry_status_filter.addItem("All statuses", "")
        for value in ("active", "closed", "renamed", "relocated", "unknown"):
            self.registry_status_filter.addItem(value.title(), value)
        filters.addWidget(self.registry_filter, 2)
        filters.addWidget(self.registry_network_filter)
        filters.addWidget(self.registry_status_filter)
        filters.addWidget(self._button("Load registry", self.load_registry, primary=True))
        filters.addWidget(self._button("Export table", self.export_registry))
        layout.addLayout(filters)
        self.registry_table = self._table(["Institution / entity", "Type", "Network", "Status", "Location",
                                           "Program wording", "Normalized domains", "Audience wording",
                                           "Normalized audiences", "Delivery modes", "Review", "ID"])
        self.registry_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.registry_table.cellClicked.connect(self._profile_selected)
        layout.addWidget(self.registry_table)
        comparison = QHBoxLayout()
        self.registry_coverage_documented = QCheckBox("Registry coverage is documented for this scope")
        comparison.addWidget(self.registry_coverage_documented)
        comparison.addWidget(self._button("Prepare listening post", self.prepare_monitor_for_entity))
        comparison.addWidget(self._button("Compare two selected entities", self.compare_selected_entities))
        comparison.addStretch(1)
        layout.addLayout(comparison)
        self.registry_profile = QPlainTextEdit()
        self.registry_profile.setReadOnly(True)
        self.registry_profile.setMaximumHeight(145)
        self.registry_profile.setPlaceholderText("Select a row to see aliases, source claims, evidence, status history, and relationships.")
        layout.addWidget(self.registry_profile)

        import_card = Card("Import a reference dataset", "Drop a file or choose one. Review suggested field mappings and invalid rows before importing. Source scope, original file, license notes, and row-level evidence are retained.")
        self.registry_drop = DatasetDropTarget("Drop CSV, TSV, XLSX, XLS, JSON, or GeoJSON to preview field mappings")
        self.registry_drop.files_dropped.connect(self._set_import_file)
        import_card.layout.addWidget(self.registry_drop)
        self.registry_file = PathField(mode="file", extensions=("csv", "tsv", "xlsx", "xls", "json", "geojson"), placeholder="Reference dataset")
        import_card.layout.addWidget(self.registry_file)
        template_row = QHBoxLayout()
        self.registry_template = QComboBox()
        for key, label in (("american_spaces", "American Spaces"), ("educationusa", "EducationUSA"),
                           ("language_education_centers", "Language education centers / classrooms"),
                           ("technical_training_workshops", "Technical training workshops"), ("custom", "Custom network")):
            self.registry_template.addItem(label, key)
        template_row.addWidget(self.registry_template)
        template_row.addWidget(self._button("Create blank template", self.create_registry_template))
        template_row.addStretch(1)
        import_card.layout.addLayout(template_row)
        import_row = QGridLayout()
        self.registry_dataset_name = QLineEdit()
        self.registry_dataset_name.setPlaceholderText("Dataset name")
        self.registry_network = QLineEdit()
        self.registry_network.setPlaceholderText("Network / institution family")
        self.registry_scope = QLineEdit()
        self.registry_scope.setPlaceholderText("Geographic and temporal scope")
        self.registry_limits = QLineEdit()
        self.registry_limits.setPlaceholderText("Known coverage limits")
        self.registry_license = QLineEdit()
        self.registry_license.setPlaceholderText("License / permitted use notes")
        import_row.addWidget(self.registry_dataset_name, 0, 0)
        import_row.addWidget(self.registry_network, 0, 1)
        import_row.addWidget(self.registry_scope, 1, 0)
        import_row.addWidget(self.registry_limits, 1, 1)
        import_row.addWidget(self.registry_license, 2, 0, 1, 2)
        import_card.layout.addLayout(import_row)
        self.registry_mapping = QPlainTextEdit()
        self.registry_mapping.setPlaceholderText('Suggested canonical mapping, editable JSON: {"name":"Institution Name","status":"Current Status"}')
        self.registry_mapping.setMaximumHeight(95)
        import_card.layout.addWidget(self.registry_mapping)
        preview_row = QHBoxLayout()
        self.registry_preview_label = QLabel("Preview not loaded")
        self.registry_preview_label.setWordWrap(True)
        self.registry_partial = QCheckBox("Accept valid rows and record invalid exclusions")
        preview_row.addWidget(self.registry_preview_label, 1)
        preview_row.addWidget(self.registry_partial)
        preview_row.addWidget(self._button("Preview dataset", self.preview_registry_import))
        preview_row.addWidget(self._button("Confirm import", self.import_registry_dataset, primary=True))
        import_card.layout.addLayout(preview_row)
        layout.addWidget(import_card)

        manual = Card("Add or update an entity", "Every submitted claim needs an HTTP(S) source. Conflicting claims remain visible until an analyst resolves them.")
        form = QGridLayout()
        self.entity_fields: dict[str, QLineEdit] = {}
        field_specs = [
            ("entity_id", "Existing entity ID (optional)"), ("name", "Name*"), ("entity_type", "Type"), ("network", "Network"), ("status", "Status"),
            ("country", "Country"), ("region", "Region"), ("city", "City"), ("address", "Address"),
            ("latitude", "Latitude"), ("longitude", "Longitude"), ("location_precision", "Location precision"),
            ("aliases", "Aliases (; separated)"), ("public_links", "Institution links (; separated)"),
            ("accounts", "Public handles (; separated)"), ("host_entities", "Host institutions (; separated)"),
            ("partner_entities", "Partners (; separated)"), ("program_domains", "Programs / services (; separated)"),
            ("audiences", "Audiences (; separated)"), ("delivery_modes", "Delivery (physical/virtual/hybrid)"),
            ("opened_date", "Opened date"), ("closed_date", "Closed date"),
        ]
        for index, (key, label) in enumerate(field_specs):
            editor = QLineEdit()
            editor.setPlaceholderText(label)
            self.entity_fields[key] = editor
            form.addWidget(editor, index // 3, index % 3)
        manual.layout.addLayout(form)
        self.entity_description = QLineEdit()
        self.entity_description.setPlaceholderText("Description")
        manual.layout.addWidget(self.entity_description)
        evidence_row = QHBoxLayout()
        self.entity_evidence = QLineEdit()
        self.entity_evidence.setPlaceholderText("Evidence URL (required)")
        self.entity_reason = QLineEdit()
        self.entity_reason.setPlaceholderText("Analyst note / reason")
        evidence_row.addWidget(self.entity_evidence, 2)
        evidence_row.addWidget(self.entity_reason, 1)
        self.entity_review_state = QComboBox()
        for value in ("unreviewed", "human_verified", "needs_followup"):
            self.entity_review_state.addItem(value.replace("_", " ").title(), value)
        evidence_row.addWidget(self.entity_review_state)
        evidence_row.addWidget(self._button("Save entity claim", self.upsert_entity, primary=True))
        manual.layout.addLayout(evidence_row)
        relation_row = QHBoxLayout()
        self.relation_source = QComboBox()
        self.relation_target = QComboBox()
        self.relation_type = QComboBox()
        for value in ("hosts", "hosted_by", "partner_of", "affiliated_with", "member_of", "successor_to", "associated_account", "delivers", "sponsors", "serves", "located_at", "other"):
            self.relation_type.addItem(value.replace("_", " ").title(), value)
        self.relation_evidence = QLineEdit()
        self.relation_evidence.setPlaceholderText("Relationship evidence URL")
        relation_row.addWidget(self.relation_source, 1)
        relation_row.addWidget(self.relation_type)
        relation_row.addWidget(self.relation_target, 1)
        relation_row.addWidget(self.relation_evidence, 2)
        relation_row.addWidget(self._button("Add relationship", self.add_relationship))
        manual.layout.addLayout(relation_row)
        layout.addWidget(manual)
        self.tabs.addTab(page, "Institution registry")

    def _build_maps_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        info = QLabel("Map the canonical registry and add as many overlapping reference layers as needed. Closed sites remain visible with a gray × marker and source-backed closure date. An as-of date filters dated activity and known lifecycle dates; unknown past locations are not reconstructed.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.map_drop = DatasetDropTarget("Drop one or more reference datasets here to add map layers")
        self.map_drop.files_dropped.connect(self._append_map_layers)
        layout.addWidget(self.map_drop)
        grid = QGridLayout()
        self.map_base_file = PathField(mode="file", extensions=("csv", "xlsx"), placeholder="Optional base activity / service dataset")
        self.map_layers = QPlainTextEdit()
        self.map_layers.setPlaceholderText("Additional reference layers, one file path per line. Example: American Spaces.csv\nEducationUSA.xlsx")
        self.map_layers.setMaximumHeight(115)
        self.map_as_of = QLineEdit()
        self.map_as_of.setPlaceholderText("Optional as-of date YYYY-MM-DD")
        self.map_output = PathField(mode="save", save_extension="html", placeholder="HTML map output")
        grid.addWidget(LabeledRow("Base layer", self.map_base_file), 0, 0, 1, 2)
        grid.addWidget(LabeledRow("Reference layers", self.map_layers), 1, 0, 1, 2)
        grid.addWidget(self.map_as_of, 2, 0)
        grid.addWidget(self.map_output, 2, 1)
        layout.addLayout(grid)
        layout.addWidget(self._button("Build workspace map", self.build_map, primary=True))
        self.tabs.addTab(page, "Maps & layers")

    def _build_data_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        card = Card("Underlying research data", "Inspect source records, project exports, or reference files as tables. Filter by any column and export the selected view as CSV, XLSX, JSONL, JSON, or GeoJSON.")
        self.data_drop = DatasetDropTarget("Drop a CSV, TSV, XLSX, JSON, JSONL, GeoJSON, or NDJSON dataset here")
        self.data_drop.files_dropped.connect(self._set_data_file)
        card.layout.addWidget(self.data_drop)
        self.data_file = PathField(mode="file", extensions=("csv", "tsv", "xlsx", "xls", "json", "geojson", "jsonl", "ndjson"), placeholder="Dataset file")
        card.layout.addWidget(self.data_file)
        filters = QHBoxLayout()
        self.data_filter_column = QComboBox()
        self.data_filter_column.addItem("All columns", "")
        self.data_filter_value = QLineEdit()
        self.data_filter_value.setPlaceholderText("Contains text")
        filters.addWidget(self.data_filter_column)
        filters.addWidget(self.data_filter_value, 1)
        filters.addWidget(self._button("Load / filter table", self.load_data_table, primary=True))
        card.layout.addLayout(filters)
        self.data_summary = QLabel("Choose a project record or reference dataset to inspect its structured rows.")
        self.data_summary.setWordWrap(True)
        card.layout.addWidget(self.data_summary)
        self.data_table = self._table([], height=440)
        self.data_table.setColumnCount(0)
        card.layout.addWidget(self.data_table)
        export_row = QHBoxLayout()
        self.data_export_path = PathField(mode="save", save_extension="csv", placeholder="Filtered table export path")
        export_row.addWidget(self.data_export_path, 1)
        export_row.addWidget(self._button("Export filtered rows", self.export_data_table))
        card.layout.addLayout(export_row)
        layout.addWidget(card)
        self.tabs.addTab(page, "Data explorer")

    def _build_monitoring_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        info = QLabel("A listening post stores query terms, public sources, cadence, target entities, and collection history. Due runs create a deduplicated evidence feed; new and changed items return to analyst review. Cadence is enforced by the due-run command. You can run it here or schedule `sugar-project monitor-run-due <project-folder>` with Windows Task Scheduler or launchd.")
        info.setWordWrap(True)
        layout.addWidget(info)
        form = QGridLayout()
        self.monitor_name = QLineEdit()
        self.monitor_name.setPlaceholderText("Listening-post name")
        self.monitor_terms = QLineEdit()
        self.monitor_terms.setPlaceholderText("Search terms, separated by semicolons")
        self.monitor_targets = QLineEdit()
        self.monitor_targets.setPlaceholderText("Organizations / handles to monitor (queried as terms)")
        self.monitor_sources = QLineEdit("bilibili")
        self.monitor_sources.setPlaceholderText("Sources: bilibili; weibo; x; bluesky; mastodon")
        self.monitor_geographies = QLineEdit()
        self.monitor_geographies.setPlaceholderText("Geographies for analyst context")
        self.monitor_cadence = QSpinBox()
        self.monitor_cadence.setRange(5, 525600)
        self.monitor_cadence.setValue(1440)
        self.monitor_cadence.setSuffix(" minutes")
        form.addWidget(self.monitor_name, 0, 0)
        form.addWidget(self.monitor_terms, 0, 1)
        form.addWidget(self.monitor_targets, 1, 0)
        form.addWidget(self.monitor_sources, 1, 1)
        form.addWidget(self.monitor_geographies, 2, 0)
        form.addWidget(self.monitor_cadence, 2, 1)
        layout.addLayout(form)
        controls = QHBoxLayout()
        controls.addWidget(self._button("Save listening post", self.save_monitor, primary=True))
        controls.addWidget(self._button("Refresh list", self.load_monitors))
        controls.addWidget(self._button("Run selected now", self.run_selected_monitor))
        controls.addWidget(self._button("Run all due now", self.run_due_monitors))
        controls.addWidget(self._button("Pause / resume selected", self.toggle_selected_monitor))
        controls.addWidget(self._button("Load incoming evidence", self.load_monitor_feed))
        controls.addStretch(1)
        layout.addLayout(controls)
        self.monitor_table = self._table(["Name", "Status", "Cadence", "Next due", "Last run", "Last result", "ID"])
        self.monitor_table.itemSelectionChanged.connect(self._selected_monitor_changed)
        layout.addWidget(self.monitor_table)
        self.material_table = self._table(["Monitor", "Change", "Actor", "Platform", "Published", "Review", "Source link", "Material ID"])
        self.material_table.cellDoubleClicked.connect(self._open_material_source)
        layout.addWidget(self.material_table)
        review = QHBoxLayout()
        self.material_note = QLineEdit()
        self.material_note.setPlaceholderText("Analyst review note")
        review.addWidget(self.material_note, 1)
        self.auto_monitoring = QCheckBox("Automatically run due posts while SUGAR is open")
        self.auto_monitoring.setChecked(bool(QSettings("Virginia Tech Diplomacy Lab", "SUGAR").value("workspace/auto_monitoring", False, type=bool)))
        self.auto_monitoring.toggled.connect(lambda checked: QSettings("Virginia Tech Diplomacy Lab", "SUGAR").setValue("workspace/auto_monitoring", checked))
        layout.insertWidget(layout.count() - 2, self.auto_monitoring)
        for label, state in (("Verify", "human_verified"), ("Needs follow-up", "needs_followup"), ("Reject", "rejected"), ("Reset review", "unreviewed")):
            review.addWidget(self._button(label, lambda value=state: self.review_selected_material(value)))
        layout.addLayout(review)
        self.monitor_result = QPlainTextEdit()
        self.monitor_result.setReadOnly(True)
        self.monitor_result.setMaximumHeight(95)
        self.monitor_result.setPlaceholderText("Due-run coverage, counts, and incoming new/changed material are summarized here.")
        layout.addWidget(self.monitor_result)
        self.tabs.addTab(page, "Listening posts")

    def _build_conversation_help_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        conversation_card = Card("Actors and conversations", "Conversation reconstruction preserves source-provided handles, replies, quotes, mentions, and thread IDs. Missing relationships are shown as missing; SUGAR does not infer who said what.")
        self.conversation_file = PathField(mode="file", extensions=("csv", "xlsx", "jsonl", "ndjson"), placeholder="Source record file")
        self.conversation_id = QLineEdit()
        self.conversation_id.setPlaceholderText("Optional conversation / thread ID")
        row = QHBoxLayout()
        row.addWidget(self.conversation_file, 2)
        row.addWidget(self.conversation_id, 1)
        row.addWidget(self._button("Build conversation view", self.build_conversation, primary=True))
        conversation_card.layout.addLayout(row)
        self.conversation_result = QPlainTextEdit()
        self.conversation_result.setReadOnly(True)
        conversation_card.layout.addWidget(self.conversation_result)
        layout.addWidget(conversation_card, 2)
        help_card = Card("How to use this workspace")
        help_text = QLabel(
            "<b>1. Start with a project.</b> Projects preserve search inputs, source coverage, evidence, annotations, maps, review states, and change history. Use subprojects for a country, network, or institution track.<br><br>"
            "<b>2. Import the external environment.</b> Preview reference data and confirm the field mapping, source, license, geography, dates, and known coverage limits. Registry claims are source-backed; contradictory sources remain visible as conflicts.<br><br>"
            "<b>3. Compare dimensions.</b> Use maps and tables to inspect place, audience, service domain, delivery mode, partners, status, and time. Geographic distance is not a competition or effectiveness score.<br><br>"
            "<b>4. Monitor changes.</b> Save listening posts, then run due monitors or use the CLI command in the Listening posts tab with an operating-system scheduler. Review new or changed evidence before using it in an assessment.<br><br>"
            "<b>5. Share reproducibly.</b> Export a portable bundle for another analyst. Bundles omit credentials; each analyst configures their own authorized source access.<br><br>"
            "<b>Troubleshooting.</b> A preview with invalid rows needs a corrected mapping or an explicit partial-import choice. A missing map marker means coordinates are absent, invalid, or too imprecise to plot. Check project history to distinguish a successful zero-result run from source failure. Due monitors need the opt-in desktop setting or an operating-system schedule. Bundle imports require a new or empty destination. A missing conversation parent was not collected; it is not inferred."
        )
        help_text.setWordWrap(True)
        help_card.layout.addWidget(help_text)
        layout.addWidget(help_card, 1)
        self.tabs.addTab(page, "Conversations & help")

    def _hub(self, action: str, **values: Any) -> None:
        if not self.workspace and action not in {"project-list", "project-import"}:
            QMessageBox.warning(self, "Choose a project", "Create or open a SUGAR project first.")
            return
        config = {"action": action, **values}
        config.setdefault("actor", self.analyst_name.text().strip() or "analyst")
        if self.workspace and action not in {"project-list", "project-import"}:
            config["workspace"] = self.workspace
        self.run_operation("workspace-hub", config, False)

    def _open_or_create_project(self) -> None:
        path = self.workspace_field.text()
        if not path:
            QMessageBox.warning(self, "Choose a project", "Choose a project folder first.")
            return
        if not (Path(path).expanduser() / "sugar-project.json").is_file():
            self.run_operation("workspace-init", {"workspace": path, "name": self.project_name.text().strip() or "SUGAR Research Project", "exist_ok": False}, False)
        else:
            self._set_active_workspace(path)
            self._hub("dashboard")

    def _set_active_workspace(self, path: str) -> None:
        self.workspace = str(Path(path).expanduser().resolve())
        self.workspace_field.setText(self.workspace)
        self.activate_workspace_callback(self.workspace)
        if not self.projects_root.text():
            self.projects_root.setText(str(Path(self.workspace).parent))
        self._hub("dashboard")
        self.load_history()

    def refresh_projects(self) -> None:
        root = self.projects_root.text()
        if not root:
            QMessageBox.warning(self, "Choose a folder", "Choose a folder to search for project workspaces.")
            return
        self._hub("project-list", projects_root=root)

    def use_selected_project(self) -> None:
        row = self.projects_table.currentRow()
        if row < 0 or row >= len(self.project_rows):
            QMessageBox.information(self, "Select a project", "Select a project row first.")
            return
        self._set_active_workspace(str(self.project_rows[row].get("root") or ""))

    def load_history(self) -> None:
        if self.workspace:
            self._hub("project-history", limit=500)

    def create_subproject(self) -> None:
        text, ok = self._text_prompt("Create a subproject", "Research track name")
        if ok and text.strip():
            self._hub("project-create-subproject", name=text.strip(), description="Research subproject")

    def export_project(self) -> None:
        output = self.bundle_output.text()
        self._hub("project-export", output_file=output or "")

    def import_project(self) -> None:
        bundle = self.bundle_input.text()
        destination = self.import_destination.text().strip()
        if not bundle or not destination:
            QMessageBox.warning(self, "Import project", "Choose a bundle and a new destination folder.")
            return
        config = {"action": "project-import", "bundle": bundle, "destination": destination}
        if self.link_imported_child.isChecked() and self.workspace:
            config["parent_workspace"] = self.workspace
        if Path(destination).exists() and any(Path(destination).iterdir()):
            QMessageBox.warning(self, "Destination not empty", "Choose a new or empty destination folder.")
            return
        if self.link_imported_child.isChecked() and self.workspace:
            try:
                Path(destination).expanduser().resolve().relative_to(Path(self.workspace).expanduser().resolve())
            except ValueError:
                QMessageBox.warning(self, "Choose a child folder", "To link this project, choose an import destination inside the active project folder.")
                return
        self.run_operation("workspace-hub", config, False)

    def _text_prompt(self, title: str, label: str) -> tuple[str, bool]:
        from PySide6.QtWidgets import QInputDialog
        return QInputDialog.getText(self, title, label)

    def _show_history_detail(self) -> None:
        row = self.project_history_table.currentRow()
        if 0 <= row < len(self.history_rows):
            self.history_detail.setPlainText(json.dumps(self.history_rows[row], ensure_ascii=False, indent=2, sort_keys=True))

    def rerun_selected_search(self) -> None:
        row = self.project_history_table.currentRow()
        if row < 0 or row >= len(self.history_rows):
            return
        entry = self.history_rows[row].get("details", {})
        command = str(entry.get("command") or "")
        if command not in {"search", "research-collect"}:
            QMessageBox.information(self, "Rerun unavailable", "Only saved Search and Research Plan collection runs can be rerun from history.")
            return
        config = entry.get("parameters") or {}
        if not isinstance(config, dict):
            return
        config = dict(config)
        config["workspace"] = self.workspace
        config.pop("source_coverage", None)
        config.pop("effective_sources", None)
        config.pop("effective_terms", None)
        config["output_directory"] = str(Path(self.workspace) / "data" / "raw" / "reruns" / uuid.uuid4().hex)
        self.run_operation(command, config, False)

    def load_registry(self) -> None:
        self._hub("registry-list", filters={
            "query": self.registry_filter.text().strip(),
            "network": self.registry_network_filter.text().strip(),
            "status": str(self.registry_status_filter.currentData() or ""),
        })

    def _set_import_file(self, paths: list[str]) -> None:
        if paths:
            self.registry_file.setText(paths[0])
            self.preview_registry_import()

    def _set_data_file(self, paths: list[str]) -> None:
        if paths:
            self.data_file.setText(paths[0])
            self.load_data_table()

    def _data_query_config(self) -> dict[str, Any]:
        return {"source_file": self.data_file.text(),
                "filter_column": str(self.data_filter_column.currentData() or ""),
                "filter_value": self.data_filter_value.text().strip(), "max_rows": 1000}

    def load_data_table(self) -> None:
        if not self.data_file.text():
            QMessageBox.warning(self, "Choose a dataset", "Choose or drop a structured dataset first.")
            return
        self._hub("dataset-browse", **self._data_query_config())

    def export_data_table(self) -> None:
        if not self.data_file.text():
            return
        target = self.data_export_path.text()
        if not target:
            QMessageBox.warning(self, "Choose an export path", "Choose a CSV, XLSX, JSONL, JSON, or GeoJSON output file.")
            return
        self._hub("dataset-export", **self._data_query_config(), output_file=target)

    def preview_registry_import(self) -> None:
        path = self.registry_file.text()
        if not path:
            QMessageBox.warning(self, "Choose a dataset", "Choose or drop a reference dataset first.")
            return
        self.preview = {}
        self._hub("registry-preview", source_file=path, sample_size=12)

    def create_registry_template(self) -> None:
        self._hub("registry-template", template=self.registry_template.currentData())

    def import_registry_dataset(self) -> None:
        if not self.preview:
            QMessageBox.information(self, "Preview first", "Load and review the dataset preview before importing.")
            return
        try:
            mapping = json.loads(self.registry_mapping.toPlainText() or "{}")
            if not isinstance(mapping, dict):
                raise ValueError("Field mapping must be a JSON object.")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid field mapping", str(exc))
            return
        invalid = int(self.preview.get("error_count", 0))
        if invalid and not self.registry_partial.isChecked():
            QMessageBox.warning(self, "Invalid rows", f"Preview found {invalid} invalid rows. Review and correct the mapping, or explicitly choose to import only valid rows.")
            return
        if QMessageBox.question(self, "Confirm reference import",
            f"Import {self.preview.get('valid_rows', 0)} valid rows from {Path(self.registry_file.text()).name}?\n\nNetwork: {self.registry_network.text() or '(unspecified)'}\nScope: {self.registry_scope.text() or '(unspecified)'}\nInvalid rows: {invalid}\n\nThe original dataset and its source scope will be retained in this project.") != QMessageBox.Yes:
            return
        self._hub("registry-import", source_file=self.registry_file.text(), mapping=mapping,
                  dataset_name=self.registry_dataset_name.text().strip(), network=self.registry_network.text().strip(),
                  geographic_scope=self.registry_scope.text().strip(), known_coverage_limits=self.registry_limits.text().strip(),
                  license_notes=self.registry_license.text().strip(), accept_partial=self.registry_partial.isChecked())

    def export_registry(self) -> None:
        self._hub("registry-export", output_file=str(Path(self.workspace) / "exports" / "entity_registry.csv") if self.workspace else "")

    def _profile_selected(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.entity_rows):
            self._hub("registry-profile", entity_id=self.entity_rows[row].get("entity_id", ""))

    def compare_selected_entities(self) -> None:
        rows = sorted({index.row() for index in self.registry_table.selectionModel().selectedRows()})
        if len(rows) != 2:
            QMessageBox.information(self, "Select two entities", "Select exactly two registry rows to compare the documented dimensions.")
            return
        self._hub("registry-compare", left_entity_id=self.entity_rows[rows[0]].get("entity_id", ""),
                  right_entity_id=self.entity_rows[rows[1]].get("entity_id", ""),
                  coverage_documented=self.registry_coverage_documented.isChecked())

    def prepare_monitor_for_entity(self) -> None:
        rows = sorted({index.row() for index in self.registry_table.selectionModel().selectedRows()})
        if len(rows) != 1:
            QMessageBox.information(self, "Select one entity", "Select one registry row to prepare a listening post.")
            return
        entity = self.entity_rows[rows[0]]
        names = [entity.get("name", ""), *(entity.get("aliases") or [])]
        self.monitor_name.setText(f"Monitor: {entity.get('name', 'institution')}")
        self.monitor_targets.setText("; ".join(value for value in names if value))
        self.monitor_terms.setText("; ".join(value for value in names if value))
        self.tabs.setCurrentIndex(4)
        self.monitor_result.setPlainText(f"Prepared a listening post for {entity.get('name')}. Review terms and sources, then save it.")

    def upsert_entity(self) -> None:
        values: dict[str, Any] = {}
        for field, editor in self.entity_fields.items():
            value = editor.text().strip()
            if value:
                if field in {"aliases", "public_links", "accounts", "host_entities", "partner_entities", "program_domains", "audiences", "delivery_modes"}:
                    values[field] = _split(value)
                else:
                    values[field] = value
        if self.entity_description.text().strip():
            values["description"] = self.entity_description.text().strip()
        evidence_url = self.entity_evidence.text().strip()
        if not values.get("name") or not evidence_url:
            QMessageBox.warning(self, "Required evidence", "Enter an entity name and a public HTTP(S) evidence URL.")
            return
        self._hub("registry-upsert", entity=values, evidence_refs=[{"source_url": evidence_url}],
                  reason=self.entity_reason.text().strip(), review_state=self.entity_review_state.currentData())

    def add_relationship(self) -> None:
        source = self.relation_source.currentData()
        target = self.relation_target.currentData()
        evidence = self.relation_evidence.text().strip()
        if not source or not target or not evidence:
            QMessageBox.warning(self, "Relationship evidence", "Choose two entities and provide a source URL for the relationship.")
            return
        self._hub("registry-relationship", source_entity_id=source, target_entity_id=target,
                  relationship_type=self.relation_type.currentData(), evidence_refs=[{"source_url": evidence}])

    def _append_map_layers(self, paths: list[str]) -> None:
        current = _split(self.map_layers.toPlainText())
        for path in paths:
            if path not in current:
                current.append(path)
        self.map_layers.setPlainText("\n".join(current))

    def build_map(self) -> None:
        base = self.map_base_file.text()
        self._hub("registry-map", source_file=base, reference_files=_split(self.map_layers.toPlainText()),
                  as_of_date=self.map_as_of.text().strip(), output_file=self.map_output.text())

    def save_monitor(self) -> None:
        if not self.monitor_name.text().strip():
            QMessageBox.warning(self, "Listening post name", "Enter a name for this monitoring definition.")
            return
        self._hub("monitor-save", name=self.monitor_name.text().strip(), terms=_split(self.monitor_terms.text()),
                  target_entities=_split(self.monitor_targets.text()), sources=_split(self.monitor_sources.text()),
                  geographies=_split(self.monitor_geographies.text()), cadence_minutes=self.monitor_cadence.value())

    def load_monitors(self) -> None:
        self._hub("monitor-list")

    def _selected_monitor(self) -> dict[str, Any] | None:
        row = self.monitor_table.currentRow()
        return self.monitor_rows[row] if 0 <= row < len(self.monitor_rows) else None

    def _selected_monitor_changed(self) -> None:
        monitor = self._selected_monitor()
        if monitor:
            self._hub("monitor-feed", monitor_id=monitor.get("monitor_id", ""))

    def run_selected_monitor(self) -> None:
        monitor = self._selected_monitor()
        if not monitor:
            QMessageBox.information(self, "Select a monitor", "Select a listening post first.")
            return
        self._hub("monitor-run", monitor_id=monitor.get("monitor_id", ""))

    def run_due_monitors(self) -> None:
        self._hub("monitor-run-due", max_monitors=25)

    def toggle_selected_monitor(self) -> None:
        monitor = self._selected_monitor()
        if not monitor:
            return
        status = "paused" if monitor.get("status") == "active" else "active"
        self._hub("monitor-status", monitor_id=monitor.get("monitor_id", ""), status=status,
                  reason="Changed in Research Workspace")

    def load_monitor_feed(self) -> None:
        monitor = self._selected_monitor() or {}
        self._hub("monitor-feed", monitor_id=monitor.get("monitor_id", ""))

    def review_selected_material(self, state: str) -> None:
        row = self.material_table.currentRow()
        if row < 0 or row >= len(self.material_rows):
            QMessageBox.information(self, "Select evidence", "Select an incoming evidence row first.")
            return
        self._hub("monitor-review", material_id=self.material_rows[row].get("material_id", ""),
                  review_state=state, note=self.material_note.text().strip())

    def _open_material_source(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.material_rows):
            item = self.material_rows[row]
            self.monitor_result.setPlainText(json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True))

    def build_conversation(self) -> None:
        self._hub("conversation-view", source_file=self.conversation_file.text(), conversation_id=self.conversation_id.text().strip())

    def handle_backend_event(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        if event == "workspace_status":
            path = str(payload.get("root") or "")
            if path:
                self.workspace = path
                self.workspace_field.setText(path)
                self.activate_workspace_callback(path)
                self._hub("dashboard")
                self.load_history()
            return
        if event != "workspace_hub_data":
            return
        action = str(payload.get("action") or "")
        data = payload.get("data")
        if action == "project-list":
            self.project_rows = data if isinstance(data, list) else []
            self.projects_table.setRowCount(len(self.project_rows))
            for row_index, project in enumerate(self.project_rows):
                values = [project.get("name"), project.get("last_activity"), project.get("artifact_count"),
                          project.get("pending_review"), project.get("child_count"), project.get("root")]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(str(value or ""))
                    if column == 0:
                        cell.setData(Qt.UserRole, project.get("root"))
                    self.projects_table.setItem(row_index, column, cell)
        elif action == "dashboard" and isinstance(data, dict):
            self.project_summary.setText(
                f"{data.get('name')} · {data.get('project_id')} · {data.get('artifact_count')} artifacts · "
                f"{data.get('pending_review')} items pending review · {data.get('child_count')} subprojects · "
                f"Last activity {data.get('last_activity', 'unknown')}"
            )
            self._hub("project-history", limit=500)
        elif action == "project-history":
            self.history_rows = data if isinstance(data, list) else []
            self.project_history_table.setRowCount(len(self.history_rows))
            for row_index, item in enumerate(self.history_rows):
                details = item.get("details", {})
                summary = details.get("parameters", {}).get("terms") or details.get("name") or details.get("reason") or ""
                values = [item.get("occurred_at"), item.get("event_type"), details.get("command", details.get("action", "")), details.get("status", ""), summary]
                for column, value in enumerate(values):
                    self.project_history_table.setItem(row_index, column, QTableWidgetItem(str(value or "")))
        elif action == "registry-preview" and isinstance(data, dict):
            self.preview = data
            self.registry_mapping.setPlainText(json.dumps(data.get("suggested_mapping", {}), ensure_ascii=False, indent=2))
            self.registry_preview_label.setText(
                f"{Path(str(data.get('path') or '')).name}: {data.get('row_count')} rows · "
                f"{data.get('valid_rows')} valid · {data.get('error_count')} invalid · "
                f"Columns: {', '.join(data.get('columns') or [])}\nSample: " + json.dumps(data.get("sample", [])[:3], ensure_ascii=False)
            )
            if not self.registry_dataset_name.text():
                self.registry_dataset_name.setText(Path(str(data.get("path") or "dataset")).stem)
        elif action == "registry-template" and isinstance(data, dict):
            self.registry_file.setText(str(data.get("path") or ""))
            self.registry_dataset_name.setText(str(data.get("label") or ""))
            if data.get("network"):
                self.registry_network.setText(str(data["network"]))
            self.registry_preview_label.setText("Created blank schema. Add source-backed rows, record scope and permitted use, then preview before importing.")
        elif action == "dataset-browse" and isinstance(data, dict):
            columns = [str(value) for value in data.get("columns", [])]
            selected = str(data.get("filter_column") or "")
            self.data_filter_column.blockSignals(True)
            self.data_filter_column.clear()
            self.data_filter_column.addItem("All columns", "")
            for column in columns:
                self.data_filter_column.addItem(column, column)
            index = self.data_filter_column.findData(selected)
            if index >= 0:
                self.data_filter_column.setCurrentIndex(index)
            self.data_filter_column.blockSignals(False)
            rows = data.get("rows", [])
            self.data_table.setColumnCount(len(columns))
            self.data_table.setHorizontalHeaderLabels(columns)
            self.data_table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                for column_index, column in enumerate(columns):
                    value = row.get(column, "") if isinstance(row, dict) else ""
                    self.data_table.setItem(row_index, column_index, QTableWidgetItem(str(value if value is not None else "")))
            self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            self.data_summary.setText(f"{Path(str(data.get('source_file') or '')).name} · {data.get('matching_rows')} matching of {data.get('row_count')} records · showing {data.get('rows_shown')}")
        elif action == "dataset-export":
            self.data_summary.setText(f"Exported {data.get('matching_rows')} rows to {data.get('output_file')}")
        elif action == "registry-list" and isinstance(data, dict):
            self.entity_rows = data.get("entities", [])
            self.registry_table.setRowCount(len(self.entity_rows))
            self.relation_source.clear()
            self.relation_target.clear()
            for row_index, entity in enumerate(self.entity_rows):
                location = ", ".join(part for part in (entity.get("city", ""), entity.get("country", "")) if part)
                programs = "; ".join(entity.get("program_descriptions") or entity.get("program_domains") or [])
                domains = "; ".join(entity.get("normalized_program_domains") or [])
                audiences = "; ".join(entity.get("audience_descriptions") or entity.get("audiences") or [])
                normalized_audiences = "; ".join(entity.get("normalized_audiences") or [])
                delivery_modes = "; ".join(entity.get("normalized_delivery_modes") or entity.get("delivery_modes") or [])
                values = [entity.get("name"), entity.get("entity_type"), entity.get("network"), entity.get("status"),
                          location, programs, domains, audiences, normalized_audiences, delivery_modes,
                          entity.get("resolved_fields", {}).get("name", {}).get("state", "unknown"), entity.get("entity_id")]
                for column, value in enumerate(values):
                    self.registry_table.setItem(row_index, column, QTableWidgetItem(str(value or "")))
                self.relation_source.addItem(str(entity.get("name") or entity.get("entity_id")), entity.get("entity_id"))
                self.relation_target.addItem(str(entity.get("name") or entity.get("entity_id")), entity.get("entity_id"))
        elif action in {"registry-profile", "registry-compare"}:
            self.registry_profile.setPlainText(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        elif action == "registry-import":
            self.registry_preview_label.setText(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
            self.preview = {}
            self.load_registry()
        elif action in {"registry-upsert", "registry-relationship"}:
            self.load_registry()
            self.registry_profile.setPlainText(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
        elif action == "project-create-subproject":
            self.project_summary.setText(f"Created subproject {data.get('name')} at {data.get('root')}")
            self.refresh_projects()
        elif action == "project-export":
            self.project_summary.setText(f"Portable bundle created: {data.get('bundle')} · {data.get('file_count')} files · SHA-256 {data.get('sha256')}")
        elif action == "project-import":
            destination = str(data.get("destination") or "")
            self.project_summary.setText(f"Imported {data.get('name')} with {data.get('file_count')} verified files.")
            if destination:
                self.workspace = destination
                self.workspace_field.setText(destination)
                self.activate_workspace_callback(destination)
                self.projects_root.setText(str(Path(destination).parent))
                self._hub("dashboard")
                self.load_history()
        elif action == "monitor-list":
            self.monitor_rows = data if isinstance(data, list) else []
            self.monitor_table.setRowCount(len(self.monitor_rows))
            for row_index, monitor in enumerate(self.monitor_rows):
                values = [monitor.get("name"), monitor.get("status"), f"{monitor.get('cadence_minutes')} min",
                          monitor.get("next_due_at"), monitor.get("last_run_at"), monitor.get("last_run_status"), monitor.get("monitor_id")]
                for column, value in enumerate(values):
                    self.monitor_table.setItem(row_index, column, QTableWidgetItem(str(value or "")))
        elif action in {"monitor-save", "monitor-status"}:
            self.load_monitors()
        elif action == "monitor-feed" and isinstance(data, dict):
            self.material_rows = data.get("material", [])
            self.material_table.setRowCount(len(self.material_rows))
            for row_index, item in enumerate(self.material_rows):
                values = [item.get("monitor_name"), item.get("change_state"), item.get("actor_handle"), item.get("platform"),
                          item.get("published_at"), item.get("review_state"), item.get("canonical_url"), item.get("material_id")]
                for column, value in enumerate(values):
                    self.material_table.setItem(row_index, column, QTableWidgetItem(str(value or "")))
            self.monitor_result.setPlainText(f"Incoming items: {data.get('count')} · unreviewed across project: {data.get('unreviewed_count')}")
        elif action == "monitor-review":
            self.load_monitor_feed()
        elif action in {"monitor-run", "monitor-run-due"}:
            self.monitor_result.setPlainText(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
            self.load_monitors()
            self.load_monitor_feed()
        elif action == "conversation-view" and isinstance(data, dict):
            self.conversation_result.setPlainText(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
