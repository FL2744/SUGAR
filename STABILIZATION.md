# SUGAR stabilization baseline — v1.1

This branch establishes a supported, testable core for SUGAR before new platform collectors are added.

## Supported path

Use the `sugar_core` package (`python -m sugar_core` or the `sugar` console script). The historical `SUGAR.py` monolith remains in the repository for reference and backward compatibility, but new engineering work should target `sugar_core`.

## What this baseline fixes

- No package installation or dependency upgrades occur at runtime.
- Linux/ARC is a first-class supported environment; report generation no longer depends on macOS font paths.
- Platform-specific engagement is normalized before analysis. Mastodon favorites/reblogs are no longer silently omitted.
- Duplicate posts found through multiple search queries retain all query matches rather than losing provenance.
- Date ranges use inclusive start and end dates consistently.
- Spreadsheet formula-injection protection does not alter numeric coordinates.
- Raw platform metrics are preserved alongside canonical engagement fields.
- Collection outputs include `collected_at`, schema/collector versions, native IDs, canonical URLs, and a metadata sidecar.
- AI enrichment separates instructions from untrusted source content and never uses language alone to infer geography.
- LLM and geocoding outputs are cached locally for repeatability and cost control.
- The macOS bridge calls the stable core instead of importing the legacy monolith.
- CI tests the core on Ubuntu and macOS with Python 3.11–3.13.

## Data model

The stable record keeps platform-neutral fields (`native_id`, `canonical_url`, `published_at`, `author_handle`, `engagement`, `query_matches`) and also exports legacy aliases such as `tweet_id`, `username`, and `translated_en` so older SUGAR workbooks remain usable.

Canonical engagement fields are `likes`, `replies`, `reposts`, `quotes`, `bookmarks`, and `impressions`. Missing metrics remain zero rather than being inferred.

## Deliberately deferred

This stabilization does **not** add Weibo, Bilibili, Douyin, WeChat, Xiaohongshu, or other new collectors. Those should be implemented only after this baseline is accepted, using the platform-neutral collector model rather than extending `SUGAR.py`.

Likewise, an influence/overlap score is not fabricated here. That methodology should be built from explicit, reviewable dimensions after the Diplomacy Lab master-data schema is agreed.
