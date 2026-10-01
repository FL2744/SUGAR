import json

import pytest
import requests

import sugar_api
from sugar_core import institutions as inst
from sugar_core.llm_providers import LLMBudget, LLMProvider, ProviderProfile
from sugar_core.research_items import ResearchItem
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace
from test_research_api import api   # noqa: F401  (fixture reuse)


def project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Institutions"))


def make_item(item_id, text, *, url=None, run_id="run_1", published="2025-03-10T09:00:00Z", **kw):
    return ResearchItem(item_id=item_id, run_id=run_id, project_id="p", platform="rss", url=url if url is not None else f"https://site-{item_id}.example/a",
                        original_text=text, published_at=published, retrieved_at="2025-04-01T00:00:00Z", query="reading room", **kw)


class FakeJSON(LLMProvider):
    def __init__(self, rows):
        super().__init__(ProviderProfile(id="f", type="local", endpoint="http://localhost:1/v1", model="m"))
        self.rows, self.calls = rows, 0

    def chat_json(self, messages, schema, **kw):
        self.calls += 1
        return {"institutions": self.rows}, None


def test_evidence_needs_a_public_address_and_a_real_quote():
    item = make_item("it_a", "The Harbor Reading Room opened in March.")
    ref = inst.item_evidence(item, "Harbor Reading Room opened")
    assert ref["source_url"].startswith("https://") and ref["quote"] == "Harbor Reading Room opened" and ref["item_id"] == "it_a"
    with pytest.raises(ValueError, match="does not appear"):
        inst.item_evidence(item, "a sentence the item never contained")
    with pytest.raises(ValueError, match="public web address"):
        inst.item_evidence(make_item("it_b", "text", url=""), "")


def test_promote_verify_and_confidence_grow_with_evidence(tmp_path):
    p = project(tmp_path)
    one = make_item("it_a", "The Harbor Reading Room reopened this spring in Exampleland.")
    two = make_item("it_b", "Harbor Reading Room hosts weekly language classes.")
    detail = inst.promote(p, {"name": "Harbor Reading Room", "network": "example-net", "city": "Harbor City", "country": "Exampleland", "status": "active",
                              "program_domains": ["language learning"], "audiences": ["university students"]}, [(one, "Harbor Reading Room reopened")], actor="ana@example.org")
    assert detail["status"] == "active" and detail["confidence"]["level"] == "low" and detail["source_count"] == 1
    assert detail["programs"] == ["language_learning"] and detail["audiences"] == ["university_students"]
    eid = detail["entity_id"]
    detail = inst.promote(p, {}, [(two, "hosts weekly language classes")], actor="ana@example.org", entity_id=eid)
    assert detail["source_count"] == 2 and detail["activity"]["items"] == 2 and detail["confidence"]["level"] == "medium"
    status_claim = detail["fields"]["status"]["claims"][0]
    detail = inst.verify(p, eid, status_claim["claim_id"], "human_verified", actor="vera@example.org", note="Checked the source page")
    assert detail["confidence"]["level"] == "high" and detail["last_verified"] and "status" in detail["confidence"]["verified_fields"]
    assert detail["fields"]["status"]["claims"][0]["reviewer"] == "vera@example.org"
    listing = inst.list_institutions(p)
    assert listing["total"] == 1 and listing["unplaced"] == 1 and listing["institutions"][0]["confidence"]["level"] == "high"


def test_conflicting_claims_lower_confidence_and_are_reported(tmp_path):
    p = project(tmp_path)
    a, b = make_item("it_a", "The Center is active."), make_item("it_b", "The Center has closed.")
    detail = inst.promote(p, {"name": "Valley Center", "status": "active"}, [(a, "is active")], actor="x")
    detail = inst.promote(p, {"status": "closed"}, [(b, "has closed")], actor="x", entity_id=detail["entity_id"])
    assert "status" in detail["conflicts"] and detail["status"] == "unknown"        # unresolved until a person decides
    assert any("disagree" in r for r in detail["confidence"]["reasons"])
    closed = next(c for c in detail["fields"]["status"]["claims"] if c["value"] == "closed")
    detail = inst.verify(p, detail["entity_id"], closed["claim_id"], "human_verified", actor="vera")
    assert detail["status"] == "closed" and detail["lifecycle"]


def test_merge_moves_claims_and_hides_the_duplicate(tmp_path):
    p = project(tmp_path)
    a = inst.promote(p, {"name": "Harbor Reading Room", "country": "Exampleland"}, [(make_item("it_a", "Harbor Reading Room is open."), "is open")], actor="x")
    b = inst.promote(p, {"name": "Harbor Reading Room (Main Branch)", "city": "Harbor City"}, [(make_item("it_b", "Main Branch news."), "Main Branch")], actor="x")
    merged = inst.merge(p, a["entity_id"], b["entity_id"], actor="vera", reason="Same place")
    assert merged["city"] == "Harbor City" and "Harbor Reading Room (Main Branch)" in merged["aliases"] and merged["activity"]["items"] == 2
    assert inst.list_institutions(p)["total"] == 1
    with pytest.raises(ValueError):
        inst.merge(p, a["entity_id"], b["entity_id"], actor="vera")


