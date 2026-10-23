import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from sugar_core.activity_coding import CodingStore, code_items, decide
from sugar_core.evidence_desk import capture_pages, country_snapshot, export_package, feed_seeds, news_feed, overview, scan_inbox, snapshot_html, youtube_feed
from sugar_core.institution_activity import assess
from sugar_core.institutions import institution_detail, page_history, promote
from sugar_core.mission_rubric import classify_text, load_rubric, save_rubric
from sugar_core.monitoring import build_digest
from sugar_core.networks import import_upload, preview_upload, set_network
from sugar_core.reference_registry import import_status, list_entities, upsert_entity
from sugar_core.research_export import verify_export
from sugar_core.research_items import ResearchItem, tag_geography
from sugar_core.research_plan import ResearchPlanSpec
from sugar_core.research_runs import ResearchProject
from sugar_core.research_api import _research_routes
from sugar_core.web_sources import extract_page
from sugar_core.workspace import SugarWorkspace
from test_research_api import api  # noqa: F401

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


def project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Office workflow"))


def item(text="Registration is open for Autumn courses for university students.", date="2026-10-01", **kw):
    return ResearchItem(item_id="it_a", run_id="run_a", project_id="p", platform="web", url="https://institute.example/programs/autumn", original_text=text,
                        published_at=date, retrieved_at="2026-10-22", **kw)


def entity(**kw):
    return {"entity_id": "ent_a", "name": "Harbor Institute", "status": "unknown", "public_links": ["https://institute.example/programs"], "claims": [], **kw}


@pytest.mark.parametrize("date,label,confidence", [("2026-10-01", "Active, high confidence", "high"), ("2025-04-01", "Active, medium confidence", "medium"),
                                                    ("2023-12-31", "Status unclear", "low"), ("", "Status unclear", "low"), ("2027-01-01", "Status unclear", "low")])
def test_activity_dates_never_use_retrieval_or_archive(date, label, confidence):
    post = item(date=date)
    result = assess(entity(), [{"item_id": post.item_id, "url": post.url}], {post.item_id: post}, archives=[{"last_ok": "2026-10-21"}], now=NOW)
    assert (result["label"], result["confidence"]) == (label, confidence)
    if not date or date > "2026-10-22":
        assert not result["last_activity_date"]
    assert result["archive_availability"]


def test_official_paths_scheduled_programs_and_negative_cues():
    post = item(date="", source_metadata={"event_dates": ["2026-11-01"]})
    result = assess(entity(), [{"item_id": post.item_id, "url": post.url}], {post.item_id: post}, now=NOW)
    assert result["label"] == "Active, high confidence" and not result["last_activity_date"]
    other = entity(public_links=["https://institute.example/another-institute"])
    assert assess(other, [{"item_id": post.item_id}], {post.item_id: post}, now=NOW)["status"] == "unknown"
    cancelled = item("All courses cancelled; the center closed.")
    result = assess(entity(), [{"item_id": cancelled.item_id}], {cancelled.item_id: cancelled}, now=NOW)
    assert result["status"] == "unknown" and result["needs_review"]


@pytest.mark.parametrize("status,label", [("closed", "Closed"), ("renamed", "Renamed/restructured"), ("relocated", "Relocated")])
def test_verified_lifecycle_separate_from_imported_status(status, label):
    assert assess(entity(status=status), [], {}, now=NOW)["status"] == "unknown"
    confirmed = entity(status=status, claims=[{"field": "status", "value": status, "review_state": "human_verified"}])
    result = assess(confirmed, [], {}, now=NOW)
    assert result["label"] == label and result["confidence"] == "high"


def test_rubric_has_unknowns_priority_precedence_and_human_review(tmp_path):
    p = project(tmp_path)
    rubric = load_rubric(p)
    assert classify_text("The organization has a website.", rubric) == []
    post = item("Commercial diplomacy workshop for engineers and university students, followed by a tea ceremony.")
    code_items(p, [post])
    rows = CodingStore(p).state(post.item_id)["codes"]
    assert [c["label"] for c in rows if c["field"] == "priority_tier"] == ["A"]
    assert {c["label"] for c in rows if c["field"] == "audience_group"} == {"students", "technical_professionals"}
    decide(p, post.item_id, "priority_tier", "A", "confirm", actor="reviewer")
    assert code_items(p, [post])["proposed"] == 0
    assert next(c for c in CodingStore(p).state(post.item_id)["codes"] if c["field"] == "priority_tier")["status"] == "confirmed"
    rubric["aliases"] = {"Successor Program": ["Programa anterior", "旧项目"]}
    rubric["version"] = 2
    save_rubric(p, rubric)
    aliases = classify_text("Programa anterior: teacher training for docentes", load_rubric(p))
    assert any(c["field"] == "program_alias" and c["label"] == "Successor Program" for c in aliases)
    with pytest.raises(ValueError):
        save_rubric(p, {"version": 1, "tiers": []})


