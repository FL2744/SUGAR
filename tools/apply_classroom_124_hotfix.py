from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch target: {label}")
    return text.replace(old, new, 1)


app_path = Path("SUGAR-Windows/app.py")
app = app_path.read_text(encoding="utf-8")

app = replace_once(
    app,
    'sources = Card("Optional source credentials", "For the core classroom Bilibili/Weibo workflow, leave this section blank unless a specific task requires an authenticated source. X, Bluesky, Mastodon, and an authorized Weibo session are optional extensions; SUGAR never manufactures accounts or bypasses access controls.")',
    'sources = Card("Optional source credentials", "Bilibili Quick Search uses ordinary anonymous public access when Bilibili currently permits it. Weibo keyword search requires an existing authorized session. X requires its API token; Bluesky and Mastodon credentials are optional for their public modes. SUGAR never manufactures accounts or bypasses access controls.")',
    "credential guidance",
)
app = replace_once(
    app,
    'source_grid.addWidget(LabeledRow("Weibo session", self.weibo_cookie, "Optional. Anonymous public surfaces remain the default when this is blank."), 2, 0, 1, 2)',
    'source_grid.addWidget(LabeledRow("Weibo session", self.weibo_cookie, "Required for Weibo keyword search. Use only a session you are authorized to use."), 2, 0, 1, 2)',
    "weibo credential hint",
)
app = replace_once(
    app,
    'saved_model = str(self.store.value("llm/model", "gpt-oss-120b"))\n        idx = self.model.findText(saved_model)\n        if idx >= 0:\n            self.model.setCurrentIndex(idx)\n        else:\n            self.model.setEditText(saved_model)',
    'saved_model = str(self.store.value("llm/model", "gpt-oss-120b"))\n        if provider == "arc":\n            saved_model = {\n                "DeepSeek-V4-Flash": "DeepSeek-V4.1-Flash",\n                "GLM-5.2": "GLM-5.3",\n            }.get(saved_model, saved_model)\n        idx = self.model.findText(saved_model)\n        if idx >= 0:\n            self.model.setCurrentIndex(idx)\n        elif provider == "arc":\n            self.model.setCurrentIndex(0)\n        else:\n            self.model.setEditText(saved_model)',
    "ARC saved-model migration",
)
app = replace_once(
    app,
    'models = ["gpt-oss-120b", "DeepSeek-V4.1-Flash", "GLM-5.3", "Kimi-K3"]',
    'models = [\n                "gpt-oss-120b",\n                "gpt-oss-120b-thinking-low",\n                "gpt-oss-120b-thinking-high",\n                "DeepSeek-V4.1-Flash",\n                "DeepSeek-V4.1-Flash-thinking-low",\n                "DeepSeek-V4.1-Flash-thinking-max",\n                "GLM-5.3",\n                "GLM-5.3-thinking-high",\n                "Kimi-K3",\n                "Kimi-K3-thinking-low",\n                "Kimi-K3-thinking-high",\n            ]',
    "ARC models",
)
app = replace_once(
    app,
    '"Recommended classroom path: connect Virginia Tech ARC once, collect a small public-source sample, inspect the outputs, then move into the advanced workflow pages only when you need them."',
    '"Recommended classroom path: first prove a small collection works, then enable ARC-powered enrichment. Keep the first Bilibili run small because live public access can be rate- or risk-controlled by the platform."',
    "home start description",
)
app = replace_once(
    app,
    '"1. Settings → Virginia Tech ARC → Get ARC API Key → paste the key → Test ARC Connection.\\n"\n            "2. Collect → Quick Search → use Bilibili and/or Weibo → enter a few search terms → Run Search.\\n"\n            "3. Open the generated files from Activity & Outputs. Basic public Bilibili/Weibo collection does not require source credentials."',
    '"1. Collect → Quick Search → leave Bilibili selected → enter one term → keep the 20-post / 1-page defaults → Run Search.\\n"\n            "2. Inspect the generated files from Activity & Outputs. If Bilibili denies anonymous access, stop rather than repeatedly retrying.\\n"\n            "3. For translation or location inference, open Settings → Virginia Tech ARC → Get ARC API Key → paste the key → Test ARC Connection. Weibo keyword search requires an authorized Weibo session."',
    "home steps",
)
app = replace_once(app, 'setup_arc = primary_button("1. Set up Virginia Tech ARC"', 'setup_arc = primary_button("3. Set up Virginia Tech ARC"', "ARC button label")
app = replace_once(app, 'collect_public = QPushButton("2. Start public collection")', 'collect_public = QPushButton("1. Start small Bilibili search")', "collection button label")
app = replace_once(app, 'self.search_sources.boxes["bilibili"].setChecked(True)\n        self.search_sources.boxes["weibo"].setChecked(True)', 'self.search_sources.boxes["bilibili"].setChecked(True)', "source defaults")
app = replace_once(app, 'self.post_languages = QLineEdit("en")', 'self.post_languages = QLineEdit()', "post language default")
app = replace_once(app, 'self.max_posts = NumberField(1, 5000, 100)\n        self.max_pages = NumberField(1, 500, 5)', 'self.max_posts = NumberField(1, 5000, 20)\n        self.max_pages = NumberField(1, 500, 1)', "safe quick-search limits")
app = replace_once(app, 'self.translate_posts.setChecked(True)', 'self.translate_posts.setChecked(False)', "translation default")
app = replace_once(app, 'self.infer_locations.setChecked(True)', 'self.infer_locations.setChecked(False)', "location default")
app = replace_once(
    app,
    'form.addWidget(LabeledRow("Sources", self.search_sources), 0, 0, 1, 2)',
    'form.addWidget(LabeledRow("Sources", self.search_sources, "Bilibili: anonymous public access when available. Weibo: authorized session required for keyword search."), 0, 0, 1, 2)',
    "source hint",
)
app = replace_once(
    app,
    '"target_language": "English",\n            "output_directory": self.search_output.text() or self.settings.default_output(),',
    '"target_language": "English",\n            "bilibili_hydrate_details": False,\n            "output_directory": self.search_output.text() or self.settings.default_output(),',
    "quick Bilibili hydration",
)
app = replace_once(
    app,
    '"<b>1.</b> Open <b>Settings</b>, choose <b>Virginia Tech ARC</b>, click <b>Get ARC API Key</b>, paste the key, and test the connection.<br><br>"\n            "<b>2.</b> Open <b>Collect → Quick Search</b>. Bilibili and Weibo are selected by default; enter a few terms and run a small search.<br><br>"\n            "<b>3.</b> Inspect the generated files under <b>Activity & Outputs</b>. The State Workflow, Intelligence, and reporting pages are advanced follow-on tools.<br><br>"\n            "<b>Source credentials are optional:</b> basic public Bilibili/Weibo collection does not require X, Bluesky, Mastodon, or Weibo credentials."',
    '"<b>1.</b> Open <b>Collect → Quick Search</b>. Leave <b>Bilibili</b> selected, use one search term, and keep the small 20-post / 1-page defaults.<br><br>"\n            "<b>2.</b> Inspect the generated files under <b>Activity & Outputs</b>. If Bilibili denies anonymous access, stop and retry later rather than repeatedly hammering the public endpoint.<br><br>"\n            "<b>3.</b> For translation/location inference, open <b>Settings</b>, choose <b>Virginia Tech ARC</b>, get your personal API key, and test the connection.<br><br>"\n            "<b>Credentials:</b> Weibo keyword search requires an authorized Weibo session. X requires its API token. Bilibili Quick Search uses anonymous public access only when Bilibili permits it."',
    "getting-started dialog",
)
app_path.write_text(app, encoding="utf-8")

