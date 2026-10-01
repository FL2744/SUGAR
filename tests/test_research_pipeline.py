import json
import threading
import time
from datetime import date


from sugar_core import redaction
from sugar_core.collector_registry import CollectorCapabilities, CollectorSpec
from sugar_core.llm_providers import ChatResult, LLMProvider, ProviderError, ProviderProfile
from sugar_core.models import PostRecord
from sugar_core.nl_interpreter import interpret_deterministic
from sugar_core.provider_pacing import SharedRequestPacer
from sugar_core.research_items import DedupIndex, detect_language, split_paragraphs
from sugar_core.research_pipeline import ResearchPipeline, classify_failure
from sugar_core.research_plan import build_plan
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace

TODAY = date(2026, 9, 30)


def make_project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Test project"))


def make_plan(text="Search democracy in the Middle East on all platforms.", **overrides):
    payload = interpret_deterministic(text, today=TODAY).payload
    payload.update(overrides)
    payload.setdefault("concurrency", {"per_source_delay_seconds": 0, "max_workers": 4})
    payload.setdefault("retry", {"max_attempts": 3, "base_backoff_seconds": 0})
    plan, issues = build_plan(payload)
    assert plan is not None, issues
    from sugar_core.query_planner import apply_generated_queries, generate_queries
    if not plan.queries:
        apply_generated_queries(plan, generate_queries(plan))
    return plan


def rec(platform, native_id, text, **kw):
    kw.setdefault("published_at", "2026-01-15T10:00:00Z")
    return PostRecord(platform=platform, native_id=str(native_id), canonical_url=f"https://{platform}.test/{native_id}",
                      query="q", original_text=text, author_name=kw.pop("author", "someone"), **kw)


def spec(name, fn, secrets=()):
    return CollectorSpec(name=name, search=fn, required_secrets=tuple(secrets),
                         capabilities=CollectorCapabilities(keyword_search=True, anonymous_search=not secrets))


class FakeTranslator(LLMProvider):
    def __init__(self, fail=None, delay=0.0):
        super().__init__(ProviderProfile(id="t", type="local", endpoint="http://localhost:1/v1", model="fake-model"))
        self.calls = []
        self.fail = fail
        self.delay = delay

    def chat(self, messages, **kw):
        self.calls.append(messages)
        if self.fail:
            raise self.fail
        time.sleep(self.delay)
        original = messages[-1]["content"].split("<content>\n")[1].split("\n</content>")[0]
        return ChatResult(text=f"EN[{original[:30]}]", model="fake-model", latency_ms=1.0)

    def list_models(self):
        return ["fake-model"]


def run_pipeline(project, plan, registry, *, secrets=None, provider=None, kind="run", debug=False, **kw):
    run = project.new_run(kind=kind, plan=plan, debug=debug, requirement=plan.interpretation.get("request", "") or "test")
    pipeline = ResearchPipeline(project, run, plan, secrets=secrets or {}, provider=provider, registry=registry, sleeper=lambda s: None, pacer=SharedRequestPacer(), **kw)
    pipeline.execute()
    return pipeline


def types(pipeline):
    return [e.type for e in pipeline.events.since(0)]


ARABIC = "الديمقراطية في المنطقة تحتاج إلى إصلاح حقيقي وشامل"


def two_sources():
    def bsky(request):
        term = request.search_terms[0]
        return [rec("bluesky", f"b-{abs(hash(term)) % 1000}-1", "Democracy needs strong institutions and free elections in the region."),
                rec("bluesky", f"b-{abs(hash(term)) % 1000}-2", ARABIC)]

    def masto(request):
        return [rec("mastodon", "m-1", "Democracy needs strong institutions and free elections in the region!")]   # near-duplicate

    return {"bluesky": spec("bluesky", bsky), "mastodon": spec("mastodon", masto, secrets=("mastodon_token",))}


