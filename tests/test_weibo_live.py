from __future__ import annotations

import os

import pytest

from sugar_core.weibo_investigation import investigate_weibo_seed


pytestmark = pytest.mark.skipif(
    os.environ.get("SUGAR_LIVE_WEIBO") != "1",
    reason="set SUGAR_LIVE_WEIBO=1 to run the bounded public Weibo integration smoke test",
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

    insight = result.insights
    assert insight["seed"]["reported_engagement"]["likes"] > 0
    assert insight["retrieval"]["surface_status"]["seed"]["status"] == "ok"
    assert "not a sentiment poll" in insight["interpretation_guardrail"]

    print("LIVE_WEIBO_SEED", insight["seed"])
    print("LIVE_WEIBO_RETRIEVAL", insight["retrieval"])
    print("LIVE_WEIBO_AUTHOR_CONTEXT", insight["author_context"])
