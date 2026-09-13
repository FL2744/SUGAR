# SUGAR collector interface

SUGAR treats collection platforms as adapters into a common evidence pipeline rather than as one-off scraper implementations.

The collector registry lives in `sugar_core/collector_registry.py`. The shared service asks the registry for a selected source and sends it a `CollectorRequest`; platform-specific details remain inside the adapter.

## Capability model

A platform advertises the surfaces SUGAR actually implements:

- `keyword_search`
- `known_item`
- `comments`
- `profile_timeline`
- `authenticated_search`
- `anonymous_search`

A capability is a statement about the current SUGAR implementation, not a claim that the underlying platform can never expose anything else.

This matters for Chinese social-media sources because access surfaces differ sharply by platform. A source can therefore support known public URLs and comments without pretending that anonymous keyword search is available.

Current registry examples:

| Source | Keyword search | Known item | Comments | Anonymous search |
| --- | --- | --- | --- | --- |
| X | yes | no | no | no |
| Bluesky | yes | no | no | yes |
| Mastodon | yes | no | no | yes/instance-dependent |
| Bilibili | yes/public-session-dependent | yes | yes/public-response-dependent | yes/fail-closed |

Future Weibo, WeChat, REDnote, Douyin, Zhihu, and Kuaishou adapters should advertise only the surfaces they can actually provide under the project's public/authorized-access rules.

## Normalized thread relationships

`PostRecord` schema 1.2 adds:

- `record_key`: derived stable identity in the form `<platform>:<native_id>`
- `parent_record_key`: direct parent post/video/comment where known
- `thread_root_key`: root content item for the discussion/thread where known
- `conversation_id`: the platform-native conversation/root identity where known

These fields are deliberately separate from `raw_stats`. They let downstream analysis distinguish a post from a comment and preserve discussion structure across platforms.

A collector should leave a relationship blank when the source does not expose enough evidence to identify it. It should not infer a parent or root from text similarity.

For Bilibili registry comment collection, top-level comments are linked to the source video as both parent and thread root. Future Weibo comments should link to the source status in the same way; nested replies should use their direct reply parent when the public response supplies it.

## Adding a platform

A new platform should normally be added in four layers:

1. A platform module that performs bounded collection and normalizes results into `PostRecord`.
2. A `CollectorSpec` registration declaring the implemented capabilities and adapters.
3. Deterministic fixture tests for response parsing, provenance, pagination, access-control failures, metric semantics, and relationship fields.
4. Only after those pass, UI/CLI exposure and live field testing.

Do not add another platform-specific `if source == ...` block to `service.run_search`; register the adapter instead.

## Access-control rule

Collectors must stop explicitly when a surface requires access state SUGAR has not been authorized to use. The default research client does not solve CAPTCHAs, synthesize login cookies, spoof device identities, rotate identities/proxies to evade controls, or reproduce anti-bot signatures for the purpose of defeating an access gate.

Authenticated or official-API collectors can still be supported when credentials are legitimately provided; their capability metadata should make that dependency visible.

## Metric semantics

Cross-platform metrics are mapped only where the concepts are reasonably compatible. Platform-native measures that do not have a defensible canonical equivalent stay in `raw_stats`.

For example, Bilibili `share`, `coin`, and `danmaku` values are retained natively rather than automatically being relabeled as X-style reposts or replies.
