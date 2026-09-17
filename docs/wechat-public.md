# Public WeChat Official Account article ingestion

SUGAR supports a deliberately narrow WeChat surface: ingestion of a specific public Official Account article that the analyst already knows about and can open at `https://mp.weixin.qq.com/...`.

This is a **known-item** collector, not a claim that anonymous WeChat keyword search is generally available. In both desktop clients it appears under **Public URL**, separate from Quick Search.

## Supported surface

For a normal public Official Account article, SUGAR preserves:

- a stable article identity derived from WeChat article parameters or the public `/s/` token;
- the final canonical `mp.weixin.qq.com` URL;
- article title and public body text;
- displayed Official Account name and `__biz` identity when the URL exposes it;
- published time when the public page exposes a recognizable timestamp;
- exact collection time, source mode, source host, source URL, collector/schema version, and optional research-query provenance.

WeChat article pages do not expose defensibly comparable engagement metrics through this supported path, so SUGAR leaves canonical engagement empty rather than manufacturing values.

## Access boundary

The collector performs ordinary HTTPS requests to `mp.weixin.qq.com`. Every redirect is validated **before** SUGAR follows it and must remain on the same public host. HTTP 401/403, rate limiting, security-verification pages, deleted/unavailable-content pages, and unrecognized non-article responses fail explicitly.

SUGAR does not:

- automate WeChat login or extract browser/client credentials;
- collect private chats, contacts, Mini Programs, or account-only content;
- solve CAPTCHAs or security-verification challenges;
- fabricate device/session state or reproduce anti-bot signatures to defeat an access gate;
- treat an inaccessible article as evidence that no relevant activity exists.

## Discovery

Keyword discovery is intentionally **not implemented** in this collector. A later discovery adapter may use an ordinary public search surface when its availability and provenance can be validated, but discovery should remain distinct from the original WeChat article that serves as primary evidence.

## Reproducibility

Normal CI uses deterministic HTML/HTTP fixtures for article parsing, stable identity, redirect validation, and access failures. Live platform availability can change independently of SUGAR and should be tested separately with a small, bounded public article sample from the intended research environment.
