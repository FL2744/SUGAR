from datetime import date

import pytest

from sugar_core.nl_interpreter import interpret_deterministic
from sugar_core.query_planner import dispatch_text, generate_queries, rebuild_plan_queries
from sugar_core.research_plan import build_plan

TODAY = date(2026, 9, 30)


def interpret(text):
    return interpret_deterministic(text, today=TODAY)


def test_acceptance_sentence_needs_no_special_syntax():
    result = interpret("Search democracy in the Middle East on all platforms.")
    p = result.payload
    assert p["topic"] == "democracy"
    assert p["geography"] == ["Middle East"]
    assert p["source_scope"] == "all_enabled"
    assert p["languages"] == ["auto"]
    assert "timeframe" not in p               # no restriction unless stated
    assert result.clarifications == []
    plan, issues = build_plan(p)
    assert plan is not None and not [i for i in issues if i.severity == "error"]


@pytest.mark.parametrize("sentence", [
    "Search democracy in the Middle East across all platforms",
    "search for democracy in the middle east everywhere",
    "Please find democracy in the Middle East on every social platform",
    "democracy middle east",
    "I want you to research democracy in the Middle East on all sources",
])
def test_paraphrases_of_the_acceptance_sentence(sentence):
    p = interpret(sentence).payload
    assert p["topic"] == "democracy" and p["geography"] == ["Middle East"]


def test_platforms_are_named_naturally_and_unsupported_ones_are_reported():
    p = interpret("Find posts about elections in Tunisia between 2019 and 2022 on X and Reddit").payload
    assert p["topic"] == "elections"
    assert p["source_scope"] == "selected" and p["platforms"] == ["x"]
    r = interpret("Find posts about elections in Tunisia on Twitter and Bluesky")
    assert r.payload["platforms"] == ["x", "bluesky"]
    assert any("Reddit" in w for w in interpret("elections on Reddit").warnings)
    # the letter X in ordinary text is not a platform
    assert interpret("Search malcolm X speeches in the United States").payload.get("platforms", []) == []


def test_time_expressions():
    assert interpret("climate policy in Brazil since 2023").payload["timeframe"]["start"] == "2023-01-01"
    tf = interpret("protests in Iran over the last 6 months").payload["timeframe"]
    assert (tf["start"], tf["end"]) == ("2026-03-30", "2026-09-30")
    tf = interpret("elections in Tunisia between 2019 and 2022").payload["timeframe"]
    assert (tf["start"], tf["end"]) == ("2019-01-01", "2022-12-31")
    tf = interpret("corruption in Nigeria since March 2021").payload["timeframe"]
    assert tf["start"] == "2021-03-01" and tf["end"] == ""
    tf = interpret("sanctions in Turkey in 2019").payload["timeframe"]
    assert (tf["start"], tf["end"]) == ("2019-01-01", "2019-12-31")
    tf = interpret("sanctions in Turkey before 2020").payload["timeframe"]
    assert tf["end"] == "2019-12-31"
    assert interpret("Vision 2030 in Saudi Arabia").payload["topic"] == "Vision 2030"    # a bare year is not a date
    assert "timeframe" not in interpret("Vision 2030 in Saudi Arabia").payload


def test_languages_translation_depth_and_exclusions():
    p = interpret("Look into protests in Iran in Persian and English, translate to English, deep search, excluding memes").payload
    assert p["topic"] == "protests" and p["geography"] == ["Iran"]
    assert p["languages"] == ["fa", "en"]
    assert p["translation"]["policy"] == "always"
    assert p["depth"] == "deep"
    assert p["exclusions"] == ["memes"]
    assert interpret("elections in Egypt, don't translate").payload["translation"]["policy"] == "never"
    assert interpret("a quick look at sanctions in Turkey").payload["depth"] == "quick"