def test_import_open_tbd_and_unresolved_labels_are_prescored_without_calls(tmp_path):
    p = project(tmp_path)
    csv = b"name,country,status,description,source_url\nHarbor Institute,Mexico,Open,Tea ceremony,https://example.org/a\nRiver Institute,Mexico,TBD,Commercial diplomacy,https://example.org/b\nHill Institute,Mexico,Suspended,Teacher training,https://example.org/c\n"
    preview = preview_upload(p, "institutions.csv", csv)
    assert preview["error_count"] == 0
    with patch("requests.sessions.Session.request", side_effect=AssertionError("No network allowed")):
        result = import_upload(p, preview["file_id"], mapping=preview["suggested_mapping"], network="subject", role="subject")
    assert result["added"] == 3 and len(result["assessments"]) == 3
    rows = list_entities(p.workspace)
    assert {r["status"] for r in rows} == {"active", "unknown"}
    assert all(r["activity"]["status"] == "unknown" for r in result["assessments"])
    assert any(c["label"] == "D" for r in result["assessments"] for c in r["programs"]["codes"])
    assert {ref["reported_status"] for r in rows for c in r["claims"] for ref in c["evidence_refs"]} == {"Open", "TBD", "Suspended"}
    assert import_status("Merged") == "unknown"


def test_wayback_is_cached_in_details_and_never_makes_it_active(tmp_path):
    p = project(tmp_path)
    detail = promote(p, {"name": "Harbor Institute", "public_links": ["https://institute.example/"]}, [], source_urls=[{"url": "https://institute.example/"}], actor="analyst")
    page_history(p, detail["entity_id"], history_fn=lambda url: {"url": url, "total": 10, "last_ok": "2026-10-21", "snapshots": []})
    result = institution_detail(p, detail["entity_id"])["activity_assessment"]
    assert result["archive_availability"][0]["total"] == 10 and result["status"] == "unknown"


def test_keyless_feed_helpers_known_account_seeds_and_locales(tmp_path):
    p = project(tmp_path)
    channel = "UC" + "a" * 22
    assert "channel_id=" + channel in youtube_feed("https://www.youtube.com/channel/" + channel)
    with pytest.raises(ValueError):
        youtube_feed("https://youtube.com/@unresolved")
    with pytest.raises(ValueError):
        youtube_feed("https://bad.example/channel/" + channel)
    assert "hl=es" in news_feed('"Harbor Institute"', "es", "MX")
    upsert_entity(p.workspace, {"name": "Harbor", "accounts": ["https://www.youtube.com/channel/" + channel]}, evidence_refs=[{"source_url": "https://example.org"}])
    seeds = feed_seeds(p, query="Harbor", language="es", country="MX")
    assert len(seeds["feeds"]) == 2


def test_capture_import_sanitizes_is_deduplicated_and_inbox_is_bounded(tmp_path):
    p = project(tmp_path)
    page = {"filename": "event.html", "source_url": "https://example.org/event?token=secret-value", "html": '<html><title>Teacher training</title><script>credential-secret</script><form>private-form</form><p>Commercial diplomacy workshop for engineers in Mexico.</p></html>'}
    with patch("requests.sessions.Session.request", side_effect=AssertionError("No network allowed")):
        result = capture_pages(p, [page])
    assert result["imported"] == 1 and not result["errors"]
    stored = p.load_items(result["run_id"])[0]
    assert "token" not in stored.url and "credential-secret" not in stored.original_text and "private-form" not in stored.original_text
    assert any(c["label"] == "A" for c in CodingStore(p).state(stored.item_id)["codes"])
    assert capture_pages(p, [page])["imported"] == 0
    updated = {**page, "html": page["html"].replace("engineers", "business leaders")}
    result2 = capture_pages(p, [updated])
    revised = p.load_items(result2["run_id"])[0]
    assert revised.item_id == stored.item_id and revised.changed_since_known and revised.known_from_run == result["run_id"]
    from sugar_core.evidence_desk import all_items
    assert len(all_items(p)) == 1 and "business leaders" in all_items(p)[0].original_text
    inbox = p.root / "capture-inbox"
    inbox.mkdir()
    (inbox / "another.html").write_text('<html><p>Teachers joined a new workshop in Mexico.</p></html>', encoding="utf-8")
    (inbox / "another.url.txt").write_text("https://example.org/second", encoding="utf-8")
    assert scan_inbox(p)["imported"] == 1
    assert (inbox / "another.html").is_file()
    assert scan_inbox(p)["imported"] == 0
    bad = capture_pages(p, [{"filename": "bad.html", "html": "Visible words"}])
    assert bad["errors"] and not bad["imported"]


