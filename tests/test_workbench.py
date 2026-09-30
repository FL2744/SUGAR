import json
import threading
import zipfile
from datetime import date

import pytest

from _fake_llm import FakeLLMServer
from sugar_core.collector_registry import CollectorCapabilities, CollectorSpec
from sugar_core.credential_store import CredentialStore
from sugar_core.llm_providers import ProviderProfile, ProviderRegistry
from sugar_core.models import PostRecord
from sugar_core.research_export import verify_export
from sugar_core.research_runs import ResearchProject
from sugar_core.workbench import ResearchWorkbench, RunConflict, WorkbenchError
from sugar_core.workspace import SugarWorkspace

KEY = "sk-test-valid-key-1234567890"
TODAY = date(2026, 9, 30)
ARABIC = "الديمقراطية في المنطقة تحتاج إلى إصلاح حقيقي وشامل"


def rec(platform, native_id, text, **kw):
    return PostRecord(platform=platform, native_id=str(native_id), canonical_url=f"https://{platform}.test/{native_id}", query="q",
                      original_text=text, author_name="someone", published_at=kw.pop("published_at", "2026-03-01T00:00:00Z"), **kw)


def spec(name, fn, secrets=()):
    return CollectorSpec(name=name, search=fn, required_secrets=tuple(secrets),
                         capabilities=CollectorCapabilities(keyword_search=True, anonymous_search=not secrets))


def bench(tmp_path, registry=None, **kw):
    store = CredentialStore(tmp_path / "home", backend="memory")
    providers = ProviderRegistry(tmp_path / "home", store)
    if registry is None:
        def bsky(request):
            term = request.search_terms[0]
            return [rec("bluesky", f"{term}-en", f"Democracy needs strong institutions and free elections, says {term}"),
                    rec("bluesky", f"{term}-ar", f"{ARABIC} {term}", latitude=30.0, longitude=31.2)]

        def masto(request):
            raise RuntimeError("Mastodon rate limit reached (429).")

        registry = {"bluesky": spec("bluesky", bsky), "mastodon": spec("mastodon", masto, secrets=("mastodon_token",))}
    return ResearchWorkbench(providers=providers, store=store, registry=registry, sleeper=lambda s: None, **kw)


def project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Diplomacy Lab project"))


def prepare(wb, proj, text="Search democracy in the Middle East on all platforms.", **plan_overrides):
    out = wb.interpret(text, mode="deterministic", project=proj, today=TODAY)
    payload = out["plan"]
    payload["concurrency"] = {"per_source_delay_seconds": 0, "max_workers": 4}
    payload["retry"] = {"max_attempts": 2, "base_backoff_seconds": 0}
    payload.update(plan_overrides)
    return wb.save_plan(proj, payload, reason="interpreted", request=text)


