from __future__ import annotations

from typing import Any

import pytest

from tools.live_public_api_benchmark import MAX_RECORDS_PER_SOURCE, MeteredSession, run_benchmark


class FakeResponse:
    def __init__(self, payload: dict[str, Any], url: str, status_code: int = 200) -> None:
        self._payload = payload
        self.url = url
        self.status_code = status_code
        self.headers = {"X-RateLimit-Remaining": "42"}
        self.content = b"{}"

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def close(self) -> None:
        return None


class FakeSession(MeteredSession):
    def __init__(self, response: FakeResponse) -> None:
        super().__init__()
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:  # type: ignore[override]
        kwargs.setdefault("allow_redirects", False)
        assert kwargs["allow_redirects"] is False
        self.calls.append((url, kwargs))
        self.events.append({
            "status_code": 200,
            "elapsed_seconds": 0.001,
            "response_bytes": 2,
            "error_type": "",
            "rate_limit_headers": {"X-RateLimit-Remaining": "42"},
        })
        return self.response


@pytest.mark.parametrize("instance", ["http://mastodon.social", "https://mastodon.social/search", "https://user@mastodon.social"])
def test_live_benchmark_rejects_non_origin_or_non_https_instance(instance: str) -> None:
    with pytest.raises(ValueError):
        run_benchmark("education", instance)


def test_live_benchmark_caps_records_and_emits_only_aggregate_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import live_public_api_benchmark as benchmark

    sessions: list[FakeSession] = []

    def fake_session() -> FakeSession:
        payload = {
            "posts": [{
                "uri": "at://did:plc:secret/app.bsky.feed.post/post1",
                "author": {"handle": "secret.example", "displayName": "Private Name"},
                "record": {"text": "A public education update.", "createdAt": "2026-09-19T12:00:00Z", "langs": ["en"]},
                "replyCount": 1, "repostCount": 2, "likeCount": 3,
            }],
            "statuses": [{
                "id": "987654321", "created_at": "2026-09-19T12:00:00Z",
                "url": "https://mastodon.social/@secret/987654321", "content": "<p>Education update.</p>",
                "account": {"acct": "secret", "display_name": "Private Name"},
            }],
        }
        index = len(sessions)
        key = "posts" if index == 0 else "statuses"
        session = FakeSession(FakeResponse({key: payload[key]}, "https://example.test/api"))
        sessions.append(session)
        return session

    monkeypatch.setattr(benchmark, "MeteredSession", fake_session)
    monkeypatch.setattr(benchmark, "__version__", "test")
    report = benchmark.run_benchmark("education", mastodon_token="test-token")

    assert report["request_policy"]["max_http_requests"] == 2
    assert report["request_policy"]["max_records_per_source"] == MAX_RECORDS_PER_SOURCE
    assert report["request_policy"]["retries"] == 0
    assert report["request_policy"]["redirects_followed"] == 0
    assert report["request_policy"]["authenticated_sources"] == ["mastodon"]
    assert report["local_checkpoint"]["round_trip_exact"] is True
    assert report["local_checkpoint"]["records_restored"] == 2
    assert all(len(session.calls) == 1 for session in sessions)
    serialized = str(report)
    assert "A public education update" not in serialized
    assert "secret.example" not in serialized
    assert "Private Name" not in serialized
    assert "987654321" not in serialized
    assert "test-token" not in serialized
    assert report["intelligence"]["status"] == "not_scored"


def test_live_benchmark_does_not_treat_unauthenticated_mastodon_search_as_zero_results(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools import live_public_api_benchmark as benchmark

    monkeypatch.delenv("SUGAR_MASTODON_TOKEN", raising=False)
    monkeypatch.setattr(benchmark, "collect_bluesky", lambda **kwargs: [])
    monkeypatch.setattr(benchmark, "collect_mastodon", lambda **kwargs: pytest.fail("must not make an anonymous status search"))

    report = benchmark.run_benchmark("education", mastodon_token="")

    assert report["sources"]["mastodon"]["status"] == "credential_required"
    assert report["sources"]["mastodon"]["request_count"] == 0
    assert report["sources"]["mastodon"]["access_requirement"] == "user token with read:search"
