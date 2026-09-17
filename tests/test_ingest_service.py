from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from sugar_core import service
from sugar_core.models import PostRecord


def _record() -> PostRecord:
    return PostRecord(
        platform="wechat",
        native_id="ARTICLE123",
        canonical_url="https://mp.weixin.qq.com/s/ARTICLE123",
        query="",
        content_type="article",
        original_text="Public article",
        source_mode="wechat_public_article",
        source_host="mp.weixin.qq.com",
    )


def test_ingest_saves_normalized_public_item_and_metadata(tmp_path: Path, monkeypatch):
    seen = {}

    def fake_fetch(source, identifier, request):
        seen.update(source=source, identifier=identifier, request=request)
        return _record()

    monkeypatch.setattr(service, "fetch_registered_item", fake_fetch)
    events = []
    outputs = service.run_ingest(
        {
            "source": "wechat",
            "identifier": "https://mp.weixin.qq.com/s/ARTICLE123",
            "query": "public diplomacy",
            "output_directory": str(tmp_path),
        },
        progress=lambda event, values: events.append((event, values)),
    )

    assert seen["source"] == "wechat"
    assert seen["request"].search_terms == ["public diplomacy"]
    csv = next(Path(value) for value in outputs if value.endswith(".csv"))
    metadata_path = csv.with_suffix(".metadata.json")
    assert csv.is_file()
    assert csv.with_suffix(".xlsx").is_file()
    frame = pd.read_csv(csv)
    assert frame.loc[0, "platform"] == "wechat"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["operation"] == "ingest"
    assert metadata["source"] == "wechat"
    assert metadata["input_identifier"].endswith("ARTICLE123")
    assert metadata["collector_capabilities"]["known_item"] is True
    assert [event for event, _ in events] == ["starting", "collecting", "collected", "saved"]


def test_ingest_rejects_missing_or_search_only_source(tmp_path: Path):
    with pytest.raises(ValueError, match="Choose a source"):
        service.run_ingest({"identifier": "something", "output_directory": str(tmp_path)})

    with pytest.raises(ValueError, match="known-item retrieval"):
        service.run_ingest(
            {"source": "x", "identifier": "123", "output_directory": str(tmp_path)},
            secrets={"x_bearer_token": "not-used-for-known-item"},
        )