def test_acceptance_flow_from_plain_sentence_to_inspectable_reproducible_results(tmp_path):
    wb, proj = bench(tmp_path), project(tmp_path)
    sentence = "Search democracy in the Middle East on all platforms."
    # 1-3: accepted without special syntax, inferred into a structured plan, shown for review
    out = wb.interpret(sentence, mode="deterministic", project=proj, today=TODAY)
    assert out["method"] == "deterministic" and not out["needs_manual_entry"] and out["clarifications"] == []
    rows = {r["label"]: r["value"] for r in out["summary"]}
    assert rows == {"Research topic": "democracy", "Region": "Middle East", "Platforms": "All enabled platforms", "Languages": "Automatic",
                    "Date range": "No restriction", "Collection depth": "Standard"}
    assert out["plan"]["queries"]                                               # the plan is auditable before running
    saved = prepare(wb, proj, sentence)
    assert saved["plan"]["version"] == 1 and proj.meta()["requirement_text"] == sentence
    # LLM for translation
    with FakeLLMServer(reply="translated text") as server:
        wb.providers.upsert(ProviderProfile(id="main", type="openai_compatible", endpoint=server.url, model="gpt-test"), secret=KEY, make_default=True)
        wb.set_platform_secret("mastodon_token", "masto-token-abcdef123456")
        # 4-8: execute against enabled sources, survive the failing platform, preserve provenance
        started = wb.start_run(proj, wait=True)["run"]
    run_id = started["run_id"]
    run = wb.get_run(proj, run_id)
    assert run["status"] == "completed_with_warnings"
    assert run["sources"]["bluesky"]["status"] == "success" and run["sources"]["mastodon"]["status"] in {"failed", "partial"}
    assert "INCOMPLETE" in run["completeness"]["summary"] and "Mastodon" in run["completeness"]["summary"]
    assert run["provider_ref"]["profile_id"] == "main" and "credential_ref" in run["provider_ref"] and KEY not in json.dumps(run)
    # 5-7: events were structured and complete
    events = wb.events(proj, run_id)
    kinds = [e["type"] for e in events["events"]]
    assert events["finished"] and {"research.plan.created", "item.discovered", "translation.completed", "source.failed", "provider.rate_limited",
                                   "pipeline.completed"} <= set(kinds)
    # 9-10: inspectable results with grouping, translation toggle data, provenance
    results = wb.results(proj, run_id, group_by="language")
    assert {g["key"] for g in results["groups"]} >= {"ar", "en"}
    arabic = wb.results(proj, run_id, language="ar")["items"][0]
    assert arabic["original_text"].startswith("الديمقراطية") and arabic["translated_text"] == "translated text"
    detail = wb.item_detail(proj, run_id, arabic["item_id"])
    assert [n["type"] for n in detail["evidence_chain"]][:3] == ["search_result", "fetched_document", "extracted_paragraph"]
    assert detail["translations"][0]["provider"] == "openai_compatible" and detail["project_id"] == proj.project_id
    assert any(g for g in wb.results(proj, run_id, group_by="geography")["groups"])
    assert wb.results(proj, run_id, text="strong institutions")["total"] >= 1
    # 11: the run is preserved so another researcher can understand how it was produced
    exported = wb.export(proj, run_id)
    assert {"plan.json", "run-manifest.json", "sources.csv", "corpus.jsonl", "translations.jsonl", "activity-log.jsonl", "results.csv", "report.md", "geo.geojson"} <= set(exported["files"])
    assert verify_export(exported["directory"])["ok"] and verify_export(exported["archive"])["ok"]
    report = (proj.root / "exports" / run_id / "report.md").read_text(encoding="utf-8")
    assert "Search democracy" in report or "democracy" in report and "INCOMPLETE" in report
    assert KEY not in report and "masto-token-abcdef123456" not in report
    with zipfile.ZipFile(exported["archive"]) as bundle:
        assert any(n.endswith("activity-log.jsonl") for n in bundle.namelist())
    # tamper detection
    (proj.root / "exports" / run_id / "sources.csv").write_text("tampered")
    assert not verify_export(exported["directory"])["ok"]


def test_only_one_active_run_per_project(tmp_path):
    gate, started = threading.Event(), threading.Event()

    def slow(request):
        started.set()
        gate.wait(5)
        return []

    wb, proj = bench(tmp_path, {"bluesky": spec("bluesky", slow)}), project(tmp_path)
    prepare(wb, proj)
    run_id = wb.start_run(proj)["run"]["run_id"]
    assert started.wait(5)
    with pytest.raises(RunConflict):
        wb.start_run(proj)
    wb.control(proj, run_id, "pause")
    assert wb.get_run(proj, run_id)["status"] == "paused"
    gate.set()
    wb.control(proj, run_id, "cancel")
    assert wb.pipeline(proj, run_id).join(10)
    assert wb.get_run(proj, run_id)["status"] == "cancelled"
    with pytest.raises(WorkbenchError):
        wb.control(proj, run_id, "pause")                # finished runs cannot be paused


