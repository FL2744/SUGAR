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

A capability is a statement about the current SUGAR implementation, not a claim that the underlying platform can never expose anything else. This matters particularly for Chinese social-media sources because access surfaces differ sharply by platform. A source can support known public URLs without pretending that general anonymous keyword search is available.

Current registry:

| Source | Keyword search | Known item | Comments | Anonymous keyword search | Notes |
| --- | --- | --- | --- | --- | --- |
| X | yes | no | no | no | API credential required |
| Bluesky | yes | no | no | yes | Optional authenticated PDS path |
| Mastodon | yes | no | no | instance-dependent | Instance-scoped search |
| Bilibili | yes | yes | yes | yes/fail-closed | Public responses can still be access/session dependent |
| Weibo | yes | yes | yes | yes/availability varies | Optional legitimate existing session can change coverage |
| WeChat | no | yes | no | no | Known public Official Account article URL import only |
| Zhihu | yes | yes | no | no | Keyword search uses approved Open Platform Access Secret; known public URL import is separate |
| Douyin | no | yes | no | no | Known public/share URL import only; no general search claim without approved official search access |

The classroom preview exposes known-item collection through a generic `sugar-import` / `import-public` workflow. This keeps `known_item=True` sources usable without adding fake keyword-search adapters.

## Public-item import

`sugar_core/public_import.py` accepts one or more known public URLs/IDs and calls the registered platform adapter. It writes the same CSV/XLSX/metadata family as normal collection and can register those files in a project workspace.

For web-page imports such as WeChat, Zhihu, and Douyin, `public_items.py`:

- validates platform host allowlists before making a request;
- follows redirects only when the final host still belongs to the selected platform;
- extracts only content/metadata exposed in the ordinary public response;
- fails explicitly on verification/CAPTCHA/access-gate signals;
- refuses unsupported/non-HTML responses or pages with insufficient evidence;
- does not manufacture sessions, signatures, cookies, or device state.

Known public item import is evidence acquisition, not proof that the platform offers broad discoverability or representative coverage.

## Normalized thread relationships

`PostRecord` schema 1.2 includes:

- `record_key`: derived stable identity in the form `<platform>:<native_id>`
- `parent_record_key`: direct parent post/video/comment where known
- `thread_root_key`: root content item for the discussion/thread where known
- `conversation_id`: the platform-native conversation/root identity where known

These fields are deliberately separate from `raw_stats`. They let downstream analysis distinguish a post from a comment and preserve discussion structure across platforms.

A collector should leave a relationship blank when the source does not expose enough evidence to identify it. It should not infer a parent or root from text similarity.

For Bilibili and Weibo comment collection, top-level comments link to the source content as thread root. Nested replies should use their direct reply parent only when the source response supplies it.

## Adding a platform

A new platform should normally be added in four layers:

1. A platform module that performs bounded collection/import and normalizes results into `PostRecord`.
2. A `CollectorSpec` registration declaring only implemented capabilities and adapters.
3. Deterministic fixture tests for response parsing, provenance, pagination/access failures, metric semantics, relationships, credential handling, and redirect/access-control behavior.
4. Only after those pass, UI/CLI exposure and bounded live field testing.

Do not add another platform-specific `if source == ...` branch to `service.run_search`; register the adapter instead.

## Access-control rule

Collectors must stop explicitly when a surface requires access state SUGAR has not been authorized to use. The research client does not solve CAPTCHAs, synthesize login cookies, spoof device identities, rotate identities/proxies to evade controls, reproduce anti-bot signatures to defeat an access gate, or silently convert blocked access into a zero-activity finding.

Authenticated or official-API collectors can be supported when credentials are legitimately provided; their capability metadata and UI should make that dependency visible.

## Metric semantics

Cross-platform metrics are mapped only where the concepts are reasonably compatible. Platform-native measures that do not have a defensible canonical equivalent stay in `raw_stats`.

For example, Bilibili `share`, `coin`, and `danmaku` values remain native rather than automatically being relabeled as X-style reposts or replies. The Zhihu official adapter maps explicit up-vote/comment counts to the closest canonical engagement fields while retaining the source values in `raw_stats`.