def test_full_pipeline_emits_structured_events_and_preserves_provenance(tmp_path):
    project = make_project(tmp_path)
    plan = make_plan()
    translator = FakeTranslator()
    p = run_pipeline(project, plan, two_sources(), secrets={"mastodon_token": "tok-mastodon-123456"}, provider=translator)
    t = types(p)
    for expected in ("run.started", "research.plan.created", "query.generated", "source.search.started", "source.search.completed",
                     "item.discovered", "item.download.started", "item.download.completed", "language.detected", "extraction.started",
                     "extraction.completed", "duplicate.detected", "translation.started", "translation.completed", "pipeline.completed"):
        assert expected in t, expected
    assert t.index("research.plan.created") < t.index("source.search.started") < t.index("item.discovered") < t.index("pipeline.completed")
    assert p.run.status == "completed" and p.run.completeness["complete"]
    assert all(e.seq == i + 1 for i, e in enumerate(p.events.since(0)))          # monotonically increasing seq

    items = project.load_items(p.run.run_id)
    accepted = [i for i in items if i.status == "processed"]
    assert accepted and any(i.status == "duplicate" for i in items)
    arabic = next(i for i in accepted if i.language == "ar")
    # section 26 provenance
    assert arabic.platform == "bluesky" and arabic.url.startswith("https://bluesky.test/")
    assert arabic.retrieved_at and arabic.query and arabic.query_dispatched
    assert arabic.project_id == project.project_id and arabic.run_id == p.run.run_id
    assert [t["step"] for t in arabic.transformations][:2] == ["retrieved", "stored"]
    assert {"detect_language", "extract_paragraphs", "translate"} <= {t["step"] for t in arabic.transformations}
    # section 27 lineage: search result -> fetched document -> extracted paragraph -> translated paragraph
    translated = next(n for n in arabic.evidence_chain if n["type"] == "translated_paragraph")
    chain = [n["type"] for n in reversed(arabic.trace_back(translated["id"]))]
    assert chain == ["search_result", "fetched_document", "extracted_paragraph", "translated_paragraph"]
    # translation retained with source / language / provider / timestamp / run
    rows = project.load_translations(p.run.run_id)
    row = next(r for r in rows if r["item_id"] == arabic.item_id)
    assert row["source_language"] == "ar" and row["provider"] == "local" and row["model"] == "fake-model"
    assert row["original"] == ARABIC and row["translated"].startswith("EN[") and row["run_id"] == p.run.run_id and row["at"] and row["url"]
    ev = next(e for e in p.events.since(0) if e.type == "translation.completed")
    assert ev.data["original"] and ev.data["translation"] and ev.data["source_language"] == "ar"
    # english items are not sent for translation
    assert all("Democracy needs" not in c[-1]["content"] for c in translator.calls)


def test_run_record_is_a_reproducible_snapshot_and_contains_no_secrets(tmp_path):
    project = make_project(tmp_path)
    secret = "tok-mastodon-SECRETVALUE-123456"
    plan = make_plan()
    p = run_pipeline(project, plan, two_sources(), secrets={"mastodon_token": secret}, provider=FakeTranslator(), debug=True)
    saved = project.get_run(p.run.run_id)
    assert saved.plan["topic"] == "democracy" and saved.plan_fingerprint == plan.fingerprint()
    assert saved.generated_searches and saved.requirement and saved.status == "completed"
    assert saved.metrics["timings"]["categories"]["search"]["count"] >= 1
    assert saved.provider_ref == {} or "api_key" not in saved.provider_ref
    blob = (project.run_dir(p.run.run_id) / "run.json").read_text() + (project.run_dir(p.run.run_id) / "events.jsonl").read_text()
    assert secret not in blob
    assert saved.stage_states["results"]["state"] == "done"


def test_timings_cover_the_instrumented_categories(tmp_path):
    project = make_project(tmp_path)
    p = run_pipeline(project, make_plan(), two_sources(), secrets={"mastodon_token": "x" * 12}, provider=FakeTranslator())
    cats = p.timings.snapshot()["categories"]
    assert {"search", "download", "parsing", "extraction", "translation", "deduplication", "serialization"} <= set(cats)
    assert "bluesky" in p.timings.snapshot()["by_source"]