def test_five_distinct_refresh_operations(tmp_path):
    calls = {"n": 0, "phase": 1}

    def bsky(request):
        calls["n"] += 1
        return [rec("bluesky", "stable", "Democracy stays the same across both runs of this collection"),
                rec("bluesky", "evolving", f"Democracy commentary edited in phase {calls['phase']} by its author today"),
                rec("bluesky", f"new-{calls['n']}-{request.search_terms[0]}", f"Fresh democracy commentary {calls['n']} {request.search_terms[0]} appears here")]

    wb, proj = bench(tmp_path, {"bluesky": spec("bluesky", bsky)}), project(tmp_path)
    prepare(wb, proj, "democracy in Egypt on bluesky")
    first = wb.start_run(proj, wait=True)["run"]["run_id"]
    collected = calls["n"]

    # Rerun: same plan snapshot, new run object linked to its parent
    rerun = wb.start_run(proj, kind="rerun", parent_run_id=first, wait=True)["run"]
    assert rerun["kind"] == "rerun" and rerun["parent_run_id"] == first and rerun["plan_fingerprint"] == wb.get_run(proj, first)["plan_fingerprint"]
    assert calls["n"] > collected

    # Refresh sources: searches again, restricted to newer material, flags known vs new
    before = calls["n"]
    calls["phase"] = 2
    refresh = wb.start_run(proj, kind="refresh_sources", wait=True)["run"]
    assert calls["n"] > before and refresh["kind"] == "refresh_sources" and refresh["counts"]["known"] >= 1
    assert refresh["counts"]["new"] >= 1 and refresh["counts"]["changed"] == 1         # the edited post is detected as changed
    assert any(e["type"] == "item.changed" for e in wb.events(proj, refresh["run_id"])["events"])
    assert wb.results(proj, refresh["run_id"], new_only=True)["total"] < wb.results(proj, refresh["run_id"])["total"]

    # Reprocess: no collection at all
    before = calls["n"]
    reprocess = wb.start_run(proj, kind="reprocess", parent_run_id=first, wait=True)["run"]
    assert calls["n"] == before and reprocess["kind"] == "reprocess" and reprocess["parent_run_id"] == first

    # Rebuild plan / Reinterpret: proposals only, nothing saved until the researcher accepts
    version = proj.load_plan().version
    rebuilt = wb.rebuild_plan(proj)
    assert rebuilt["operation"] == "rebuild_plan" and proj.load_plan().version == version
    proj.save_requirement("democracy in Egypt on bluesky")
    reinterpreted = wb.reinterpret(proj, mode="deterministic")
    assert reinterpreted["operation"] == "reinterpret_request" and reinterpreted["plan"]["topic"] == "democracy"
    assert proj.load_plan().version == version
    kinds = [r["kind"] for r in wb.list_runs(proj)]
    assert sorted(kinds) == ["refresh_sources", "reprocess", "rerun", "run"]


def test_rerun_without_history_and_unknown_parent_are_clear_errors(tmp_path):
    wb, proj = bench(tmp_path), project(tmp_path)
    prepare(wb, proj)
    with pytest.raises(WorkbenchError, match="no earlier run"):
        wb.start_run(proj, kind="rerun")
    with pytest.raises(WorkbenchError, match="no earlier run"):
        wb.start_run(proj, kind="refresh_sources")
    empty = ResearchProject(SugarWorkspace.create(tmp_path / "ws_empty", name="Empty"))
    with pytest.raises(WorkbenchError, match="no research plan"):
        wb.start_run(empty)


def test_retrying_a_failed_source_after_the_run_starts_a_linked_follow_up(tmp_path):
    state = {"fail": True}

    def flaky(request):
        if state["fail"]:
            raise RuntimeError("X rejected the bearer token (401).")
        return [rec("x", request.search_terms[0], f"democracy post about {request.search_terms[0]} and more words here")]

    wb, proj = bench(tmp_path, {"x": spec("x", flaky), "bluesky": spec("bluesky", lambda r: [rec("bluesky", r.search_terms[0], f"some democracy text {r.search_terms[0]} many words")])}), project(tmp_path)
    prepare(wb, proj)
    first = wb.start_run(proj, wait=True)["run"]["run_id"]
    assert wb.get_run(proj, first)["sources"]["x"]["status"] == "failed"
    state["fail"] = False
    follow = wb.control(proj, first, "retry_source", source="x")["run"]
    wb.pipeline(proj, follow["run_id"]).join(10)
    done = wb.get_run(proj, follow["run_id"])
    assert done["parent_run_id"] == first and list(done["sources"]) == ["x"] and done["sources"]["x"]["status"] == "success"


