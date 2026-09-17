from __future__ import annotations

import json
from pathlib import Path

from sugar_core.llm import LLMConfig
from sugar_core.models import PostRecord
from sugar_core.observation_storage import save_observations
from sugar_core.observations import observation_from_post
from sugar_core.state_workflow import package_from_files
from sugar_core import triage_io


def _coverage() -> dict:
    return {
        "schema_version": "1.0",
        "overall_status": "partial",
        "sources": {
            "bluesky": {"source": "bluesky", "status": "success", "records": 1, "attempted": True},
            "bilibili": {
                "source": "bilibili",
                "status": "unavailable",
                "records": 0,
                "attempted": True,
                "reason": "HTTP 403 access control",
            },
        },
    }


def _record() -> PostRecord:
    return PostRecord(
        platform="bluesky",
        native_id="1",
        canonical_url="https://example.test/1",
        query="example",
        query_matches=["example"],
        original_text="Public-source evidence",
    )


def test_triage_dataset_carries_collection_coverage_into_observation_metadata(monkeypatch, tmp_path: Path):
    source = tmp_path / "records.csv"
    source.write_text("placeholder", encoding="utf-8")
    source.with_suffix(".coverage.json").write_text(json.dumps(_coverage()), encoding="utf-8")
    source.with_suffix(".metadata.json").write_text(json.dumps({
        "operation": "external_import",
        "source_system": "partner-system",
        "source_sha256": "b" * 64,
    }), encoding="utf-8")
    record = _record()
    observation = observation_from_post(record)
    captured: dict = {}

    monkeypatch.setattr(triage_io, "load_post_records", lambda path: [record])
    monkeypatch.setattr(triage_io, "triage_posts", lambda *args, **kwargs: [observation])

    def fake_save(observations, output_file, *, metadata=None):
        captured.update(metadata or {})

    monkeypatch.setattr(triage_io, "save_observations", fake_save)
    triage_io.triage_dataset(
        source,
        tmp_path / "observations.csv",
        llm=LLMConfig(provider="custom", model="test", api_key="unused", base_url="https://example.test/v1"),
    )

    assert captured["source_coverage"]["sources"]["bilibili"]["status"] == "unavailable"
    assert captured["source_dataset_provenance"]["source_system"] == "partner-system"
    assert captured["source_dataset_provenance"]["source_sha256"] == "b" * 64


def test_state_package_surfaces_collection_limitations_from_observation_metadata(tmp_path: Path):
    observation = observation_from_post(_record())
    observations_file = tmp_path / "observations.csv"
    save_observations([observation], observations_file, metadata={"source_coverage": _coverage()})

    outputs = package_from_files(observations_file, tmp_path / "state", name="coverage_case")
    brief_path = next(Path(path) for path in outputs if path.endswith(".brief.md"))
    snapshot_path = next(Path(path) for path in outputs if path.endswith(".snapshot.json"))
    lineage_path = next(Path(path) for path in outputs if path.endswith(".lineage.json"))
    brief = brief_path.read_text(encoding="utf-8")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))

    assert "bilibili=unavailable (0 records)" in brief
    assert "must not be interpreted as evidence of no activity" in brief
    assert snapshot["collection_coverage"]["overall_status"] == "partial"
    assert lineage["dataset_provenance"]["source_coverage"]["overall_status"] == "partial"
