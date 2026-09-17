import pytest

from sugar_core.collectors import collect_bluesky, collect_mastodon, collect_x


class FakeResponse:
    def __init__(self, payload, url="https://example.test/request", status_code=200):
        self._payload = payload
        self.url = url
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def test_collectors_skip_blank_queries_without_network_calls():
    for collector, kwargs in (
        (collect_x, {"bearer_token": "token"}),
        (collect_bluesky, {}),
        (collect_mastodon, {"instance_url": "https://example.social"}),
    ):
        session = FakeSession([])
        assert collector(search_terms=["", "   "], session=session, **kwargs) == []
        assert session.calls == []


@pytest.mark.parametrize(
    ("collector", "kwargs", "message"),
    [
        (collect_x, {"bearer_token": "token"}, "X search"),
        (collect_bluesky, {}, "Bluesky search"),
        (collect_mastodon, {"instance_url": "https://example.social"}, "Mastodon search"),
    ],
)
def test_collectors_fail_with_a_clear_error_for_non_object_payload(collector, kwargs, message):
    with pytest.raises(RuntimeError, match=message):
        collector(
            search_terms=["test"],
            session=FakeSession([FakeResponse(["not", "an", "object"])]),
            **kwargs,
        )


@pytest.mark.parametrize(
    ("collector", "kwargs", "payload", "message"),
    [
        (collect_x, {"bearer_token": "token"}, {"data": {}, "meta": {}}, "X search returned an unexpected data shape"),
        (collect_x, {"bearer_token": "token"}, {"data": [], "meta": []}, "X search returned an unexpected meta shape"),
        (collect_bluesky, {}, {"posts": {}}, "Bluesky search returned an unexpected posts shape"),
        (
            collect_mastodon,
            {"instance_url": "https://example.social"},
            {"statuses": {}},
            "Mastodon search returned an unexpected statuses shape",
        ),
    ],
)
def test_collectors_reject_malformed_list_shapes(collector, kwargs, payload, message):
    with pytest.raises(RuntimeError, match=message):
        collector(search_terms=["test"], session=FakeSession([FakeResponse(payload)]), **kwargs)


@pytest.mark.parametrize(
    ("collector", "kwargs", "payload"),
    [
        (collect_x, {"bearer_token": "token"}, {"data": [{}], "meta": {}}),
        (collect_bluesky, {}, {"posts": [{}]}),
        (collect_mastodon, {"instance_url": "https://example.social"}, {"statuses": [{}]}),
    ],
)
def test_collectors_skip_items_without_stable_native_ids(collector, kwargs, payload):
    assert collector(search_terms=["test"], session=FakeSession([FakeResponse(payload)]), **kwargs) == []


@pytest.mark.parametrize("status_code", [401, 403, 404, 429, 500])
@pytest.mark.parametrize(
    ("collector", "kwargs"),
    [
        (collect_x, {"bearer_token": "token"}),
        (collect_bluesky, {}),
        (collect_mastodon, {"instance_url": "https://example.social"}),
    ],
)
def test_collectors_fail_closed_for_http_access_and_server_errors(collector, kwargs, status_code):
    with pytest.raises(RuntimeError):
        collector(
            search_terms=["test"],
            session=FakeSession([FakeResponse({}, status_code=status_code)]),
            **kwargs,
        )


def test_x_duplicate_across_queries_preserves_both_queries():
    payload = {
        "data": [
            {
                "id": "123",
                "text": "hello",
                "author_id": "u1",
                "created_at": "2026-09-10T10:00:00Z",
                "lang": "en",
                "public_metrics": {"like_count": 2},
            }
        ],
        "includes": {"users": [{"id": "u1", "name": "A", "username": "a"}]},
        "meta": {},
    }
    session = FakeSession([FakeResponse(payload), FakeResponse(payload)])
    rows = collect_x(bearer_token="t", search_terms=["alpha", "beta"], max_posts_per_query=10, session=session)
    assert len(rows) == 1
    assert rows[0].query_matches == ["alpha", "beta"]
    assert rows[0].thread_root_key == "x:123"
    assert rows[0].conversation_id == "123"
    assert rows[0].access_mode == "authenticated"


