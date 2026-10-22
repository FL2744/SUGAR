import csv
import io
import json
from datetime import datetime, timezone

import pytest

from sugar_core.analysis_export import analysis_files, export_map
from sugar_core.post_map import post_pins
from sugar_core.research_api import _research_routes
from sugar_core.research_export import verify_export
from sugar_core.research_items import ResearchItem, tag_geography
from sugar_core.research_plan import ResearchPlanSpec
from sugar_core.research_results import query_items
from sugar_core.research_runs import ResearchProject
from sugar_core.sentiment import score_item, score_text
from sugar_core.temporal import iso_utc
from sugar_core.workspace import SugarWorkspace


def project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Map regression"))


def post(i, date="2026-03-01T10:00:00Z", text="We welcome peaceful education in Belgium", **kw):
    item = ResearchItem(item_id=f"it_{i}", run_id="run_test", project_id="p", platform="bluesky", published_at=date,
                        retrieved_at="2026-10-22T10:00:00Z", original_text=text, language="en", url=f"https://bsky.app/{i}", **kw)
    tag_geography(item, [])
    return item


def test_utc_sort_is_chronological_and_missing_dates_are_last():
    items = [post(1, "2026-03-01T10:00:00+02:00"), post(2, "2026-03-01T08:30:00Z"), post(3, ""), post(4, "bad-date")]
    assert [r["item_id"] for r in query_items(items, sort="newest")["items"]] == ["it_2", "it_1", "it_3", "it_4"]
    assert [r["item_id"] for r in query_items(items, sort="oldest")["items"]] == ["it_1", "it_2", "it_3", "it_4"]
    assert iso_utc(items[0].published_at) == "2026-03-01T08:00:00Z"
    with pytest.raises(ValueError):
        query_items(items, sort="arbitrary")


def test_map_date_range_uses_publication_not_retrieval_and_deduplicates(tmp_path):
    p = project(tmp_path)
    items = [post(1, "2026-03-02T00:30:00+02:00"), post(2, "2026-03-02T00:01:00Z"), post(3, ""),
             post(1, "2025-01-01"), post(4, text="No named place and no origin here")]
    result = post_pins(p, items, since="2026-03-01", until="2026-03-01")
    assert [r["item_id"] for r in result["pins"]] == ["it_1"]
    all_time = post_pins(p, items)
    assert len(all_time["pins"]) == 3
    assert all_time["coverage"] == {"unique_posts": 4, "mapped_posts": 3, "unlocated_posts": 1, "undated_posts": 1}
    assert all_time["pins"][-1]["item_id"] == "it_3"
    now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
    assert post_pins(p, items, days=1, now=now)["pins"] == []
    assert post_pins(p, [post(10, "2027-01-01T00:00:00Z")], days=1, now=now)["pins"] == []
    with pytest.raises(ValueError):
        post_pins(p, items, since="2026-04-01", until="2026-03-01")


def test_api_map_scans_all_runs_including_partial_saved_results(tmp_path):
    p = project(tmp_path)
    plan = p.save_plan(ResearchPlanSpec(topic="education", research_question="Education"))
    for n in range(8):
        run = p.new_run(kind="run", plan=plan)
        run.status = "cancelled" if n == 0 else "completed"
        p.save_run(run)
        p.save_items(run.run_id, [post(n)])

    class Workbench:
        list_runs = staticmethod(lambda project: project.list_runs())
        items = staticmethod(lambda project, rid: project.load_items(rid))

    code, result = _research_routes("GET", "map/posts", {}, {}, Workbench(), p)
    assert code == 200 and result["runs_scanned"] == 8
    assert len(result["pins"]) == 8


def test_result_paging_can_reach_thousands_without_losing_order():
    items = [post(n, f"2026-03-{1 + n % 28:02}T10:00:00Z") for n in range(3001)]
    ids = []
    for offset in range(0, 3001, 200):
        result = query_items(items, offset=offset, limit=200, sort="oldest")
        assert result["total"] == 3001
        ids.extend(r["item_id"] for r in result["items"])
    assert len(ids) == len(set(ids)) == 3001


