import json
import threading
from http.server import ThreadingHTTPServer

import pytest
import requests

import sugar_api
from _fake_llm import FakeLLMServer
from sugar_core.collector_registry import CollectorCapabilities, CollectorSpec
from sugar_core.credential_store import CredentialStore
from sugar_core.llm_providers import ProviderRegistry
from sugar_core.models import PostRecord
from sugar_core.workbench import ResearchWorkbench

KEY = "sk-test-valid-key-1234567890"
ARABIC = "الديمقراطية في المنطقة تحتاج إلى إصلاح حقيقي وشامل"


def _rec(platform, native_id, text):
    return PostRecord(platform=platform, native_id=str(native_id), canonical_url=f"https://{platform}.test/{native_id}", query="q",
                      original_text=text, author_name="a", published_at="2026-03-01T00:00:00Z")


@pytest.fixture()
def api(tmp_path, monkeypatch):
    store = CredentialStore(tmp_path / "home", backend="file")

    def bsky(request):
        term = request.search_terms[0]
        return [_rec("bluesky", f"{term}-en", f"Democracy needs strong institutions and open debate says {term}"), _rec("bluesky", f"{term}-ar", f"{ARABIC} {term}")]

    def gated(request):
        raise RuntimeError("Mastodon rate limit reached (429).")

    registry = {"bluesky": CollectorSpec(name="bluesky", search=bsky, capabilities=CollectorCapabilities(keyword_search=True, anonymous_search=True)),
                "mastodon": CollectorSpec(name="mastodon", search=gated, required_secrets=("mastodon_token",),
                                          capabilities=CollectorCapabilities(keyword_search=True))}
    wb = ResearchWorkbench(providers=ProviderRegistry(tmp_path / "home", store), store=store, registry=registry, sleeper=lambda s: None)
    monkeypatch.setattr(sugar_api, "_workspace_root", tmp_path / "workspaces")
    (tmp_path / "workspaces").mkdir()
    monkeypatch.setattr(sugar_api, "_workbench", wb)
    monkeypatch.setattr(sugar_api.SugarApiHandler, "api_token", "tok-123")
    monkeypatch.setattr(sugar_api.SugarApiHandler, "allowed_origins", {"http://localhost:1420"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), sugar_api.SugarApiHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    session = requests.Session()
    session.headers["Authorization"] = "Bearer tok-123"
    yield base, session, wb
    server.shutdown()
    server.server_close()


def wait_done(session, base, wid, rid, timeout=20):
    import time
    end = time.time() + timeout
    while time.time() < end:
        run = session.get(f"{base}/api/workspaces/{wid}/runs/{rid}").json()["run"]
        if run["status"] in {"completed", "completed_with_warnings", "failed", "cancelled"}:
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_auth_and_cors_are_enforced_on_new_routes(api):
    base, session, _ = api
    assert requests.get(f"{base}/api/providers").status_code == 401
    assert session.get(f"{base}/api/providers", headers={"Origin": "http://evil.example"}).status_code == 403
    ok = session.get(f"{base}/api/providers", headers={"Origin": "http://localhost:1420"})
    assert ok.status_code == 200 and ok.headers["Access-Control-Allow-Origin"] == "http://localhost:1420"
    assert session.get(f"{base}/api/health").json()["features"]
    assert session.get(f"{base}/api/nope").status_code == 404


def test_provider_lifecycle_never_returns_or_stores_secrets_in_responses(api, tmp_path):
    base, session, wb = api
    with FakeLLMServer() as server:
        body = {"profile": {"id": "main", "name": "Lab OpenAI-compatible", "type": "openai_compatible", "endpoint": server.url, "model": "gpt-test"},
                "secret": KEY, "make_default": True}
        response = session.post(f"{base}/api/providers", json=body)
        assert response.status_code == 200 and KEY not in response.text
        profile = response.json()["profile"]
        assert profile["has_credential"] is True and profile["credential_ref"] == "provider:main" and profile["credential_label"] == "Endpoint API key"
        listing = session.get(f"{base}/api/providers").json()
        assert listing["default_profile_id"] == "main" and KEY not in json.dumps(listing) and {t["id"] for t in listing["types"]} >= {"openai", "local"}
        assert KEY not in (tmp_path / "home" / "providers.json").read_text(encoding="utf-8")
        ok = session.post(f"{base}/api/providers/main/test").json()
        assert ok["report"]["ok"] and ok["profile"]["status"]["state"] == "ok"
        # draft test with a wrong key: nothing saved, provider-specific error returned
        bad = session.post(f"{base}/api/providers/test", json={"profile": body["profile"], "secret": "sk-wrong-00000000000000"}).json()["report"]
        assert not bad["ok"] and bad["error_stage"] == "credential" and "Settings → LLM Providers" in bad["message"]
        # updating without sending a secret keeps the stored one
        session.post(f"{base}/api/providers", json={"profile": {"id": "main", "model": "gpt-other"}})
        assert wb.providers.secret_for(wb.providers.get("main")) == KEY and wb.providers.get("main").model == "gpt-other"
        assert session.post(f"{base}/api/providers", json={"profile": {"type": "openai_compatible", "model": "m"}}).status_code == 400   # needs endpoint
        assert session.post(f"{base}/api/providers", json={"profile": {"type": "nonsense"}}).status_code == 400
        assert session.delete(f"{base}/api/providers/main").status_code == 200
        assert session.delete(f"{base}/api/providers/main").status_code == 404
        assert wb.store.get("provider:main") == ""


def test_end_to_end_research_flow_over_http(api):
    base, session, wb = api
    created = session.post(f"{base}/api/workspaces", json={"name": "Middle East democracy"}).json()
    wid = created["id"]
    sentence = "Search democracy in the Middle East on all platforms."
    interp = session.post(f"{base}/api/interpret", json={"text": sentence, "mode": "deterministic", "workspace_id": wid}).json()
    assert interp["method"] == "deterministic" and interp["plan"]["topic"] == "democracy" and interp["summary"][1]["value"] == "Middle East"
    plan = interp["plan"]
    plan["retry"] = {"max_attempts": 2, "base_backoff_seconds": 0}
    plan["concurrency"] = {"per_source_delay_seconds": 0, "max_workers": 4}
    saved = session.post(f"{base}/api/workspaces/{wid}/research/plan", json={"plan": plan, "request": sentence, "reason": "interpreted"}).json()
    assert saved["plan"]["version"] == 1
    session.post(f"{base}/api/platform-credentials", json={"key": "mastodon_token", "value": "masto-token-abcdef123456"})
    assert {p["id"]: p["state"] for p in session.get(f"{base}/api/platforms").json()["platforms"]}["mastodon"] == "ready"

    started = session.post(f"{base}/api/workspaces/{wid}/runs", json={"kind": "run"})
    assert started.status_code == 201
    rid = started.json()["run"]["run_id"]
    run = wait_done(session, base, wid, rid)
    assert run["status"] == "completed_with_warnings" and run["completeness"]["incomplete_sources"] == ["mastodon"]

    events = session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/events").json()
    assert events["finished"] and events["events"][0]["type"] == "run.started"
    after = events["events"][5]["seq"]
    later = session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/events", params={"after": after, "stage": "search"}).json()["events"]
    assert later and all(e["seq"] > after and e["stage"] == "search" for e in later)
    assert session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/events", params={"severity": "error"}).json()["events"][0]["type"] == "source.failed"

    # the SSE stream replays a finished run and then ends
    with session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/stream", stream=True) as stream:
        assert stream.headers["Content-Type"].startswith("text/event-stream")
        text = stream.raw.read().decode("utf-8")
    assert "event: activity" in text and "event: end" in text and "pipeline.completed" in text

    results = session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/results", params={"group_by": "platform"}).json()
    assert results["groups"][0]["key"] == "bluesky" and results["total"] >= 2
    item_id = session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/results", params={"language": "ar"}).json()["items"][0]["item_id"]
    detail = session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/items/{item_id}").json()["item"]
    assert detail["evidence_chain"] and detail["project_id"] == wid or detail["project_id"]
    assert session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/results", params={"group_by": "bogus"}).status_code == 400

    assert session.post(f"{base}/api/workspaces/{wid}/runs/{rid}/control", json={"action": "pause"}).status_code == 409   # finished run
    export = session.post(f"{base}/api/workspaces/{wid}/runs/{rid}/export").json()
    assert export["archive"].endswith(f"{rid}.zip")
    download = session.get(f"{base}/api/workspaces/{wid}/files/{export['archive']}")
    assert download.status_code == 200 and download.content[:2] == b"PK"

    # reprocess / rerun through the same endpoint
    again = session.post(f"{base}/api/workspaces/{wid}/runs", json={"kind": "reprocess", "parent_run_id": rid}).json()["run"]
    done = wait_done(session, base, wid, again["run_id"])
    assert done["kind"] == "reprocess" and done["parent_run_id"] == rid
    assert len(session.get(f"{base}/api/workspaces/{wid}/runs").json()["runs"]) == 2

    # project list shows the research fields; timeline records the lifecycle
    row = next(r for r in session.get(f"{base}/api/workspaces").json()["workspaces"] if r["id"] == wid)
    assert row["research_question"] and row["status"] and row["last_activity"] and row["run_count"] == 2
    timeline = [e["event_type"] for e in session.get(f"{base}/api/workspaces/{wid}/timeline").json()["events"]]
    assert {"requirement_edited", "plan_interpreted", "run_started", "run_completed"} <= set(timeline)
    overview = session.get(f"{base}/api/workspaces/{wid}/research").json()
    assert overview["requirement_text"] == sentence and len(overview["plan_versions"]) == 1

    # notes, members, settings
    assert session.post(f"{base}/api/workspaces/{wid}/research/notes", json={"text": "Look at the Gulf", "author": "Alejandro Grenier"}).json()["note"]["author"] == "Alejandro Grenier"
    assert session.post(f"{base}/api/workspaces/{wid}/research/settings", json={"changes": {"enabled_sources": ["bluesky"]}}).json()["settings"]["enabled_sources"] == ["bluesky"]

    # diagnostics report for bug reports is redacted
    report = session.get(f"{base}/api/diagnostics/report").json()["report"]
    assert "masto-token-abcdef123456" not in report and "SUGAR" in report and "mastodon" in report.lower()


def test_unknown_project_and_invalid_ids_are_rejected(api):
    base, session, _ = api
    assert session.get(f"{base}/api/workspaces/00000000-0000-0000-0000-000000000000/runs").status_code == 404
    assert session.get(f"{base}/api/workspaces/not-a-uuid/runs").status_code in {400, 404}


def test_manual_entry_and_plan_normalization_endpoints(api):
    base, session, _ = api
    manual = session.post(f"{base}/api/plan/manual", json={"fields": {"topic": "democracy", "platforms": ["bluesky"]}}).json()
    assert manual["plan"]["source_scope"] == "selected"
    normalized = session.post(f"{base}/api/plan/normalize", json={"plan": {"topic": "x", "depth": "thorough"}}).json()
    assert normalized["plan"]["depth"] == "deep" and normalized["issues"]
    assert session.post(f"{base}/api/plan/normalize", json={"plan": {"topic": ""}}).status_code == 400
    empty = session.post(f"{base}/api/interpret", json={"text": "Search", "mode": "deterministic"}).json()
    assert empty["needs_manual_entry"] and empty["clarifications"]


def test_live_event_stream_delivers_progress_while_the_run_is_still_working(api):
    import time
    base, session, wb = api
    gate = threading.Event()
    started = threading.Event()

    def slow(request):
        started.set()
        gate.wait(10)
        return [_rec("bluesky", request.search_terms[0], f"Democracy text for {request.search_terms[0]} and its many institutions today")]

    wb.registry.pop("mastodon")
    wb.registry["bluesky"] = CollectorSpec(name="bluesky", search=slow, capabilities=CollectorCapabilities(keyword_search=True, anonymous_search=True))
    wid = session.post(f"{base}/api/workspaces", json={"name": "Live"}).json()["id"]
    interp = session.post(f"{base}/api/interpret", json={"text": "democracy in Egypt", "mode": "deterministic"}).json()
    plan = interp["plan"]
    plan["concurrency"] = {"per_source_delay_seconds": 0, "max_workers": 2}
    session.post(f"{base}/api/workspaces/{wid}/research/plan", json={"plan": plan, "request": "democracy in Egypt"})
    rid = session.post(f"{base}/api/workspaces/{wid}/runs", json={}).json()["run"]["run_id"]
    assert started.wait(5)

    import http.client
    host, port = base.replace("http://", "").split(":")
    connection = http.client.HTTPConnection(host, int(port), timeout=20)
    connection.request("GET", f"/api/workspaces/{wid}/runs/{rid}/stream", headers={"Authorization": "Bearer tok-123"})
    response = connection.getresponse()
    assert response.status == 200 and response.getheader("Content-Type").startswith("text/event-stream")
    lines: list[str] = []
    opened = time.time()
    while True:
        line = response.readline().decode("utf-8")
        if not line:
            break
        lines.append(line.rstrip("\n"))
        if line.startswith("event: activity") and not gate.is_set():
            assert time.time() - opened < 5                      # events arrive while the collector is still blocked
            assert session.get(f"{base}/api/workspaces/{wid}/runs/{rid}").json()["run"]["status"] == "running"
            gate.set()
        if line.startswith("event: end"):
            break
    connection.close()
    text = "\n".join(lines)
    assert text.index("query.generated") < text.index("source.search.started") < text.index("item.discovered") < text.index("pipeline.completed")
    assert "event: progress" in text and '"lag_ms"' in text
    # resuming with ?after= does not repeat earlier events
    last = max(int(line.split(": ")[1]) for line in text.splitlines() if line.startswith("id: "))
    with session.get(f"{base}/api/workspaces/{wid}/runs/{rid}/stream", params={"after": last}, stream=True) as stream:
        tail = stream.raw.read().decode("utf-8")
    assert "event: activity" not in tail and "event: end" in tail


def test_local_folders_can_be_linked_only_when_paths_are_exposed(api, tmp_path, monkeypatch):
    base, session, _ = api
    folder = tmp_path / "my-existing-project"
    assert session.post(f"{base}/api/workspaces/open", json={"path": str(folder), "create": True}).status_code == 403
    monkeypatch.setattr(sugar_api.SugarApiHandler, "expose_paths", True)
    assert session.post(f"{base}/api/workspaces/open", json={"path": str(folder)}).status_code == 404        # not a project, not asked to create
    linked = session.post(f"{base}/api/workspaces/open", json={"path": str(folder), "create": True, "name": "Folder project"}).json()
    assert linked["path"] == str(folder.resolve()) and linked["name"] == "Folder project"
    again = session.post(f"{base}/api/workspaces/open", json={"path": str(folder)}).json()
    assert again["id"] == linked["id"]                                                                        # stable id per folder
    rows = session.get(f"{base}/api/workspaces").json()["workspaces"]
    assert [r["path"] for r in rows if r["id"] == linked["id"]] == [str(folder.resolve())]
    assert session.get(f"{base}/api/workspaces/{linked['id']}/research").json()["summary"]["name"] == "Folder project"


def test_member_tokens_follow_project_roles_and_never_reach_admin_routes(api):
    import json as _json
    base, session, _ = api
    wid = session.post(f"{base}/api/workspaces", json={"name": "Team"}).json()["id"]
    profile = sugar_api.get_workspace_root() / wid / ".sugar" / "project-profile.json"
    profile.parent.mkdir(exist_ok=True)
    profile.write_text(_json.dumps({"members": [{"name": "Vera Viewer", "email": "v@example.org", "role": "Viewer"},
                                                {"name": "Ana Analyst", "email": "a@example.org", "role": "Analyst"}]}))
    tokens = {}
    for email in ("v@example.org", "a@example.org"):
        tokens[email] = session.post(f"{base}/api/workspaces/{wid}/access", json={"email": email}).json()["token"]
    viewer, analyst = (requests.Session() for _ in range(2))
    viewer.headers["Authorization"] = f"Bearer {tokens['v@example.org']}"
    analyst.headers["Authorization"] = f"Bearer {tokens['a@example.org']}"
    plan = {"topic": "democracy", "platforms": ["bluesky"]}
    assert viewer.get(f"{base}/api/workspaces/{wid}/research").status_code == 200
    assert viewer.get(f"{base}/api/workspaces/{wid}/runs").status_code == 200
    assert viewer.post(f"{base}/api/workspaces/{wid}/research/plan", json={"plan": plan}).status_code == 403
    assert viewer.post(f"{base}/api/workspaces/{wid}/runs", json={}).status_code == 403
    assert analyst.post(f"{base}/api/workspaces/{wid}/research/plan", json={"plan": plan}).status_code == 200
    assert analyst.post(f"{base}/api/workspaces/{wid}/research/settings", json={"changes": {"debug": True}}).status_code == 403   # owner only
    members = session.get(f"{base}/api/workspaces/{wid}/research").json()["members"]
    assert {m["email"] for m in members} == {"v@example.org", "a@example.org"}
    for member in (viewer, analyst):                  # spending money / exposing configuration is administrator-only
        for method, path in (("get", "/api/providers"), ("get", "/api/diagnostics/report"), ("post", "/api/platform-credentials"),
                             ("post", "/api/interpret"), ("post", "/api/workspaces/open")):
            assert getattr(member, method)(f"{base}{path}").status_code in {400, 403}, path
        assert member.get(f"{base}/api/providers").status_code == 403
    assert analyst.post(f"{base}/api/interpret", json={"text": "democracy", "mode": "deterministic", "workspace_id": wid}).status_code == 200
    assert viewer.post(f"{base}/api/interpret", json={"text": "democracy", "workspace_id": wid}).status_code == 403
    other = session.post(f"{base}/api/workspaces", json={"name": "Other"}).json()["id"]
    assert viewer.get(f"{base}/api/workspaces/{other}/research").status_code == 403                  # scoped to its own project
    assert session.delete(f"{base}/api/workspaces/{wid}/access/a@example.org").status_code == 200  # main's revoke still works
    assert analyst.get(f"{base}/api/workspaces/{wid}/research").status_code == 401
