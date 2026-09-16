from __future__ import annotations

import json
from pathlib import Path

import pytest

from sugar_core.models import PostRecord
from sugar_core.service import run_search


def _record(platform: str = "bilibili") -> PostRecord:
    return PostRecord(
        platform=platform,
        native_id="demo-1",
        canonical_url="https://example.invalid/demo-1",
        query="demo",
        query_matches=["demo"],
        original_text="demo record",
    )


def test_multi_source_search_continues_after_one_source_fails(monkeypatch, tmp_path: Path):
    events: list[tuple[str, dict]] = []

    def fake_collect(source, _request):
        if source == "bluesky":
            raise RuntimeError("403 access blocked")
        return [_record(source)]

    monkeypatch.setattr("sugar_core.service.collect_registered_source", fake_collect)
    outputs = run_search(
        {
            "sources": ["bluesky", "bilibili"],
            "terms": ["demo"],
            "translate_posts": False,
            "infer_locations": False,
            "output_directory": str(tmp_path),
        },
        progress=lambda event, values: events.append((event, values)),
    )

    csv_path = Path(outputs[0])
    assert csv_path.is_file()
    metadata = json.loads(csv_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert metadata["partial_collection"] is True
    assert metadata["successful_sources"] == ["bilibili"]
    assert metadata["source_failures"]["bluesky"]["exception"] == "RuntimeError"
    assert any(event == "source_failed" and values["source"] == "bluesky" for event, values in events)
    assert any(event == "collected" and values["source"] == "bilibili" for event, values in events)


def test_search_fails_clearly_when_every_source_fails(monkeypatch, tmp_path: Path):
    def fake_collect(source, _request):
        raise RuntimeError(f"{source} unavailable")

    monkeypatch.setattr("sugar_core.service.collect_registered_source", fake_collect)
    with pytest.raises(RuntimeError, match="All selected sources failed"):
        run_search(
            {
                "sources": ["bluesky", "bilibili"],
                "terms": ["demo"],
                "translate_posts": False,
                "infer_locations": False,
                "output_directory": str(tmp_path),
            }
        )
