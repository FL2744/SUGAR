from __future__ import annotations

from pathlib import Path

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
    assert exported["schema_version"] == "1.2"


def test_capabilities_advertise_partial_platform_surfaces():
    caps = collector_capabilities()

    assert caps["bilibili"]["keyword_search"] is True
    assert caps["bilibili"]["known_item"] is True
    assert caps["bilibili"]["comments"] is True
    assert caps["x"]["keyword_search"] is True
    assert caps["x"]["comments"] is False


def test_required_credentials_are_validated_before_collection(monkeypatch):
    request = CollectorRequest(search_terms=["test"], secrets={})

    with pytest.raises(ValueError, match="x_bearer_token"):
        collect_registered_source("x", request)


def test_bilibili_search_records_get_thread_roots(monkeypatch):
    monkeypatch.setattr(
        collector_registry,
        "collect_bilibili_public",
        lambda **kwargs: [_record("bilibili", "BV123", "video")],
    )

    rows = collect_registered_source(
        "bilibili",
        CollectorRequest(search_terms=["Confucius Institute"]),
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
