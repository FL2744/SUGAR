![SUGAR logo](sugar-logo.png)

# SUGAR

**System for User-Generated Content Gathering, Analysis, and Representation**

SUGAR is a cross-platform public-source research system for collecting social-media material, preserving provenance, organizing evidence, conducting spatial and structured analysis, and producing reviewable research products. It is developed for Virginia Tech Diplomacy Lab work on public diplomacy and PRC-supported cultural/public-engagement networks, while the core remains platform-neutral.

Current package version: **1.2.0**.

## What SUGAR does

SUGAR provides one shared Python research core with native macOS and Windows clients. The supported pipeline is:

**Collect → Normalize → Enrich/triage → Human review → Evidence dataset → Spatial/analytic products → Refresh**

The core currently supports collection/workflows for **X, Bluesky, Mastodon, Bilibili, and Weibo**, including resumable high-volume harvesting, source provenance, thread relationships, AI-assisted triage, research observations, project workspaces, mapping, State-specific assessment/review, networks, rollups, freshness/change detection, and analytic-intelligence workflows.

SUGAR deliberately distinguishes **presence, activity, reach, engagement, outcomes, and causal influence**. It does not manufacture a universal influence score or treat collection density as influence.

## Entry points

| Surface | Purpose |
| --- | --- |
| `SUGAR-macOS/` | Native SwiftUI application for macOS 13+ |
| `SUGAR-Windows/` | Native PySide6 research workbench for Windows |
| `sugar` | General collection, harvest, triage, overlap, mapping, and reporting CLI |
| `sugar-project` | Persistent project-workspace management |
| `sugar-state` | State/Diplomacy Lab evidence-to-brief workflow |
| `sugar-intel` | Structured analytic-intelligence workflow |
| `sugar_bridge.py` | Typed line-delimited JSON process boundary used by desktop clients |

Both desktop applications call the same `sugar_core` implementation. Collection semantics, evidence rules, assessment logic, maps, and synthesis should not be reimplemented in individual frontends.

## Desktop use

### macOS

The packaged macOS application requires **macOS 13 Ventura or newer**. Development/test builds may not be publicly notarized; only override Gatekeeper warnings for builds obtained from a trusted project source. Credentials entered through the native app are stored using macOS Keychain where supported.

See [`SUGAR-macOS/README.md`](SUGAR-macOS/README.md) for build, packaging, compatibility, signing, and troubleshooting details.

### Windows

The Windows workbench packages `SUGAR.exe` plus a separate `sugar-bridge.exe` child process. That separation keeps the UI responsive, provides real cancellation, and isolates backend failures. Development/CI bundles are unsigned and may trigger SmartScreen; production distribution should use normal Authenticode signing rather than weakening endpoint protections.

See [`SUGAR-Windows/README.md`](SUGAR-Windows/README.md) for development, packaging, credentials, and troubleshooting.

## Python installation

Python **3.11–3.13** is supported.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

For development:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

SUGAR never installs or upgrades packages at runtime.

## Project workspaces

SUGAR 1.2 adds persistent project workspaces. A workspace keeps a portable `sugar-project.json` manifest, a local `.sugar/workspace.sqlite3` artifact registry, and standardized locations for raw collection, research observations, reference layers, State assessments, maps, reports, and intelligence outputs.

```bash
sugar-project init ./team4 \
  --name "Diplomacy Lab Team 4" \
  --description "PRC public-diplomacy research"

sugar-project status ./team4
sugar-project path ./team4 observations
sugar-project register ./team4 observations data/observations/kyrgyzstan.xlsx
```

Research files remain ordinary CSV/XLSX/JSONL/GeoJSON/HTML/Word/PDF files rather than being hidden inside the project database. Secrets are never stored in the workspace manifest or registry by SUGAR.

Portable projects can be transferred with `sugar-project archive PROJECT ARCHIVE.sugar.zip` and
validated into a new directory with `sugar-project restore ARCHIVE.sugar.zip NEW_PROJECT`. External
artifact references remain explicit and are not silently copied.

See [`docs/project-workspaces.md`](docs/project-workspaces.md) for the workspace schema, layout, portability rules, Python API, and desktop bridge operations.

## Collection

| Source | Current supported surface |
| --- | --- |
| X | API v2 recent/full-archive search, subject to caller access/billing |
| Bluesky | Public AppView search; optional authenticated PDS proxy path |
| Mastodon | Instance-scoped status search |
| Bilibili | Public video search, known-video metadata, and public comments |
| Weibo | Public/authorized search where available, known-public-post retrieval, comments, seed expansion, qualification workflows |

All collectors normalize into the shared `PostRecord` model. SUGAR preserves stable native IDs, canonical URLs, collection/published times, query matches, canonical engagement fields, raw platform metrics, source mode, and schema/collector versions.

One content object can match multiple queries; deduplication retains every matching query rather than discarding discovery provenance.

### High-volume harvesting

`harvest` is the durable collection path for thousands or tens of thousands of records. It decomposes work into deterministic tasks, checkpoints completed work to SQLite, resumes without recollection, records rate-limit/defer events, and separates raw collection from later AI processing.

```bash
sugar harvest \
  --sources bilibili,weibo \
  --terms-file csm_terms_zh.txt \
  --target 10000 \
  --output ./runs/csm_sep14 \
  --name csm_sep14
```

See [`docs/high-volume-harvest.md`](docs/high-volume-harvest.md).