def test_x_duplicate_pages_do_not_consume_unique_query_budget():
    def payload(native_id: str, token: str | None):
        body = {
            "data": [
                {
                    "id": native_id,
                    "text": native_id,
                    "author_id": "u1",
                    "created_at": "2026-09-10T10:00:00Z",
                    "public_metrics": {},
                }
            ],
            "includes": {"users": [{"id": "u1", "username": "a"}]},
            "meta": {},
        }
        if token:
            body["meta"]["next_token"] = token
        return body

    session = FakeSession(
        [
            FakeResponse(payload("one", "cursor-1")),
            FakeResponse(payload("one", "cursor-2")),
            FakeResponse(payload("two", None)),
        ]
    )
    rows = collect_x(
        bearer_token="t",
        search_terms=["q"],
        max_posts_per_query=2,
        max_pages_per_query=3,
        session=session,
    )

    assert [row.native_id for row in rows] == ["one", "two"]
    assert len(session.calls) == 3


def test_x_repeated_pagination_token_is_bounded():
    payload = {
        "data": [
            {
                "id": "one",
                "text": "one",
                "author_id": "u1",
                "created_at": "2026-09-10T10:00:00Z",
                "public_metrics": {},
            }
        ],
        "includes": {"users": [{"id": "u1", "username": "a"}]},
        "meta": {"next_token": "same-cursor"},
    }
    session = FakeSession([FakeResponse(payload), FakeResponse(payload), FakeResponse(payload)])

    rows = collect_x(
        bearer_token="t",
        search_terms=["q"],
        max_posts_per_query=5,
        max_pages_per_query=5,
        session=session,
    )

    assert [row.native_id for row in rows] == ["one"]
    assert len(session.calls) == 2


def _bluesky_post(native_id: str) -> dict:
    return {
        "uri": f"at://did:plc:author/app.bsky.feed.post/{native_id}",
        "author": {"handle": "person.test", "displayName": "Person"},
        "record": {"text": native_id, "createdAt": "2026-09-10T10:00:00Z", "langs": ["en"]},
        "replyCount": 0,
        "repostCount": 0,
        "likeCount": 0,
        "quoteCount": 0,
    }


def test_bluesky_duplicate_pages_do_not_consume_unique_query_budget():
    session = FakeSession(
        [
            FakeResponse({"posts": [_bluesky_post("one")], "cursor": "cursor-1"}),
            FakeResponse({"posts": [_bluesky_post("one")], "cursor": "cursor-2"}),
            FakeResponse({"posts": [_bluesky_post("two")]}),
        ]
    )
    rows = collect_bluesky(
        search_terms=["q"],
        max_posts_per_query=2,
        max_pages_per_query=3,
        session=session,
    )

    assert [row.native_id for row in rows] == ["one", "two"]
    assert len(session.calls) == 3


def test_bluesky_repeated_cursor_is_bounded():
    payload = {"posts": [_bluesky_post("one")], "cursor": "same-cursor"}
    session = FakeSession([FakeResponse(payload), FakeResponse(payload), FakeResponse(payload)])

    rows = collect_bluesky(search_terms=["q"], max_posts_per_query=5, max_pages_per_query=5, session=session)

    assert [row.native_id for row in rows] == ["one"]
    assert len(session.calls) == 2


def _mastodon_status(native_id: str) -> dict:
    return {
        "id": native_id,
        "created_at": "2026-09-10T20:00:00Z",
        "url": f"https://m.example/@a/{native_id}",
        "content": f"<p>{native_id}</p>",
        "replies_count": 0,
        "reblogs_count": 0,
        "favourites_count": 0,
        "account": {"acct": "a", "display_name": "A"},
    }


def test_mastodon_duplicate_pages_do_not_consume_unique_query_budget():
    page = [_mastodon_status("one"), _mastodon_status("two"), _mastodon_status("one"), _mastodon_status("two")]
    session = FakeSession(
        [
            FakeResponse({"statuses": page}),
            FakeResponse({"statuses": page}),
            FakeResponse({"statuses": [_mastodon_status("three"), _mastodon_status("four")] * 2}),
        ]
    )
    rows = collect_mastodon(
        instance_url="https://m.example",
        search_terms=["q"],
        access_token="token",
        max_posts_per_query=4,
        max_pages_per_query=3,
        session=session,
    )

    assert [row.native_id for row in rows] == ["one", "two", "three", "four"]
    assert len(session.calls) == 3


