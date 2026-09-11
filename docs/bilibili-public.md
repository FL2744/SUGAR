# Public-only Bilibili collection

SUGAR's initial Bilibili support is intentionally conservative. It collects only material returned through ordinary public web requests and stops when Bilibili requires access state that SUGAR does not provide.

## Supported operations

The collector module currently provides three building blocks:

- `collect_bilibili_public(...)`: keyword discovery of public videos
- `fetch_bilibili_video(...)`: metadata retrieval for a known BV video identifier
- `collect_bilibili_comments(...)`: publicly returned top-level comments for a known video

The first implementation is a Python collector API rather than a GUI/CLI source option. Keeping the collector isolated allows its public-access behavior and response normalization to be reviewed before it is wired into the shared service and macOS app.

## Access boundary

The collector does **not**:

- log in to Bilibili
- accept or synthesize `SESSDATA`
- generate WBI signatures
- generate or spoof device identifiers
- solve CAPTCHAs
- rotate proxies or identities
- retry around anti-abuse blocks
- attempt to recover content the anonymous public endpoint does not return

The optional session initialization step performs one normal GET of Bilibili's public homepage using the same honest SUGAR research-client user agent. This allows Bilibili to establish whatever ordinary anonymous session state it chooses to provide. SUGAR does not fabricate session values.

If Bilibili returns HTTP 401/403/429 or application-level access-control responses such as `-101`, `-352`, or `-412`, the collector raises `BilibiliAccessError` with an explicit explanation and stops.

This is important because Bilibili's web API behavior changes over time. Community documentation disagrees on whether the current keyword-search endpoint requires WBI signing or only ordinary anonymous session state. SUGAR therefore treats live accessibility as an observed condition rather than implementing a bypass mechanism.

## Data normalization

Bilibili videos are stored as normal `PostRecord` objects with:

- `platform = bilibili`
- `content_type = video`
- BV identifier as the preferred native ID
- canonical `https://www.bilibili.com/video/<BVID>` URL
- publication time normalized to UTC ISO-8601
- uploader MID/name as author handle/name
- title and description as source text
- query provenance preserved across duplicate search hits

Public comments use `content_type = comment`, the reply ID (`rpid`) as the native ID, comment text as source text, commenter MID/name as author identity, and a canonical video URL with a reply anchor.

## Engagement semantics

SUGAR only maps metrics that have a sufficiently close cross-platform meaning:

| Bilibili | SUGAR canonical field |
| --- | --- |
| `like` | `likes` |
| `reply` | `replies` |
| `favorite` | `bookmarks` |
| `view` | `impressions` |

Bilibili `share` is **not** mapped to SUGAR `reposts`, because sharing a video is not the same platform behavior as reposting/retweeting. `share`, `coin`, and `danmaku` remain available in `raw_stats` for Bilibili-specific analysis.

## Search and metadata

Keyword discovery uses Bilibili's current web video-search endpoint:

`/x/web-interface/wbi/search/type`

The collector sends no WBI signature. If Bilibili rejects the ordinary public request, the collection fails closed.

For returned BV identifiers, the collector can hydrate results through:

`/x/web-interface/view`

This provides fuller video metadata and engagement statistics. If an individual detail lookup fails for a normal non-access reason, the valid search-result metadata is retained rather than dropping the discovered video. An explicit access-control response still stops the run.

## Comments

Top-level comment collection uses:

`/x/v2/reply/main`

The collector follows the endpoint's returned cursor and stops at the configured page/comment cap or when the API reports the end of the public result set.

Anonymous comment coverage may be partial. A SUGAR comment collection therefore means **comments returned by the public endpoint under the recorded collection conditions**, not all comments on the video.

Nested replies are not yet expanded in this first implementation.

## Reproducibility and research use

The collector preserves the exact request URL in `source_url`, native IDs, collection timestamp through `PostRecord`, query matches, raw Bilibili metrics, and normalized fields. This lets later triage or human review trace a record back to the public source.

Before production use, the team should run a small live smoke test from the intended Virginia Tech/ARC environment and record whether anonymous search, metadata, and comments are currently available. Unit tests intentionally use fixtures rather than depending on Bilibili's live service in CI.
