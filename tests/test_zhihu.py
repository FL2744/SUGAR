from __future__ import annotations

import pytest

from sugar_core.zhihu import ZHIHU_SEARCH_URL, collect_zhihu_official


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def test_zhihu_official_search_maps_structured_results_and_auth_headers():
    session = FakeSession(
        {
            "Code": 0,
            "Message": "success",
            "Data": {
                "Items": [
                    {
                        "Title": "How to understand <em>RAG</em>",
                        "ContentText": "A <em>retrieval</em> answer.",
                        "Url": "https://www.zhihu.com/question/123/answer/456",
                        "AuthorName": "Example Author",
                        "VoteUpCount": 128,
                        "CommentCount": 15,
                        "EditTime": 1710000000,
                    }
                ]
            },
        }
    )
    records = collect_zhihu_official(
        search_terms=["RAG"],
        access_secret="secret-value",
        max_posts_per_query=8,
        session=session,
    )

    assert len(records) == 1
    record = records[0]
    assert record.platform == "zhihu"
    assert record.native_id == "answer-456"
    assert record.original_text == "A retrieval answer."
    assert record.author_name == "Example Author"
    assert record.engagement == {"likes": 128, "replies": 15}
    assert record.source_mode == "zhihu_official_search"

    url, kwargs = session.calls[0]
    assert url == ZHIHU_SEARCH_URL
    assert kwargs["params"] == {"Query": "RAG"}
    assert kwargs["headers"]["Authorization"] == "Bearer secret-value"
    assert kwargs["headers"]["X-Request-Timestamp"].isdigit()
    assert kwargs["allow_redirects"] is False
    assert "secret-value" not in str(kwargs["params"])


def test_zhihu_search_requires_legitimate_access_secret():
    with pytest.raises(ValueError, match="Access Secret"):
        collect_zhihu_official(search_terms=["test"], access_secret="")


def test_zhihu_api_error_fails_explicitly():
    session = FakeSession({"Code": 40101, "Message": "permission denied", "Data": {}})
    with pytest.raises(RuntimeError, match="permission denied"):
        collect_zhihu_official(search_terms=["test"], access_secret="secret", session=session)


def test_zhihu_results_without_urls_are_not_invented():
    session = FakeSession({"Code": 0, "Data": {"Items": [{"Title": "No source URL"}]}})
    assert collect_zhihu_official(search_terms=["test"], access_secret="secret", session=session) == []
