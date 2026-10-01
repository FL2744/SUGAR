import json

import pytest
import requests

import sugar_api
from sugar_core import profiles
from sugar_core.query_planner import generate_queries
from sugar_core.reference_registry import list_entities
from sugar_core.research_plan import ResearchPlanSpec
from sugar_core.networks import network_settings
from sugar_core.monitoring import list_monitors
from sugar_core.activity_coding import propose_by_pattern
from sugar_core.research_items import ResearchItem
from test_research_api import api   # noqa: F401
from test_workbench import bench, project as make_project

PROFILE = {
    "profile_version": 1, "name": "Example method", "description": "A reusable method.",
    "networks": [{"name": "subject-net", "role": "subject"}, {"name": "ref-net", "role": "reference", "label": "Reference"}],
    "request": "Search cultural centers in Kenya on all platforms.",
    "queries": ["reading room programs"],
    "sources": {"web_seeds": ["https://site.example/", "ftp://nope"], "rss_feeds": ["https://site.example/feed"]},
    "glossary": {"cultural centers": {"fr": "centres culturels", "synonyms": ["cultural hubs"]}},
    "coding_terms": {"audience": {"educators": ["tutors"]}, "program": {"steam": ["maker space"]}},
    "relevance": {"include": ["cultural"], "exclude": ["sports"]},
    "institutions": [{"name": "Seed Center", "network": "subject-net", "country": "Kenya", "city": "Nairobi", "source_url": "https://wiki.example/Seed"}],
    "monitors": [{"name": "Weekly", "cadence_hours": 168}],
}


def test_a_profile_is_checked_bounded_and_free_of_credentials():
    clean = profiles.parse_profile(json.dumps(PROFILE))
    assert clean["sources"]["web_seeds"] == ["https://site.example/"] and clean["networks"][1]["role"] == "reference"
    assert clean["glossary"]["cultural centers"]["fr"] == "centres culturels"
    for bad, message in ((b"not json", "valid JSON"), (b"[]", "JSON object"), (json.dumps({**PROFILE, "profile_version": 9}), "version"),
                         (json.dumps({**PROFILE, "api_key": "sk-1"}), "credentials"), (json.dumps({**PROFILE, "name": " "}), "name"),
                         (json.dumps({**PROFILE, "institutions": [{"name": "No source"}]}), "source address"),
                         (json.dumps({**PROFILE, "coding_terms": {"audience": {"made_up": ["x"]}}}), "standard audience label")):
        with pytest.raises(ValueError, match=message):
            profiles.parse_profile(bad)
    with pytest.raises(ValueError, match="1 MB"):
        profiles.parse_profile("x" * 1_100_000)


def test_applying_a_profile_sets_up_the_whole_method(tmp_path):
    wb, proj = bench(tmp_path), make_project(tmp_path)
    done = profiles.apply_profile(wb, proj, PROFILE, actor="owner@example.org")
    assert {"2 network(s)", "research plan"} <= set(done["applied"]) and any("starting institution" in a for a in done["applied"]) and any("monitor" in a for a in done["applied"])
    assert {n: v["role"] for n, v in network_settings(proj).items()} == {"subject-net": "subject", "ref-net": "reference"}
    settings = proj.meta()["settings"]
    assert settings["web_seeds"] == ["https://site.example/"] and settings["relevance"]["exclude"] == ["sports"] and settings["coding_terms"]["program"]["steam"] == ["maker space"]
    plan = proj.load_plan()
    assert plan.geography == ["Kenya"] and any(q["text"] == "reading room programs" and q["origin"] == "analyst" for q in plan.queries)
    assert plan.extra["glossary"]["cultural centers"]["fr"] == "centres culturels"
    assert [e["name"] for e in list_entities(proj.workspace)] == ["Seed Center"] and list_entities(proj.workspace)[0]["claims"][0]["review_state"] == "unreviewed"
    assert list_monitors(proj)[0]["name"] == "Weekly"


def test_profile_vocabulary_reaches_query_generation_and_activity_coding():
    plan = ResearchPlanSpec.from_dict({"topic": "cultural centers", "languages": ["fr"], "extra": {"glossary": {"cultural centers": {"fr": "centres culturels"}}}})
    assert any(q.text == "centres culturels" and q.language == "fr" for q in generate_queries(plan))
    item = ResearchItem(item_id="it_a", run_id="r", project_id="p", platform="web", url="https://x.example", original_text="The tutors ran a maker space session.")
    base = {(p["field"], p["label"]) for p in propose_by_pattern(item)}
    extra = {(p["field"], p["label"]) for p in propose_by_pattern(item, {"audience": {"educators": ["tutors"]}, "program": {"steam": ["maker space"]}})}
    assert ("audience", "educators") not in base and {("audience", "educators"), ("program", "steam")} <= extra


def test_export_roundtrips_without_credentials_and_can_seed_a_new_project(tmp_path):
    wb, source = bench(tmp_path / "a"), make_project(tmp_path / "a")
    profiles.apply_profile(wb, source, PROFILE)
    exported = profiles.export_profile(wb, source, name="Copy", include_institutions=True)
    assert exported["name"] == "Copy" and exported["institutions"][0]["source_url"] == "https://wiki.example/Seed" and exported["monitors"][0]["cadence_hours"] == 168
    assert "token" not in json.dumps(exported).lower() and "sk-" not in json.dumps(exported)
    wb2, target = bench(tmp_path / "b"), make_project(tmp_path / "b")
    profiles.apply_profile(wb2, target, profiles.parse_profile(exported))
    assert {n for n in network_settings(target)} == {"subject-net", "ref-net"} and target.load_plan().geography == ["Kenya"]


def test_http_apply_is_owner_only_and_export_is_readable(api):   # noqa: F811
    base, session, _ = api
    wid = session.post(f"{base}/api/workspaces", json={"name": "Team"}).json()["id"]
    profile = sugar_api.get_workspace_root() / wid / ".sugar" / "project-profile.json"
    profile.parent.mkdir(exist_ok=True)
    profile.write_text(json.dumps({"members": [{"name": "Ana Analyst", "email": "a@example.org", "role": "Analyst"}]}))
    token = session.post(f"{base}/api/workspaces/{wid}/access", json={"email": "a@example.org"}).json()["token"]
    analyst = requests.Session()
    analyst.headers["Authorization"] = f"Bearer {token}"
    url = f"{base}/api/workspaces/{wid}/research/profile"
    assert analyst.post(url, json={"profile": PROFILE}).status_code == 403
    assert analyst.get(url).status_code == 200
    applied = session.post(url, json={"profile": PROFILE})
    assert applied.status_code == 200 and "research plan" in applied.json()["applied"]
    assert session.post(url, json={"profile": {**PROFILE, "token": "x"}}).status_code == 400
    exported = session.get(url, params={"institutions": "1"}).json()["profile"]
    assert exported["networks"] and exported["institutions"][0]["name"] == "Seed Center"
