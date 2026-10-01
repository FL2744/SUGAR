import csv
import io

from sugar_core import evaluation
from sugar_core.research_items import ResearchItem
from sugar_core.research_plan import ResearchPlanSpec


def item(i, text):
    return ResearchItem(item_id=f"it_{i:02d}", run_id="r", project_id="p", platform="web", url=f"https://s.example/{i}", original_text=text, status="collected")


ITEMS = [item(1, "Reading rooms open in Kenya with language classes for university students."), item(2, "Football results from Saturday."),
         item(3, "A reading room workshop for teachers in Kenya."), item(4, "Weather and traffic."), item(5, "Kenya reading rooms host a robotics workshop.")]
PLAN = ResearchPlanSpec.from_dict({"topic": "reading rooms", "geography": ["Kenya"]})


def test_the_sample_sheet_hides_predictions_and_is_reproducible():
    one, two = evaluation.sample_csv(ITEMS, 4, seed=3), evaluation.sample_csv(ITEMS, 4, seed=3)
    rows = list(csv.DictReader(io.StringIO(one)))
    assert one == two and len(rows) == 4 and list(rows[0]) == evaluation.SAMPLE_COLUMNS and not any(r["gold_relevance"] for r in rows)
    assert "score" not in one.splitlines()[0] and "band" not in one.splitlines()[0]


def test_scores_agree_with_a_person_and_report_counts():
    labels = io.StringIO()
    w = csv.writer(labels)
    w.writerow(evaluation.SAMPLE_COLUMNS)
    gold = {1: ("relevant", "university_students", "language_learning"), 2: ("not_relevant", "", ""), 3: ("relevant", "educators", ""), 4: ("not_relevant", "", ""), 5: ("relevant", "", "steam")}
    for i, (rel, aud, prog) in gold.items():
        w.writerow([f"it_{i:02d}", "r", "web", "", "en", "", rel, aud, prog])
    w.writerow(["it_zz", "r", "web", "", "en", "", "relevant", "", ""])
    result = evaluation.score_labels(labels.getvalue(), ITEMS, PLAN)
    assert result["labeled_relevance"] == 5 and result["unknown_item_ids"] == 1
    assert result["relevance"]["precision"] == 1.0 and result["relevance"]["recall"] == 1.0 and result["relevance"]["true_negatives"] == 2
    assert result["audience"]["by_label"]["university_students"]["tp"] == 1 and result["audience"]["by_label"]["educators"]["tp"] == 1
    assert result["program"]["by_label"]["language_learning"]["tp"] == 1 and "0.3" in result["relevance"]["by_threshold"] and "rough estimate" in result["note"]


def test_a_blank_sheet_scores_nothing_without_failing():
    blank = evaluation.sample_csv(ITEMS, 5)
    result = evaluation.score_labels(blank, ITEMS, PLAN)
    assert result["labeled_relevance"] == 0 and result["relevance"]["precision"] is None and result["audience"]["overall"]["f1"] is None
