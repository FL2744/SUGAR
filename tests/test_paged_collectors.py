from __future__ import annotations

from dataclasses import dataclass

from sugar_core.collector_registry import CollectorRequest
from sugar_core.paged_collectors import collect_bilibili_page_range, collect_weibo_page_range


@dataclass
class FakeResponse:
    payload: object
    url: str = "https://example.test/api"
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

    def get(self, url, params=None, **kwargs):
        self.calls.append({"url": url, "params": dict(params or {}), **kwargs})
        if not self.responses:
            raise AssertionError(f"unexpected request: {url}")
        return self.responses.pop(0)


def test_bilibili_page_adapter_starts_at_checkpointed_page(monkeypatch):
    payload = {
        "code": 0,
        "data": {
            "result": [
                {
                    "bvid": "BV6PAGE",
                    "aid": 600,
                    "title": "Public program",
                    "description": "Example",
                    "author": "Example Center",
                    "mid": 10,
                    "pubdate": 1789056000,
                    "play": 10,
                }
            ]
        },
    }
    session = QueueSession([FakeResponse(payload)])
    monkeypatch.setattr("sugar_core.bilibili.create_bilibili_session", lambda: session)

    rows = collect_bilibili_page_range(
        CollectorRequest(
            search_terms=["孔子学院"],
            max_posts_per_query=20,
            max_pages_per_query=1,
            config={
                "_harvest_page_start": 6,
                "_harvest_page_count": 1,
                "bilibili_hydrate_details": False,
                "bilibili_initialize_session": False,
            },
        )
    )

    assert [row.native_id for row in rows] == ["BV6PAGE"]
    assert session.calls[0]["params"]["page"] == 6
    assert session.calls[0]["params"]["keyword"] == "孔子学院"


def test_weibo_page_adapter_starts_at_checkpointed_page(monkeypatch):
    status = {
        "id": "11001",
        "bid": "Qpage11",
        "created_at": "Sat Sep 12 10:00:00 +0800 2026",
        "text": "<b>Public program</b>",
        "attitudes_count": 2,
        "comments_count": 1,
        "reposts_count": 0,
        "user": {"id": "42", "screen_name": "Example account", "location": "北京"},
    }
    session = QueueSession(
        [FakeResponse({"ok": 1, "data": {"cards": [{"card_type": 9, "mblog": status}]}})]
    )
    monkeypatch.setattr("sugar_core.weibo.create_weibo_session", lambda cookie="": session)

    rows = collect_weibo_page_range(
        CollectorRequest(
            search_terms=["鲁班工坊"],
            max_posts_per_query=20,
            max_pages_per_query=1,
            config={
                "_harvest_page_start": 11,
                "_harvest_page_count": 1,
                "weibo_hydrate_details": False,
            },
        )
    )

    assert [row.native_id for row in rows] == ["11001"]
    assert session.calls[0]["params"]["page"] == 11
    assert "鲁班工坊" in session.calls[0]["params"]["containerid"]