## State / Diplomacy Lab workflow

The `sugar-state` suite keeps source-grounded `ResearchObservation` evidence separate from sponsor-specific `StateAssessment` judgments. It supports:

- monitored-entity/alias registries and reproducible query plans;
- strategic-audience, program-domain, and narrative coding;
- explicit PRC-support basis/evidence;
- guarded AI triage followed by human review;
- American Spaces/EducationUSA/U.S. public-diplomacy overlap;
- evidence-integrity auditing;
- verified-only maps, networks, BLUFs, and country/city rollups;
- collection freshness, change detection, and research-gap prioritization.

Example:

```bash
sugar-state package observations.xlsx \
  --assessments state.reviewed.jsonl \
  --us-sites us_presence.csv \
  --entities monitored_entities.csv \
  --previous-assessments prior_state.jsonl \
  --output ./state_package \
  --name quarterly_update
```

See [`docs/state-department-workflow.md`](docs/state-department-workflow.md) and [`docs/state-analytic-intelligence.md`](docs/state-analytic-intelligence.md).

## Mapping and spatial analysis

The research map can consume raw source exports or richer research-observation datasets. It supports marker clustering, reference overlays, review-state layers, activity-density windows, verified-only density, geographic-confidence weighting, nearest-reference proximity, and explicit U.S.-overlap views.

Heat layers represent mapped-record density, **not influence**. Geographic proximity represents distance, **not competition or coordination**.

See [`docs/research-map.md`](docs/research-map.md) and [`docs/spatial-overlap.md`](docs/spatial-overlap.md).

## AI use

LLM enrichment and triage are optional. Source text is treated as untrusted data and separated from model instructions. SUGAR does not infer a country from language alone and does not infer private/street-level locations.

AI runs can be bounded with `--max-llm-tokens`. Add `--max-llm-cost-usd` plus explicit input/output
cost rates when a provider-dollar ceiling is required; the shared budget covers retries and parallel
State synthesis workers.

For State-specific analysis, AI cannot self-verify evidence, confirm PRC support, invent acceptable evidence references, or establish causal influence. High-consequence claims remain subject to explicit evidence and human review.

Supported LLM configuration includes OpenAI-compatible providers and Virginia Tech ARC. Credentials are supplied at runtime; they must not be committed to the repository or inserted into project manifests.

## Research and access boundaries

SUGAR is designed for ordinary public or explicitly authorized access. It does **not** solve CAPTCHAs, manufacture authentication/session state, spoof devices, rotate proxies/accounts to evade limits, or bypass platform access controls. When a source denies access, requires unsupported login/verification, or rate-limits collection, the collector must fail or defer explicitly rather than converting that failure into evidence of zero activity.

The State workflow is a research methodology and product for the Diplomacy Lab project. It is not a Department of State security authorization, ATO, official intelligence product, procurement approval, or AI certification.

## Repository architecture

The supported implementation lives in `sugar_core/`. Historical pre-package monoliths have been removed from the working tree; Git history remains available if project archaeology is ever needed.

See [`docs/architecture.md`](docs/architecture.md) for module boundaries, frontend/core dependency rules, bridge architecture, and test expectations.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — current system architecture and engineering rules
- [`docs/project-workspaces.md`](docs/project-workspaces.md) — persistent project-workspace contract
- [`docs/collector-interface.md`](docs/collector-interface.md) — collector capabilities and normalization contract
- [`docs/collector-capability-matrix.md`](docs/collector-capability-matrix.md) — visible access/capability matrix and coverage semantics
- [`docs/high-volume-harvest.md`](docs/high-volume-harvest.md) — durable large-scale collection
- [`docs/stress-testing.md`](docs/stress-testing.md) — offline scale probes and stress-test plan
- [`docs/legal-and-data-handling.md`](docs/legal-and-data-handling.md) — public/authorized access definitions and data-handling boundaries
- [`docs/release-readiness.md`](docs/release-readiness.md) — tracked hardening ledger and candidate gate
- [`docs/bilibili-public.md`](docs/bilibili-public.md) — Bilibili public collector
- [`docs/weibo-public.md`](docs/weibo-public.md) — Weibo public collector
- [`docs/weibo-investigation.md`](docs/weibo-investigation.md) — known-post investigation workflow
- [`docs/weibo-qualification.md`](docs/weibo-qualification.md) — reproducible Weibo acceptance/qualification
- [`docs/research-observations.md`](docs/research-observations.md) — evidence-layer schema
- [`docs/research-map.md`](docs/research-map.md) — analytical map methodology
- [`docs/spatial-overlap.md`](docs/spatial-overlap.md) — reference-network proximity analysis
- [`docs/state-department-workflow.md`](docs/state-department-workflow.md) — State workflow and integrity rules
- [`docs/state-analytic-intelligence.md`](docs/state-analytic-intelligence.md) — structured analytic products
- [`docs/state-agentic-deep-mode.md`](docs/state-agentic-deep-mode.md) — iterative synthesis mode

## Development and contribution

Before opening a pull request:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

CI runs the Python suite on Ubuntu, macOS, and Windows with Python 3.11–3.13, runs lint/type/dependency/security gates, verifies wheel/sdist installation, and separately builds/smoke-tests the packaged macOS and Windows applications. Schema, collector, bridge, workspace, or methodology changes should include regression tests and documentation in the same pull request.

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), and [`CHANGELOG.md`](CHANGELOG.md).