def test_interactive_retry_inside_an_active_run(tmp_path):
    gate = threading.Event()
    state = {"fail": True}

    def flaky(request):
        if state["fail"]:
            raise RuntimeError("Weibo access control blocked the request.")
        return [rec("weibo", request.search_terms[0], f"democracy discussion {request.search_terms[0]} in the feed")]

    def hold(request):
        gate.wait(5)
        return []

    wb, proj = bench(tmp_path, {"weibo": spec("weibo", flaky), "bluesky": spec("bluesky", hold)}), project(tmp_path)
    prepare(wb, proj)
    run_id = wb.start_run(proj)["run"]["run_id"]
    pipeline = wb.pipeline(proj, run_id)
    for _ in range(100):
        if pipeline.sources.get("weibo") and pipeline.sources["weibo"].status == "failed":
            break
        threading.Event().wait(0.05)
    assert pipeline.sources["weibo"].status == "failed"
    state["fail"] = False
    wb.control(proj, run_id, "retry_source", source="weibo")
    gate.set()
    assert pipeline.join(15)
    assert pipeline.sources["weibo"].status == "success" and pipeline.counts["collected"] >= 1


def test_plan_versions_are_immutable_and_history_is_a_timeline(tmp_path):
    wb, proj = bench(tmp_path), project(tmp_path)
    first = prepare(wb, proj)["plan"]
    edited = dict(first, depth="deep")
    second = wb.save_plan(proj, edited, reason="edited")["plan"]
    assert second["version"] == 2 and second["limits"]["max_pages_per_query"] == 3
    assert [v["version"] for v in proj.plan_versions()] == [1, 2]
    assert proj.load_plan(first["plan_id"], 1).depth == "standard"
    assert wb.save_plan(proj, second, reason="edited")["plan"]["version"] == 2           # unchanged -> no new version
    proj.update_settings({"enabled_sources": ["bluesky"], "debug": True})
    proj.add_member("William Taggart", "editor")
    proj.add_note("Check the Gulf results", author="Alejandro Grenier")
    kinds = [e["event_type"] for e in proj.timeline()]
    assert {"requirement_edited", "plan_interpreted", "plan_edited", "settings_changed", "member_changed", "note_added"} <= set(kinds)
    with pytest.raises(ValueError):
        proj.add_member("x", "emperor")


def test_enabled_sources_setting_limits_all_enabled_scope(tmp_path):
    seen = []

    def make(name):
        def fn(request):
            seen.append(name)
            return []
        return spec(name, fn)

    wb, proj = bench(tmp_path, {"bluesky": make("bluesky"), "weibo": make("weibo")}), project(tmp_path)
    prepare(wb, proj)
    proj.update_settings({"enabled_sources": ["bluesky"]})
    wb.start_run(proj, wait=True)
    assert set(seen) == {"bluesky"}


def test_coded_findings_extend_the_evidence_chain_and_can_be_traced_back(tmp_path):
    wb, proj = bench(tmp_path), project(tmp_path)
    prepare(wb, proj, "democracy on bluesky")
    run_id = wb.start_run(proj, wait=True)["run"]["run_id"]
    item = next(i for i in proj.load_items(run_id) if i.status == "processed")
    paragraph = item.paragraphs[0]["node_id"]
    finding = proj.add_finding(run_id, item.item_id, paragraph, "support for elections", author="William Taggart")
    assert finding["trace"] == ["search_result", "fetched_document", "extracted_paragraph", "coded_finding"]
    with pytest.raises(KeyError):
        proj.add_finding(run_id, item.item_id, "nope", "x")


