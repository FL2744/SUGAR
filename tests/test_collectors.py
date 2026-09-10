from sugar_core.collectors import collect_mastodon, collect_x


class FakeResponse:
    def __init__(self, payload, url="https://example.test/request", status_code=200):
        self._payload = payload; self.url = url; self.status_code = status_code; self.text = ""
    def json(self): return self._payload
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses): self.responses = iter(responses); self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs)); return next(self.responses)


def test_x_duplicate_across_queries_preserves_both_queries():
    payload = {
        "data": [{"id":"123","text":"hello","author_id":"u1","created_at":"2026-09-10T10:00:00Z","lang":"en","public_metrics":{"like_count":2}}],
        "includes": {"users":[{"id":"u1","name":"A","username":"a"}]}, "meta": {}
    }
    session = FakeSession([FakeResponse(payload), FakeResponse(payload)])
    rows = collect_x(bearer_token="t", search_terms=["alpha","beta"], max_posts_per_query=10, session=session)
    assert len(rows) == 1
    assert rows[0].query_matches == ["alpha", "beta"]


def test_mastodon_until_date_inclusive_and_metrics():
    payload = {"statuses":[{
        "id":"9", "created_at":"2026-09-10T20:00:00Z", "url":"https://m.example/@a/9", "content":"<p>hello</p>",
        "replies_count":1, "reblogs_count":2, "favourites_count":3, "account":{"acct":"a","display_name":"A"}
    }]}
    session = FakeSession([FakeResponse(payload)])
    rows = collect_mastodon(instance_url="https://m.example", search_terms=["q"], until="2026-09-10", session=session)
    assert len(rows) == 1
    assert rows[0].engagement["likes"] == 3
    assert rows[0].engagement["reposts"] == 2
