from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core.collection_control import (
    finish_collection_control,
    read_collection_control,
    start_collection_control,
    update_collection_control,
)
from sugar_core.models import PostRecord
from sugar_core.service import run_search
from sugar_core.workspace import SugarWorkspace


def _workspace(path: Path) -> SugarWorkspace:
    return SugarWorkspace.create(path, name="Collection control tests")


def test_collection_control_updates_scope_retry_and_cooperative_cancel(tmp_path: Path):
    workspace = _workspace(tmp_path / "project")
    started = start_collection_control(
        workspace,
        "run_12345678",
        sources=["bluesky"],
        terms=["first query"],
        since="2025-01-01",
        until="2025-12-31",
        post_languages=["en"],
        excluded_topics=["spam"],
    )

    assert started["revision"] == 1
    assert started["cancel_requested"] is False
    updated = update_collection_control(
        workspace,
        "run_12345678",
        sources=["mastodon"],
        terms=["new query"],
        since="2025-02-01",
        post_languages=["zh"],
        excluded_topics=["tourism"],
        retry_source="bluesky",
    )
    assert updated["revision"] == 2
    assert updated["sources"] == ["mastodon"]
    assert updated["terms"] == ["new query"]
    assert updated["post_languages"] == ["zh"]
    assert updated["retry_requests"][0]["source"] == "bluesky"

    cancelled = update_collection_control(workspace, "run_12345678", cancel=True)
    assert cancelled["cancel_requested"] is True
    finish_collection_control(workspace, "run_12345678", status="cancelled")
    assert read_collection_control(workspace, "run_12345678")["status"] == "cancelled"
    with pytest.raises(ValueError, match="no longer active"):
        update_collection_control(workspace, "run_12345678", terms=["too late"])


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"sources": ["unknown-social-site"]}, "Unsupported collection source"),
        ({"since": "not-a-date"}, "valid ISO date"),
        ({"since": "2025-12-31", "until": "2025-01-01"}, "on or before"),
    ],
)
def test_collection_control_rejects_invalid_live_scope(tmp_path: Path, changes, message: str):
    workspace = _workspace(tmp_path / "project")
    start_collection_control(workspace, "run_12345678", sources=["bluesky"], terms=["query"])
    with pytest.raises(ValueError, match=message):
        update_collection_control(workspace, "run_12345678", **changes)


def test_run_search_applies_scope_changes_at_the_next_request_boundary(monkeypatch, tmp_path: Path):
    control = {
        "status": "running",
        "revision": 1,
        "sources": ["bluesky"],
        "terms": ["first query"],
        "since": "2025-01-01",
        "until": "2025-12-31",
        "post_languages": ["en"],
        "excluded_topics": [],
        "retry_requests": [],
        "cancel_requested": False,
    }
    observed = []

    def collect(source, request):
        observed.append((source, request))
        if len(observed) == 1:
            control.update({
                "revision": 2,
                "sources": ["mastodon"],
                "terms": ["second query"],
                "since": "2025-02-01",
                "until": "2025-11-30",
                "post_languages": ["zh"],
                "excluded_topics": ["omit-me"],
            })
            return [PostRecord("bluesky", "1", "https://example.test/1", "first query", original_text="keep old")]
        return [
            PostRecord("mastodon", "2", "https://example.test/2", "second query", original_text="omit-me record"),
            PostRecord("mastodon", "3", "https://example.test/3", "second query", original_text="keep new"),
        ]

    monkeypatch.setattr("sugar_core.service.collect_registered_source", collect)
    outputs = run_search(
        {
            "sources": ["bluesky"],
            "terms": ["first query"],
            "since": "2025-01-01",
            "until": "2025-12-31",
            "post_languages": ["en"],
            "output_directory": str(tmp_path),
            "translate_posts": False,
            "infer_locations": False,
            "continue_on_source_error": True,
        },
        {},
        control_reader=lambda: control,
    )

    assert [(source, request.search_terms) for source, request in observed] == [
        ("bluesky", ["first query"]),
        ("mastodon", ["second query"]),
    ]
    second_request = observed[1][1]
    assert second_request.since == "2025-02-01"
    assert second_request.until == "2025-11-30"
    assert second_request.config["post_languages"] == ["zh"]
    records = Path(outputs[0]).read_text(encoding="utf-8-sig")
    assert "keep old" in records and "keep new" in records
    assert "omit-me record" not in records
    metadata = json.loads(Path(outputs[2]).read_text(encoding="utf-8"))
    assert metadata["sources"] == ["bluesky", "mastodon"]
    assert metadata["since"] == "2025-02-01"