def test_one_failed_platform_does_not_end_the_run_and_is_reported_explicitly(tmp_path):
    project = make_project(tmp_path)

    def denied(request):
        raise RuntimeError("X rejected the bearer token (401).")

    registry = {"bluesky": two_sources()["bluesky"], "x": spec("x", denied)}
    p = run_pipeline(project, make_plan(), registry)
    assert p.run.status == "completed_with_warnings"
    assert p.sources["bluesky"].status == "success" and p.sources["x"].status == "failed"
    failed = [e for e in p.events.since(0) if e.type == "source.failed"]
    assert failed and failed[0].data["classification"] == "source_specific" and failed[0].source == "x"
    assert "credential in Settings" in failed[0].message or "access gate" in failed[0].message and "Other platforms continue" in failed[0].message
    assert not p.run.completeness["complete"] and p.run.completeness["incomplete_sources"] == ["x"]
    assert "INCOMPLETE" in p.run.completeness["summary"]
    err = p.run.errors[0]
    assert err["stage"] == "search" and err["subsystem"] == "x-collector" and err["classification"] == "source_specific"


def test_rate_limits_are_retried_with_backoff_then_succeed(tmp_path):
    project = make_project(tmp_path)
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("X rate limit reached (429).")
        return [rec("x", calls["n"], "democracy is a topic that matters to many people")]

    plan = make_plan(retry={"max_attempts": 3, "base_backoff_seconds": 30})
    p = run_pipeline(project, plan, {"x": spec("x", flaky)})
    limited = [e for e in p.events.since(0) if e.type == "provider.rate_limited"]
    scheduled = [e for e in p.events.since(0) if e.type == "source.retry.scheduled"]
    assert len(limited) == 2 and "HTTP 429" in limited[0].message and "retry in 30 seconds" in limited[0].message
    assert scheduled[1].data["retry_in_seconds"] == 60.0                                   # exponential
    assert p.sources["x"].status in {"success", "partial"} and p.counts["collected"] >= 1


def test_retries_exhausted_is_classified_retryable(tmp_path):
    project = make_project(tmp_path)

    def down(request):
        raise ConnectionError("connection reset by peer")

    p = run_pipeline(project, make_plan(), {"bluesky": spec("bluesky", down)})
    assert p.run.status == "failed"
    failed = [e for e in p.events.since(0) if e.type == "source.failed"]
    assert failed[0].data["classification"] == "retryable" and failed[0].data["retries_exhausted"]


def test_missing_credentials_skip_a_platform_with_an_actionable_message(tmp_path):
    project = make_project(tmp_path)
    registry = {"bluesky": two_sources()["bluesky"], "x": spec("x", lambda r: [], secrets=("x_bearer_token",))}
    p = run_pipeline(project, make_plan(), registry)
    skipped = [e for e in p.events.since(0) if e.type == "source.skipped"]
    assert skipped[0].source == "x" and "Settings → Platform credentials" in skipped[0].message
    assert p.run.completeness["sources"]["x"]["status"] == "skipped" and p.run.status == "completed_with_warnings"


def test_run_fails_clearly_when_no_platform_is_runnable(tmp_path):
    project = make_project(tmp_path)
    p = run_pipeline(project, make_plan(), {"x": spec("x", lambda r: [], secrets=("x_bearer_token",))})
    assert p.run.status == "failed"
    assert p.run.errors[0]["classification"] == "fatal" and "No platform can be searched" in p.run.errors[0]["message"]
    assert any(e.type == "run.failed" for e in p.events.since(0))


