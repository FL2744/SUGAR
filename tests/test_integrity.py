from types import SimpleNamespace

import pandas as pd
from langdetect import DetectorFactory

from sugar_core import enrichment
from sugar_core.enrichment import detect_language, geocode_location
from sugar_core.reporting import _prepare
from sugar_core.utils import JsonCache


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
