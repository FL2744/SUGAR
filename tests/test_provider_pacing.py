from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sugar_core import service
from sugar_core.llm import LLMConfig
from sugar_core.provider_pacing import SharedRequestPacer


def test_shared_request_pacer_spaces_starts_between_threads():
    pacer = SharedRequestPacer()
    starts: list[float] = []
    lock = threading.Lock()

    def request_start():
        assert pacer.acquire(interval_seconds=0.04)
        with lock:
            starts.append(time.monotonic())

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _index: request_start(), range(4)))

    starts.sort()
    assert len(starts) == 4
    assert all(right - left >= 0.03 for left, right in zip(starts, starts[1:]))


def test_shared_cooldown_delays_all_waiting_sources_and_honors_cancel():
    pacer = SharedRequestPacer()
    pacer.defer(0.1)
    started = time.monotonic()
    assert pacer.acquire(interval_seconds=0)
    assert time.monotonic() - started >= 0.08

    pacer.defer(2)
    assert pacer.acquire(interval_seconds=0, cancelled=lambda: True) is False


def test_run_search_collects_independent_sources_concurrently(monkeypatch, tmp_path):
    active = 0
    maximum_active = 0
    lock = threading.Lock()
    release = threading.Event()

    def collect(source, request):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            if active >= 2:
                release.set()
        assert release.wait(timeout=2), "platform collectors did not overlap"
        with lock:
            active -= 1
        return []

    monkeypatch.setattr(service, "collect_registered_source", collect)
    outputs = service.run_search({
        "sources": ["x", "bluesky"],
        "terms": ["public education"],
        "translate_posts": False,
        "infer_locations": False,
        "output_directory": str(tmp_path),
        "max_parallel_sources": 2,
        "shared_request_interval_seconds": 0,
    })

    metadata_path = next(path for path in outputs if path.endswith(".metadata.json"))
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    assert maximum_active == 2
    assert metadata["collection_requests"] == 2
    assert metadata["max_parallel_sources"] == 2
    assert metadata["source_coverage"]["sources"]["x"]["status"] == "zero_result"
    assert metadata["source_coverage"]["sources"]["bluesky"]["status"] == "zero_result"


def test_search_term_translation_runs_in_parallel_and_keeps_stable_order(monkeypatch, tmp_path):
    active = 0
    maximum_active = 0
    lock = threading.Lock()
    release = threading.Event()
    barrier = threading.Barrier(4)

    def translate(_client, _config, _cache, term, language):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        barrier.wait(timeout=2)
        with lock:
            active -= 1
        release.set()
        return f"{term} ({language})"

    monkeypatch.setattr(service, "create_client", lambda _llm: object())
    monkeypatch.setattr(service, "translate_search_term", translate)
    result = service._translated_terms(
        ["education", "exchange"], ["es", "zh"],
        LLMConfig(api_key="test-only"), tmp_path, max_workers=4,
    )

    assert release.is_set()
    assert maximum_active == 4
    assert result == ["education", "exchange", "education (es)", "education (zh)", "exchange (es)", "exchange (zh)"]
