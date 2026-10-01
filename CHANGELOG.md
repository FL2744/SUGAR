# Changelog

Notable SUGAR changes are recorded here. Dates refer to the repository integration date, not necessarily the first experimental commit.

## Unreleased

### Collection and exported-map fixes

- Keep evidence review, geography, mapping, and export controls inside their panel by wrapping them at narrower window widths.

- Build literal keyword plans without including provider instructions; recognize explicitly named collection sources and discard outdated interpretations when the question changes.
- Put planning and collection before optional dataset import in the advanced evidence workflow; pass AI configuration through to collection.
- Export self-contained maps with bundled Natural Earth country boundaries and local map libraries, including the overview map, without tile-server or CDN requests. This background provides country-level context rather than street detail.
- Show full saved English translations in point popups, with expandable originals and source links. Keep background and heat layers from intercepting point clicks.
- Include map assets in macOS and Windows packages and retain data attribution while hiding library branding.

### Added

- **Research workbench.** Plain-language requests are interpreted into a persistent, typed `ResearchPlanSpec` (topic, geography, actors, timeframe, languages, platforms, queries, exclusions, depth, limits, translation, de-duplication, provider, refresh, concurrency, retry, extension fields) that is shown for review (run / edit / advanced) before anything executes.
- LLM interpretation harness with JSON-schema output, safe repair, bounded retry with feedback, and fallback to a deterministic interpreter and then manual structured entry; clarification is requested only when the topic cannot be inferred.
- Provider-aware LLM configuration (OpenAI, OpenAI-compatible, Anthropic, Virginia Tech ARC, local) with typed credentials, per-stage *Test connection* (reachable / credential / model / inference), and provider-specific errors.
- Secure local credential storage (OS vault or owner-only file, environment and `.env.local` overrides) and shared secret redaction for logs, events, run records, exports, and diagnostic reports.
- Structured activity events, a concurrent pipeline (Plan → Search → Collect → Translate → Process → Results), live translation view, pause/resume/cancel, query edits and item exclusion during a run, retry of failed sources, failure classes (fatal / source-specific / retryable / skipped / warning), and explicit reporting of incomplete collection.
- Run objects, project data model, project timeline, provenance and evidence-chain lineage, timing instrumentation, Debug Mode, verifiable export bundles (JSON/JSONL/CSV/GeoJSON/Markdown + manifest with SHA-256).
- New UI: Research, Activity, Results, Projects, Settings with explicit Save, Basic/Advanced modes, text-size and density settings, rem-based typography for high-DPI displays, prominent *New project*, compact project list, About page with attribution.
- Workbench runs share main's request pacer and provider cooldowns, search Mastodon as public `#hashtag` timelines when no token is saved (explaining each adaptation), read credentials saved in the OS vault, and enforce project roles (viewer/reviewer/analyst/owner) on every workbench route; providers, credentials, diagnostics and folder access are administrator-only.
- Desktop app starts a loopback research API sidecar for live runs; `sugar-bridge serve`.
- `tools/demo_workbench_server.py` offline demo with simulated platforms and model.
- **More reliable sources beyond social platforms:** Wikipedia (any language edition), worldwide news coverage (GDELT), scholarly works (OpenAlex), and news/institution feeds you name (RSS/Atom, saved per project). They need no account, return the same record shape, and share de-duplication, translation and provenance.
- **Team review:** per-item verdicts (relevant / not relevant / follow up), tags, and comment threads kept as an append-only log with the real author taken from the authenticated member; quick triage on each result, review filters and progress in Results, and entries in the project timeline. Reviewers can annotate; viewers read only.
- **First-run setup** (name, choose OpenAI, Virginia Tech ARC or no AI, test the key and pick from the account's models, see which sources are ready, try an example), skippable and repeatable from Settings.
- **Explicit AI model choice** on the Research page (OpenAI, Virginia Tech ARC, or no AI) carried into the plan and run; an unusable choice warns and never falls back to another provider.
- **Soft per-run model-call budget** (default 500, 0 = unlimited): when spent, optional translation pauses with one notice; collection and the run are never failed or blocked.
- Command palette (Ctrl/⌘+K), keyboard-shortcut help (?), and completion toasts.

### Changed

- Plan summaries show readable dates ("1 Apr 2026 – 1 Oct 2026") and language names; incomplete collection is listed one source per row with a retry button; the plan's Run/Edit bar stays visible; the phone layout uses a compact top bar.
- "Refresh plan" is replaced by five distinct operations (Reinterpret request, Rebuild plan, Refresh sources, Reprocess results, Rerun).
- Credentials are no longer entered as session-only fields; bridge operations resolve them from the environment and then from saved Settings.
- Project authors now include William Taggart.

## 1.6.1 — 2026-10-01

### Collection and workflow

- retry anonymous Bluesky searches against Bluesky's public AppView when its cached public hostname returns 403; preserve collected first-page records when a later page fails;
- support explicit public Mastodon `#hashtag` timelines without a search token, with separate provenance from authorized keyword search;
- restore live collection outputs in the desktop evidence panel, and allow known public Bilibili videos, Weibo posts, and WeChat articles to enter the evidence workflow by URL;
- expose location inference and evidence-map generation in the desktop research workflow;
- classify Bilibili challenge responses and public API 401/403 responses as unavailable coverage instead of empty results.

### Live verification

- collected and saved real Bluesky and Mastodon posts, completed a research plan using both, and triaged live posts into insight artifacts;
- ingested and triaged real Bilibili video and Weibo post URLs; generated analysis and maps from live, location-enriched X and Mastodon records;
- Weibo and Bilibili keyword search still face provider login/access challenges in this environment. WeChat article retrieval encountered a TLS hostname mismatch and remains unavailable here; SUGAR does not disable certificate verification.

## 1.6.0 — 2026-10-01

### Added

- added API-enforced project roles with one-time project-scoped member tokens, owner-managed issuance/revocation, append-only project comments, and reusable research requirement templates;
- added analyst-attributed dataset geography assignments, change detection for stale annotations, side-by-side region comparisons, and map layer toggles with draggable coordinate review;
- connected saved listening posts to the desktop/browser workspace, including schedule editing, pause/resume, and run-due checks; added bounded per-platform collection tuning;
- expanded deterministic question, activity, and place extraction across Portuguese, German, Italian, Russian, Arabic, and Chinese while retaining exact source spans for explicit concepts;
- added browser accessibility/readability coverage to CI and raised the package release version.

### Quality

- verified the packaged frontend build, all six headless Chromium workflows, WCAG 2.2 A/AA checks, and focused backend/API/workspace tests;
- verified the full Python suite, Ruff, a Windows MSI and bundled sidecar, and packaged sidecar access to the OS credential vault;
- used the vault-saved credentials for OpenAI model discovery, strict structured interpretation with exact source spans, query/text translation, and an X search that returned one record;
- exercised Bluesky, Bilibili, Mastodon, and Weibo through the real collection pipeline; Bilibili completed with zero results while the other three reported unavailable access for this environment.

## 1.5.0 — 2026-09-30

### Added

- added live collection controls for queries, sources, exclusions, languages, date windows, source retries, and cooperative stop requests;
- added cross-provider request pacing, parallel source collection, bounded collection requests, an estimated memory budget, and parallel order-preserving observation extraction;
- added OpenAI strict structured output for multilingual requirement interpretation, with analyst approval before a compiled strategy drives search;
- added optional translation of collected posts, project-level notes and a member roster, analyst-reviewed coded findings, export format selection, and geographic grouping summaries;
- added Windows Credential Manager, macOS Keychain, and supported Linux vault integration with no plaintext credential fallback;
- increased the desktop text-size floor to 16px and expanded responsive, dark-mode, and accessibility coverage;

### Fixed

- project file references are constrained to their owning workspace, GeoJSON exports retain valid coordinate ordering, and JSON exports are emitted as JSON arrays;
- Windows and macOS sidecar build scripts now include the credential-vault runtime;
- frozen desktop workspaces now report the packaged SUGAR version when Python distribution metadata is absent.

### Quality

- added API and browser tests for live collection controls, project profiles, dataset formats, geography summaries, memory limits, and strict structured output;
- verified the Windows Credential Manager integration, OpenAI model access, structured interpretation, Spanish translation, X search, and anonymous Bilibili pipeline against live services;
- added the expanded Playwright suite to the existing CI UI job and retained the repository OPSEC check.

## 1.4.0 — 2026-09-30

### Added

- added research requirement controls for date range, language codes, excluded topics, and collection sources; plan collection now carries the configured date, source, and language filters;
- OpenAI triage now requests strict JSON Schema output, with the parsed evidence spans still checked against source text;

### Fixed

- removed target-specific institute and partner references from the Ghana education research demo so it passes the public repository OPSEC check; regenerated the example workspace and its portable handoff from the corrected source inventory;
- increased muted-text contrast across the shared desktop workspace, labeled hidden file inputs, and added light/dark appearance selection with a remembered theme;
- aligned the Python package and core version with the existing 1.4.0 desktop application.

### Quality

- added Chromium Playwright coverage for browser project creation, research-requirement submission, session-only credentials, and WCAG 2.2 A/AA checks across the primary workspace views;
- added the browser suite to CI and verified the Windows MSI and bundled sidecar with the packaged no-credential workflow.

## 1.3.0 — 2026-09-24

### Added

- added the shared Research Workspace in Windows and macOS with project switching, subprojects, dashboards/history, registry and dataset inspection, reference map layers, conversation context, listening-post review, and portable project exchange;
- added a provenance-preserving generic institution/service registry with CSV/TSV/XLSX/XLS/JSON/GeoJSON import preview, explicit field mapping, row validation, lifecycle/conflict history, similar-name review suggestions, relationship evidence, dimension-by-dimension comparison, and blank network templates;
- added versioned exact-label normalization for sourced program domains, audiences, and delivery modes while retaining original source wording and leaving unclassified values visible rather than guessing;
- added filterable and exportable underlying datasets, historical as-of map views, actor-aware conversation reconstruction, saved query monitoring with deduplicated new/changed material, and auditable analyst review state;
- added hash-verified portable project bundles with safe import staging and path portability for recorded history; bundle exchange excludes credential material and is asynchronous;
- documented the research workspace's implementation boundary, including that generated templates do not contain an authoritative maintained institution inventory and that SUGAR does not replace OASIS/MODE or estimate outcomes from public activity;

- added a reusable `ingest`/Public URL workflow for collector surfaces that support known-item retrieval, with normalized CSV/XLSX/metadata outputs and the same workspace/provenance contract as search;
- added fail-closed public WeChat Official Account article ingestion for `mp.weixin.qq.com` URLs, including stable article identity, account/publish metadata, source provenance, same-origin redirect validation, deterministic fixtures, and Windows/macOS Public URL UI;
- WeChat capability metadata deliberately advertises known-item ingestion only; keyword discovery, private WeChat surfaces, automated login state, challenge solving, and access-control bypass remain unsupported;
- integration-first external CSV/JSONL ingestion that normalizes partner/Department exports into `PostRecord`, preserves unmapped source fields, quarantines invalid identities, merges duplicate query provenance, and emits source-hashed import manifests;
- versioned research requirements and bounded search plans with stable IDs, explicit branch families/statuses, mode-specific branch/hop budgets, and timestamped audit events;
- optional provider-neutral model-assisted query planning with generator provenance, target-neutral exclusions, and evidence-grounded follow-up branches that reject invented evidence IDs;
- executable plan collection and feedback commands that reuse the shared collector registry, join triaged observations back to query branches, track uncertainty separately from decisive relevance evidence, and apply deterministic continue/retire/review rules.
- portable research handoff directories/ZIPs with canonical JSONL evidence, requirement/search-plan context, generated or analyst-supplied limitations, optional review/analytic outputs, schema/software metadata, per-artifact SHA-256 hashes, and standalone verification.
- durable per-source collection coverage that distinguishes success, successful zero-result searches, partial collection, unavailable access, and collector failure; adaptive branches pause when every requested source is inaccessible, and coverage limitations propagate into State briefs and handoff packages.
- portable root-level `sugar-artifacts.json` workspace catalogs now preserve registered evidence, requirements/search plans, review state, limitations, and outputs independently of the local SQLite index; moved projects can rebuild `.sugar/workspace.sqlite3` from the catalog while retaining missing/external artifact state, and handoff components are registered individually.
- explicit evidence-lineage indexes now connect State claims and sponsor-support findings to observations, source evidence identities, canonical records, and dataset provenance; exact structured contradictions are enumerated separately, raw/import metadata survives triage, and handoff verification checks semantic lineage consistency as well as file hashes.
- added a transparent next-evidence ranking that combines uncovered requirement scope, hypothesis collection needs, and measured branch relevance, novelty, duplicates, and source counts; selected proposals are saved as paused, auditable plan branches for analyst review.
- next-evidence reports now explain why candidates rank, use a comparable completed-branch cohort for historical yield/triage planning references when candidate metrics are absent, and safely accept a single-string hypothesis collection need.
- added content-similarity lineage candidates, evidence-linked temporal entity/event graphs, and leave-one-source/factor-out sensitivity reports over human-verified State evidence; each output records its method and limits.
- added an optional DuckDB/Parquet path that streams canonical CSV/JSONL datasets into platform-partitioned Zstandard Parquet and supports bounded SQL queries without loading the corpus into pandas.
- extended observation evidence references with source-language metadata and added corresponding research-quality controls to both desktop clients.
- added hash-linked media manifests, local preservation, optional analyst-supplied OCR/transcripts, timestamped citations, and observation attachment for image/audio/video evidence;
- added a saved-page capture path that stores sanitized visible text and public media references while removing scripts, hidden controls, and credential-like values;
- added offline lexical evidence search and opt-in cross-lingual embedding indexes, with local index reuse and query/corpus transmission disclosed in both desktop clients;
- added project merging with canonical-record deduplication, contributor provenance, preserved analyst artifacts, explicit review-conflict reports, and combined corpus/query-duplication summaries;
- added hash-based artifact derivation metadata, stale-state propagation, an upstream-first incremental rebuild report, and a six-case offline research-calibration suite;
- advanced the temporal evidence graph with human-supplied alias resolution, ambiguous-alias reporting, claim/evidence nodes, and media timestamp references; ResearchObservation is now schema 1.4.
- connected source-backed project-registry claims, relationships, and lifecycle events to the temporal evidence graph; Windows and macOS now capture relationship review state and optional sourced valid-time dates, with pipeline freshness tracking the registry inputs.

### Changed

- imported URL-only records retain their canonical `record_key` when converted to research observations, canonical JSONL is accepted by shared result loading, and triage loading preserves parent/thread/conversation relationships.
- Windows collection validates date ranges before starting, makes all generated outputs selectable, and defaults resumable harvest to a public Bilibili source; backend cancellation no longer blocks the window, and unexpected backend exits now show an actionable error.
- macOS adds cancellation to Activity, validates search date ranges, accepts newline-separated search terms, and exposes full output paths for copying.
- Windows and macOS research projects can now prepare unreviewed observations and blank State assessments directly from imported or collected records without an AI key; the Windows project page can verify its exported handoff in place.
- applying a human review workbook now keeps the reviewed CSV as the active observations artifact, so later handoff and audits do not mistake the workbook or metadata JSON for the dataset.
- handoff publishing tolerates brief Windows file-indexer locks while moving its completed staging directory into place.

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
- tagged releases build and publish Windows x64, macOS Apple Silicon, and Python distribution artifacts from the same reviewed commit;
- Intel Mac desktop builds are no longer a supported distribution target, leaving one unambiguous macOS download for current classroom users;
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
