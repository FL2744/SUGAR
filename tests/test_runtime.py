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
    monkeypatch.setattr(service, "collect_bluesky", lambda **kwargs: [record])
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