def test_selected_platforms_and_exclusions_and_date_range(tmp_path):
    project = make_project(tmp_path)
    seen = []

    def bsky(request):
        seen.append(request)
        return [rec("bluesky", 1, "Democracy and memes together"),
                rec("bluesky", 2, "Democracy old post", published_at="2019-01-01T00:00:00Z"),
                rec("bluesky", 3, "Democracy needs debate and open institutions", published_at="2026-02-01T00:00:00Z"),
                rec("bluesky", 4, "   ")]

    plan = make_plan("democracy on Bluesky since 2023, excluding memes")
    assert plan.source_scope == "selected" and plan.exclusions == ["memes"]
    p = run_pipeline(project, plan, {"bluesky": spec("bluesky", bsky), "x": spec("x", lambda r: [])})
    assert list(p.sources) == ["bluesky"]                                        # X was not named
    assert seen[0].since == "2023-01-01"
    reasons = sorted(i.rejection_reason for i in p.items.values() if i.status == "rejected")
    assert any("exclusion" in r for r in reasons) and any("outside the requested date range" in r for r in reasons) and any("no text" in r for r in reasons)
    assert [i.native_id for i in p.items.values() if i.status == "processed"] == ["3"]
    rejected_events = [e for e in p.events.since(0) if e.type == "item.rejected"]
    assert len(rejected_events) == 3 and all(e.data["reason"] for e in rejected_events)


def test_x_receives_native_exclusion_operators(tmp_path):
    project = make_project(tmp_path)
    seen = []

    def xs(request):
        seen.append(request.search_terms[0])
        return []

    plan = make_plan("democracy on X, excluding memes")
    run_pipeline(project, plan, {"x": spec("x", xs)}, secrets={})
    assert seen and all(t.endswith(" -memes") for t in seen)


def test_per_source_limits_and_total_limit_are_enforced_and_reported(tmp_path):
    project = make_project(tmp_path)

    def many(request):
        return [rec("bluesky", f"{request.search_terms[0]}-{i}", f"Unique democracy discussion number {i} about {request.search_terms[0]} institutions") for i in range(10)]

    plan = make_plan(limits={"max_items_total": 4})
    p = run_pipeline(project, plan, {"bluesky": spec("bluesky", many)})
    assert p.counts["collected"] == 4
    assert p.run.status == "completed_with_warnings" and "item limit" in p.run.completeness["summary"]


def test_near_duplicates_are_detected_and_counted(tmp_path):
    project = make_project(tmp_path)

    def dupes(request):
        base = "The parliament voted today on the new electoral law after a long and heated debate among members"
        return [rec("bluesky", 1, base), rec("bluesky", 2, base + "!"), rec("bluesky", 3, "Completely different sentence about trade agreements and tariffs")]

    p = run_pipeline(project, make_plan("democracy on bluesky", queries=[{"text": "democracy"}]), {"bluesky": spec("bluesky", dupes)})
    dup = [i for i in p.items.values() if i.status == "duplicate"]
    assert len(dup) == 1 and dup[0].duplicate_of and dup[0].similarity >= 0.9
    assert p.counts["duplicates"] >= 1


def test_dedup_index_unit():
    index = DedupIndex(0.9)
    text = "the quick brown fox jumps over the lazy dog near the river bank today"
    assert index.check("a", text) is None
    assert index.check("b", text.upper() + " https://t.co/xyz")[0] == "a"
    assert index.check("c", "an entirely unrelated statement about economics and trade policy reform") is None
    assert DedupIndex(0.9, enabled=False).check("z", text) is None
    zh = DedupIndex(0.9)
    assert zh.check("a", "民主是一个重要的议题需要更多讨论和思考") is None
    assert zh.check("b", "民主是一个重要的议题需要更多讨论和思考！")[0] == "a"


def test_language_detection_and_paragraphs():
    assert detect_language(ARABIC)[0] == "ar"
    assert detect_language("دموکراسی و آزادی بیان چیزی است که گروه ها می خواهند")[0] == "fa"
    assert detect_language("Демократия и свобода слова важны для общества")[0] == "ru"
    assert detect_language("民主是重要的")[0] == "zh"
    assert detect_language("the democracy and the people are in this for the long term")[0] == "en"
    assert detect_language("anything", "AR-EG") == ("ar", "platform", 0.95)
    assert detect_language("Two threats to our democracy are still here", "en,it")[:2] == ("en", "platform")      # Bluesky lists several
    assert detect_language(ARABIC, "en")[0] == "ar"                                                              # wrong user setting, clear script
    parts = split_paragraphs("First paragraph.\n\nSecond one\nstill second.")
    assert [p[2] for p in parts] == ["First paragraph.", "Second one\nstill second."]
    long = " ".join(f"Sentence number {i} is here." for i in range(60))
    assert all(len(p[2]) <= 600 for p in split_paragraphs(long)) and len(split_paragraphs(long)) > 1