def test_question_forms_and_demonyms():
    p = interpret("How is NATO enlargement discussed in Finland?").payload
    assert p["topic"] == "NATO enlargement" and p["geography"] == ["Finland"]
    assert p["research_question"].startswith("How is NATO enlargement discussed")
    p = interpret("what do Egyptians think about the IMF loan").payload
    assert p["geography"] == ["Egypt"] and p["topic"] == "IMF loan"
    p = interpret("Find what people are saying about climate policy in Brazil on Bluesky and Mastodon").payload
    assert p["topic"] == "climate policy" and p["platforms"] == ["bluesky", "mastodon"]


def test_unknown_place_is_accepted_with_an_assumption_and_no_interruption():
    r = interpret("Tell me about education reform in Kyiv on twitter")
    assert r.payload["topic"] == "education reform"
    assert r.payload["geography"] == ["Kyiv"]
    assert any("Kyiv" in a for a in r.assumptions)
    assert r.clarifications == []


def test_clarification_only_when_the_topic_cannot_be_inferred():
    assert interpret("Search").clarifications == ["What subject would you like to research?"]
    r = interpret("in the Middle East")
    assert r.clarifications and "Middle East" in r.clarifications[0]
    assert interpret("").clarifications
    assert interpret("democracy").clarifications == []


def test_monitoring_intent_configures_refresh_without_eating_the_topic():
    p = interpret("monitor sanctions in Turkey daily").payload
    assert p["topic"] == "sanctions" and p["collection_mode"] == "monitoring"
    assert p["refresh"]["mode"] == "scheduled" and p["refresh"]["interval_hours"] == 24


def test_quoted_phrases_and_subtopics_become_search_terms():
    p = interpret('quick look at "human rights" in the Gulf').payload
    assert p["topic"] == "human rights" and p["search_terms"] == ["human rights"]
    p = interpret("freedom of speech and press freedom in Lebanon").payload
    assert p["search_terms"] == ["freedom of speech", "press freedom"]


def test_defaults_are_recorded_as_assumptions_when_not_stated():
    r = interpret("democracy in Egypt")
    assert set(r.defaulted_fields) >= {"timeframe", "languages", "platforms", "depth"}
    assert any("No platforms were named" in a for a in r.assumptions)


# ---- query planning ---------------------------------------------------------------------
def _plan(text, **overrides):
    payload = interpret(text).payload
    payload.update(overrides)
    plan, _ = build_plan(payload)
    return plan


def test_generated_queries_are_auditable_and_bounded_by_depth():
    plan = _plan("Search democracy in the Middle East on all platforms.")
    queries = generate_queries(plan)
    enabled = [q for q in queries if q.enabled]
    assert len(enabled) == plan.limits["query_count"] == 6
    assert queries[0].text == 'democracy "Middle East"'
    assert any(q.language == "ar" and q.text == "ديمقراطية" for q in queries)        # local-language variant
    assert all(q.rationale for q in queries)
    assert len(queries) > len(enabled)                                                 # extras are kept, disabled
    quick = generate_queries(_plan("quick search democracy in the Middle East"))
    assert sum(q.enabled for q in quick) == 3 and not any(q.language for q in quick if q.enabled)


def test_platform_specific_and_exclusion_dispatch():
    plan = _plan("democracy in the Middle East", source_scope="all_enabled")
    zh = [q for q in generate_queries(plan) if q.platform in {"weibo", "bilibili"}]
    assert zh and all(q.language == "zh" for q in zh)
    assert dispatch_text(generate_queries(plan)[0], "x", ["memes", "fan art"]) == 'democracy "Middle East" -memes -"fan art"'
    assert dispatch_text(generate_queries(plan)[0], "bluesky", ["memes"]) == 'democracy "Middle East"'


def test_analyst_queries_survive_rebuild():
    plan = _plan("democracy in Egypt")
    plan.queries = [{"text": "my custom query", "origin": "analyst"}]
    rebuilt, warnings = rebuild_plan_queries(plan)
    assert warnings == []
    assert any(q["text"] == "my custom query" and q["enabled"] for q in rebuilt.queries)
    assert rebuilt.version == 2