bili_path = Path("sugar_core/bilibili.py")
bili = bili_path.read_text(encoding="utf-8")
bili = replace_once(
    bili,
    '                    except BilibiliAccessError:\n                        raise\n                    except (requests.RequestException, RuntimeError, ValueError):\n                        # A single detail failure should not discard a valid public search result.\n                        record = search_record',
    '                    except (BilibiliAccessError, requests.RequestException, RuntimeError, ValueError):\n                        # Detail hydration is optional. Preserve a valid search result even if\n                        # the separate metadata endpoint is unavailable or access-controlled.\n                        record = search_record',
    "Bilibili hydration fallback",
)
bili_path.write_text(bili, encoding="utf-8")

bridge_path = Path("sugar_bridge.py")
bridge = bridge_path.read_text(encoding="utf-8")
bridge = replace_once(
    bridge,
    '        available_model_count=len(model_ids),\n    )',
    '        available_model_count=len(model_ids),\n        available_models=model_ids,\n    )',
    "ARC model discovery payload",
)
bridge_path.write_text(bridge, encoding="utf-8")

guide_path = Path("docs/classroom-quick-start.md")
guide = guide_path.read_text(encoding="utf-8")
guide = guide.replace("Bilibili and Weibo are selected by default", "Bilibili is selected by default")
guide = guide.replace("Bilibili/Weibo", "Bilibili")
guide += "\n\n## Live-source reliability note\n\nFor a first Bilibili run, use one search term, 20 posts per query, and one page. Quick Search disables per-result Bilibili detail hydration so a classroom test does not create a large burst of requests. Bilibili may still deny anonymous search under its current access/risk-control policy; if that happens, stop and retry later rather than repeatedly retrying. Weibo keyword search requires an existing authorized Weibo session.\n"
guide_path.write_text(guide, encoding="utf-8")

