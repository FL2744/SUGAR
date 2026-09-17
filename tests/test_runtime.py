import json
from pathlib import Path

from sugar_bridge import backend_info
from sugar_core.models import PostRecord
from sugar_core import service


def test_backend_diagnostics_has_support_fields():
    info = backend_info()
    assert info["version"]
    assert info["architecture"]
    assert info["python"]
    assert info["runtime"] in {"python", "bundled"}


def test_search_progress_reports_major_stages(monkeypatch, tmp_path: Path):
    record = PostRecord(
        platform="bluesky",
        native_id="1",
        canonical_url="https://example.test/1",
        query="test",
        query_matches=["test"],
        published_at="2026-09-10T12:00:00Z",
        original_text="test",
    )
    monkeypatch.setattr(service, "collect_registered_source", lambda source, request: [record])
    events = []

    outputs = service.run_search(
        {
            "sources": ["bluesky"],
            "terms": ["test"],
            "translate_posts": False,
            "infer_locations": False,
            "output_directory": str(tmp_path),
        },
        {},
        progress=lambda event, values: events.append((event, values)),
    )

    names = [event for event, _ in events]
    assert names[0] == "starting"
    assert "collecting" in names
    assert "collected" in names
    assert "enriching" in names
    assert "saving" in names
    assert names[-1] == "saved"
    assert all(Path(path).exists() for path in outputs)


def test_search_preflight_rejects_missing_x_token(tmp_path: Path):
    try:
        service.run_search(
            {
                "sources": ["x"],
                "terms": ["test"],
                "translate_posts": False,
                "infer_locations": False,
                "output_directory": str(tmp_path),
            },
            {},
        )
    except ValueError as exc:
        assert "bearer token" in str(exc).lower()
    else:
        raise AssertionError("missing X token should fail before collection")
    coverage_files = list(tmp_path.glob("*.coverage.json"))
    assert len(coverage_files) == 1
    coverage = json.loads(coverage_files[0].read_text(encoding="utf-8"))
    assert coverage["sources"]["x"]["status"] == "unavailable"


def test_search_can_continue_after_unavailable_source_and_preserve_coverage(monkeypatch, tmp_path: Path):
    record = PostRecord(
        platform="bluesky",
        native_id="2",
        canonical_url="https://example.test/2",
        query="test",
        query_matches=["test"],
        original_text="test",
    )

    def collect(source, request):
        if source == "bilibili":
            raise RuntimeError("HTTP 403 forbidden by access control")
        return [record]

    monkeypatch.setattr(service, "collect_registered_source", collect)
    outputs = service.run_search(
        {
            "sources": ["bilibili", "bluesky"],
            "terms": ["test"],
            "translate_posts": False,
            "infer_locations": False,
            "continue_on_source_error": True,
            "output_directory": str(tmp_path),
        },
        {},
    )

    coverage_path = next(Path(path) for path in outputs if path.endswith(".coverage.json"))
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    assert coverage["overall_status"] == "partial"
    assert coverage["sources"]["bilibili"]["status"] == "unavailable"
    assert coverage["sources"]["bilibili"]["access_mode"] == "anonymous_public"
    assert coverage["sources"]["bluesky"]["status"] == "success"
    assert coverage["sources"]["bluesky"]["access_mode"] == "public_appview"
    metadata_path = next(Path(path) for path in outputs if path.endswith(".metadata.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_coverage"] == coverage
