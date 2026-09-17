from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once("pyproject.toml", 'version = "1.2.0"', 'version = "1.2.1"')
    replace_once("sugar_core/__init__.py", '__version__ = "1.2.0"', '__version__ = "1.2.1"')
    replace_once("README.md", "Current package version: **1.2.0**.", "Current package version: **1.2.1**.")

    # Public OPSEC should block mission targeting, not legitimate language names.
    replace_once("tests/test_public_opsec.py", '        "Chi" + "nese",\n', "")

    # Shared desktop bridge: add a lightweight provider/model availability check.
    replace_once(
        "sugar_bridge.py",
        "from sugar_core.desktop_ops import DESKTOP_ANALYTIC_OPERATIONS, run_desktop_analytic_operation\n",
        "from sugar_core.desktop_ops import DESKTOP_ANALYTIC_OPERATIONS, run_desktop_analytic_operation\n"
        "from sugar_core.llm import ARC_BASE_URL, LLMConfig, create_client\n",
    )
    replace_once(
        "sugar_bridge.py",
        '    "diagnostics",\n} | WORKSPACE_OPERATIONS',
        '    "diagnostics",\n    "llm-check",\n} | WORKSPACE_OPERATIONS',
    )
    replace_once(
        "sugar_bridge.py",
        "def _workspace_path(config: dict[str, Any]) -> str:\n",
        '''def _run_llm_check(config: dict[str, Any], secrets: dict[str, str]) -> list[str]:
    raw = config.get("llm") or {}
    if not isinstance(raw, dict):
        raise ValueError("llm configuration must be an object.")
    provider = str(raw.get("provider") or "arc").strip()
    model = str(raw.get("model") or "gpt-oss-120b").strip()
    base_url = str(raw.get("base_url") or "").strip()
    llm_config = LLMConfig(
        provider=provider,
        model=model,
        api_key=secrets.get("llm_api_key", ""),
        base_url=base_url,
    )
    client = create_client(llm_config)
    response = client.models.list()
    model_ids = sorted(
        str(getattr(item, "id", "")).strip()
        for item in getattr(response, "data", [])
        if str(getattr(item, "id", "")).strip()
    )
    endpoint = base_url or (ARC_BASE_URL if provider == "arc" else "provider default")
    emit(
        "llm_connection",
        provider=provider,
        endpoint=endpoint,
        model=model,
        selected_model_available=(not model_ids or model in model_ids),
        available_model_count=len(model_ids),
    )
    return []


def _workspace_path(config: dict[str, Any]) -> str:
''',
    )
    replace_once(
        "sugar_bridge.py",
        '''        if args.command in WORKSPACE_OPERATIONS:
            outputs = _run_workspace_operation(args.command, config)
        elif args.command == "search":
''',
        '''        if args.command == "llm-check":
            outputs = _run_llm_check(config, secrets)
        elif args.command in WORKSPACE_OPERATIONS:
            outputs = _run_workspace_operation(args.command, config)
        elif args.command == "search":
''',
    )

    # Windows: current ARC models and visible classroom setup/test flow.
    replace_once(
        "SUGAR-Windows/app.py",
        "class SettingsPage(QWidget):\n    diagnostics_requested = Signal()\n",
        "class SettingsPage(QWidget):\n    diagnostics_requested = Signal()\n    arc_test_requested = Signal()\n",
    )
    replace_once(
        "SUGAR-Windows/app.py",
        '            models = ["gpt-oss-120b", "DeepSeek-V4-Flash", "GLM-5.2", "Kimi-K3"]',
        '            models = ["gpt-oss-120b", "DeepSeek-V4.1-Flash", "GLM-5.3", "Kimi-K3"]',
    )
    replace_once(
        "SUGAR-Windows/app.py",
        '''        llm.layout.addLayout(grid)
        root.addWidget(llm)
''',
        '''        llm.layout.addLayout(grid)
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
''',
    )
    replace_once(
        "SUGAR-Windows/app.py",
        '''        self.runner.event.connect(self._event); self.runner.outputs_changed.connect(self.activity.set_outputs); self.runner.error.connect(self._error); self.runner.running_changed.connect(self.activity.set_running); self.settings_page.diagnostics_requested.connect(self._diagnostics_run)
''',
        '''        self.runner.event.connect(self._event); self.runner.outputs_changed.connect(self.activity.set_outputs); self.runner.error.connect(self._error); self.runner.running_changed.connect(self.activity.set_running); self.settings_page.diagnostics_requested.connect(self._diagnostics_run); self.settings_page.arc_test_requested.connect(self._arc_test_run)
''',
    )
    replace_once(
        "SUGAR-Windows/app.py",
        '''    def _diagnostics_run(self)->None:
        if self.runner.is_running: return
''',
        '''    def _arc_test_run(self)->None:
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
''',
    )
    replace_once(
        "SUGAR-Windows/app.py",
        '''        if event in {"diagnostics","backend"}:
            self._diagnostics=payload; self.home.update_diagnostics(payload)
        self.activity.append_event(payload)
''',
        '''        if event in {"diagnostics","backend"}:
            self._diagnostics=payload; self.home.update_diagnostics(payload)
        if event=="llm_connection":
            available=bool(payload.get("selected_model_available",True)); model=str(payload.get("model") or "ARC model")
            self.settings_page.arc_status.setText("ARC connected" if available else "ARC connected · model unavailable"); self.settings_page.arc_status.set_tone("good" if available else "warn")
            message=f"Connected to Virginia Tech ARC. {model} is available." if available else f"Connected to Virginia Tech ARC, but {model} was not listed by the service. Choose another ARC model."
            QMessageBox.information(self,"ARC connection",message) if available else QMessageBox.warning(self,"ARC connection",message)
        self.activity.append_event(payload)
''',
    )

    # macOS: refresh model catalog and restore legitimate language labels.
    replace_once(
        "SUGAR-macOS/Sources/LLMProvider.swift",
        "// Model catalogs checked against official provider documentation on 2026-09-10.",
        "// Model catalogs checked against official provider documentation on 2026-09-17.",
    )
    replace_once(
        "SUGAR-macOS/Sources/LLMProvider.swift",
        '        case .arc: ["gpt-oss-120b", "DeepSeek-V4-Flash", "GLM-5.3", "Kimi-K3"]',
        '        case .arc: ["gpt-oss-120b", "DeepSeek-V4.1-Flash", "GLM-5.3", "Kimi-K3"]',
    )
    replace_once("SUGAR-macOS/Sources/ContentView.swift", '.init(name: "sponsoring-state", value: "zh"),', '.init(name: "Chinese", value: "zh"),')
    replace_once("SUGAR-macOS/Sources/ContentView.swift", '.init(name: "Simplified sponsoring-state", value: "Simplified sponsoring-state"),', '.init(name: "Simplified Chinese", value: "Simplified Chinese"),')
    replace_once("SUGAR-macOS/Sources/ContentView.swift", '.init(name: "Traditional sponsoring-state", value: "Traditional sponsoring-state"),', '.init(name: "Traditional Chinese", value: "Traditional Chinese"),')
    replace_once(
        "SUGAR-macOS/Sources/ContentView.swift",
        '''            .gridColumnAlignment(.leading)
            .frame(maxWidth: .infinity)

            if !model.legacyLLMKey.isEmpty {
''',
        '''            .gridColumnAlignment(.leading)
            .frame(maxWidth: .infinity)

            GroupBox("Virginia Tech ARC quick setup") {
                VStack(alignment: .leading, spacing: 9) {
                    Text("ARC's shared hosted-model API is available to Virginia Tech students, faculty, and staff without a separate ARC HPC account. Your personal API key stays in SUGAR's Keychain storage.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                    Link("1. Get ARC API Key", destination: URL(string: "https://llm.arc.vt.edu")!)
                    Text("2. In ARC: User profile → Settings → Account → API keys. Create a personal key and paste it into the ARC API key field above.")
                        .font(.callout)
                    Text("3. Test the connection below. Then choose Virginia Tech ARC as the LLM provider in Search; gpt-oss-120b is the default classroom model.")
                        .font(.callout)
                    Button("3. Test ARC Connection") {
                        model.run(command: "llm-check", config: [
                            "llm": LLMProvider.arc.configuration(model: "gpt-oss-120b", customBaseURL: "")
                        ])
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.arcKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isRunning)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(4)
            }

            if !model.legacyLLMKey.isEmpty {
''',
    )

    # macOS runner: send the selected ARC key for the connectivity check and render the result.
    replace_once(
        "SUGAR-macOS/Sources/AppModel.swift",
        '''        guard command != "search" || provider != nil else {
            log = "Choose a valid LLM provider."
            return
        }
''',
        '''        guard !["search", "llm-check"].contains(command) || provider != nil else {
            log = "Choose a valid LLM provider."
            return
        }
''',
    )
    replace_once(
        "SUGAR-macOS/Sources/AppModel.swift",
        '''        if command == "search", needsLLM, selectedKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            log = "Enter the \(provider!.title) API key in Settings before running this search."
            return
        }
        let secrets = BackendSecrets(
            xToken: xToken, llmKey: command == "search" ? selectedKey : "", blueskyIdentifier: blueskyIdentifier,
''',
        '''        if command == "search", needsLLM, selectedKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            log = "Enter the \(provider!.title) API key in Settings before running this search."
            return
        }
        if command == "llm-check", selectedKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            log = "Enter your ARC API key in Settings before testing the ARC connection."
            return
        }
        let usesLLMKey = command == "search" || command == "llm-check"
        let secrets = BackendSecrets(
            xToken: xToken, llmKey: usesLLMKey ? selectedKey : "", blueskyIdentifier: blueskyIdentifier,
''',
    )
    replace_once(
        "SUGAR-macOS/Sources/AppModel.swift",
        '''            case "starting":
''',
        '''            case "llm_connection":
                let provider = json["provider"] as? String ?? "LLM"
                let model = json["model"] as? String ?? "model"
                let available = json["selected_model_available"] as? Bool ?? true
                lines.append(available ? "Connected to \(provider == \"arc\" ? \"Virginia Tech ARC\" : provider) • \(model) available" : "Connected to \(provider) • \(model) not listed")
            case "starting":
''',
    )

    # Repository guidance mirrors the app.
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    marker = "## Research and access boundaries\n"
    if marker not in text:
        raise RuntimeError("README insertion marker not found")
    arc_section = '''## Virginia Tech ARC quick start

SUGAR can use Virginia Tech ARC's shared hosted-model API for translation and AI-assisted analysis while the desktop application itself runs locally. For the shared API, Virginia Tech students, faculty, and staff do not need a separate ARC HPC account.

1. Open **Settings** in SUGAR and choose **Get ARC API Key**, or visit `https://llm.arc.vt.edu`.
2. Sign in with Virginia Tech credentials and open **User profile → Settings → Account → API keys**.
3. Create a personal key and paste it into SUGAR's ARC/API-key field. Never share the key.
4. Choose **Virginia Tech ARC** and use **Test ARC Connection**.
5. Use an ARC model in an AI-assisted workflow. The classroom defaults are `gpt-oss-120b`, `DeepSeek-V4.1-Flash`, `GLM-5.3`, and `Kimi-K3`.

ARC's shared API endpoint is `https://llm-api.arc.vt.edu/api/v1`. Dedicated Open OnDemand LLM sessions are a separate ARC workflow and require an ARC account/allocation.

'''
    readme.write_text(text.replace(marker, arc_section + marker, 1), encoding="utf-8")

    (ROOT / "docs" / "arc-quick-start.md").write_text(
        '''# Virginia Tech ARC quick start

SUGAR can use Virginia Tech ARC as its OpenAI-compatible LLM provider while SUGAR itself runs on the user's computer.

## Classroom setup

1. Open SUGAR **Settings**.
2. Choose **Get ARC API Key** to open `https://llm.arc.vt.edu`.
3. Sign in with Virginia Tech credentials.
4. Open **User profile → Settings → Account → API keys** and create a personal API key.
5. Paste the key into SUGAR's ARC/API-key field. Keep it private.
6. Choose **Virginia Tech ARC** and press **Test ARC Connection**.
7. Select an ARC model for AI-assisted workflows.

As checked against ARC documentation on 2026-09-17, the primary shared model IDs are:

- `gpt-oss-120b`
- `DeepSeek-V4.1-Flash`
- `GLM-5.3`
- `Kimi-K3`

The shared endpoint is `https://llm-api.arc.vt.edu/api/v1`. ARC documents the shared API as available to Virginia Tech students, faculty, and staff without a separate ARC account and with no individual charge for hosted-model API access. Model availability can change, so future releases should re-check ARC's current model documentation.

Dedicated Open OnDemand LLM sessions at `https://ood.arc.vt.edu` are different: they require an ARC account/allocation and consume service units.
''',
        encoding="utf-8",
    )

    (ROOT / "tests" / "test_arc_classroom_ux.py").write_text(
        '''from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_ARC_MODELS = ("gpt-oss-120b", "DeepSeek-V4.1-Flash", "GLM-5.3", "Kimi-K3")


def test_arc_model_catalogs_are_current():
    windows = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    mac = (ROOT / "SUGAR-macOS" / "Sources" / "LLMProvider.swift").read_text(encoding="utf-8")
    for model in CURRENT_ARC_MODELS:
        assert model in windows
        assert model in mac
    assert "DeepSeek-V4-Flash" not in windows
    assert "DeepSeek-V4-Flash" not in mac
    assert "GLM-5.2" not in windows


def test_arc_onboarding_is_visible_in_both_desktops():
    windows = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    mac = (ROOT / "SUGAR-macOS" / "Sources" / "ContentView.swift").read_text(encoding="utf-8")
    for text in (windows, mac):
        assert "Get ARC API Key" in text
        assert "Test ARC Connection" in text
        assert "llm.arc.vt.edu" in text


def test_mac_language_names_are_not_opsec_redacted():
    mac = (ROOT / "SUGAR-macOS" / "Sources" / "ContentView.swift").read_text(encoding="utf-8")
    assert 'name: "Chinese", value: "zh"' in mac
    assert "Simplified Chinese" in mac
    assert "Traditional Chinese" in mac
    assert "sponsoring-state" not in mac


def test_bridge_exposes_llm_connection_check():
    import sugar_bridge
    assert "llm-check" in sugar_bridge.ALL_OPERATIONS
''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