test_path = Path("tests/test_windows_classroom_ux.py")
test = test_path.read_text(encoding="utf-8")
# Update the previous defaults assertion from the earlier classroom PR.
test = test.replace('assert \'self.search_sources.boxes["weibo"].setChecked(True)\' in app\n', 'assert \'self.search_sources.boxes["weibo"].setChecked(True)\' not in app\n')
extra = '''\n\ndef test_classroom_quick_search_is_bounded_and_credential_honest() -> None:\n    app = (ROOT / "SUGAR-Windows" / "app.py").read_text(encoding="utf-8")\n    assert "NumberField(1, 5000, 20)" in app\n    assert "NumberField(1, 500, 1)" in app\n    assert '"bilibili_hydrate_details": False' in app\n    assert "Weibo keyword search requires an authorized Weibo session" in app\n    assert '"DeepSeek-V4-Flash": "DeepSeek-V4.1-Flash"' in app\n    assert "DeepSeek-V4.1-Flash-thinking-max" in app\n    assert "gpt-oss-120b-thinking-high" in app\n'''
if "test_classroom_quick_search_is_bounded_and_credential_honest" not in test:
    test = test.rstrip() + extra + "\n"
test_path.write_text(test, encoding="utf-8")

bili_test_path = Path("tests/test_bilibili.py")
bili_test = bili_test_path.read_text(encoding="utf-8")
extra_bili = '''\n\ndef test_detail_access_gate_keeps_valid_search_result() -> None:\n    search = {\n        "code": 0,\n        "data": {\n            "result": [{\n                "bvid": "BV1SAFEFALLBACK",\n                "aid": 123,\n                "title": "Public search result",\n                "description": "Search metadata remains usable",\n                "author": "Example",\n                "mid": 1,\n                "pubdate": 1789056000,\n            }]\n        },\n    }\n    blocked_detail = {"code": -412, "message": "request blocked", "data": None}\n    session = FakeSession([FakeResponse(search), FakeResponse(blocked_detail)])\n    records = collect_bilibili_public(\n        search_terms=["test"],\n        max_posts_per_query=1,\n        max_pages_per_query=1,\n        hydrate_details=True,\n        initialize_session=False,\n        session=session,\n    )\n    assert len(records) == 1\n    assert records[0].native_id == "BV1SAFEFALLBACK"\n    assert records[0].source_mode == "bilibili_public_search"\n'''
if "test_detail_access_gate_keeps_valid_search_result" not in bili_test:
    bili_test = bili_test.rstrip() + extra_bili + "\n"
bili_test_path.write_text(bili_test, encoding="utf-8")

arc_test_path = Path("tests/test_arc_classroom_ux.py")
arc_test = arc_test_path.read_text(encoding="utf-8")
extra_arc = '''\n\ndef test_arc_check_emits_live_model_catalog() -> None:\n    bridge = Path("sugar_bridge.py").read_text(encoding="utf-8")\n    assert "available_models=model_ids" in bridge\n'''
if "test_arc_check_emits_live_model_catalog" not in arc_test:
    arc_test = arc_test.rstrip() + extra_arc + "\n"
arc_test_path.write_text(arc_test, encoding="utf-8")

print("Applied v1.2.4 classroom hotfix source changes.")