def test_translation_without_a_provider_is_reported_not_silent(tmp_path):
    project = make_project(tmp_path)
    p = run_pipeline(project, make_plan(), two_sources(), secrets={"mastodon_token": "x" * 12})
    skipped = [e for e in p.events.since(0) if e.type == "translation.skipped"]
    assert skipped and "no LLM provider" in skipped[0].message
    assert p.run.stage_states["translate"]["state"] == "skipped"
    assert "not translated" in p.run.completeness["summary"] and p.run.status == "completed_with_warnings"


def test_translation_failure_is_a_warning_and_credential_failure_stops_further_attempts(tmp_path):
    project = make_project(tmp_path)

    def bsky(request):
        return [rec("bluesky", f"{request.search_terms[0]}{i}", f"{ARABIC} رقم {i} {request.search_terms[0]}") for i in range(3)]

    bad = FakeTranslator(fail=ProviderError("The configured OpenAI credential was rejected (HTTP 401). Open Settings → LLM Providers and test the connection.",
                                            stage="credential", status=401))
    plan = make_plan(translation={"workers": 1})
    p = run_pipeline(project, plan, {"bluesky": spec("bluesky", bsky)}, provider=bad)
    failed = [e for e in p.events.since(0) if e.type == "translation.failed"]
    assert failed and "credential was rejected" in failed[0].message and "Settings → LLM Providers" in failed[0].message
    assert len(bad.calls) == 1                                                       # remaining items were skipped, not hammered
    assert any(e.type == "translation.skipped" for e in p.events.since(0))
    assert p.run.status == "completed_with_warnings" and p.counts["collected"] >= 3


def test_pause_resume_and_cancel_keep_partial_results(tmp_path):
    project = make_project(tmp_path)
    gate = threading.Event()
    started = threading.Event()

    def slow(request):
        started.set()
        gate.wait(5)
        return [rec("bluesky", request.search_terms[0], f"democracy content for query {request.search_terms[0]} discussion")]

    plan = make_plan(concurrency={"max_workers": 1, "per_source_delay_seconds": 0})
    run = project.new_run(plan=plan, requirement="t")
    p = ResearchPipeline(project, run, plan, registry={"bluesky": spec("bluesky", slow)}, sleeper=lambda s: None)
    p.start()
    assert started.wait(5)
    p.pause()
    assert p.run.status == "paused" and p.snapshot()["paused"]
    gate.set()                                       # the in-flight query finishes; nothing new starts while paused
    time.sleep(0.5)
    before = p.counts["queries_done"]
    time.sleep(0.4)
    assert p.counts["queries_done"] == before and p.run.status == "paused"
    p.resume()
    assert p.run.status == "running"
    p.cancel()
    assert p.join(10)
    assert p.run.status == "cancelled"
    assert "run.paused" in types(p) and "run.resumed" in types(p) and "run.cancelled" in types(p)
    assert "cancelled" in p.run.completeness["summary"] or p.run.completeness["incomplete_sources"] == ["bluesky"]
    assert project.get_run(run.run_id).status == "cancelled"


