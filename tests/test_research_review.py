import json

import pytest
import requests

import sugar_api
from sugar_core.research_review import ReviewStore, replay
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace
from test_research_api import api, wait_done   # noqa: F401  (fixture reuse)


def store(tmp_path):
    return ReviewStore(ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Review project")))


def test_verdicts_tags_and_comments_replay_in_order(tmp_path):
    s = store(tmp_path)
    s.apply("it_a", {"kind": "verdict", "verdict": "relevant"}, author="ana@example.org")
    s.apply("it_a", {"kind": "tag_add", "tag": "#Reading Room"}, author="ana@example.org")
    s.apply("it_a", {"kind": "comment", "text": "Cites the opening date."}, author="vera@example.org")
    s.apply("it_a", {"kind": "verdict", "verdict": "follow_up"}, author="vera@example.org")     # latest verdict wins
    s.apply("it_b", {"kind": "verdict", "verdict": "not_relevant"}, author="ana@example.org")
    state = s.state("it_a")
    assert state["verdict"] == "follow_up" and state["verdict_by"] == "vera@example.org" and state["tags"] == ["reading room"]
    assert [c["author"] for c in state["comments"]] == ["vera@example.org"]
    assert s.summary()["verdicts"] == {"relevant": 0, "not_relevant": 1, "follow_up": 1} and s.summary()["tags"] == {"reading room": 1}
    s.apply("it_a", {"kind": "tag_remove", "tag": "reading room"}, author="ana@example.org")
    assert s.state("it_a")["tags"] == []
    s.apply("it_a", {"kind": "verdict", "verdict": ""}, author="ana@example.org")                # clearing is allowed
    assert s.state("it_a")["verdict"] == ""
    assert replay(s.events())["it_b"]["verdict"] == "not_relevant"                                  # the log is append-only history


def test_invalid_review_actions_are_rejected(tmp_path):
    s = store(tmp_path)
    for bad in ({"kind": "verdict", "verdict": "great"}, {"kind": "tag_add", "tag": "  #"}, {"kind": "comment", "text": "  "}, {"kind": "nope"}):
        with pytest.raises(ValueError):
            s.apply("it_a", bad, author="x")
    with pytest.raises(ValueError):
        s.apply("", {"kind": "comment", "text": "hi"}, author="x")
    for i in range(20):
        s.apply("it_a", {"kind": "tag_add", "tag": f"t{i}"}, author="x")
    with pytest.raises(ValueError, match="at most"):
        s.apply("it_a", {"kind": "tag_add", "tag": "one-too-many"}, author="x")


def test_review_over_http_enforces_roles_and_records_the_real_author(api):   # noqa: F811
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
    url = f"{base}/api/workspaces/{wid}/research/review"
    assert viewer.post(url, json={"item_id": "it_x", "kind": "comment", "text": "hello"}).status_code == 403        # viewers read only
    # a reviewer cannot pose as someone else: the author comes from the token, not the request
    ok = reviewer.post(url, json={"item_id": "it_x", "kind": "comment", "text": "Looks right", "author": "Someone Else", "_author": "spoof"})
    assert ok.status_code == 200
    comment = ok.json()["review"]["comments"][0]
    assert comment["author"] == "r@example.org" and comment["text"] == "Looks right"
    assert viewer.get(url, params={"item_id": "it_x"}).json()["review"]["comments"][0]["author"] == "r@example.org"   # viewers can read
    assert reviewer.post(url, json={"item_id": "it_x", "kind": "verdict", "verdict": "bogus"}).status_code == 400
    assert session.post(url, json={"item_id": "it_x", "kind": "verdict", "verdict": "relevant", "author": "Alejandro"}).json()["summary"]["verdicts"]["relevant"] == 1



def test_results_carry_review_state_filters_and_per_run_counts(tmp_path):
    from test_workbench import bench, prepare, project as make_project
    wb, proj = bench(tmp_path), make_project(tmp_path)
    prepare(wb, proj)
    run = wb.start_run(proj, wait=True)
    run_id = run["run"]["run_id"] if "run" in run else run["run_id"]
    items = wb.results(proj, run_id)["items"] or [i for g in wb.results(proj, run_id, group_by="platform")["groups"] for i in g["items"]]
    assert len(items) >= 2
    first, second = items[0]["item_id"], items[1]["item_id"]
    proj.review.apply(first, {"kind": "verdict", "verdict": "relevant"}, author="ana@example.org")
    proj.review.apply(first, {"kind": "tag_add", "tag": "keep"}, author="ana@example.org")
    proj.review.apply("it_from_another_run", {"kind": "verdict", "verdict": "relevant"}, author="ana@example.org")
    everything = wb.results(proj, run_id, group_by="none")
    assert everything["review"]["reviewed"] == 1                                # only this run's items are counted
    row = next(i for i in everything["items"] if i["item_id"] == first)
    assert row["review"] == {"verdict": "relevant", "tags": ["keep"], "comments": 0}
    assert [i["item_id"] for i in wb.results(proj, run_id, verdict="relevant")["items"]] == [first]
    assert second in [i["item_id"] for i in wb.results(proj, run_id, verdict="unreviewed")["items"]]
    assert [i["item_id"] for i in wb.results(proj, run_id, tag="keep")["items"]] == [first]
