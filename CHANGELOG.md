# Changelog

Notable SUGAR changes are recorded here. Dates refer to the repository integration date, not necessarily the first experimental commit.

## Unreleased

### Added

- integration-first external CSV/JSONL ingestion that normalizes partner/Department exports into `PostRecord`, preserves unmapped source fields, quarantines invalid identities, merges duplicate query provenance, and emits source-hashed import manifests;
- versioned research requirements and bounded search plans with stable IDs, explicit branch families/statuses, mode-specific branch/hop budgets, and timestamped audit events;
- optional provider-neutral model-assisted query planning with generator provenance, target-neutral exclusions, and evidence-grounded follow-up branches that reject invented evidence IDs;
- executable plan collection and feedback commands that reuse the shared collector registry, join triaged observations back to query branches, track uncertainty separately from decisive relevance evidence, and apply deterministic continue/retire/review rules.
- portable research handoff directories/ZIPs with canonical JSONL evidence, requirement/search-plan context, generated or analyst-supplied limitations, optional review/analytic outputs, schema/software metadata, per-artifact SHA-256 hashes, and standalone verification.

### Changed

- imported URL-only records retain their canonical `record_key` when converted to research observations, canonical JSONL is accepted by shared result loading, and triage loading preserves parent/thread/conversation relationships.

## 1.2.6 — 2026-09-17

### Fixed

- OpenAI-compatible LLM calls now negotiate `max_tokens` / `max_completion_tokens` and unsupported deterministic-temperature parameters instead of repeatedly failing valid live searches;
- frozen desktop geocoding uses the bundled verified CA store, and a geocoder outage no longer discards otherwise valid collection/enrichment results;
- empty bounded searches are persisted as valid zero-record research outputs instead of surfacing as a generic desktop exit-code failure;
- local HTML maps no longer default to the OpenStreetMap France HOT tile service, which could return a terms-of-use/403 tile error for local `file://` reports;
- macOS Quick Search now exposes Bilibili and Weibo, uses the same bounded first-run defaults as Windows, and supports an authorized Weibo session from Keychain;
- Bilibili Quick Search preserves valid search-result metadata when optional detail hydration is separately access-controlled;
- Windows packaged build metadata now reports desktop bridge protocol 3 consistently with the bundled backend.

### Release engineering

- desktop CI now retains a validated macOS application archive as well as the Windows portable bundle;
- tagged releases build and publish Windows x64, macOS Apple Silicon, macOS Intel, and Python distribution artifacts from the same reviewed commit;
- package, backend, README, and desktop release versioning are re-synchronized at 1.2.6 after the interim classroom snapshot tags.

### Changed

- Python 3.14 is now a first-class supported runtime across package metadata and the Ubuntu/macOS/Windows test matrix; Windows packaged-app validation runs on Python 3.14, while the macOS packaged backend intentionally remains on Python 3.12 to preserve the macOS 13 deployment floor;
- SUGAR is now explicitly released under Apache License 2.0 with a copyright notice identifying Alejandro Grenier and contributors, repository/package legal metadata, third-party notices, contribution licensing terms, and legal files embedded into packaged desktop and Python distributions;
- workspace runtime discovery now falls back to the most recent existing artifact when a newer registration is missing, and Weibo investigation/qualification outputs are classified consistently as raw-collection artifacts;
- Weibo qualification now treats fewer than two fresh replicates as an unassessed reproducibility advisory rather than silently skipping the gate, and real-post investigation artifacts are included in the returned/registered qualification outputs;
- hardened the evidence-constrained synthesis and LLM boundary with deterministic tests for retry/cache behavior, prompt-injection boundaries, JSON parsing, agent failure handling, integrator evidence allowlisting, orchestration, and persisted synthesis artifacts;
- alternative-hypothesis consistency labels are now normalized case-insensitively instead of silently downgrading valid mixed-case labels to `mixed`;
- deterministic collection reports now have parity between DOCX and PDF outputs for engagement, recurring vocabulary, geographic caveats, and descriptive context, with PDF text safely escaped for ordinary special characters;
- release hardening now validates package builds, dependency vulnerabilities, correctness linting, and test coverage in dedicated CI;
- branch-aware core coverage now has a 70% regression floor, below the current measured suite coverage;
- developer dependencies now include reproducible local quality/build tooling, with a separate dependency-audit extra;
- all installed SUGAR command-line entry points expose a top-level `--version` flag;
- runtime dependency declarations in `requirements.txt` are regression-tested against authoritative `pyproject.toml` metadata;
- map heat-window construction no longer relies on pandas' deprecated generic NumPy timedelta conversion;
- workspace SQLite connections now close deterministically after each transaction instead of waiting for garbage collection;
- test runs now treat leaked files, database handles, and other unraisable resource warnings as failures;
- GitHub Actions artifact uploads now use the current Node 24-based action generation;
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
