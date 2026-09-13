from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

import requests

from sugar_core.weibo_investigation import (
    build_weibo_insights,
    investigate_weibo_seed,
    parse_weibo_seed,
    render_weibo_brief,
    save_weibo_investigation,
)


class FakeResponse:
    def __init__(self, payload=None, *, text="", status_code=200, url="https://m.weibo.cn/test"):
        self._payload = payload if payload is not None else {}
        self.text = text
        self.status_code = status_code
        self.url = url

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class QueueSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        if not self.responses:
            raise AssertionError(f"unexpected request: {url}")
        response = self.responses.pop(0)
        if response.url.endswith("/test"):
            response.url = url + ("?" + urlencode(params) if params else "")
        return response


def _real_shaped_seed():
    # Contract fixture anchored to the public 2026-07-13 ANTA KAI 3 post
    # https://m.weibo.cn/status/5320265912291527, observed publicly in September 2026.
    return {
        "id": "5320265912291527",
        "bid": "REALKAITEST",
        "created_at": "Mon Jul 13 09:08:00 +0800 2026",
        "text": "#鞋吧FRESH# ANTA KAI 3 欧文KAI3「凯风」配色，以中国传统沙燕风筝为灵感，并融入日月双翼和雷鸟等欧文部落元素，巧妙的将东西方文化相融合 #2026欧文中国行##MoveLikeKai#",
        "attitudes_count": 124,
        "comments_count": 49,
        "reposts_count": 26,
        "user": {"id": "889900", "screen_name": "鞋吧Sneakersbar", "location": "北京"},
    }


def _comment(cid, user, location, text, likes):
    return {
        "id": cid,
        "created_at": "Mon Jul 13 10:48:00 +0800 2026",
        "text": text,
        "like_count": likes,
        "total_number": 0,
        "user": {"id": f"u{cid}", "screen_name": user, "location": location},
    }


def _repost(rid, user, location, text, likes):
    return {
        "id": rid,
        "created_at": "Mon Jul 13 11:00:00 +0800 2026",
        "text": text,
        "attitudes_count": likes,
        "comments_count": 0,
        "reposts_count": 0,
        "user": {"id": f"r{rid}", "screen_name": user, "location": location},
    }


def _timeline(mid, text, likes, comments, reposts):
    return {
        "id": mid,
        "created_at": "Sun Jul 12 09:00:00 +0800 2026",
        "text": text,
        "attitudes_count": likes,
        "comments_count": comments,
        "reposts_count": reposts,
        "user": {"id": "889900", "screen_name": "鞋吧Sneakersbar", "location": "北京"},
    }


def test_parse_weibo_seed_accepts_real_public_url_forms():
    assert parse_weibo_seed("5320265912291527") == "5320265912291527"
    assert parse_weibo_seed("https://m.weibo.cn/status/5320265912291527?jumpfrom=weibocom") == "5320265912291527"
    assert parse_weibo_seed("https://m.weibo.cn/detail/5320265912291527") == "5320265912291527"
    assert parse_weibo_seed("https://weibo.com/123456/Rdbsx9nPk") == "Rdbsx9nPk"


def test_real_shaped_seed_expands_comments_reposts_and_author_context(tmp_path: Path):
    seed = _real_shaped_seed()
    comments = [
        _comment("c1", "你是单身狗", "湖北", "元素攻击", 3),
        _comment("c2", "万年陪跑的小天才", "浙江", "酷", 1),
        _comment("c3", "JessieWang87", "广东", "哇哦，好看", 6),
    ]
    reposts = [
        _repost("r1", "传播者甲", "上海", "中国风筝元素很好看 #MoveLikeKai#", 4),
        _repost("r2", "传播者乙", "广东", "转发微博 @鞋吧Sneakersbar", 1),
    ]
    timeline = [
        _timeline("p1", "上一条球鞋内容 #鞋吧FRESH#", 30, 8, 4),
        _timeline("p2", "另一条篮球鞋内容", 60, 12, 6),
        _timeline("p3", "品牌文化内容", 20, 4, 2),
    ]
    session = QueueSession(
        [
            FakeResponse({"ok": 1, "data": seed}),
            FakeResponse({"ok": 1, "data": {"data": comments}}),
            FakeResponse({"ok": 1, "data": {"data": reposts}}),
            FakeResponse({"ok": 1, "data": {"cards": [{"card_group": [{"mblog": row} for row in timeline]}]}}),
        ]
    )

    result = investigate_weibo_seed(
        "https://m.weibo.cn/status/5320265912291527",
        max_comments=10,
        comment_pages=1,
        max_reposts=10,
        repost_pages=1,
        author_posts=10,
        author_pages=1,
        session=session,
    )

    assert result.seed.native_id == "5320265912291527"
    assert result.seed.engagement == {
        "likes": 124,
        "replies": 49,
        "reposts": 26,
        "quotes": 0,
        "bookmarks": 0,
        "impressions": 0,
    }
    assert len(result.comments) == 3
    assert len(result.reposts) == 2
    assert len(result.author_posts) == 3
    assert all(row.parent_record_key == "weibo:5320265912291527" for row in result.reposts)

    insights = result.insights
    assert insights["retrieval"]["comment_retrieved_to_reported_ratio"] == round(3 / 49, 4)
    assert insights["retrieval"]["repost_retrieved_to_reported_ratio"] == round(2 / 26, 4)
    assert insights["author_context"]["seed_vs_recent_likes"]["percentile"] == 1.0
    assert any(item["value"] == "MoveLikeKai" for item in insights["content_signals"]["hashtags"])
    assert any(item["region"] == "广东" for item in insights["response_context"]["top_regions"])
    assert "not the complete audience" in insights["interpretation_guardrail"]

    brief = render_weibo_brief(result)
    assert "124 likes" in brief
    assert "49 comments" in brief
    assert "public sample" in brief
    assert "MoveLikeKai" in brief

    outputs = save_weibo_investigation(result, tmp_path, name="kai3")
    assert len(outputs) == 5
    assert (tmp_path / "kai3.csv").is_file()
    assert (tmp_path / "kai3.xlsx").is_file()
    assert (tmp_path / "kai3.insights.json").is_file()
    assert (tmp_path / "kai3.brief.md").is_file()


def test_insight_builder_does_not_create_sentiment_scores_or_labels():
    from sugar_core.models import PostRecord

    seed = PostRecord(
        platform="weibo",
        native_id="1",
        canonical_url="https://m.weibo.cn/detail/1",
        query="",
        original_text="测试",
        engagement={"likes": 1, "replies": 10, "reposts": 2},
    )
    insight = build_weibo_insights(seed, [], [], [])
    assert "sentiment_score" not in insight
    assert "sentiment_label" not in insight
    assert "not a sentiment poll" in insight["interpretation_guardrail"]