def test_country_snapshot_offline_map_source_chains_flags_and_exports(tmp_path):
    p = project(tmp_path)
    run = p.new_run(plan=ResearchPlanSpec(research_question="Office demo"))
    post = item("Commercial diplomacy workshop for engineers in Mexico. Review candidate phrase.")
    post.run_id = run.run_id
    tag_geography(post, [])
    p.save_items(run.run_id, [post])
    rubric = load_rubric(p)
    rubric["alert_terms"] = ["Review candidate phrase"]
    save_rubric(p, rubric)
    code_items(p, [post])
    row = promote(p, {"name": "Harbor Institute", "country": "Mexico", "city": "Merida", "latitude": 20.97, "longitude": -89.59,
                       "public_links": ["https://institute.example/programs"]}, [(post, "")], actor="analyst")
    set_network(p, "reference", role="reference")
    for name, lat in [("American Space Demo", 20.99), ("Embassy Demo", 21.01)]:
        upsert_entity(p.workspace, {"name": name, "country": "Mexico", "network": "reference", "latitude": lat, "longitude": -89.6}, evidence_refs=[{"source_url": "https://example.org/reference"}])
    snapshot = country_snapshot(p, "Mexico")
    assert row["entity_id"] in snapshot["active_institutions"]
    assert len(snapshot["flagged_narratives"]) == 1
    route = snapshot["flagged_narratives"][0]["routing_candidates"][0]
    assert route["embassy"]["name"] == "Embassy Demo" and route["american_space"]["name"] == "American Space Demo"
    rendered = snapshot_html(snapshot)
    assert "<svg" in rendered and "<path" in rendered and "<script" not in rendered
    assert post.url in rendered and "country_named_in_text" not in rendered
    snapshot["country"] = '<script>alert("bad")</script>'
    assert "<script>" not in snapshot_html(snapshot)
    for result in [export_package(p, country="Mexico"), export_package(p, ai_only=True, country="Mexico")]:
        archive = p.workspace.root / result["archive"]
        assert verify_export(archive)["ok"]
        with zipfile.ZipFile(archive) as bundle:
            assert any(n.endswith("approved-tool-prompt.txt") for n in bundle.namelist())
            evidence = json.loads(bundle.read(next(n for n in bundle.namelist() if n.endswith("evidence-package.jsonl"))))
            assert evidence["item_id"] == post.item_id and evidence["activity_codes"]
    assert overview(p)["countries"] == ["Mexico"]


def test_structured_events_are_preserved_without_using_access_date():
    page = extract_page('<html><script type="application/ld+json">{"@graph":[{"@type":"EducationEvent","startDate":"2026-11-01"}]}</script><main>Course registration opens soon.</main></html>')
    assert page["event_dates"] == ["2026-11-01"] and not page["published"]
    cancelled = extract_page('<script type="application/ld+json">{"@type":"Event","startDate":"2026-11-01","eventStatus":"https://schema.org/EventCancelled"}</script><main>Course registration</main>')
    assert cancelled["cancelled_events"] == ["2026-11-01"]
    post = item(source_metadata=cancelled)
    assert assess(entity(), [{"item_id": post.item_id}], {post.item_id: post}, now=NOW)["status"] == "unknown"