def test_pattern_candidates_find_names_countries_and_status_hints():
    items = [make_item("it_a", "The Lakeside Cultural Center in Kenya was closed last year. Join the Riverside Language Institute for classes."),
             make_item("it_b", "Lakeside Cultural Center hosted a workshop. 北方语言学院举办了讲座。")]
    rows = {c["name"]: c for c in inst.pattern_candidates(items)}
    assert "Lakeside Cultural Center" in rows and rows["Lakeside Cultural Center"]["mentions"] == 2 and rows["Lakeside Cultural Center"]["country"] == "Kenya"
    assert rows["Lakeside Cultural Center"]["status_hint"] == "closed"
    assert "Riverside Language Institute" in rows and "北方语言学院" in rows
    assert all("quote" in e for c in rows.values() for e in c["evidence"])


def test_model_suggestions_must_quote_the_item_and_respect_the_budget():
    items = [make_item("it_a", "Registration opened at the Delta Skills Academy on Monday."), make_item("it_b", "Nothing relevant here.")]
    provider = FakeJSON([{"name": "Delta Skills Academy", "type": "academy", "city": "Delta", "country": "Exampleland", "status": "active", "quote": "opened at the Delta Skills Academy", "item": 1},
                         {"name": "Invented Institute", "quote": "a quote that was never written", "item": 1},
                         {"name": "Misnumbered", "quote": "Nothing relevant here.", "item": 9}])
    found, warnings = inst.ai_candidates(items, provider, LLMBudget(5))
    assert [c["name"] for c in found] == ["Delta Skills Academy"] and found[0]["status_hint"] == "active" and not warnings
    spent = LLMBudget(1)
    spent.take(1)
    none, warnings = inst.ai_candidates(items, provider, spent)
    assert none == [] and warnings and "budget" in warnings[0]


def test_geocoding_places_only_what_it_can_and_never_breaks(tmp_path):
    p = project(tmp_path)
    inst.promote(p, {"name": "Harbor Reading Room", "city": "Harbor City", "country": "Exampleland"}, [(make_item("it_a", "Harbor Reading Room is open."), "is open")], actor="x")
    inst.promote(p, {"name": "Nowhere Center", "country": "Atlantis"}, [(make_item("it_b", "Nowhere Center is open."), "is open")], actor="x")
    inst.promote(p, {"name": "Unplaceable", "status": "active"}, [(make_item("it_c", "Unplaceable is open."), "is open")], actor="x")

    def fake(query, cache):
        if "Atlantis" in query:
            raise RuntimeError("service unavailable")
        return {"latitude": 12.5, "longitude": 45.5, "display_name": query}
    result = inst.geocode_missing(p, geocoder=fake)
    assert len(result["placed"]) == 1 and len(result["failed"]) == 1
    placed = [r for r in inst.list_institutions(p)["institutions"] if r["placed"]]
    assert len(placed) == 1 and placed[0]["location_precision"] == "city" and placed[0]["latitude"] == 12.5


def test_http_roles_authorship_and_candidate_flow(api):   # noqa: F811
    base, session, _ = api
    wid = session.post(f"{base}/api/workspaces", json={"name": "Team"}).json()["id"]
    profile = sugar_api.get_workspace_root() / wid / ".sugar" / "project-profile.json"
    profile.parent.mkdir(exist_ok=True)
    profile.write_text(json.dumps({"members": [{"name": "Vera Viewer", "email": "v@example.org", "role": "Viewer"},
                                               {"name": "Rae Reviewer", "email": "r@example.org", "role": "Reviewer"}]}))
    sessions = {}
    for email in ("v@example.org", "r@example.org"):
        token = session.post(f"{base}/api/workspaces/{wid}/access", json={"email": email}).json()["token"]
        sessions[email] = requests.Session()
        sessions[email].headers["Authorization"] = f"Bearer {token}"
    viewer, reviewer = sessions["v@example.org"], sessions["r@example.org"]
    url = f"{base}/api/workspaces/{wid}/research/institutions"
    assert session.get(url).json()["total"] == 0 and viewer.get(url).status_code == 200
    assert viewer.post(url, json={"values": {"name": "X Center"}, "evidence": []}).status_code == 403          # analysts and owners record institutions
    assert reviewer.post(url, json={"values": {"name": "X Center"}, "evidence": []}).status_code == 403
    assert session.post(url, json={"values": {"name": "X Center"}, "evidence": []}).status_code == 400            # evidence is required
    assert session.post(url, json={"values": {"name": "X Center"}, "evidence": [{"run_id": "run_none", "item_id": "it_zzz"}]}).status_code in {404}
    assert session.post(f"{url}/candidates", json={"run_id": "run_none", "mode": "deterministic"}).status_code == 404
    assert session.get(f"{url}/00000000-0000-0000-0000-000000000000").status_code == 404


def test_an_analyst_can_cite_an_official_page_directly(tmp_path):
    p = project(tmp_path)
    detail = inst.promote(p, {"name": "Valley Library", "status": "active"}, [], actor="ana", source_urls=[{"url": "https://library.example.org/about", "note": "Official about page"}])
    assert detail["source_count"] == 1 and detail["evidence"][0]["kind"] == "analyst_cited"
    with pytest.raises(ValueError, match="http"):
        inst.promote(p, {"name": "Bad"}, [], actor="ana", source_urls=[{"url": "file:///etc/passwd"}])
    with pytest.raises(ValueError, match="at least one"):
        inst.promote(p, {"name": "Nothing"}, [], actor="ana")