@pytest.mark.parametrize("text, expected", [("I am very happy with our wonderful progress!", 1), ("I am not happy with their terrible failure!", -1)])
def test_exploratory_axes_include_negation_and_direction(text, expected):
    score = score_text(text, language="en")
    assert score["valence"] == expected and 0 <= score["intensity"] <= 1
    assert -1 <= score["direction"] <= 1 and score["matched_terms"]


def test_sentiment_abstains_and_records_translation_basis():
    assert score_text("La bonne éducation aide les étudiants", language="fr")["valence"] is None
    assert score_text("The library opens on Monday", language="en")["valence"] is None
    item = post(1)
    item.language = "zh"
    item.translation = {"status": "done", "text": "They welcome peaceful education", "target_language": "English"}
    score = score_item(item)
    assert score["valence"] == 1 and score["basis"] == "english_translation"
    item.translation["target_language"] = "French"
    assert score_item(item)["status"] == "unscored"


def test_analysis_export_preserves_full_multiline_text_types_and_provenance(tmp_path):
    p = project(tmp_path)
    full = "=formula\nBelgium, éducation\t" + "source evidence " * 250
    item = post(1, text=full, author="@researcher", source_metadata={"discovery": {"path": ["https://a.example/", "https://a.example/story"]}})
    p.review.apply(item.item_id, {"kind": "verdict", "verdict": "relevant"}, author="Analyst")
    files = analysis_files(p, [item, post(2, date="", text="No place or lexical evidence")])
    rows = list(csv.DictReader(io.StringIO(files["analysis.csv"].decode("utf-8-sig"))))
    assert rows[0]["original_text"] == "'" + full and rows[0]["author"] == "'@researcher"
    assert rows[0]["origin_latitude"] == "" and rows[0]["map_placement"] == "mentioned"
    exact = [json.loads(line) for line in files["analysis.jsonl"].decode().splitlines()]
    assert exact[0]["original_text"] == full and exact[0]["verdict"] == "relevant" and exact[0]["reviewer"] == "Analyst"
    assert exact[1]["valence"] is None and exact[1]["published_at"] == ""
    assert exact[0]["source_metadata"] == item.source_metadata
    feature = json.loads(files["map.geojson"])["features"][0]
    assert feature["properties"]["placement"] == "mentioned" and not feature["properties"]["origin_known"]
    timeline = list(csv.DictReader(io.StringIO(files["timeline.csv"].decode("utf-8-sig"))))
    assert sum(int(row["unique_posts"]) for row in timeline) == 2


def test_map_export_has_full_text_exact_scope_and_valid_hashes(tmp_path):
    p = project(tmp_path)
    items = [post(1, text="Belgium\n" + "full text " * 300), post(2, "2025-01-01"), post(3, text="Education in France")]
    result = export_map(p, items, filters={"since": "2026-01-01", "target": "Belgium"})
    assert result["manifest"]["scope"]["unique_posts"] == 1
    assert verify_export(p.workspace.root / result["archive"])["ok"]
    data = (p.workspace.root / result["directory"] / "analysis.jsonl").read_text(encoding="utf-8")
    assert json.loads(data)["original_text"] == items[0].original_text


def test_bulk_limits_survive_plan_round_trips():
    p = ResearchPlanSpec(topic="education", limits={"max_posts_per_query": 10000, "max_pages_per_query": 100, "max_items_total": 10000, "target_items": 10000})
    again = ResearchPlanSpec.from_dict(p.to_dict())
    assert again.limits["max_posts_per_query"] == 10000 and again.limits["max_pages_per_query"] == 100
    assert again.limits["target_items"] == 10000


def test_invalid_legacy_coordinates_cannot_break_the_whole_map(tmp_path):
    p = project(tmp_path)
    items = [post(1, coordinates={"lat": float("nan"), "lon": 0}), post(2, coordinates={"lat": 99, "lon": 0}),
             post(3, coordinates={"lat": 0, "lon": 0})]
    result = post_pins(p, items)
    assert next(pin for pin in result["pins"] if pin["item_id"] == "it_1")["placement"] == "mentioned"
    assert next(pin for pin in result["pins"] if pin["item_id"] == "it_3")["origin"]["latitude"] == 0
    json.dumps(result, allow_nan=False)