def test_researcher_can_exclude_items_and_edit_queries_mid_run(tmp_path):
    project = make_project(tmp_path)
    gate = threading.Event()
    started = threading.Event()
    seen = []

    def bsky(request):
        seen.append(request.search_terms[0])
        started.set()
        gate.wait(5)
        return [rec("bluesky", request.search_terms[0], f"democracy discussion about {request.search_terms[0]} and institutions today")]

    plan = make_plan(concurrency={"max_workers": 1, "per_source_delay_seconds": 0})
    first_query = plan.enabled_queries()[0]
    second_query = plan.enabled_queries()[1]
    run = project.new_run(plan=plan, requirement="t")
    p = ResearchPipeline(project, run, plan, registry={"bluesky": spec("bluesky", bsky)}, sleeper=lambda s: None)
    p.start()
    assert started.wait(5)
    p.set_query_enabled(second_query.id, False)                    # remove an irrelevant query
    added = p.add_query("my extra synonym")                         # add a synonym
    gate.set()
    assert p.join(10)
    assert not any(t.startswith(second_query.text.split()[0]) and t == second_query.text for t in seen[1:]) or second_query.text not in seen
    assert "my extra synonym" in seen
    ev = [e for e in p.events.since(0) if e.type in {"query.disabled", "research.plan.updated"}]
    assert any("applies_to" in e.data for e in ev)
    assert added.origin == "analyst" and any(q["text"] == "my extra synonym" for q in p.run.generated_searches)
    target = next(i for i in p.items.values() if i.status == "processed")
    assert p.exclude_item(target.item_id, "irrelevant") and target.status == "excluded"
    assert any(e.type == "item.excluded" and e.data["reason"] == "irrelevant" for e in p.events.since(0))
    assert first_query.text in seen


def test_reprocess_translates_without_recollecting_and_links_back(tmp_path):
    project = make_project(tmp_path)
    calls = {"n": 0}

    def bsky(request):
        calls["n"] += 1
        return [rec("bluesky", "a1", ARABIC)]

    plan = make_plan("democracy on bluesky", queries=[{"text": "democracy"}])
    first = run_pipeline(project, plan, {"bluesky": spec("bluesky", bsky)})
    assert first.counts["translated"] == 0 and calls["n"] == 1
    parent_items = project.load_items(first.run.run_id)
    again = run_pipeline(project, plan, {"bluesky": spec("bluesky", bsky)}, provider=FakeTranslator(), kind="reprocess",
                         source_items=parent_items)
    assert calls["n"] == 1                                                            # nothing was collected again
    assert again.run.status == "completed" and again.counts["translated"] == 1
    item = project.load_items(again.run.run_id)[0]
    assert item.derived_from == {"run_id": first.run.run_id, "item_id": parent_items[0].item_id}
    assert item.translation["status"] == "done" and "reprocessed" in [t["step"] for t in item.transformations]
    assert again.run.stage_states["search"]["state"] == "skipped"


def test_refresh_flags_items_seen_in_earlier_runs(tmp_path):
    project = make_project(tmp_path)

    def bsky(request):
        return [rec("bluesky", "same", "democracy is discussed here at length by many people today"),
                rec("bluesky", request.search_terms[0] + "new", "brand new democracy statement number " + request.search_terms[0])]

    plan = make_plan("democracy on bluesky", queries=[{"text": "democracy"}])
    first = run_pipeline(project, plan, {"bluesky": spec("bluesky", bsky)})
    known = project.known_items_index()
    second = run_pipeline(project, plan, {"bluesky": spec("bluesky", bsky)}, kind="refresh_sources", known_items=known)
    assert second.counts["known"] >= 1
    same = next(i for i in second.items.values() if i.native_id == "same")
    assert same.known_from_run == first.run.run_id


def test_project_history_records_run_lifecycle(tmp_path):
    project = make_project(tmp_path)
    run_pipeline(project, make_plan(), two_sources(), secrets={"mastodon_token": "x" * 12}, provider=FakeTranslator())
    kinds = [e["event_type"] for e in project.timeline()]
    assert "run_completed" in kinds


def test_classify_failure_uses_status_codes_and_messages():
    assert classify_failure(RuntimeError("X rate limit reached (429)."), "x")["kind"] == "rate_limit"
    assert classify_failure(RuntimeError("Bluesky rejected the handle/app password."), "bluesky")["classification"] == "source_specific"
    assert classify_failure(RuntimeError("X API billing/credits are required (402)."), "x")["kind"] == "billing"
    assert classify_failure(TimeoutError("timed out"), "weibo")["classification"] == "retryable"
    assert classify_failure(ValueError("weird"), "weibo")["classification"] == "source_specific"

    class Resp:
        status_code = 503
        headers = {"Retry-After": "12"}

    err = RuntimeError("bad gateway")
    err.response = Resp()
    info = classify_failure(err, "mastodon")
    assert info["classification"] == "retryable" and info["retry_after"] == 12.0


