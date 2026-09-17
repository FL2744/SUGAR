![SUGAR logo](sugar-logo.png)

# SUGAR

**System for User-Generated Content Gathering, Analysis, and Representation**

SUGAR is a cross-platform public-source research system for collecting social-media material, preserving provenance, organizing evidence, conducting spatial and structured analysis, and producing reviewable research products. The public engine is target-neutral; project-specific targets, query plans, and case data belong in non-public project configuration.

Current package version: **1.2.6**.

License: **Apache License 2.0**. Copyright 2026 Alejandro Grenier and contributors.

## What SUGAR does

SUGAR provides one shared Python research core with native macOS and Windows clients. The supported pipeline is:

**Collect → Normalize → Enrich/triage → Human review → Evidence dataset → Spatial/analytic products → Refresh**

The core currently supports collection/workflows for **X, Bluesky, Mastodon, Bilibili, and Weibo**, including resumable high-volume harvesting, source provenance, thread relationships, AI-assisted triage, research observations, project workspaces, mapping, State-specific assessment/review, networks, rollups, freshness/change detection, and analytic-intelligence workflows.

For integration-first research, the core can also ingest external CSV/JSONL datasets into the same canonical evidence model and persist a research requirement plus an auditable adaptive search plan. Model-assisted query expansion is optional; collection, imported evidence, plan state, and human review remain usable without it.

Completed or intermediate research can be exported with `sugar handoff` as a portable directory/ZIP containing canonical evidence, requirement/search-plan context, coverage limitations, review state, provenance, and existing analytic outputs. `sugar verify-handoff` verifies every manifest-listed artifact by SHA-256 and byte length.

SUGAR deliberately distinguishes **presence, activity, reach, engagement, outcomes, and causal influence**. It does not manufacture a universal influence score or treat collection density as influence.

## Entry points

| Surface | Purpose |
| --- | --- |
| `SUGAR-macOS/` | Native SwiftUI application for macOS 13+ |
| `SUGAR-Windows/` | Native PySide6 research workbench for Windows |
| `sugar` | Requirements/planning, external import, collection/harvest, triage, overlap, mapping, and reporting CLI |
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

Python **3.11–3.14** is supported.

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

SUGAR 1.2 adds persistent project workspaces. A workspace keeps a portable `sugar-project.json` identity/layout manifest, a portable `sugar-artifacts.json` evidentiary catalog, a rebuildable local `.sugar/workspace.sqlite3` index, and standardized locations for raw collection, research observations, reference layers, State assessments, maps, reports, and intelligence outputs.

```bash
sugar-project init ./team4 \
  --name "Diplomacy Lab Team 4" \
  --description "public-diplomacy research"

sugar-project status ./team4
sugar-project path ./team4 observations
sugar-project register ./team4 observations data/observations/example host country.xlsx
```

Research files remain ordinary CSV/XLSX/JSONL/GeoJSON/HTML/Word/PDF files rather than being hidden inside the project database. Secrets are never stored in the workspace manifest or registry by SUGAR.

If a project is copied to another machine without `.sugar/workspace.sqlite3`, opening it rebuilds the local artifact index from `sugar-artifacts.json`; registered missing files remain visible as missing, and deliberately external references remain marked external.

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

Bounded searches also emit a collection-coverage sidecar that distinguishes successful zero-result searches from partial, unavailable, and failed source access. Adaptive plan execution preserves successful sources, pauses branches when every requested surface is inaccessible, and carries these limitations through triage, State briefs, and portable handoff bundles.

External Department/partner exports can enter the same pipeline with `sugar import`. CSV and JSONL inputs are normalized into `PostRecord`, invalid identities are quarantined or rejected explicitly, and an import manifest records source-system name, SHA-256, field mapping, and accepted/rejected counts. See [`docs/importer-interface.md`](docs/importer-interface.md).

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
- explicit sponsor-support basis/evidence;
- guarded AI triage followed by human review;
- American Spaces/EducationUSA/U.S. public-diplomacy overlap;
- evidence-integrity auditing;
- verified-only maps, networks, BLUFs, and country/city rollups;
- collection freshness, change detection, and research-gap prioritization.
- research-question-first planning with bounded model-assisted query expansion, evidence-grounded pivots, and branch stopping rules.

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

See [`docs/research-requirements.md`](docs/research-requirements.md), [`docs/state-department-workflow.md`](docs/state-department-workflow.md), and [`docs/state-analytic-intelligence.md`](docs/state-analytic-intelligence.md).

## Mapping and spatial analysis

The research map can consume raw source exports or richer research-observation datasets. It supports marker clustering, reference overlays, review-state layers, activity-density windows, verified-only density, geographic-confidence weighting, nearest-reference proximity, and explicit U.S.-overlap views.

Heat layers represent mapped-record density, **not influence**. Geographic proximity represents distance, **not competition or coordination**.

See [`docs/research-map.md`](docs/research-map.md) and [`docs/spatial-overlap.md`](docs/spatial-overlap.md).

## AI use

LLM enrichment and triage are optional. Source text is treated as untrusted data and separated from model instructions. SUGAR does not infer a country from language alone and does not infer private/street-level locations.

