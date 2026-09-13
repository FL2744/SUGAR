# Weibo public collector

SUGAR's Weibo adapter is designed for overt public-source research. It uses ordinary first-party mobile-web request semantics and fails explicitly when Weibo requires login, verification, or other access state.

The collector does not automate Weibo login, generate visitor cookies, extract browser credentials, solve CAPTCHAs, spoof device identifiers, rotate proxies/identities, or retry around risk-control gates.

## Implemented surfaces

### Known public status

`fetch_weibo_status(status_id)` reads a public status through the first-party mobile PWA JSON route:

`https://m.weibo.cn/statuses/show?id=<id-or-bid>`

When the returned status reports long text, SUGAR attempts the ordinary public extension route:

`https://m.weibo.cn/statuses/extend?id=<id-or-bid>`

If the extension route is separately unavailable, the shorter public status remains usable rather than causing the whole record to be discarded.

### Comments

`collect_weibo_comments(status_id)` uses the basic mobile comment surface:

`https://m.weibo.cn/api/comments/show?id=<status-id>&page=<page>`

Anonymous responses can be partial. SUGAR records only what the endpoint returns. It stops when pages are empty or repeat rather than attempting to unlock deeper comment pagination.

Top-level comments are normalized with the source status as `parent_record_key` and `thread_root_key`. When the public response identifies a direct replied-to comment, the direct parent comment is preserved while the status remains the thread root.

### Keyword search

`collect_weibo_public(search_terms=...)` uses the mobile search container route with `page_type=searchall`.

Weibo's anonymous search availability is not assumed to be stable. If the server returns a login-required response, SUGAR raises `WeiboAccessError` and stops. An existing legitimate session cookie may be supplied by the caller; the collector never creates or harvests one.

The backend bridge can receive an optional cookie through `SUGAR_WEIBO_COOKIE`. This is deliberately optional and is not emitted in logs or output datasets.

## Current capability declaration

The registry currently advertises Weibo as:

- keyword search: yes, availability-dependent and fail-closed
- known-item retrieval: yes
- comments: yes, public/basic response only
- profile timeline: not yet implemented
- anonymous search: supported where Weibo permits the ordinary mobile request
- authenticated search: supported when the caller legitimately supplies existing session state

This capability declaration describes SUGAR's implementation. It is not a promise that Weibo will return every surface from every network/session at all times.

## Normalization

Status records preserve:

- stable Weibo status ID and bid when supplied
- public canonical mobile URL
- author ID/name/location when exposed
- UTC-normalized publication time
- likes, comments, and repost counts
- platform-native source/region/long-text indicators in `raw_stats`
- HTML-stripped readable text
- repost flag when the response contains `retweeted_status`
- thread root and conversation identity

Comments preserve:

- stable comment ID
- source status/thread identity
- direct reply parent when explicitly supplied
- author metadata
- comment text
- likes and reply count
- query/source provenance

## Metric semantics

Weibo's `attitudes_count`, `comments_count`, and `reposts_count` map reasonably to SUGAR's canonical likes, replies, and reposts for status-level descriptive analysis.

The mapping is not itself a claim that a Weibo repost has the same audience meaning, algorithmic distribution, or influence effect as an X repost. Platform-native raw values remain available for platform-specific analysis.

## Access evidence used during implementation

Recent public tooling in 2026 independently documents anonymous `m.weibo.cn/statuses/show` status retrieval using the mobile PWA request headers and basic public comment retrieval. Other contemporary clients report `ok: -100` when particular mobile surfaces require login. SUGAR treats those server responses as authoritative at runtime and stops instead of embedding circumvention logic.

Useful external references for maintainers:

- https://github.com/wuaishare/sharextract
- https://github.com/tamnd/weibo-cli
- https://github.com/bidabrain/weiboX

These references are implementation reconnaissance, not dependencies; SUGAR's tests use deterministic fixtures and do not call live Weibo endpoints in CI.
