import json

import pytest
import requests

import sugar_api
from sugar_core import activity_coding as ac
from sugar_core import institutions as inst
from sugar_core.llm_providers import LLMBudget, LLMProvider, ProviderProfile
from sugar_core.research_items import ResearchItem
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace
from test_research_api import api   # noqa: F401


def project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Coding"))


def make_item(item_id, text, *, run_id="run_1", url=None):
    return ResearchItem(item_id=item_id, run_id=run_id, project_id="p", platform="web", url=url or f"https://site.example/{item_id}", original_text=text,
                        published_at="2025-03-01T00:00:00Z", retrieved_at="2025-04-01T00:00:00Z")


class FakeJSON(LLMProvider):
    def __init__(self, items):
        super().__init__(ProviderProfile(id="f", type="local", endpoint="http://localhost:1/v1", model="m"))
        self.payload, self.calls = {"items": items}, 0

    def chat_json(self, messages, schema, **kw):
        self.calls += 1
        return self.payload, None


def by_field(proposals, field):
    return {p["label"]: p for p in proposals if p["field"] == field}


def test_patterns_label_audiences_programs_activity_and_reported_attendance():
    item = make_item("it_a", "The center held a free English class for university students on Monday. More than 1,200 participants joined the robotics workshop. "
                             "Registration is open to the public.")
    proposals = ac.propose_by_pattern(item)
    assert set(by_field(proposals, "audience")) == {"university_students", "general_public"}
    assert {"language_learning", "steam"} <= set(by_field(proposals, "program"))
    assert by_field(proposals, "attendance")["1200"]["quote"].startswith("More than 1,200")
    assert "workshop" in by_field(proposals, "activity_type")
    assert all(p["quote"] and p["method"] == "pattern" for p in proposals)


def test_vague_words_and_names_do_not_produce_labels():
    item = make_item("it_b", "Students enjoyed the world-class media coverage of the stem of the plant at the Language Institute.")
    labels = {(p["field"], p["label"]) for p in ac.propose_by_pattern(item)}
    assert not any(f in {"audience"} for f, _ in labels) and ("program", "steam") not in labels and ("activity_type", "class") not in labels


def test_other_languages_are_matched():
    zh = ac.propose_by_pattern(make_item("it_c", "学院为大学生举办了汉语课程和书法展览，共有300名学员参加。"))
    assert {"university_students"} <= set(by_field(zh, "audience")) and {"language_learning", "cultural_programming"} <= set(by_field(zh, "program")) and by_field(zh, "attendance")["300"]
    es = ac.propose_by_pattern(make_item("it_d", "Un taller para profesores y estudiantes universitarios con 80 participantes."))
    assert {"educators", "university_students"} <= set(by_field(es, "audience")) and by_field(es, "attendance")["80"]


def test_model_codes_are_grounded_in_the_item_and_limited_to_the_labels():
    items = [make_item("it_a", "Registration opened for the cybersecurity bootcamp for young professionals. 45 participants attended."), make_item("it_b", "Unrelated.")]
    provider = FakeJSON([{"item": 1, "codes": [
        {"field": "audience", "label": "young_professionals", "quote": "bootcamp for young professionals"},
        {"field": "program", "label": "steam", "quote": "never said this"},
        {"field": "program", "label": "not_a_real_label", "quote": "Registration opened"},
        {"field": "attendance", "label": "45", "quote": "45 participants attended"},
        {"field": "attendance", "label": "450", "quote": "45 participants attended"}]}])
    rows, warnings = ac.propose_by_model(items, provider, LLMBudget(3))
    assert {(r["field"], r["label"]) for r in rows["it_a"]} == {("audience", "young_professionals"), ("attendance", "45")} and not warnings
    spent = LLMBudget(1)
    spent.take(1)
    none, warnings = ac.propose_by_model(items, provider, spent)
    assert none == {} and "budget" in warnings[0]


