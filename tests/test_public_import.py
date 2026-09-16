from __future__ import annotations

import json
from pathlib import Path

from sugar_core.models import PostRecord
from sugar_core.public_import import run_public_import


def test_public_import_saves_standard_sugar_outputs(monkeypatch, tmp_path: Path):
    def fake_fetch(source, item, request):
        return PostRecord(
            platform=source,
            native_id="item-1",
            canonical_url=item,
            query=item,
            original_text="Public source text",
            source_mode=f"{source}_public_url",
            source_host="example.invalid",
            source_url=item,
        )

    monkeypatch.setattr("sugar_core.public_import.fetch_registered_item", fake_fetch)
    outputs = run_public_import(
        {
            "source": "wechat",
            "items": ["https://mp.weixin.qq.com/s/example"],
            "output_directory": str(tmp_path),
            "name": "classroom",
        }
    )

    assert len(outputs) == 3
    csv_path = Path(outputs[0])
    xlsx_path = Path(outputs[1])
    metadata_path = Path(outputs[2])
    assert csv_path.is_file()
    assert xlsx_path.is_file()
    assert metadata_path.is_file()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["source"] == "wechat"
    assert metadata["mode"] == "known_public_item_import"
    assert metadata["items_requested"] == 1
    assert metadata["items_collected"] == 1
    assert metadata["collector_capabilities"]["known_item"] is True


def test_public_import_deduplicates_repeated_input_before_collection(monkeypatch, tmp_path: Path):
    calls = []

    def fake_fetch(source, item, request):
        calls.append(item)
        return PostRecord(
            platform=source,
            native_id=str(len(calls)),
            canonical_url=item,
            query=item,
            original_text="text",
        )

    monkeypatch.setattr("sugar_core.public_import.fetch_registered_item", fake_fetch)
    run_public_import(
        {
            "source": "douyin",
            "items": ["https://www.douyin.com/video/1", "https://www.douyin.com/video/1"],
            "output_directory": str(tmp_path),
        }
    )
    assert calls == ["https://www.douyin.com/video/1"]


def test_public_import_normalizes_weibo_url_before_collection(monkeypatch, tmp_path: Path):
    calls = []
    public_url = "https://m.weibo.cn/status/5320265912291527"

    def fake_fetch(source, item, request):
        calls.append((source, item))
        return PostRecord(
            platform=source,
            native_id=item,
            canonical_url=public_url,
            original_text="Weibo public source text",
        )

    monkeypatch.setattr("sugar_core.public_import.fetch_registered_item", fake_fetch)
    outputs = run_public_import(
        {
            "source": "weibo",
            "items": [public_url],
            "output_directory": str(tmp_path),
        }
    )

    assert calls == [("weibo", "5320265912291527")]
    assert Path(outputs[0]).is_file()
