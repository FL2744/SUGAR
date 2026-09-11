from __future__ import annotations

from urllib.parse import urlencode

import pytest
import requests

from sugar_core.bilibili import (
    BilibiliAccessError,
    collect_bilibili_comments,
    collect_bilibili_public,
    fetch_bilibili_video,
    normalize_bilibili_engagement,
)


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, url="https://api.bilibili.com/test"):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.url = url

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        if not self.responses:
            raise AssertionError(f"Unexpected GET {url}")
        response = self.responses.pop(0)
        if response.url.endswith("/test"):
            response.url = url + ("?" + urlencode(params) if params else "")
        return response


def _video_payload(*, bvid="BV1TEST123", aid=1001, pubdate=1789056000):
    return {
        "code": 0,
        "message": "0",
        "data": {
            "bvid": bvid,
            "aid": aid,
            "cid": 555,
            "title": "Confucius Institute technology workshop",
            "desc": "Public event for university students in Bishkek.",
            "pubdate": pubdate,
            "duration": 180,
            "tname": "Education",
            "owner": {"mid": 77, "name": "Example University"},
            "stat": {
                "view": 1200,
                "like": 80,
                "coin": 7,
                "favorite": 12,
                "reply": 5,
                "danmaku": 9,
                "share": 14,
            },
        },
    }


def test_bilibili_metrics_do_not_mislabel_shares_as_reposts():
    normalized = normalize_bilibili_engagement(
        {"view": 1000, "like": 50, "favorite": 8, "reply": 6, "share": 20}
    )
    assert normalized == {
        "likes": 50,
        "replies": 6,
        "reposts": 0,
        "quotes": 0,
        "bookmarks": 8,
        "impressions": 1000,
    }


def test_fetch_public_video_normalizes_metadata_and_preserves_native_stats():
    session = FakeSession([FakeResponse(_video_payload())])
    record = fetch_bilibili_video("BV1TEST123", query="孔子学院", session=session)

    assert record.platform == "bilibili"
    assert record.content_type == "video"
    assert record.native_id == "BV1TEST123"
    assert record.canonical_url == "https://www.bilibili.com/video/BV1TEST123"
    assert record.author_handle == "77"
    assert record.author_name == "Example University"
    assert record.engagement["likes"] == 80
    assert record.engagement["impressions"] == 1200
    assert record.engagement["reposts"] == 0
    assert record.raw_stats["share"] == 14
    assert record.raw_stats["coin"] == 7
    assert record.raw_stats["danmaku"] == 9
    assert "technology workshop" in record.original_text
    assert record.query_matches == ["孔子学院"]


def test_keyword_search_merges_duplicate_video_query_provenance_without_auth_state():
    search_one = {
        "code": 0,
        "data": {
            "result": [
                {
                    "bvid": "BV1DUPLICATE",
                    "aid": 100,
                    "title": '<em class="keyword">Confucius</em> event',
                    "description": "Student program",
                    "author": "Example Center",
                    "mid": 10,
                    "pubdate": 1789056000,
                    "play": 100,
                    "review": 3,
                    "favorites": 4,
                }
            ]
        },
    }
    search_two = {
        "code": 0,
        "data": {
            "result": [
                {
                    "bvid": "BV1DUPLICATE",
                    "aid": 100,
                    "title": "孔子学院 event",
                    "description": "Student program",
                    "author": "Example Center",
                    "mid": 10,
                    "pubdate": 1789056000,
                    "play": 110,
                    "review": 4,
                    "favorites": 5,
                }
            ]
        },
    }
    session = FakeSession([FakeResponse(search_one), FakeResponse(search_two)])

    records = collect_bilibili_public(
        search_terms=["Confucius Institute", "孔子学院"],
        max_posts_per_query=1,
        max_pages_per_query=1,
        hydrate_details=False,
        initialize_session=False,
        session=session,
    )

    assert len(records) == 1
    assert records[0].query_matches == ["Confucius Institute", "孔子学院"]
    assert records[0].native_id == "BV1DUPLICATE"
    assert "<em" not in records[0].original_text


def test_search_fails_closed_when_bilibili_returns_access_control_code():
    session = FakeSession(
        [FakeResponse({"code": -412, "message": "request blocked", "data": None})]
    )
    with pytest.raises(BilibiliAccessError, match="will not synthesize credentials"):
        collect_bilibili_public(
            search_terms=["孔子学院"],
            initialize_session=False,
            session=session,
        )


def test_search_date_filter_uses_inclusive_dates():
    result = {
        "code": 0,
        "data": {
            "result": [
                {
                    "bvid": "BV1INRANGE",
                    "aid": 1,
                    "title": "In range",
                    "pubdate": 1788998400,
                },
                {
                    "bvid": "BV1OUTRANGE",
                    "aid": 2,
                    "title": "Out of range",
                    "pubdate": 1789084800,
                },
            ]
        },
    }
    session = FakeSession([FakeResponse(result)])
    records = collect_bilibili_public(
        search_terms=["test"],
        since="2026-09-10",
        until="2026-09-10",
        max_posts_per_query=20,
        max_pages_per_query=1,
        hydrate_details=False,
        initialize_session=False,
        session=session,
    )
    assert [record.native_id for record in records] == ["BV1INRANGE"]


def test_public_comment_pagination_normalizes_top_level_replies():
    detail = FakeResponse(_video_payload(bvid="BV1COMMENTS", aid=222))
    first_page = FakeResponse(
        {
            "code": 0,
            "data": {
                "replies": [
                    {
                        "rpid": 9001,
                        "ctime": 1789056000,
                        "like": 12,
                        "rcount": 2,
                        "member": {"mid": 501, "uname": "Commenter A"},
                        "content": {"message": "This workshop is for university students."},
                    }
                ],
                "cursor": {"next": 1, "is_end": False},
            },
        }
    )
    second_page = FakeResponse(
        {
            "code": 0,
            "data": {
                "replies": [
                    {
                        "rpid": 9002,
                        "ctime": 1789059600,
                        "like": 3,
                        "rcount": 0,
                        "member": {"mid": 502, "uname": "Commenter B"},
                        "content": {"message": "Where can I register?"},
                    }
                ],
                "cursor": {"next": 2, "is_end": True},
            },
        }
    )
    session = FakeSession([detail, first_page, second_page])

    comments = collect_bilibili_comments(
        "BV1COMMENTS",
        query="technology workshop",
        max_comments=10,
        max_pages=5,
        session=session,
    )

    assert [comment.native_id for comment in comments] == ["9001", "9002"]
    assert comments[0].content_type == "comment"
    assert comments[0].author_handle == "501"
    assert comments[0].author_name == "Commenter A"
    assert comments[0].engagement["likes"] == 12
    assert comments[0].engagement["replies"] == 2
    assert comments[0].canonical_url.endswith("#reply9001")
    assert session.calls[1]["params"]["next"] == 0
    assert session.calls[2]["params"]["next"] == 1


def test_public_comment_access_gate_is_not_bypassed():
    detail = FakeResponse(_video_payload(bvid="BV1COMMENTS", aid=222))
    blocked = FakeResponse({"code": -101, "message": "not logged in", "data": None})
    session = FakeSession([detail, blocked])

    with pytest.raises(BilibiliAccessError, match="will not synthesize credentials"):
        collect_bilibili_comments("BV1COMMENTS", session=session)