def test_confirming_rejecting_and_applying_to_an_institution(tmp_path):
    p = project(tmp_path)
    item = make_item("it_a", "The Harbor Reading Room held a language class and a workshop for university students.")
    summary = ac.code_items(p, [item])
    assert summary["proposed"] >= 3 and summary["with_codes"] == 1
    state = ac.CodingStore(p).state("it_a")
    assert all(c["status"] == "proposed" for c in state["codes"])
    ac.decide(p, "it_a", "audience", "university_students", "confirm", actor="vera@example.org", run_id="run_1")
    ac.decide(p, "it_a", "program", "language_learning", "confirm", actor="vera@example.org", run_id="run_1")
    ac.decide(p, "it_a", "activity_type", "workshop", "reject", actor="vera@example.org", run_id="run_1")
    codes = {(c["field"], c["label"]): c for c in ac.CodingStore(p).state("it_a")["codes"]}
    assert codes[("audience", "university_students")]["status"] == "confirmed" and codes[("audience", "university_students")]["decided_by"] == "vera@example.org"
    assert codes[("activity_type", "workshop")]["status"] == "rejected"
    with pytest.raises(ValueError, match="not proposed"):
        ac.decide(p, "it_a", "program", "steam", "reject", actor="x")
    ac.decide(p, "it_a", "program", "cultural_programming", "confirm", actor="vera", quote="held a language class and a workshop")       # an analyst adds a code with supporting words
    detail = inst.promote(p, {"name": "Harbor Reading Room"}, [(item, "Harbor Reading Room held")], actor="ana")
    result = ac.apply_to_institution(p, detail["entity_id"], item, actor="vera@example.org")
    assert set(result["applied"]) == {"university_students", "language_learning", "cultural_programming"}
    after = inst.institution_detail(p, detail["entity_id"])
    assert "university_students" in after["audiences"] and "language_learning" in after["programs"]
    claim = after["fields"]["audiences"]["claims"][0]
    assert claim["review_state"] == "human_verified" and claim["evidence"][0]["quote"] and claim["evidence"][0]["item_id"] == "it_a"
    summary = ac.CodingStore(p).summary({"it_a"})
    assert summary["confirmed"]["audience"] == {"university_students": 1} and summary["items_coded"] == 1


def test_apply_needs_a_confirmed_code(tmp_path):
    p = project(tmp_path)
    item = make_item("it_a", "A class for university students.")
    detail = inst.promote(p, {"name": "X Center"}, [(item, "A class")], actor="a")
    ac.code_items(p, [item])
    with pytest.raises(ValueError, match="Confirm at least one"):
        ac.apply_to_institution(p, detail["entity_id"], item, actor="a")


def test_http_roles_and_flow(api):   # noqa: F811
    base, session, _ = api
    wid = session.post(f"{base}/api/workspaces", json={"name": "Team"}).json()["id"]
    profile = sugar_api.get_workspace_root() / wid / ".sugar" / "project-profile.json"
    profile.parent.mkdir(exist_ok=True)
    profile.write_text(json.dumps({"members": [{"name": "Vera Viewer", "email": "v@example.org", "role": "Viewer"}, {"name": "Rae Reviewer", "email": "r@example.org", "role": "Reviewer"}]}))
    sessions = {}
    for email in ("v@example.org", "r@example.org"):
        token = session.post(f"{base}/api/workspaces/{wid}/access", json={"email": email}).json()["token"]
        sessions[email] = requests.Session()
        sessions[email].headers["Authorization"] = f"Bearer {token}"
    viewer, reviewer = sessions["v@example.org"], sessions["r@example.org"]
    root = f"{base}/api/workspaces/{wid}/research/coding"
    assert viewer.get(root).status_code == 200
    body = {"item_id": "it_x", "field": "audience", "label": "educators", "decision": "confirm", "quote": "for teachers"}
    assert viewer.post(f"{root}/decide", json=body).status_code == 403
    done = reviewer.post(f"{root}/decide", json=body)
    assert done.status_code == 200 and done.json()["codes"][0]["decided_by"] == "r@example.org"
    assert reviewer.post(f"{root}/run", json={"run_id": "nope"}).status_code == 403      # running coding is an analyst action
    assert session.post(f"{root}/run", json={"run_id": "nope", "mode": "deterministic"}).status_code == 404
