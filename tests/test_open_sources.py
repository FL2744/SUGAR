"""Open-source collectors, exercised against recorded-shape responses (no network)."""

import pytest
import requests

from sugar_core import open_sources as osrc
from sugar_core.collector_registry import COLLECTORS


class FakeResponse:
    def __init__(self, payload=None, *, status=200, text="", content=b"", headers=None, url="https://example.test/x"):
        self._payload, self.status_code, self.text, self.content, self.headers, self.url = payload, status, text, content, headers or {}, url

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        response = self.responses.pop(0)
        response.url = url
        return response


def test_wikipedia_returns_articles_per_language_with_extracts():
    session = FakeSession(
        FakeResponse({"query": {"search": [{"pageid": 7, "title": "American Spaces", "timestamp": "2025-03-02T10:00:00Z", "wordcount": 900}]}}),
        FakeResponse({"query": {"pages": [{"pageid": 7, "title": "American Spaces", "extract": "Public diplomacy centers run with partners.", "fullurl": "https://en.wikipedia.org/wiki/American_Spaces"}]}}))
    rows = osrc.collect_wikipedia(search_terms=["american spaces"], languages=["en"], session=session)
    assert len(rows) == 1 and rows[0].platform == "wikipedia" and rows[0].native_id == "en:7"
    assert rows[0].published_at == "2025-03-02T10:00:00Z" and "public diplomacy centers" in rows[0].original_text.lower()
    assert rows[0].content_type == "article" and rows[0].platform_language == "en" and rows[0].query_matches == ["american spaces"]


def test_gdelt_maps_languages_filters_dates_and_quotes_phrases():
    articles = {"articles": [
        {"url": "https://news.example/a", "title": "Reading rooms open abroad", "seendate": "20250310T120000Z", "domain": "news.example", "language": "Chinese", "sourcecountry": "Exampleland"},
        {"url": "https://news.example/old", "title": "Old story", "seendate": "20200101T000000Z", "domain": "news.example", "language": "English", "sourcecountry": "X"}]}
    session = FakeSession(FakeResponse(articles))
    rows = osrc.collect_gdelt(search_terms=["cultural center"], since="2025-01-01", until="2025-12-31", session=session, min_interval=0)
    assert [r.canonical_url for r in rows] == ["https://news.example/a"]          # the 2020 item is outside the window
    assert rows[0].platform_language == "zh" and rows[0].author_location == "Exampleland" and rows[0].raw_stats["text_scope"] == "headline only"
    params = session.calls[0][1]
    assert params["query"] == '"cultural center"' and params["startdatetime"].startswith("20250101") and params["enddatetime"].startswith("20251231")


def test_gdelt_plain_text_rejection_becomes_a_clear_error():
    session = FakeSession(FakeResponse(None, text="The specified phrase is too short."))
    with pytest.raises(ValueError, match="could not run"):
        osrc.collect_gdelt(search_terms=["ab"], session=session, min_interval=0)


def test_openalex_rebuilds_abstracts_and_reports_citations():
    work = {"id": "https://openalex.org/W123", "doi": "https://doi.org/10.1/x", "title": "Public diplomacy outposts", "publication_date": "2024-05-01",
            "cited_by_count": 12, "language": "en", "type": "article",
            "abstract_inverted_index": {"Cultural": [0], "centers": [1], "abroad": [2]},
            "authorships": [{"author": {"display_name": "A. Scholar"}}, {"author": {"display_name": "B. Author"}}],
            "primary_location": {"source": {"display_name": "Journal of Examples"}}}
    session = FakeSession(FakeResponse({"results": [work]}))
    rows = osrc.collect_openalex(search_terms=["public diplomacy"], since="2024-01-01", session=session)
    assert rows[0].original_text.endswith("Cultural centers abroad") and rows[0].engagement == {"citations": 12}
    assert rows[0].author_name == "A. Scholar; B. Author" and rows[0].canonical_url == "https://doi.org/10.1/x"
    assert "from_publication_date:2024-01-01" in session.calls[0][1]["filter"]


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>New reading room opens</title><link>https://site.example/1</link><description>&lt;p&gt;Books and programs for the public&lt;/p&gt;</description>
<pubDate>Mon, 10 Mar 2025 09:00:00 GMT</pubDate><guid>g1</guid></item>
<item><title>Unrelated sports update</title><link>https://site.example/2</link><description>Scores</description><pubDate>Mon, 10 Mar 2025 10:00:00 GMT</pubDate></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Reading room programs</title>
<link href="https://atom.example/e1"/><summary>Public programs</summary><updated>2025-03-11T08:00:00Z</updated><id>tag:e1</id></entry></feed>"""


def test_rss_and_atom_entries_are_matched_cleaned_and_dated():
    session = FakeSession(FakeResponse(content=RSS), FakeResponse(content=ATOM))
    rows = osrc.collect_rss(search_terms=["reading room"], feeds=["https://site.example/feed", "https://atom.example/feed"], session=session)
    assert sorted(r.canonical_url for r in rows) == ["https://atom.example/e1", "https://site.example/1"]
    first = next(r for r in rows if r.canonical_url.endswith("/1"))
    assert "<p>" not in first.original_text and first.published_at == "2025-03-10T09:00:00Z" and first.source_host == "site.example"


def test_rss_needs_feeds_and_survives_one_bad_feed():
    with pytest.raises(ValueError, match="feed address"):
        osrc.collect_rss(search_terms=["x"], feeds=[])
    session = FakeSession(FakeResponse(status=500), FakeResponse(content=ATOM))
    rows = osrc.collect_rss(search_terms=["reading room"], feeds=["https://bad.example/f", "https://atom.example/f"], session=session)
    assert len(rows) == 1


def test_feed_parser_ignores_external_entities():
    evil = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss><channel><item><title>&x;</title><link>https://a.example/1</link></item></channel></rss>'
    entries = osrc.parse_feed(evil)
    assert all("root:" not in e["title"] for e in entries)


def test_rate_limit_surfaces_as_a_retryable_429():
    from sugar_core.research_pipeline import classify_failure
    session = FakeSession(FakeResponse(status=429, headers={"Retry-After": "30"}))
    with pytest.raises(RuntimeError) as caught:
        osrc.collect_openalex(search_terms=["x"], session=session)
    assert classify_failure(caught.value, "openalex")["classification"] == "retryable"


def test_registry_and_opt_in_behaviour():
    assert {"wikipedia", "gdelt", "openalex", "rss"} <= set(COLLECTORS)
    assert COLLECTORS["rss"].enabled_by == "rss_feeds" and not COLLECTORS["gdelt"].enabled_by
    assert all(COLLECTORS[n].capabilities.anonymous_search and not COLLECTORS[n].required_secrets for n in ("wikipedia", "gdelt", "openalex", "rss"))
