# Changelog

Notable SUGAR changes are recorded here. Dates refer to the repository integration date, not necessarily the first experimental commit.

## Unreleased

### Changed

- normal `sugar` and `sugar-state` workflows now auto-discover project workspaces, route outputs to canonical project directories when no explicit destination is supplied, and register generated artifacts automatically;
- desktop State/intelligence operations can resolve the latest registered observations and assessment artifacts from a workspace instead of requiring every file path to be reselected;
- added a typed `state-map` desktop operation;
- State research maps now classify every mapped observation by geographic precision, separate precision classes into distinct layers, expose precision/confidence in popups and metadata, and display uncertainty envelopes for approximate locations;
- missing State-map coordinates can optionally be resolved from explicit site/city/region evidence through a cached public geocoder;
- geocoder feature metadata and bounding boxes are preserved so site queries that resolve only to a city/region are automatically downgraded rather than presented with false precision;
- country-only observations are not placed at artificial national centroids, and broad/low-confidence locations are excluded from activity-density rendering.

### Research integrity

- geographic resolution does not infer an event venue from an institution name alone;
- geocoded coordinates remain derived evidence and do not modify the underlying observation record or verification state;
- State-map density remains equal-weight activity-location density rather than a reach, engagement, or influence score.

## 1.2.0 — 2026-09-14

### Added

- persistent project workspaces with portable `sugar-project.json` manifests;
- local `.sugar/workspace.sqlite3` artifact registry with portable in-project paths, explicit external-artifact tracking, missing-file health reporting, and workspace discovery;
- `sugar-project` CLI for workspace initialization, status, canonical paths, artifact registration, and listing;
- typed desktop bridge workspace operations (`workspace-init`, `workspace-status`, `workspace-register`);
- native Windows PySide6 research workbench and portable packaged application over the shared `sugar_core`/bridge architecture;
- structured State/analytic-intelligence desktop operations;
- project architecture and workspace documentation;
- repository contributor and security policies.

### Changed

- desktop bridge protocol advanced to version 3;
- package metadata updated to reflect the current cross-platform beta architecture;
- README rewritten around the supported core, desktop clients, workspace model, State workflow, and current collector coverage;
- repository organization/stabilization documents rewritten so historical migration notes are no longer presented as the current architecture;
- local workspace and Windows build state added to default ignore rules;
- CI expanded with cross-platform workspace smoke coverage and packaged Windows workspace validation.

### Research integrity

- no change to SUGAR's fail-closed collection/access policy;
- no change to the separation between source evidence, AI triage, and human verification;
- no universal influence score introduced; presence, activity, reach, engagement, outcomes, and causal influence remain distinct.

## 1.1.x — 2026-09-10 to 2026-09-13

The 1.1 stabilization line established `sugar_core` as the supported implementation and then expanded the system substantially.

### Core stabilization

- removed runtime dependency installation/upgrades;
- made Linux/ARC a first-class environment;
- normalized cross-platform engagement fields while preserving raw platform metrics;
- preserved multi-query discovery provenance during deduplication;
- standardized inclusive date-range semantics;
- added source/collection/schema metadata and output sidecars;
- hardened AI enrichment instruction/source separation and location inference;
- added repeatable caching and broader CI coverage.

### Collection and scale

- Bilibili public video search, known-video retrieval, and comment collection;
- collector capability/registry interface and thread relationships;
- Weibo public/authorized search, known-post retrieval, comments, account/seed investigation, qualification, and durable seed harvesting;
- resumable high-volume harvesting with SQLite checkpoints, deterministic task plans, rate-limit-aware defer/resume behavior, and large deterministic orchestration tests.

### Evidence and analysis

- `ResearchObservation` evidence layer and grounded AI triage;
- spatial-overlap/reference-network analysis;
- expanded research maps with review-state, density, reference, and provenance layers;
- State-specific schema, human review workflow, evidence audit, American Spaces/EducationUSA overlap, verified-only BLUFs/maps/networks, rollups, freshness/change detection, monitored entities, and research-gap analysis;
- structured analytic-intelligence packets, tradecraft/epistemic-debt auditing, competing hypotheses, longitudinal comparison, and iterative synthesis.

See `STABILIZATION.md` for the original v1.1 baseline invariants and `docs/architecture.md` for the current design.
