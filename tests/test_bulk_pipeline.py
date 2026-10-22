from sugar_core import open_sources
from sugar_core.research_items import ResearchItem
from test_open_sources import FakeResponse, FakeSession
from test_research_pipeline import make_plan, make_project, rec, run_pipeline, spec


def test_parallel_bulk_collection_shares_cap_and_persists_thousands(tmp_path):
    project = make_project(tmp_path)
    requests = []

    def source(name):
        def search(request):
            requests.append((name, request.max_posts_per_query, request.max_pages_per_query))
            return [rec(name, n, f"Education program number {n} in Belgium supports university students", platform_language="en") for n in range(min(2400, request.max_posts_per_query))]
        return spec(name, search)

    plan = make_plan(topic="education", source_scope="selected", platforms=["bluesky", "mastodon"],
                     queries=[{"text": "education", "enabled": True}, {"text": "universities", "enabled": True}],
                     limits={"max_posts_per_query": 5000, "max_pages_per_query": 100, "max_items_total": 3500, "target_items": 3500},
                     dedup={"enabled": False}, translation={"policy": "never"})
    pipeline = run_pipeline(project, plan, {"bluesky": source("bluesky"), "mastodon": source("mastodon")})
    assert pipeline.counts["collected"] == 3500
    stored = project.load_items(pipeline.run.run_id)
    assert len([i for i in stored if i.status in {"collected", "processed"}]) == 3500
    assert pipeline.run.metrics["collection"]["target_reached"]
    assert all(pages == 100 for _, _, pages in requests)
    assert any(e.type == "query.skipped" and e.data.get("reason") == "item_limit" for e in pipeline.events.since(0, limit=100000))


def test_openalex_cursor_pagination_exhaustion_and_item_cap():
    def work(n):
        return {"id": f"https://openalex.org/W{n}", "title": f"Education {n}", "language": "en"}
    session = FakeSession(FakeResponse({"results": [work(1), work(2)], "meta": {"next_cursor": "next"}}),
                          FakeResponse({"results": [work(3), work(4)], "meta": {"next_cursor": "last"}}))
    records = open_sources.collect_openalex(search_terms=["education"], max_posts_per_query=3, max_pages_per_query=20, session=session)
    assert len(records) == 3 and len(session.calls) == 2
    assert session.calls[0][1]["cursor"] == "*" and session.calls[1][1]["cursor"] == "next"
    assert session.calls[1][1]["per-page"] == 1


def test_paginated_failure_keeps_completed_pages():
    session = FakeSession(FakeResponse({"results": [{"id": "https://openalex.org/W1", "title": "Education"}], "meta": {"next_cursor": "next"}}),
                          FakeResponse(status=429))
    import pytest
    with pytest.raises(RuntimeError) as caught:
        open_sources.collect_openalex(search_terms=["education"], max_posts_per_query=500, max_pages_per_query=10, session=session)
    assert len(caught.value.partial_records) == 1


def test_wikipedia_uses_continuation_and_stops_on_repeated_cursor():
    session = FakeSession(
        FakeResponse({"query": {"search": [{"pageid": 1, "title": "One"}]}, "continue": {"sroffset": 50, "continue": "-||"}}),
        FakeResponse({"query": {"pages": [{"pageid": 1, "extract": "Education one"}]}}),
        FakeResponse({"query": {"search": [{"pageid": 2, "title": "Two"}]}, "continue": {"sroffset": 50, "continue": "-||"}}),
        FakeResponse({"query": {"pages": [{"pageid": 2, "extract": "Education two"}]}}))
    records = open_sources.collect_wikipedia(search_terms=["education"], max_posts_per_query=1000, max_pages_per_query=100, session=session)
    assert len(records) == 2 and session.calls[2][1]["sroffset"] == 50


def test_older_stored_items_open_without_source_metadata():
    item = ResearchItem.from_dict({"item_id": "it_1", "run_id": "r", "project_id": "p", "platform": "bluesky"})
    assert item.source_metadata == {}


def test_rss_pages_are_fetched_once_for_multiple_queries_in_one_run():
    feed = b'<rss><channel><item><title>Education culture programs</title><link>https://example.test/a</link><guid>a</guid></item></channel></rss>'
    session = FakeSession(FakeResponse(content=feed))
    cache = {}
    first = open_sources.collect_rss(search_terms=["education"], feeds=["https://example.test/rss"], session=session, cache=cache)
    second = open_sources.collect_rss(search_terms=["culture"], feeds=["https://example.test/rss"], session=session, cache=cache)
    assert first and second and len(session.calls) == 1