def test_current_advertised_term_matches_group_method_without_inventing_a_day():
    post = item("Official institute website advertises Autumn 2026 courses.", date="")
    result = assess(entity(), [{"item_id": post.item_id}], {post.item_id: post}, now=NOW)
    assert result["label"] == "Active, high confidence" and not result["needs_review"]
    assert result["last_activity_date"] == "" and result["current_program_periods"] == ["Autumn 2026"]
    historic = item("The institute hosted courses in 2019. This retrospective describes its past events.")
    result = assess(entity(), [{"item_id": historic.item_id}], {historic.item_id: historic}, now=NOW)
    assert result["status"] == "unknown" and not result["last_activity_date"]


def test_imported_roots_use_previously_collected_evidence_without_creating_links(tmp_path):
    p = project(tmp_path)
    run = p.new_run(plan=ResearchPlanSpec(research_question="Programs"))
    post = item("Autumn 2026 programming and course registration.", date="")
    post.run_id = run.run_id
    p.save_items(run.run_id, [post])
    record = upsert_entity(p.workspace, {"name": "Harbor Institute", "country": "Mexico", "public_links": ["https://institute.example/programs"]}, evidence_refs=[{"source_url": "https://example.org/import"}])
    detail = institution_detail(p, record["entity_id"])
    assert detail["activity_assessment"]["status"] == "active" and not detail["links"]
    assert detail["activity_assessment"]["signals"][0]["association"].startswith("automatic")
    snapshot = country_snapshot(p, "Mexico")
    assert snapshot["coverage"]["source_items"] == 1 and snapshot["coverage"]["automatic_associations"] == 1
    assert snapshot["recent_programs"][0]["association"] == "automatic_institution_candidate"
    (p.root / "study-rubric.json").write_text("not JSON", encoding="utf-8")
    assert institution_detail(p, record["entity_id"])["activity_assessment"]["status"] == "active"
    with pytest.raises(ValueError, match="needs repair"):
        load_rubric(p, strict=True)


def test_digest_adds_new_narrative_and_priority_codes_then_stays_quiet(tmp_path):
    p = project(tmp_path)
    build_digest(p)
    rubric = load_rubric(p)
    rubric["alert_terms"] = ["Review candidate phrase"]
    save_rubric(p, rubric)
    code_items(p, [item("Commercial diplomacy: Review candidate phrase.")])
    digest = build_digest(p)
    assert digest["counts"]["new_narrative_flags"] == 1 and digest["counts"]["new_program_codes"] == 1
    assert "narrative review candidates" in digest["summary"]
    assert build_digest(p)["summary"] == "Nothing changed since the last check."


def test_office_api_is_keyless_and_configuration_uses_owner_role(tmp_path):
    import sugar_api
    p = project(tmp_path)
    with patch("requests.sessions.Session.request", side_effect=AssertionError("No network allowed")):
        status, payload = _research_routes("GET", "office", {}, {}, None, p)
        assert status == 200 and payload["institutions"] == 0
        status, payload = _research_routes("POST", "office/approved-ai", {}, {"country": "Mexico"}, None, p)
        assert status == 200 and "archive" in payload
        status, payload = _research_routes("POST", "office/feeds", {}, {"query": "Harbor", "language": "es", "country": "MX"}, None, p)
        assert status == 200 and payload["feeds"]
    assert sugar_api.SugarApiHandler._research_role("POST", "research", "office/rubric") == "owner"
    assert sugar_api.SugarApiHandler._research_role("GET", "research", "office") == "viewer"
    assert sugar_api.SugarApiHandler._research_role("POST", "research", "office/captures") == "analyst"
    with pytest.raises(ValueError):
        _research_routes("POST", "office/captures", {}, {"pages": ["bad"]}, None, p)


