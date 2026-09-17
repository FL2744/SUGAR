# SUGAR external importer interface

SUGAR treats Department or partner datasets as peer inputs to SUGAR-native collectors. An analyst should not have to recollect public-source material merely because another approved system produced it first.

## Supported inbound formats

The first stable inbound boundary supports CSV and JSONL/NDJSON. Input normalizes into the same `PostRecord` shape used by native collectors.

```bash
sugar import northstar-export.csv \
  --source-system northstar-export \
  --map native_id=item_id \
  --map original_text=body \
  --map published_at=timestamp
```

If the upstream export has no platform field, the analyst must provide one explicitly:

```bash
sugar import messages.jsonl --platform telegram
```

SUGAR does not infer a platform from arbitrary text, fabricate a source item ID, or convert import time into publication time. Each accepted row requires a platform/source identity plus either a native ID or canonical URL.

## Safe mapping

Common unambiguous aliases such as `post_id`, `url`, `text`, `timestamp`, and `username` are recognized. If two candidate columns for one canonical field contain different values, the row is rejected until the analyst supplies an explicit `--map CANONICAL=SOURCE_COLUMN` rule.

Unmapped source fields are preserved by default under `raw_stats.external_fields` so a handoff does not silently discard upstream context. Use `--drop-unmapped` only when the project intentionally wants a narrower normalized copy.

## Invalid rows and provenance

Default behavior quarantines invalid rows to `*.rejected.jsonl`; `--strict` instead fails on the first invalid row. Successful imports write canonical CSV/XLSX, canonical JSONL, an `*.import.json` manifest, and a rejected-row JSONL when needed.

The manifest records the import schema/version, source SHA-256, upstream system name, resolved mapping, import time, accepted/rejected/duplicate counts, and output names. Duplicate canonical identities are merged using the existing `PostRecord` merge rule so multiple query matches remain provenance rather than being discarded.

This interface is intentionally file-based and public. A future Northstar, contractor, or Department API adapter should normalize through the same boundary instead of bypassing it.
