from sugar_core import analysis
from sugar_core.llm_providers import LLMBudget, LLMProvider, ProviderProfile
from sugar_core.research_items import ResearchItem
from sugar_core.research_plan import ResearchPlanSpec
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace


def item(i, text, platform="web", lang="en"):
    return ResearchItem(item_id=f"it_{i}", run_id="run_1", project_id="p", platform=platform, url=f"https://s.example/{i}", original_text=text, language=lang,
                        status="collected", published_at="2025-03-01T00:00:00Z")


def project(tmp_path):
    return ResearchProject(SugarWorkspace.create(tmp_path / "ws", name="Analysis"))


class FakeJSON(LLMProvider):
    def __init__(self, rows):
        super().__init__(ProviderProfile(id="f", type="local", endpoint="http://localhost:1/v1", model="m"))
        self.rows, self.calls = rows, 0

    def chat_json(self, messages, schema, **kw):
        self.calls += 1
        return {"items": self.rows}, None


def plan(**kw):
    return ResearchPlanSpec.from_dict({"topic": "reading rooms", "geography": ["Kenya"], **kw})


def test_pattern_relevance_explains_itself_and_never_rejects():
    terms = analysis.plan_terms(plan(), {"relevance": {"include": ["library"], "exclude": ["football"]}})
    on = analysis.score_item(item(1, "The new reading rooms in Kenya open a library wing."), terms)
    off = analysis.score_item(item(2, "Football scores from the weekend."), terms)
    excluded = analysis.score_item(item(3, "Reading rooms and football in Kenya."), terms)
    assert on["band"] == "likely" and "mentions" in on["reasons"][0] and off["band"] == "unlikely" and "does not mention" in off["reasons"][0]
    assert excluded["score"] < on["score"] and any("excluded" in r for r in excluded["reasons"])


def test_model_only_refines_uncertain_items_within_budget(tmp_path):
    p = project(tmp_path)
    items = [item(1, "Reading rooms in Kenya."), item(2, "Something about rooms and weather."), item(3, "Totally unrelated.")]
    provider = FakeJSON([{"item": 1, "relevance": 3, "reason": "Directly about reading rooms"}])
    result = analysis.score_run(p, items, plan(), provider=provider, budget=LLMBudget(2))
    assert result["scored"] == 3 and provider.calls == 1 and result["model_refined"] <= 1
    latest = analysis.RelevanceStore(p).latest()
    assert set(latest) == {"it_1", "it_2", "it_3"} and latest["it_1"]["method"] == "pattern"          # confident items skip the model
    spent = LLMBudget(1)
    spent.take(1)
    again = analysis.score_run(p, items, plan(), provider=provider, budget=spent)
    assert again["warnings"] and again["model_refined"] == 0 and provider.calls == 1


def test_themes_group_items_by_shared_distinctive_words():
    items = [item(i, f"Language classes for students number {i}. English language classes held weekly.") for i in range(5)] + \
            [item(10 + i, f"Robotics workshop session {i}. The robotics workshop drew a crowd of learners.") for i in range(5)] + [item(99, "Unrelated note about parking.")]
    result = analysis.themes(items)
    labels = " | ".join(t["label"] for t in result["themes"])
    assert result["items"] == 11 and result["themes"] and ("language" in labels or "classes" in labels) and ("robotics" in labels or "workshop" in labels)
    assert all(t["examples"] and t["count"] >= 2 for t in result["themes"]) and "describe what the collected items say" in result["note"]
    assert analysis.themes(items[:2])["themes"] == []