@pytest.mark.parametrize(
    ("collector", "kwargs", "payload"),
    [
        (
            collect_x,
            {"bearer_token": "token"},
            {
                "data": [
                    {
                        "id": "outside",
                        "text": "outside",
                        "created_at": "2025-01-01T10:00:00Z",
                        "public_metrics": {},
                    },
                    {
                        "id": "inside",
                        "text": "inside",
                        "created_at": "2026-06-01T10:00:00Z",
                        "public_metrics": {},
                    },
                ],
                "meta": {},
            },
        ),
        (
            collect_bluesky,
            {},
            {"posts": [_bluesky_post("outside"), _bluesky_post("inside")]},
        ),
        (
            collect_mastodon,
            {"instance_url": "https://example.social"},
            {"statuses": [_mastodon_status("outside"), _mastodon_status("inside")]},
        ),
    ],
)
def test_collectors_apply_date_bounds_locally(collector, kwargs, payload):
    if collector is collect_bluesky:
        payload["posts"][0]["record"]["createdAt"] = "2025-01-01T10:00:00Z"
        payload["posts"][1]["record"]["createdAt"] = "2026-06-01T10:00:00Z"
    elif collector is collect_mastodon:
        payload["statuses"][0]["created_at"] = "2025-01-01T10:00:00Z"
        payload["statuses"][1]["created_at"] = "2026-06-01T10:00:00Z"
    rows = collector(
        search_terms=["q"],
        since="2026-01-01",
        until="2026-12-31",
        session=FakeSession([FakeResponse(payload)]),
        **kwargs,
    )

    assert [row.native_id for row in rows] == ["inside"]


def test_x_reply_preserves_parent_and_conversation():
    payload = {
        "data": [
            {
                "id": "124",
                "conversation_id": "100",
                "text": "reply",
                "author_id": "u1",
                "created_at": "2026-09-10T10:00:00Z",
                "lang": "en",
                "public_metrics": {},
                "referenced_tweets": [{"type": "replied_to", "id": "123"}],
            }
        ],
        "includes": {"users": [{"id": "u1", "name": "A", "username": "a"}]},
        "meta": {},
    }
    rows = collect_x(
        bearer_token="t",
        search_terms=["alpha"],
        max_posts_per_query=10,
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
        "posts": [
            {
                "uri": uri,
                "author": {"handle": "person.test", "displayName": "Person"},
                "record": {
                    "text": "reply",
                    "createdAt": "2026-09-10T10:00:00Z",
                    "langs": ["en"],
                    "reply": {"root": {"uri": root_uri}, "parent": {"uri": parent_uri}},
                },
                "replyCount": 1,
                "repostCount": 0,
                "likeCount": 2,
                "quoteCount": 0,
            }
        ]
    }
    rows = collect_bluesky(
        search_terms=["reply"],
        max_posts_per_query=10,
        session=FakeSession([FakeResponse(payload)]),
    )
    assert rows[0].parent_record_key == "bluesky:parent"
    assert rows[0].thread_root_key == "bluesky:root"
    assert rows[0].conversation_id == root_uri
    assert rows[0].access_mode == "anonymous"


def test_mastodon_until_date_inclusive_and_metrics():
    payload = {
        "statuses": [
            {
                "id": "9",
                "created_at": "2026-09-10T20:00:00Z",
                "url": "https://m.example/@a/9",
                "content": "<p>hello</p>",
                "replies_count": 1,
                "reblogs_count": 2,
                "favourites_count": 3,
                "account": {"acct": "a", "display_name": "A"},
            }
        ]
    }
    session = FakeSession([FakeResponse(payload)])
    rows = collect_mastodon(instance_url="https://m.example", search_terms=["q"], until="2026-09-10", session=session)
    assert len(rows) == 1
    assert rows[0].engagement["likes"] == 3
    assert rows[0].engagement["reposts"] == 2
    assert rows[0].thread_root_key == "mastodon:9"
    assert rows[0].conversation_id == "9"
    assert rows[0].access_mode == "anonymous"


def test_mastodon_reply_preserves_parent_without_inventing_root():
    payload = {
        "statuses": [
            {
                "id": "10",
                "in_reply_to_id": "9",
                "created_at": "2026-09-10T20:05:00Z",
                "url": "https://m.example/@a/10",
                "content": "<p>reply</p>",
                "replies_count": 0,
                "reblogs_count": 0,
                "favourites_count": 1,
                "account": {"acct": "a", "display_name": "A"},
            }
        ]
    }
    rows = collect_mastodon(
        instance_url="https://m.example",
        search_terms=["q"],
        session=FakeSession([FakeResponse(payload)]),
    )
    assert rows[0].parent_record_key == "mastodon:9"
    assert rows[0].thread_root_key == ""
    assert rows[0].conversation_id == ""
