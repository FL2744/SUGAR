from pathlib import Path
from types import SimpleNamespace
import tomllib

import pandas as pd
from langdetect import DetectorFactory

import sugar_core
from sugar_core import enrichment
from sugar_core.enrichment import detect_language, geocode_location
from sugar_core.reporting import _prepare
from sugar_core.utils import JsonCache


def test_package_version_matches_pyproject():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["version"] == sugar_core.__version__


def test_requirements_match_pyproject_runtime_dependencies():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(metadata["project"]["dependencies"])
    requirements = {
        line.strip()
        for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert requirements == declared


def test_language_detection_sets_deterministic_seed():
    DetectorFactory.seed = None
    first = detect_language("This is a short piece of English research text.")
    second = detect_language("This is a short piece of English research text.")
    assert DetectorFactory.seed == 0
    assert first == second


def test_unique_ids_are_scoped_by_platform():
    frame = pd.DataFrame([
        {"platform": "x", "native_id": "123", "published_at": "2026-09-10T10:00:00Z", "engagement": "{}"},
        {"platform": "bluesky", "native_id": "123", "published_at": "2026-09-10T10:01:00Z", "engagement": "{}"},
        {"platform": "x", "native_id": "123", "published_at": "2026-09-10T10:02:00Z", "engagement": "{}"},
    ])
    _, metrics = _prepare(frame)
    assert metrics["unique_ids"] == 2


def test_nominatim_uncached_requests_are_throttled(monkeypatch, tmp_path):
    cache = JsonCache(tmp_path / "geo.json")
    monkeypatch.setattr(enrichment, "_NOMINATIM_LAST_REQUEST", 10.0)
    clock = iter([10.25, 11.25])
    monkeypatch.setattr(enrichment.time, "monotonic", lambda: next(clock))
    sleeps = []
    monkeypatch.setattr(enrichment.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        enrichment,
        "_request_nominatim",
        lambda location, user_agent: SimpleNamespace(
            latitude=37.2296, longitude=-80.4139, address="Blacksburg, Virginia, USA"
        ),
    )

    result = geocode_location("Blacksburg, Virginia", cache, min_delay_seconds=1.0)

    assert sleeps == [0.75]
    assert result["latitude"] == 37.2296
    assert result["longitude"] == -80.4139


def test_geocode_cache_hit_skips_network_and_throttle(monkeypatch, tmp_path):
    cache = JsonCache(tmp_path / "geo.json")
    monkeypatch.setattr(enrichment, "_NOMINATIM_LAST_REQUEST", 0.0)
    monkeypatch.setattr(
        enrichment,
        "_request_nominatim",
        lambda location, user_agent: SimpleNamespace(
            latitude=37.2296, longitude=-80.4139, address="Blacksburg, Virginia, USA"
        ),
    )
    first = geocode_location("Blacksburg, Virginia", cache, min_delay_seconds=0.0)

    def should_not_run(*args, **kwargs):
        raise AssertionError("cached geocode unexpectedly touched the network")

    monkeypatch.setattr(enrichment, "_request_nominatim", should_not_run)
    monkeypatch.setattr(enrichment.time, "sleep", should_not_run)
    second = geocode_location("Blacksburg, Virginia", cache, min_delay_seconds=1.0)

    assert second == first


def test_nominatim_uses_bundled_verified_ca_context(monkeypatch):
    import ssl
    captured = {}

    class Geocoder:
        def __init__(self, **kwargs):
            captured.update(kwargs)
        def geocode(self, *args, **kwargs):
            return None

    monkeypatch.setattr("geopy.geocoders.Nominatim", Geocoder)
    enrichment._request_nominatim("Canada", "SUGAR test")
    context = captured["ssl_context"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.cert_store_stats()["x509_ca"] > 0


def test_geocoding_outage_preserves_enriched_records_and_does_not_cache(monkeypatch, tmp_path):
    import pytest
    from geopy.exc import GeocoderUnavailable
    from sugar_core.llm import LLMConfig
    from sugar_core.models import PostRecord

    records = [PostRecord(platform="test", native_id=str(i), canonical_url="", query="test",
                          original_text="Original") for i in range(2)]
    monkeypatch.setattr(enrichment, "detect_language", lambda _: "fr")
    monkeypatch.setattr(enrichment, "create_client", lambda _: object())
    monkeypatch.setattr(enrichment, "translate_text", lambda *args: "Translated")
    monkeypatch.setattr(enrichment, "infer_location", lambda *args: dict(
        location_name="Canada", confidence=0.9, source="profile", reason="Explicit country"))
    calls = []
    def unavailable(*args):
        calls.append(args)
        raise GeocoderUnavailable("certificate verify failed")
    monkeypatch.setattr(enrichment, "_request_nominatim", unavailable)
    monkeypatch.setattr(enrichment, "_NOMINATIM_LAST_REQUEST", 0.0)
    events = []
    with pytest.warns(RuntimeWarning, match="saving results without coordinates"):
        result = enrichment.enrich_records(records, llm=LLMConfig(), cache_dir=tmp_path,
                                           progress=lambda event, data: events.append((event, data)))
    assert result == records
    assert len(calls) == 1
    assert all(r.translated_text == "Translated" and r.inferred_location == "Canada" for r in result)
    assert all(r.latitude is None and r.longitude is None for r in result)
    assert result[0].raw_stats["geocoding"]["status"] == "failed"
    assert result[1].raw_stats["geocoding"]["status"] == "skipped"
    assert any(event == "warning" for event, _ in events)
    assert JsonCache(tmp_path / "geocode.json").data == {}