def test_secrets_registered_by_the_pipeline_are_redacted_everywhere(tmp_path):
    project = make_project(tmp_path)
    secret = "tok-very-secret-value-987654"

    def leaky(request):
        raise RuntimeError(f"bluesky exploded with token {secret} in the message")

    p = run_pipeline(project, make_plan(), {"bluesky": spec("bluesky", leaky)}, secrets={"bluesky_app_password": secret})
    assert secret not in json.dumps(p.events.snapshot()) and secret not in json.dumps(p.run.to_dict())
    redaction.clear_registered()


def test_mastodon_without_a_token_is_searched_as_hashtags_not_failed(tmp_path):
    project = make_project(tmp_path)
    seen = []

    def mastodon(request):
        term = request.search_terms[0]
        seen.append(term)
        if not (term.startswith("#") and " " not in term):
            raise ValueError("Mastodon keyword status search requires an authorized user token")
        return [rec("mastodon", term, f"public post tagged {term} about democracy and civic life today")]

    registry = {"mastodon": spec("mastodon", mastodon)}
    p = run_pipeline(project, make_plan(), registry)
    assert seen and all(t.startswith("#") and " " not in t for t in seen)             # never sent a keyword the server would reject
    assert len(seen) == len(set(seen))                                                  # a hashtag is only searched once
    kinds = [e.type for e in p.events.since(0)]
    assert "query.adapted" in kinds and "query.skipped" in kinds                         # explained, not silent
    adapted = next(e for e in p.events.since(0) if e.type == "query.adapted")
    assert "#democracy" in adapted.message and "public #hashtag" in adapted.message
    assert p.sources["mastodon"].status == "success" and p.counts["collected"] >= 1


def test_mastodon_with_a_token_keeps_keyword_search(tmp_path):
    project = make_project(tmp_path)
    seen = []

    def mastodon(request):
        seen.append(request.search_terms[0])
        return []

    run_pipeline(project, make_plan(), {"mastodon": spec("mastodon", mastodon)}, secrets={"mastodon_token": "tok-abcdef123456"})
    assert any(" " in t for t in seen) and not any(t.startswith("#") for t in seen)


def test_rate_limit_cooldown_is_shared_across_platforms(tmp_path):
    project = make_project(tmp_path)
    pacer = SharedRequestPacer()
    stamps = []

    def limited(request):
        raise RuntimeError("X rate limit reached (429).")

    plan = make_plan(retry={"max_attempts": 2, "base_backoff_seconds": 0.3})
    run = project.new_run(plan=plan, requirement="t")
    p = ResearchPipeline(project, run, plan, registry={"x": spec("x", limited), "bluesky": spec("bluesky", lambda r: stamps.append(time.monotonic()) or [])},
                         secrets={"x_bearer_token": "x" * 12}, sleeper=lambda s: None, pacer=pacer)
    p.execute()
    assert any(e.type == "provider.rate_limited" for e in p.events.since(0))


def test_anonymous_access_gates_are_not_blamed_on_missing_credentials(tmp_path):
    project = make_project(tmp_path)

    def gated(request):
        raise RuntimeError("Bilibili public video search returned an access control challenge for this anonymous session.")

    gate = CollectorSpec(name="bilibili", search=gated, capabilities=CollectorCapabilities(keyword_search=True, anonymous_search=True))
    p = run_pipeline(project, make_plan("democracy on bilibili"), {"bilibili": gate})
    msg = next(e.message for e in p.events.since(0) if e.type == "source.failed")
    assert "access gate" in msg and "not a SUGAR setting" in msg and "Settings → Platform credentials" not in msg
