from __future__ import annotations

import pytest

from sugar_core import collector_registry
from sugar_core.collector_registry import (
    CollectorRequest,
    collector_capabilities,
    collect_registered_comments,
    collect_registered_source,
    fetch_registered_item,
)
from sugar_core.models import PostRecord
from sugar_core.storage import records_to_frame


def _record(platform: str, native_id: str, content_type: str = "post") -> PostRecord:
    return PostRecord(
        platform=platform,
        native_id=native_id,
        canonical_url=f"https://example.test/{native_id}",
        query="test",
        content_type=content_type,
        original_text="example",
    )


def test_record_key_and_relationships_are_exported():
    record = _record("weibo", "abc")
    record.parent_record_key = "weibo:parent"
    record.thread_root_key = "weibo:root"
    record.conversation_id = "root"

    exported = record.export_dict()

    assert record.record_key == "weibo:abc"
    assert exported["record_key"] == "weibo:abc"
    assert exported["parent_record_key"] == "weibo:parent"
    assert exported["thread_root_key"] == "weibo:root"
    assert exported["conversation_id"] == "root"
    assert exported["schema_version"] == "1.3"


def test_relationship_columns_are_prominent_in_dataset_exports():
    record = _record("weibo", "abc")
    record.parent_record_key = "weibo:parent"
    record.thread_root_key = "weibo:root"
    record.conversation_id = "root"

    frame = records_to_frame([record])

    assert list(frame.columns[:7]) == [
        "platform",
        "native_id",
        "record_key",
        "content_type",
        "parent_record_key",
        "thread_root_key",
        "conversation_id",
    ]
    assert frame.loc[0, "parent_record_key"] == "weibo:parent"


def test_capabilities_advertise_partial_platform_surfaces():
    caps = collector_capabilities()

    assert caps["bilibili"]["keyword_search"] is True
    assert caps["bilibili"]["known_item"] is True
    assert caps["bilibili"]["comments"] is True
    assert caps["x"]["keyword_search"] is True
    assert caps["x"]["comments"] is False
    assert caps["wechat"]["known_item"] is True
    assert caps["wechat"]["keyword_search"] is False
    assert caps["wechat"]["comments"] is False


def test_required_credentials_are_validated_before_collection():
    request = CollectorRequest(search_terms=["test"], secrets={})

    with pytest.raises(ValueError, match="x bearer token"):
        collect_registered_source("x", request)

    with pytest.raises(ValueError, match="mastodon token"):
        collect_registered_source("mastodon", request)


def test_mastodon_status_search_is_not_advertised_as_anonymous():
    caps = collector_capabilities()["mastodon"]
    assert caps["keyword_search"] is True
    assert caps["authenticated_search"] is True
    assert caps["anonymous_search"] is False


def test_bilibili_search_records_get_thread_roots(monkeypatch):
    monkeypatch.setattr(
        collector_registry,
        "collect_bilibili_public",
        lambda **kwargs: [_record("bilibili", "BV123", "video")],
    )

    rows = collect_registered_source(
        "bilibili",
        CollectorRequest(search_terms=["language-and-culture centers"]),
    )

    assert rows[0].thread_root_key == "bilibili:BV123"
    assert rows[0].conversation_id == "BV123"


def test_bilibili_known_item_gets_thread_root(monkeypatch):
    monkeypatch.setattr(
        collector_registry,
        "fetch_bilibili_video",
        lambda native_id, query="": _record("bilibili", native_id, "video"),
    )

    row = fetch_registered_item("bilibili", "BV456")

    assert row.thread_root_key == "bilibili:BV456"
    assert row.conversation_id == "BV456"


def test_bilibili_known_item_accepts_public_video_url(monkeypatch):
    seen = {}

    def fake_fetch(native_id, query=""):
        seen["native_id"] = native_id
        return _record("bilibili", native_id, "video")

    monkeypatch.setattr(collector_registry, "fetch_bilibili_video", fake_fetch)
    row = fetch_registered_item("bilibili", "https://www.bilibili.com/video/BV1ABC123/?spm_id_from=333")
    assert seen["native_id"] == "BV1ABC123"
    assert row.native_id == "BV1ABC123"


def test_weibo_known_item_accepts_public_status_url(monkeypatch):
    seen = {}

    def fake_fetch(native_id, **kwargs):
        seen["native_id"] = native_id
        return _record("weibo", native_id)

    monkeypatch.setattr(collector_registry, "fetch_weibo_status", fake_fetch)
    row = fetch_registered_item("weibo", "https://weibo.com/123456/NabcDEF12")
    assert seen["native_id"] == "NabcDEF12"
    assert row.native_id == "NabcDEF12"


def test_wechat_known_item_uses_shared_registry_and_gets_thread_root(monkeypatch):
    monkeypatch.setattr(
        collector_registry,
        "fetch_wechat_article",
        lambda identifier, query="": _record("wechat", "ARTICLE123", "article"),
    )

    row = fetch_registered_item(
        "wechat",
        "https://mp.weixin.qq.com/s/ARTICLE123",
        CollectorRequest(search_terms=["public diplomacy"]),
    )

    assert row.thread_root_key == "wechat:ARTICLE123"
    assert row.conversation_id == "ARTICLE123"


def test_bilibili_comments_link_to_video(monkeypatch):
    monkeypatch.setattr(
        collector_registry,
        "collect_bilibili_comments",
        lambda native_id, **kwargs: [
            _record("bilibili", "9001", "comment"),
            _record("bilibili", "9002", "comment"),
        ],
    )

    rows = collect_registered_comments(
        "bilibili",
        "BVROOT",
        CollectorRequest(max_posts_per_query=10, max_pages_per_query=2),
    )

    assert len(rows) == 2
    assert all(row.parent_record_key == "bilibili:BVROOT" for row in rows)
    assert all(row.thread_root_key == "bilibili:BVROOT" for row in rows)
    assert all(row.conversation_id == "BVROOT" for row in rows)


def test_unsupported_surface_fails_explicitly():
    with pytest.raises(ValueError, match="comment retrieval"):
        collect_registered_comments("x", "123")
