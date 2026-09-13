from sugar_core.collectors import collect_bluesky, collect_mastodon, collect_x


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
    assert rows[0].thread_root_key == "x:123"
    assert rows[0].conversation_id == "123"


def test_x_reply_preserves_parent_and_conversation():
    payload = {
        "data": [{
            "id":"124", "conversation_id":"100", "text":"reply", "author_id":"u1",
            "created_at":"2026-09-10T10:00:00Z", "lang":"en", "public_metrics":{},
            "referenced_tweets":[{"type":"replied_to","id":"123"}],
        }],
        "includes": {"users":[{"id":"u1","name":"A","username":"a"}]}, "meta": {}
    }
    rows = collect_x(
        bearer_token="t", search_terms=["alpha"], max_posts_per_query=10,
        session=FakeSession([FakeResponse(payload)]),
    )
    assert rows[0].parent_record_key == "x:123"
    assert rows[0].thread_root_key == "x:100"
    assert rows[0].conversation_id == "100"
    assert rows[0].raw_stats["replied_to_id"] == "123"


def test_bluesky_reply_preserves_root_and_parent():
    uri = "at://did:plc:author/app.bsky.feed.post/child"
    root_uri = "at://did:plc:root/app.bsky.feed.post/root"
    parent_uri = "at://did:plc:parent/app.bsky.feed.post/parent"
    payload = {
        "posts": [{
            "uri": uri,
            "author": {"handle":"person.test","displayName":"Person"},
            "record": {
                "text":"reply", "createdAt":"2026-09-10T10:00:00Z", "langs":["en"],
                "reply": {"root":{"uri":root_uri}, "parent":{"uri":parent_uri}},
            },
            "replyCount":1, "repostCount":0, "likeCount":2, "quoteCount":0,
        }]
    }
    rows = collect_bluesky(
        search_terms=["reply"], max_posts_per_query=10,
        session=FakeSession([FakeResponse(payload)]),
    )
    assert rows[0].parent_record_key == "bluesky:parent"
    assert rows[0].thread_root_key == "bluesky:root"
    assert rows[0].conversation_id == root_uri


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
    assert rows[0].thread_root_key == "mastodon:9"
    assert rows[0].conversation_id == "9"


def test_mastodon_reply_preserves_parent_without_inventing_root():
    payload = {"statuses":[{
        "id":"10", "in_reply_to_id":"9", "created_at":"2026-09-10T20:05:00Z",
        "url":"https://m.example/@a/10", "content":"<p>reply</p>",
        "replies_count":0, "reblogs_count":0, "favourites_count":1,
        "account":{"acct":"a","display_name":"A"}
    }]}
    rows = collect_mastodon(
        instance_url="https://m.example", search_terms=["q"],
        session=FakeSession([FakeResponse(payload)]),
    )
    assert rows[0].parent_record_key == "mastodon:9"
    assert rows[0].thread_root_key == ""
    assert rows[0].conversation_id == ""
