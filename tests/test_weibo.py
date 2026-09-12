from __future__ import annotations

from dataclasses import dataclass

import pytest

from sugar_core import collector_registry
from sugar_core.collector_registry import CollectorRequest, collector_capabilities
from sugar_core.weibo import (
    WeiboAccessError,
    collect_weibo_comments,
    collect_weibo_public,
    create_weibo_session,
    fetch_weibo_status,
)


@dataclass
class FakeResponse:
    payload: object
    url: str = "https://m.weibo.cn/test"
    status_code: int = 200

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class QueueSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"unexpected request: {url}")
        return self.responses.pop(0)


def _status(status_id="123", text="<b>Hello</b> world", created="Sat Sep 12 10:00:00 +0800 2026"):
    return {
        "id": status_id,
        "bid": "Qabc123",
        "created_at": created,
        "text": text,
        "attitudes_count": 7,
        "comments_count": 3,
        "reposts_count": 2,
        "user": {"id": "42", "screen_name": "中国机构", "location": "北京"},
    }


def test_public_session_uses_pwa_headers_without_inventing_cookie():
    session = create_weibo_session()

    assert session.headers["MWeibo-Pwa"] == "1"
    assert session.headers["X-Requested-With"] == "XMLHttpRequest"
    assert "Cookie" not in session.headers


def test_supplied_cookie_is_forwarded_but_not_generated():
    session = create_weibo_session("SUB=legitimate-user-session")

    assert session.headers["Cookie"] == "SUB=legitimate-user-session"


def test_fetch_status_normalizes_text_time_metrics_and_thread_root():
    session = QueueSession(
        [FakeResponse({"ok": 1, "data": _status()}, url="https://m.weibo.cn/statuses/show?id=123")]
    )

    record = fetch_weibo_status("123", session=session)

    assert record.platform == "weibo"
    assert record.native_id == "123"
    assert record.original_text == "Hello world"
    assert record.published_at == "2026-09-12T02:00:00Z"
    assert record.engagement["likes"] == 7
    assert record.engagement["replies"] == 3
    assert record.engagement["reposts"] == 2
    assert record.thread_root_key == "weibo:123"
    assert record.conversation_id == "123"
    assert record.author_name == "中国机构"


def test_fetch_long_status_uses_public_extend_text():
    status = _status(text="short")
    status["isLongText"] = True
    session = QueueSession(
        [
            FakeResponse({"ok": 1, "data": status}),
            FakeResponse({"ok": 1, "data": {"longTextContent": "<p>完整 正文</p>"}}),
        ]
    )

    record = fetch_weibo_status("123", session=session)

    assert record.original_text == "完整 正文"
    assert len(session.calls) == 2


def test_login_required_fails_closed():
    session = QueueSession([FakeResponse({"ok": -100, "msg": "请先登录"})])

    with pytest.raises(WeiboAccessError, match="requires a logged-in"):
        fetch_weibo_status("123", session=session)


def test_search_preserves_multi_query_provenance_without_hydration():
    card = {"card_type": 9, "mblog": _status()}
    session = QueueSession(
        [
            FakeResponse({"ok": 1, "data": {"cards": [card]}}),
            FakeResponse({"ok": 1, "data": {"cards": [card]}}),
        ]
    )

    rows = collect_weibo_public(
        search_terms=["孔子学院", "Confucius Institute"],
        max_posts_per_query=1,
        max_pages_per_query=1,
        hydrate_details=False,
        session=session,
    )

    assert len(rows) == 1
    assert rows[0].query_matches == ["孔子学院", "Confucius Institute"]
    assert rows[0].source_mode == "weibo_public_search"


def test_search_login_gate_is_not_retried_or_bypassed():
    session = QueueSession([FakeResponse({"ok": -100, "msg": "未登录"})])

    with pytest.raises(WeiboAccessError):
        collect_weibo_public(
            search_terms=["鲁班工坊"],
            hydrate_details=False,
            session=session,
        )

    assert len(session.calls) == 1


def test_comments_link_to_status_and_direct_reply_parent():
    comment = {
        "id": "9001",
        "created_at": "Sat Sep 12 11:00:00 +0800 2026",
        "text": "<span>公开评论</span>",
        "like_count": 4,
        "total_number": 1,
        "reply_comment": {"id": "8999"},
        "user": {"id": "77", "screen_name": "评论者"},
    }
    session = QueueSession([FakeResponse({"ok": 1, "data": {"data": [comment]}})])

    rows = collect_weibo_comments("123", max_pages=1, session=session)

    assert len(rows) == 1
    row = rows[0]
    assert row.content_type == "comment"
    assert row.parent_record_key == "weibo:8999"
    assert row.thread_root_key == "weibo:123"
    assert row.conversation_id == "123"
    assert row.original_text == "公开评论"
    assert row.engagement["likes"] == 4


def test_top_level_comment_parent_is_status():
    comment = {
        "id": "9002",
        "created_at": "Sat Sep 12 11:00:00 +0800 2026",
        "text": "top level",
        "user": {"id": "78", "screen_name": "评论者2"},
    }
    session = QueueSession([FakeResponse({"ok": 1, "data": {"data": [comment]}})])

    row = collect_weibo_comments("123", max_pages=1, session=session)[0]

    assert row.parent_record_key == "weibo:123"
    assert row.thread_root_key == "weibo:123"


def test_registry_advertises_weibo_surfaces_and_passes_optional_cookie(monkeypatch):
    captured = {}

    def fake_collect(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(collector_registry, "collect_weibo_public", fake_collect)
    request = CollectorRequest(
        search_terms=["美国空间"],
        secrets={"weibo_cookie": "SUB=user-provided"},
    )

    rows = collector_registry.collect_registered_source("weibo", request)
    caps = collector_capabilities()["weibo"]

    assert rows == []
    assert captured["cookie"] == "SUB=user-provided"
    assert caps["keyword_search"] is True
    assert caps["known_item"] is True
    assert caps["comments"] is True
    assert caps["anonymous_search"] is True
    assert caps["authenticated_search"] is True