def test_project_summary_has_the_fields_the_project_list_shows(tmp_path):
    wb, proj = bench(tmp_path), project(tmp_path)
    assert proj.summary()["status"] == "draft"
    prepare(wb, proj)
    summary = proj.summary()
    assert summary["research_question"] and summary["status"] == "ready" and summary["last_activity"] and summary["updated_at"]
    wb.start_run(proj, wait=True)
    assert proj.summary()["run_count"] == 1 and proj.summary()["status"] in {"completed", "attention"}


def test_platform_status_reports_credentials_without_exposing_them(tmp_path):
    wb = bench(tmp_path)
    rows = {r["id"]: r for r in wb.platform_status()}
    assert rows["mastodon"]["state"] == "needs_credential" and rows["bluesky"]["state"] == "ready"
    wb.set_platform_secret("mastodon_token", "masto-token-abcdef123456")
    rows = {r["id"]: r for r in wb.platform_status()}
    assert rows["mastodon"]["state"] == "ready" and "masto-token" not in json.dumps(rows)
    with pytest.raises(WorkbenchError):
        wb.set_platform_secret("not_a_key", "v")
    wb.set_platform_secret("mastodon_token", "")
    assert {r["id"]: r for r in wb.platform_status()}["mastodon"]["state"] == "needs_credential"


def test_test_provider_records_status_and_surfaces_provider_specific_errors(tmp_path):
    wb = bench(tmp_path)
    with FakeLLMServer() as server:
        wb.providers.upsert(ProviderProfile(id="main", type="openai_compatible", endpoint=server.url, model="gpt-test"), secret="sk-wrong-000000000000")
        bad = wb.test_provider("main")
        assert not bad["ok"] and bad["error_stage"] == "credential"
        assert wb.providers.get("main").status["state"] == "failed"
        wb.providers.upsert(wb.providers.get("main"), secret=KEY)
        good = wb.test_provider("main")
        assert good["ok"] and wb.providers.get("main").status["state"] == "ok"
        draft = wb.test_provider("", overrides=ProviderProfile(id="draft", type="openai_compatible", endpoint=server.url, model="gpt-test"), secret=KEY)
        assert draft["ok"]
    with pytest.raises(WorkbenchError):
        wb.test_provider("missing")


def test_interpret_uses_the_configured_model_and_falls_back_when_its_credential_is_bad(tmp_path):
    wb, proj = bench(tmp_path), project(tmp_path)
    good = {"topic": "democracy", "research_question": "What is being said about democracy in the Middle East?", "geography": ["Middle East"],
            "actors": [], "timeframe_start": "", "timeframe_end": "", "languages": ["auto"], "all_platforms": True, "platforms": [],
            "search_terms": [], "exclusions": [], "depth": "standard", "collection_mode": "discovery", "translation_policy": "auto",
            "analysis_goals": [], "assumptions": [], "clarifications": []}
    with FakeLLMServer(reply=json.dumps(good)) as server:
        wb.providers.upsert(ProviderProfile(id="main", type="openai_compatible", endpoint=server.url, model="gpt-test"), secret=KEY, make_default=True)
        out = wb.interpret("Search democracy in the Middle East on all platforms.", project=proj, today=TODAY)
        assert out["method"] == "llm" and out["provider"]["id"] == "main" and out["plan"]["provider"]["profile_id"] == "main"
        wb.providers.upsert(wb.providers.get("main"), secret="sk-revoked-key-0000000000")
        out = wb.interpret("Search democracy in the Middle East on all platforms.", project=proj, today=TODAY)
        assert out["method"] == "deterministic" and "credential was rejected" in out["fallback_reason"]
    assert out["plan"]["topic"] == "democracy"


def test_manual_structured_entry_path(tmp_path):
    wb = bench(tmp_path)
    out = wb.manual_plan({"topic": "democracy", "geography": ["Egypt"], "platforms": ["bluesky"]})
    assert out["plan"]["source_scope"] == "selected" and out["summary"][2]["value"] == "bluesky"
    bad = wb.manual_plan({"topic": ""})
    assert bad["plan"] is None and bad["issues"]
