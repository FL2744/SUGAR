# Collection coverage and absence semantics

SUGAR records collection coverage separately from collected content so an access failure cannot silently become a substantive finding.

## Coverage statuses

Each bounded search writes a `*.coverage.json` sidecar with one entry per requested source:

- `success` — the source completed and returned one or more records;
- `zero_result` — the source completed successfully but returned no matching records;
- `partial` — some source material was retained but the collection surface did not complete normally;
- `unavailable` — authentication, authorization, CAPTCHA, access-control, or similar source access prevented collection;
- `failed` — the collector attempted the source but encountered another explicit failure;
- `not_run` — used downstream when a requested/preferred source has no evidence that collection was attempted.

A `zero_result` is not equivalent to `unavailable`, `failed`, or `not_run`. None of these statuses proves that no real-world activity exists.

## Search behavior

Normal `sugar search` remains fail-fast by default for compatibility. Even when it raises, the source coverage sidecar is written first. Use `--continue-on-source-error` when a multi-source run should retain successful sources and record failures for the others.

Adaptive `sugar collect-plan` enables source-error continuation by default. If at least one requested source completed or returned partial material, branch results remain usable with the coverage caveat attached. If every requested surface failed or was unavailable, the affected search branches are moved to `paused` rather than `completed`; zero retrieved records are not treated as evidence of absence.

## Provenance through analysis

Coverage survives the pipeline as durable metadata:

```text
bounded collection
    -> records.coverage.json
    -> records.metadata.json
    -> triage observation metadata
    -> State package snapshot + BLUF
    -> portable handoff limitations.json
```

State-facing briefs automatically list collection-surface status when that metadata is available and add a material-limitation warning for `unavailable`, `failed`, or `partial` surfaces. Successful zero-result searches are labeled separately.

Portable handoff limitations also summarize record counts by source and language, observation geography, observed collection/publication time ranges, and search-branch/research-concept coverage. The original coverage sidecar is included as provenance when present.

## Access mode

Coverage entries record the effective access mode where SUGAR can determine it, for example `anonymous_public`, `public_appview`, `authenticated`, `session`, `authorized_api`, or `missing_credential`. This is research provenance, not an instruction to bypass source controls.
