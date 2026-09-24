from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_ARC_MODELS = ("gpt-oss-120b", "DeepSeek-V4.1-Flash", "GLM-5.3", "Kimi-K3")


def test_arc_model_catalogs_are_current():
    windows = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")
    mac = (ROOT / "SUGAR-macOS" / "Sources" / "LLMProvider.swift").read_text(encoding="utf-8")
    for model in CURRENT_ARC_MODELS:
        assert model in windows
        assert model in mac
    # Legacy names may appear only in migration dictionaries for saved settings.
    assert '"DeepSeek-V4-Flash",' not in windows
    assert "DeepSeek-V4-Flash" not in mac
    assert '"GLM-5.2",' not in windows


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


def test_mac_search_exposes_chinese_media_and_safe_first_run_defaults():
    mac = (ROOT / "SUGAR-macOS" / "Sources" / "ContentView.swift").read_text(encoding="utf-8")
    model = (ROOT / "SUGAR-macOS" / "Sources" / "AppModel.swift").read_text(encoding="utf-8")
    assert 'Toggle("Bilibili"' in mac
    assert 'Toggle("Weibo"' in mac
    assert '@State private var useBilibili = true' in mac
    assert '@State private var useWeibo = false' in mac
    assert '@State private var maxPosts = 20' in mac
    assert '@State private var maxPages = 1' in mac
    assert '@State private var translate = false' in mac
    assert '@State private var infer = false' in mac
    assert '"bilibili_hydrate_details": false' in mac
    assert 'environment["SUGAR_WEIBO_COOKIE"] = secrets.weiboCookie' in model
    assert "authorized Weibo session" in model


def test_mac_exposes_public_item_ingestion_without_wechat_search_toggle():
    mac = (ROOT / "SUGAR-macOS" / "Sources" / "ContentView.swift").read_text(encoding="utf-8")
    assert 'case ingest = "Public URL"' in mac
    assert 'struct PublicItemView: View' in mac
    assert 'PublicItemSource(label: "WeChat Official Account article", value: "wechat")' in mac
    assert 'model.run(command: "ingest"' in mac
    assert "mp.weixin.qq.com" in mac
    assert 'Toggle("WeChat"' not in mac


def test_mac_defaults_to_question_first_research_project_workflow():
    mac = (ROOT / "SUGAR-macOS" / "Sources" / "ContentView.swift").read_text(encoding="utf-8")
    model = (ROOT / "SUGAR-macOS" / "Sources" / "AppModel.swift").read_text(encoding="utf-8")
    assert 'case research = "Research Project"' in mac
    assert '@State private var selection: AppSection? = .research' in mac
    assert 'struct ResearchProjectView: View' in mac
    assert 'Section("1. Project workspace")' in mac
    assert 'Section("2. Research question")' in mac
    assert 'Section("2b. Interpret and approve the research strategy")' in mac
    assert 'Section("2c. Review search branches")' in mac
    assert 'Section("3. Gather and review evidence")' in mac
    assert 'Section("4. Human review and verified handoff")' in mac
    assert '"target_audiences": commaList(targetAudiences)' in mac
    for operation in (
        "workspace-init",
        "research-requirement",
        "research-compile",
        "research-strategy-review",
        "research-strategy-update",
        "research-plan",
        "research-plan-review",
        "research-plan-update",
        "research-import",
        "research-collect",
        "research-triage",
        "research-feedback",
        "research-handoff",
        "research-handoff-verify",
        "state-triage",
        "state-review-export",
        "state-review-apply",
    ):
        assert f'command: "{operation}"' in mac
    assert 'command == "research-triage"' in model
    assert 'command == "research-compile"' in model
    assert 'command == "state-triage"' in model
    assert 'command == "research-collect"' in model
    assert "@Published var researchPlanBranches" in model
    assert "@Published var researchStrategyConcepts" in model
    assert "@Published var researchStrategyTask" in model
    assert "@Published var researchStrategyDimensions" in model
    assert 'Text("Research dimensions")' in mac
    assert 'TextField("Operational question", text: $dimension.question)' in mac
    assert 'TextField("Indicators, comma separated", text: $dimension.indicators)' in mac
    assert '"dimension_updates": dimensionUpdates' in mac
    for label in ("Save Edits", "Approve", "Pause", "Exclude"):
        assert f'Button("{label}")' in mac
    for label in (
        "Compile Deterministically",
        "Compile + AI",
        "Approve Research Strategy",
        "Build Search Plan from Approved Strategy",
    ):
        assert f'Button("{label}")' in mac
    for label in (
        "Prepare State Assessment Suggestions",
        "Export Human Review Workbook",
        "Apply Human Review",
    ):
        assert f'Button("{label}")' in mac


def test_mac_registry_relationships_capture_review_state_and_valid_time():
    mac = (ROOT / "SUGAR-macOS" / "Sources" / "ContentView.swift").read_text(encoding="utf-8")
    for field in (
        "relationshipValidFrom", "relationshipValidTo", "relationshipReviewState", "relationshipNote",
    ):
        assert f"@State private var {field}" in mac
    assert '"valid_from": relationshipValidFrom' in mac
    assert '"valid_to": relationshipValidTo' in mac
    assert '"review_state": relationshipReviewState' in mac
    assert "Build Temporal Evidence Graph" in mac


def test_bridge_exposes_llm_connection_check():
    import sugar_bridge
    assert "llm-check" in sugar_bridge.ALL_OPERATIONS

def test_arc_check_emits_live_model_catalog() -> None:
    bridge = Path("sugar_bridge.py").read_text(encoding="utf-8")
    assert "available_models=model_ids" in bridge
