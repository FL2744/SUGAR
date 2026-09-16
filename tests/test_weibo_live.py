from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

import pytest

from sugar_core.bilibili import collect_bilibili_public
from sugar_core.weibo_investigation import investigate_weibo_seed


pytestmark = pytest.mark.skipif(
    os.environ.get("SUGAR_LIVE_WEIBO") != "1",
    reason="set SUGAR_LIVE_WEIBO=1 to run the bounded live public-source integration smoke tests",
)


def test_live_public_weibo_seed_and_context_smoke():
    # Public post independently observed in September 2026:
    # https://m.weibo.cn/status/5320265912291527
    # The text discusses ANTA KAI 3's blending of Chinese kite imagery and other cultural motifs.
    result = investigate_weibo_seed(
        "https://m.weibo.cn/status/5320265912291527",
        max_comments=5,
        comment_pages=1,
        max_reposts=5,
        repost_pages=1,
        author_posts=5,
        author_pages=1,
    )

    seed = result.seed
    assert seed.platform == "weibo"
    assert seed.native_id == "5320265912291527"
    assert seed.author_name
    assert "KAI" in seed.original_text.upper()
    assert seed.engagement.get("likes", 0) > 0
    assert seed.engagement.get("replies", 0) > 0
    assert seed.engagement.get("reposts", 0) > 0

    # This seed reports dozens of comments. The live contract therefore requires the ordinary
    # anonymous comment surface to return at least one real normalized audience response, not
    # merely the post metadata. If Weibo changes that surface, CI should tell us explicitly.
    assert result.surface_status["comments"]["status"] == "ok"
    assert len(result.comments) > 0
    assert all(row.platform == "weibo" and row.content_type == "comment" for row in result.comments)
    assert all(row.thread_root_key == "weibo:5320265912291527" for row in result.comments)

    insight = result.insights
    assert insight["seed"]["reported_engagement"]["likes"] > 0
    assert insight["retrieval"]["surface_status"]["seed"]["status"] == "ok"
    assert insight["retrieval"]["comments_retrieved"] == len(result.comments)
    assert insight["response_context"]["top_public_responses"]
    assert "not a sentiment poll" in insight["interpretation_guardrail"]

    print("LIVE_WEIBO_RAW_CREATED_AT", seed.raw_stats.get("created_at_raw"))
    print("LIVE_WEIBO_SEED", insight["seed"])
    print("LIVE_WEIBO_RETRIEVAL", insight["retrieval"])
    print("LIVE_WEIBO_TOP_RESPONSES", insight["response_context"]["top_public_responses"][:5])
    print("LIVE_WEIBO_AUTHOR_CONTEXT", insight["author_context"])


def test_live_bounded_bilibili_two_page_search_stress():
    """Probe bounded anonymous Bilibili pagination without inventing result yield.

    A valid zero-result response is different from an access/rate-limit error and must not be
    converted into evidence that the platform is unavailable. When live results are present,
    this test verifies normalized identity, query provenance, deduplication, and second-page
    provenance whenever more than one page of unique results is actually returned.
    """
    query_text = "artificial intelligence"
    records = collect_bilibili_public(
        search_terms=[query_text],
        max_posts_per_query=40,
        max_pages_per_query=2,
        hydrate_details=False,
        initialize_session=True,
    )

    print("LIVE_BILIBILI_STRESS_RECORDS", len(records))
    if not records:
        pytest.skip(
            "Bilibili returned a valid zero-result response for the bounded live query; "
            "access did not raise 403/429/access-control errors, but keyword yield is not stable enough to be a release gate."
        )

    assert len(records) <= 40
    stable_ids = [record.native_id or record.canonical_url for record in records]
    assert all(stable_ids)
    assert len(stable_ids) == len(set(stable_ids))
    assert all(record.platform == "bilibili" for record in records)
    assert all(query_text in record.query_matches for record in records)

    pages: set[str] = set()
    for record in records:
        query = parse_qs(urlparse(record.source_url).query)
        pages.update(query.get("page", []))
    assert "1" in pages
    if len(records) > 20:
        assert "2" in pages

    print("LIVE_BILIBILI_STRESS_PAGES", sorted(pages))
