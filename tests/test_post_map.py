from sugar_core import post_map
from sugar_core.country_centroids import centroid
from sugar_core.research_items import ResearchItem, tag_geography
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace


def item(item_id, text, **kw):
    it = ResearchItem(item_id=item_id, run_id="run_1", project_id="p", platform="mastodon", author="@ana", original_text=text, **{"published_at": "2026-03-01T10:00:00Z", **kw})
    tag_geography(it, [])
    return it


def test_pins_keep_origin_and_targets_apart(tmp_path):
    project = ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Pins"))
    with_coords = item("it_1", "A talk about study options in Belgium and France", coordinates={"lat": -1.29, "lon": 36.82})
    only_text = item("it_2", "Everyone in Belgium is talking about it")
    nothing = item("it_3", "No places here at all")
    result = post_map.post_pins(project, [with_coords, only_text, nothing])
    by_id = {p["item_id"]: p for p in result["pins"]}
    assert set(by_id) == {"it_1", "it_2"}
    assert by_id["it_1"]["placement"] == "origin" and by_id["it_1"]["origin"]["precision"] == "exact"
    assert {t["name"] for t in by_id["it_1"]["targets"]} == {"Belgium", "France"}
    assert by_id["it_2"]["placement"] == "mentioned" and by_id["it_2"]["origin"] is None
    assert result["targets"][0]["name"] == "Belgium" and result["targets"][0]["posts"] == 2
    assert len(result["flows"]) == 2 and all(f["posts"] == 1 for f in result["flows"])
    assert by_id["it_1"]["verified"] is False


def test_a_relevant_verdict_shows_as_verified_with_who(tmp_path):
    project = ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Pins"))
    project.review.apply("it_2", {"kind": "verdict", "verdict": "relevant"}, author="Dana")
    pin = post_map.post_pins(project, [item("it_2", "Belgium again")])["pins"][0]
    assert pin["verified"] and pin["verified_by"] == "Dana"
    assert post_map.post_pins(project, [item("it_2", "Belgium again")], verdict="none")["pins"] == []


def test_every_country_has_a_centre():
    from sugar_core import gazetteer
    assert all(centroid(c) for c in gazetteer.all_countries())


def test_a_named_city_places_the_pin_and_summarises_the_target(tmp_path):
    from datetime import datetime, timezone
    project = ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Pins"))
    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    fresh = item("it_1", "A new reading room opens in Brussels", published_at="2026-10-02T08:00:00Z")
    old = item("it_2", "Belgium again, and Brussels too", published_at="2026-08-01T08:00:00Z")
    result = post_map.post_pins(project, [fresh, old], now=now)
    pin = next(p for p in result["pins"] if p["item_id"] == "it_1")
    assert pin["placement"] == "mentioned" and abs(pin["latitude"] - 50.85) < 0.01 and pin["targets"][0]["city"] == "Brussels"
    row = result["targets"][0]
    assert row["name"] == "Belgium" and row["posts"] == 2 and row["last_24h"] == 1 and row["cities"] == {"Brussels": 2} and row["platforms"] == {"mastodon": 2}
    recent = post_map.post_pins(project, [fresh, old], days=7, now=now)
    assert [p["item_id"] for p in recent["pins"]] == ["it_1"]
