# SUGAR v1.1 stabilization baseline (historical)

This document records the v1.1 stabilization baseline that established the supported `sugar_core` architecture. It is retained for historical context; **it is not the current feature roadmap**. Current capabilities and contribution rules are documented in `README.md`, `docs/architecture.md`, and `CHANGELOG.md`.

## What v1.1 established

The v1.1 stabilization moved new engineering work away from the historical `SUGAR.py` monolith and into a supported, testable Python package. It established the following invariants:

- no runtime package installation or dependency upgrades;
- Linux/ARC as a first-class environment;
- platform-neutral engagement normalization;
- multi-query deduplication that preserves query provenance;
- consistent inclusive date semantics;
- spreadsheet formula-injection protection without corrupting coordinates;
- preservation of raw platform metrics alongside canonical fields;
- collection timestamps, schema/collector versions, stable IDs/URLs, and metadata sidecars;
- instruction/source separation for AI enrichment;
- cached LLM/geocoding results;
- the native macOS bridge calling the shared core instead of importing the legacy monolith;
- CI coverage across supported Python versions and operating systems.

## Capabilities added after the baseline

The earlier document intentionally deferred Bilibili, Weibo, other Chinese-platform work, richer State methodology, and expanded desktop support. Those statements are now obsolete. Subsequent development added, among other things:

- public/fail-closed Bilibili collection;
- public/authorized Weibo collection, known-post investigation, qualification, and seed harvesting;
- collector capability/registry interfaces and thread relationships;
- durable high-volume harvesting;
- `ResearchObservation` evidence storage and grounded triage;
- spatial-overlap and substantially richer research maps;
- State-specific schemas, review/audit, overlap, networks, rollups, freshness, gaps, and briefing products;
- structured analytic-intelligence and iterative synthesis workflows;
- native Windows workbench packaging over the shared backend;
- persistent project workspaces in v1.2.

## Invariants that still apply

The core stabilization principles remain binding even as features expand:

1. New engineering work targets `sugar_core`, not the legacy monolith.
2. Source provenance and raw evidence are preserved before analysis.
3. Access failures are explicit and are not converted into zero-activity findings.
4. Cross-platform engagement metrics are not treated as directly equivalent causal measures.
5. AI analysis remains distinguishable from human verification.
6. Frontends call shared backend logic rather than duplicating methodology.
7. Schema/bridge/workspace changes require tests and documentation.

For the current system, start with `README.md` and `docs/architecture.md`.
