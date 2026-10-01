from sugar_core import post_map
from sugar_core.country_centroids import centroid
from sugar_core.research_items import ResearchItem, tag_geography
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace


def item(item_id, text, **kw):
    it = ResearchItem(item_id=item_id, run_id="run_1", project_id="p", platform="mastodon", author="@ana", original_text=text, published_at="2026-03-01T10:00:00Z", **kw)
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