For State-specific analysis, AI cannot self-verify evidence, confirm sponsor support, invent acceptable evidence references, or establish causal influence. High-consequence claims remain subject to explicit evidence and human review.

Supported LLM configuration includes OpenAI, custom OpenAI-compatible endpoints, and Virginia Tech ARC as a development/classroom option. Credentials are supplied at runtime; they must not be committed to the repository or inserted into project manifests. Core import, evidence, project, and deterministic planning operations do not require an LLM.

## Virginia Tech ARC quick start

SUGAR can use Virginia Tech ARC's shared hosted-model API for translation and AI-assisted analysis while the desktop application itself runs locally. For the shared API, Virginia Tech students, faculty, and staff do not need a separate ARC HPC account.

1. Open **Settings** in SUGAR and choose **Get ARC API Key**, or visit `https://llm.arc.vt.edu`.
2. Sign in with Virginia Tech credentials and open **User profile → Settings → Account → API keys**.
3. Create a personal key and paste it into SUGAR's ARC/API-key field. Never share the key.
4. Choose **Virginia Tech ARC** and use **Test ARC Connection**.
5. Use an ARC model in an AI-assisted workflow. The classroom defaults are `gpt-oss-120b`, `DeepSeek-V4.1-Flash`, `GLM-5.3`, and `Kimi-K3`.

ARC's shared API endpoint is `https://llm-api.arc.vt.edu/api/v1`. Dedicated Open OnDemand LLM sessions are a separate ARC workflow and require an ARC account/allocation.

## Research and access boundaries

SUGAR is designed for ordinary public or explicitly authorized access. It does **not** solve CAPTCHAs, manufacture authentication/session state, spoof devices, rotate proxies/accounts to evade limits, or bypass platform access controls. When a source denies access, requires unsupported login/verification, or rate-limits collection, the collector must fail or defer explicitly rather than converting that failure into evidence of zero activity.

The State workflow is a research methodology and product for the Diplomacy Lab project. It is not a Department of State security authorization, ATO, official intelligence product, procurement approval, or AI certification.

## Repository architecture

The supported implementation lives in `sugar_core/`. Historical pre-package monoliths have been removed from the working tree; Git history remains available if project archaeology is ever needed.

See [`docs/architecture.md`](docs/architecture.md) for module boundaries, frontend/core dependency rules, bridge architecture, and test expectations.

For the State/Diplomacy Lab delivery target, the versioned product contract lives in [`product/requirements/state_product.v1.json`](product/requirements/state_product.v1.json), with rationale and implementation order in [`docs/product/state-product-contract.md`](docs/product/state-product-contract.md). The contract treats Virginia Tech ARC as an optional development integration rather than a State deployment dependency and requires interoperable import/export boundaries for existing Department capabilities.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — current system architecture and engineering rules
- [`docs/project-workspaces.md`](docs/project-workspaces.md) — persistent project-workspace contract
- [`docs/collector-interface.md`](docs/collector-interface.md) — collector capabilities and normalization contract
- [`docs/importer-interface.md`](docs/importer-interface.md) ? external-data normalization and provenance contract
- [`docs/research-requirements.md`](docs/research-requirements.md) ? research requirements and bounded adaptive search planning
- [`docs/handoff-bundles.md`](docs/handoff-bundles.md) ? portable evidence-package handoff and integrity verification
- [`docs/collection-coverage.md`](docs/collection-coverage.md) ? collection success/failure/availability and absence semantics
- [`docs/high-volume-harvest.md`](docs/high-volume-harvest.md) — durable large-scale collection
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

CI runs the Python suite on Ubuntu, macOS, and Windows with Python 3.11–3.14 and separately builds/smoke-tests the packaged macOS and Windows applications. The Windows package is built under Python 3.14. The macOS package deliberately embeds Python 3.12 so the frozen application can retain its macOS 13 Ventura deployment floor; that packaging choice does not limit normal SUGAR installs from using Python 3.14. Schema, collector, bridge, workspace, or methodology changes should include regression tests and documentation in the same pull request.

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), and [`CHANGELOG.md`](CHANGELOG.md).

## License and institutional status

SUGAR source code and repository documentation are released under the [Apache License 2.0](LICENSE), except for third-party material that carries its own license. See [`NOTICE`](NOTICE) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for attribution and dependency-license information.

SUGAR was developed in connection with Virginia Tech Diplomacy Lab coursework and research. Copyright for this release is identified as **Alejandro Grenier and contributors**; Virginia Tech is not identified as the licensor or copyright holder. References to Virginia Tech or the U.S. Department of State describe project context and do not make SUGAR an official product, endorsement, security authorization, or government publication.

Apache-2.0 permits use, modification, and redistribution, including by government, academic, nonprofit, and commercial users, subject to the license terms. The license does not grant rights to third-party platform content, collected research data, or third-party trademarks.

As provided by Section 6 of Apache-2.0, the license does not grant trademark rights in the SUGAR name, logo, or other project marks beyond reasonable use needed to describe the origin of the software and reproduce required notices.
