from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from sugar_core.importers import ImportSpec, ImportValidationError, import_external_dataset, import_external_records
from sugar_core.observations import observation_from_post
from sugar_core.triage_io import load_post_records


def test_external_csv_import_preserves_identity_mapping_and_quarantines_invalid_rows(tmp_path: Path):
    source = tmp_path / "northstar.csv"
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["network", "item", "link", "body", "time", "likes", "extra"])
        writer.writeheader()
        writer.writerow({
            "network": "telegram",
            "item": "42",
            "link": "https://example.test/42",
            "body": "Scholarship discussion",
            "time": "2026-09-01T12:00:00Z",
            "likes": "7",
            "extra": "preserve-me",
        })
        writer.writerow({"network": "telegram", "body": "missing identity"})

    spec = ImportSpec(
        source_system="northstar-export",
        field_map={"native_id": "item", "original_text": "body", "published_at": "time"},
    )
    result = import_external_records(source, spec)

    assert len(result.records) == 1
    assert len(result.rejected) == 1
    record = result.records[0]
    assert record.platform == "telegram"
    assert record.native_id == "42"
    assert record.original_text == "Scholarship discussion"
    assert record.engagement["likes"] == 7
    assert record.source_mode == "external_import:northstar-export"
    assert record.raw_stats["external_fields"]["extra"] == "preserve-me"


def test_external_import_deduplicates_and_merges_query_provenance(tmp_path: Path):
    source = tmp_path / "records.jsonl"
    rows = [
        {"platform": "test", "native_id": "1", "query": "alpha", "original_text": "same"},
        {"platform": "test", "native_id": "1", "query": "beta", "original_text": "same"},
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    result = import_external_records(source)

    assert len(result.records) == 1
    assert result.duplicate_rows == 1
    assert result.records[0].query_matches == ["alpha", "beta"]


def test_external_import_outputs_manifest_jsonl_and_rejections(tmp_path: Path):
    source = tmp_path / "external.csv"
    source.write_text("platform,native_id,text\nexample,1,valid\nexample,,invalid\n", encoding="utf-8")

    outputs = import_external_dataset(source, tmp_path / "normalized", source_system="upstream")
    output_paths = [Path(path) for path in outputs]
    manifest = tmp_path / "normalized.import.json"
    rejected = tmp_path / "normalized.rejected.jsonl"
    jsonl = tmp_path / "normalized.jsonl"

    assert manifest in output_paths
    assert rejected in output_paths
    assert jsonl in output_paths
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["accepted_records"] == 1
    assert payload["rejected_rows"] == 1
    assert payload["source_system"] == "upstream"
    assert len(payload["source_sha256"]) == 64


def test_external_import_strict_mode_fails_at_invalid_identity(tmp_path: Path):
    source = tmp_path / "bad.jsonl"
    source.write_text(json.dumps({"platform": "test", "text": "no id"}) + "\n", encoding="utf-8")
    with pytest.raises(ImportValidationError, match="Row 1"):
        import_external_records(source, ImportSpec(strict=True))


def test_url_only_import_keeps_stable_record_key_through_observation_conversion(tmp_path: Path):
    source = tmp_path / "url-only.jsonl"
    source.write_text(
        json.dumps({"platform": "web", "canonical_url": "https://example.test/story", "text": "Source text"}) + "\n",
        encoding="utf-8",
    )
    record = import_external_records(source).records[0]
    observation = observation_from_post(record)
    assert record.record_key == "web:https://example.test/story"
    assert observation.source_record_keys == [record.record_key]


def test_canonical_jsonl_can_feed_triage_loader_without_losing_thread_relationships(tmp_path: Path):
    source = tmp_path / "thread.jsonl"
    source.write_text(
        json.dumps({
            "platform": "example",
            "native_id": "reply-1",
            "canonical_url": "https://example.test/reply-1",
            "content_type": "comment",
            "parent_record_key": "example:root-1",
            "thread_root_key": "example:root-1",
            "conversation_id": "root-1",
            "original_text": "reply",
        }) + "\n",
        encoding="utf-8",
    )
    record = load_post_records(source)[0]
    assert record.parent_record_key == "example:root-1"
    assert record.thread_root_key == "example:root-1"
    assert record.conversation_id == "root-1"