def test_run_search_retries_a_failed_source_at_a_safe_boundary(monkeypatch, tmp_path: Path):
    control = {
        "status": "running",
        "revision": 1,
        "sources": ["bluesky"],
        "terms": ["query"],
        "since": "",
        "until": "",
        "post_languages": [],
        "excluded_topics": [],
        "retry_requests": [],
        "cancel_requested": False,
    }
    attempts = []

    def collect(source, request):
        attempts.append(source)
        if len(attempts) == 1:
            control["retry_requests"] = [{"id": "retry-1", "source": "bluesky"}]
            raise RuntimeError("temporary network failure")
        return [PostRecord("bluesky", "1", "https://example.test/1", "query", original_text="recovered")]

    monkeypatch.setattr("sugar_core.service.collect_registered_source", collect)
    outputs = run_search(
        {
            "sources": ["bluesky"],
            "terms": ["query"],
            "output_directory": str(tmp_path),
            "translate_posts": False,
            "infer_locations": False,
            "continue_on_source_error": True,
        },
        {},
        control_reader=lambda: control,
    )

    assert attempts == ["bluesky", "bluesky"]
    assert "recovered" in Path(outputs[0]).read_text(encoding="utf-8-sig")
    coverage = json.loads(Path(outputs[3]).read_text(encoding="utf-8"))
    assert coverage["sources"]["bluesky"]["status"] == "partial"


def test_run_search_honors_cancel_between_requests(monkeypatch, tmp_path: Path):
    control = {
        "status": "running",
        "revision": 1,
        "sources": ["bluesky"],
        "terms": ["first", "second"],
        "since": "",
        "until": "",
        "post_languages": [],
        "excluded_topics": [],
        "retry_requests": [],
        "cancel_requested": False,
    }
    attempts = []

    def collect(source, request):
        attempts.extend(request.search_terms)
        control["cancel_requested"] = True
        return [PostRecord("bluesky", "1", "https://example.test/1", "first", original_text="saved before stop")]

    monkeypatch.setattr("sugar_core.service.collect_registered_source", collect)
    outputs = run_search(
        {
            "sources": ["bluesky"],
            "terms": ["first", "second"],
            "output_directory": str(tmp_path),
            "translate_posts": False,
            "infer_locations": False,
            "continue_on_source_error": True,
        },
        {},
        control_reader=lambda: control,
    )

    assert attempts == ["first"]
    metadata = json.loads(Path(outputs[2]).read_text(encoding="utf-8"))
    assert metadata["collection_cancelled"] is True
    coverage = json.loads(Path(outputs[3]).read_text(encoding="utf-8"))
    assert coverage["sources"]["bluesky"]["status"] == "partial"


def test_run_search_enforces_estimated_memory_budget_and_reports_partial_coverage(monkeypatch, tmp_path: Path):
    def collect(_source, request):
        return [
            PostRecord(
                "bluesky", str(index), f"https://example.test/{index}", request.search_terms[0],
                original_text="large source text " * 10_000,
            )
            for index in range(2)
        ]

    monkeypatch.setattr("sugar_core.service.collect_registered_source", collect)
    outputs = run_search(
        {
            "sources": ["bluesky"],
            "terms": ["bounded query"],
            "output_directory": str(tmp_path),
            "translate_posts": False,
            "infer_locations": False,
            "continue_on_source_error": True,
            "max_memory_bytes": 1024 * 1024,
            "max_parallel_sources": 5,
        },
        {},
    )

    metadata = json.loads(Path(outputs[2]).read_text(encoding="utf-8"))
    coverage = json.loads(Path(outputs[3]).read_text(encoding="utf-8"))
    assert metadata["collection_memory_limit_reached"] is True
    assert metadata["max_memory_bytes"] == 1024 * 1024
    assert metadata["estimated_record_memory_bytes"] <= metadata["max_memory_bytes"]
    assert coverage["sources"]["bluesky"]["status"] == "partial"
    assert coverage["sources"]["bluesky"]["error_type"] == "MemoryBudgetExceeded"
    assert "not treated as evidence of absence" not in coverage["sources"]["bluesky"]["reason"]