def test_http_capture_results_filters_and_standalone_snapshot_download(api):  # noqa: F811 - shared pytest fixture
    base, session, _ = api
    wid = session.post(f"{base}/api/workspaces", json={"name": "Office HTTP workflow"}).json()["id"]
    root = f"{base}/api/workspaces/{wid}"
    result = session.post(root + "/research/office/captures", json={"pages": [{"filename": "event.html", "source_url": "https://example.org/programs/event",
        "html": '<html><meta property="article:published_time" content="2026-10-01"><p>Commercial diplomacy workshop for engineers and university students in Mexico.</p></html>'}]})
    assert result.status_code == 200, result.text
    rid = result.json()["run_id"]
    kept = session.get(root + f"/runs/{rid}/results?priority_tier=A&audience_group=technical_professionals").json()
    assert kept["total"] == 1 and kept["items"][0]["activity_codes"]
    assert session.get(root + f"/runs/{rid}/results?priority_tier=D").json()["total"] == 0
    iid = kept["items"][0]["item_id"]
    recorded = session.post(root + "/research/institutions", json={"values": {"name": "Harbor Institute", "country": "Mexico", "latitude": 20.97, "longitude": -89.59,
                        "public_links": ["https://example.org/programs"]}, "evidence": [{"run_id": rid, "item_id": iid}]} )
    assert recorded.status_code == 200, recorded.text
    exported = session.post(root + "/research/office/snapshot", json={"country": "Mexico"})
    assert exported.status_code == 200, exported.text
    file = session.get(root + "/files/" + exported.json()["directory"] + "/country-snapshot.html")
    assert file.status_code == 200 and "Harbor Institute" in file.text and "<svg" in file.text
    assert "attachment" in file.headers["Content-Disposition"]


def test_youtube_channel_feed_retains_description_video_type_and_account_association(tmp_path):
    from sugar_core.open_sources import collect_rss
    from sugar_core.institution_activity import candidate_links, evidence_index
    from sugar_core.research_items import record_to_item
    from test_open_sources import FakeResponse, FakeSession
    channel = "UC" + "a" * 22
    xml = f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/"><title>Harbor Institute</title><yt:channelId>{channel}</yt:channelId><entry><id>yt:video:one</id><title>Autumn workshop</title><published>2026-10-01</published><link href="https://www.youtube.com/watch?v=one"/><media:group><media:description>Teacher training workshop</media:description></media:group></entry></feed>'
    feed = youtube_feed(channel)
    records = collect_rss(search_terms=["Harbor Institute"], feeds=[feed], session=FakeSession(FakeResponse(content=xml.encode())))
    assert len(records) == 1 and records[0].content_type == "video" and "Teacher training" in records[0].original_text
    post, _ = record_to_item(records[0], run_id="run_a", project_id="p", query_id="q", query_text="Harbor Institute", dispatched="Harbor Institute")
    row = entity(accounts=["https://youtube.com/channel/" + channel], public_links=[])
    links = candidate_links(row, {post.item_id: post}, evidence_index({post.item_id: post}))
    assert links
    result = assess(row, links, {post.item_id: post}, now=NOW)
    assert result["signals"][0]["kind"] == "known_account_post" and result["last_activity_date"] == "2026-10-01"


def test_priority_reassessment_supersedes_proposals_and_retains_versioned_human_decisions(tmp_path):
    p = project(tmp_path)
    post = item("A tea ceremony for the general public.")
    code_items(p, [post])
    assert any(c["label"] == "D" for c in CodingStore(p).state(post.item_id)["codes"] if c["field"] == "priority_tier")
    post.original_text = "Commercial diplomacy with business leaders."
    code_items(p, [post])
    assert [c["label"] for c in CodingStore(p).state(post.item_id)["codes"] if c["field"] == "priority_tier"] == ["A"]
    decide(p, post.item_id, "priority_tier", "A", "confirm", actor="reviewer")
    rubric = load_rubric(p)
    rubric["version"] += 1
    rubric["tiers"][0]["terms"] = []
    save_rubric(p, rubric)
    code_items(p, [post])
    kept = next(c for c in CodingStore(p).state(post.item_id)["codes"] if c["field"] == "priority_tier" and c["label"] == "A")
    assert kept["status"] == "confirmed" and not kept["rubric_current"] and kept["rubric_version"] == rubric["version"] - 1
    decide(p, post.item_id, "priority_tier", "B", "confirm", quote="business leaders", actor="reviewer")
    codes = [c for c in CodingStore(p).state(post.item_id)["codes"] if c["field"] == "priority_tier"]
    assert [c["label"] for c in codes if c["status"] == "confirmed"] == ["B"]
    assert any(c["label"] == "A" and c["status"] == "rejected" for c in codes)


def test_capture_inbox_does_not_follow_an_external_directory(tmp_path, monkeypatch):
    p = project(tmp_path)
    inbox = p.root / "capture-inbox"
    external = tmp_path / "outside-project"
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda self, *args, **kwargs: external if self == inbox else original(self, *args, **kwargs))
    with pytest.raises(ValueError, match="inside this project"):
        scan_inbox(p)
