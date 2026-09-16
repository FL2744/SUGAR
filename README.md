![SUGAR logo](sugar-logo.png)

# SUGAR

**System for User-Generated Content Gathering, Analysis, and Representation**

SUGAR is a cross-platform public-source research system for collecting social-media material, preserving provenance, organizing evidence, conducting spatial and structured analysis, and producing reviewable research products. It is developed for Virginia Tech Diplomacy Lab work on public diplomacy and PRC-supported cultural/public-engagement networks, while the core remains platform-neutral.

Current classroom-preview package version: **1.3.0rc1**.

> **Desktop users do not need to install Python.** The packaged macOS application and single-file Windows `SUGAR.exe` include the SUGAR backend. Python 3.11–3.13 is required only for CLI/development use.

For the September 2026 classroom usability preview, start with [`docs/classroom-preview.md`](docs/classroom-preview.md).

## What SUGAR does

SUGAR provides one shared Python research core with native macOS and Windows clients. The supported pipeline is:

**Collect/import → Normalize → Enrich/triage → Human review → Evidence dataset → Spatial/analytic products → Refresh**

The core supports X, Bluesky, Mastodon, Bilibili, Weibo, WeChat Official Account public-article import, Zhihu official keyword search/public-URL import, and Douyin public-URL import. Source capabilities are intentionally explicit: SUGAR does not pretend that every platform offers equivalent search, comments, or anonymous-access surfaces.

SUGAR deliberately distinguishes **presence, activity, reach, engagement, outcomes, and causal influence**. It does not manufacture a universal influence score or treat collection density as influence.

## Entry points

| Surface | Purpose |
| --- | --- |
| `SUGAR-macOS/` | Native SwiftUI application for macOS 13+; bundled backend and classroom samples |
| `SUGAR-Windows/` | Single-file PySide6 research workbench; bundled backend worker |
| `sugar` | General keyword collection, harvest, overlap, mapping, and reporting CLI |
| `sugar-import` | Known public item/URL import through registered platform adapters |
| `sugar-project` | Persistent project-workspace management |
| `sugar-state` | State/Diplomacy Lab evidence-to-brief workflow |
| `sugar-intel` | Structured analytic-intelligence workflow |
| `sugar_bridge.py` | Typed line-delimited JSON process boundary used by desktop clients |

Both desktop applications call the same `sugar_core` implementation. Collection semantics, evidence rules, assessment logic, maps, and synthesis should not be reimplemented in individual frontends.

## Classroom preview / desktop use

### macOS

The packaged macOS application requires **macOS 13 Ventura or newer**. It includes its Python backend and sample spreadsheet/map/report, so a new tester can launch SUGAR and try map/report workflows without configuring credentials. The classroom CI build is architecture-specific and may be unsigned/not notarized; use only a build distributed by the project team. Do not disable macOS security protections globally as a workaround.

The Welcome screen links to the classroom testing guide and GitHub usability-feedback form. Every packaged classroom build includes build information tying it to its Git commit.

See [`SUGAR-macOS/README.md`](SUGAR-macOS/README.md) for compatibility, packaging, signing, and troubleshooting.

### Windows

The Windows classroom build is a **single downloadable `SUGAR.exe`**. Ordinary users do not need Python, do not extract a ZIP, and do not manage a separate backend executable. The frozen backend worker is embedded inside `SUGAR.exe` and is extracted privately at runtime so collection/analysis can remain cancellable without complicating installation.

Development/CI builds are unsigned and may trigger SmartScreen; production distribution should use normal Authenticode signing rather than weakening endpoint protections. Use the canonical GitHub artifact/release location rather than copied binaries whose source revision cannot be established.

See [`SUGAR-Windows/README.md`](SUGAR-Windows/README.md).

## Python / CLI installation

For developers and command-line users, Python **3.11–3.13** is supported:

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

## Collection and public-item import

| Source | Keyword search | Known public item / URL | Comments | Access notes |
| --- | --- | --- | --- | --- |
| X | yes | — | — | API v2 credential required |
| Bluesky | yes | — | — | Public AppView; optional authenticated PDS path |
| Mastodon | yes | — | — | Instance-scoped; token optional where instance permits |
| Bilibili | yes | yes | yes | Public surfaces, fail closed when unavailable |
| Weibo | yes, availability varies | yes | yes | Anonymous public surfaces and optional legitimate existing session |
| WeChat Official Accounts | no general search claimed | yes | no | Known public `mp.weixin.qq.com` article URLs only |
| Zhihu | yes | yes | no | Keyword search uses approved Zhihu Open Platform Access Secret; known public URLs can be imported separately |
| Douyin | no general search claimed | yes | no | Known public/share URLs only when an ordinary public page exposes defensible metadata |

All collectors normalize into the shared `PostRecord` model. SUGAR preserves stable native IDs, canonical URLs, collection/published times, query matches, canonical engagement fields where defensible, raw platform metrics, source mode, and schema/collector versions.

Known-public-item import deliberately remains separate from keyword search:

```bash
sugar-import wechat "https://mp.weixin.qq.com/s/..." --output ./runs/wechat
sugar-import zhihu "https://www.zhihu.com/question/.../answer/..." --output ./runs/zhihu
sugar-import douyin "https://www.douyin.com/video/..." --output ./runs/douyin
```

The desktop bridge exposes the same workflow as **Public URL Import**. If a platform redirects to an unrelated host, presents a verification/CAPTCHA/access gate, or returns insufficient public evidence, SUGAR fails explicitly rather than bypassing the gate or recording zero activity.

### High-volume harvesting

`harvest` is the durable collection path for thousands or tens of thousands of records on collectors that actually expose keyword/paged collection. It decomposes work into deterministic tasks, checkpoints completed work to SQLite, resumes without recollection, records rate-limit/defer events, and separates raw collection from later AI processing.

```bash
sugar harvest \
  --sources bilibili,weibo \
  --terms-file csm_terms_zh.txt \
  --target 10000 \
  --output ./runs/csm_sep14 \
  --name csm_sep14
```

See [`docs/high-volume-harvest.md`](docs/high-volume-harvest.md).

## Project workspaces

A workspace keeps a portable `sugar-project.json` manifest, a local `.sugar/workspace.sqlite3` artifact registry, and standardized locations for raw collection, research observations, reference layers, State assessments, maps, reports, and intelligence outputs.

```bash
sugar-project init ./team4 \
  --name "Diplomacy Lab Team 4" \
  --description "PRC public-diplomacy research"

sugar-project status ./team4
sugar-project path ./team4 observations
sugar-project register ./team4 observations data/observations/kyrgyzstan.xlsx
```

Research files remain ordinary CSV/XLSX/JSONL/GeoJSON/HTML/Word/PDF files rather than being hidden inside the project database. Secrets are never stored in the workspace manifest or registry by SUGAR.

See [`docs/project-workspaces.md`](docs/project-workspaces.md).

## State / Diplomacy Lab workflow

The `sugar-state` suite keeps source-grounded `ResearchObservation` evidence separate from sponsor-specific `StateAssessment` judgments. It supports monitored entities/query plans, strategic-audience/program-domain/narrative coding, explicit support evidence, guarded AI triage followed by human review, source-conflict adjudication, American Spaces/EducationUSA comparison, evidence auditing, verified-only products, freshness/change detection, and research-gap prioritization.

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

LLM enrichment and triage are optional. A collection can run without an LLM key when translation, translated query expansion, and location inference are off. Source text is treated as untrusted data and separated from model instructions. SUGAR does not infer a country from language alone and does not infer private/street-level locations.

For State-specific analysis, AI cannot self-verify evidence, confirm support, invent acceptable evidence references, or establish causal influence. High-consequence claims remain subject to explicit evidence and human review.

Supported LLM configuration includes OpenAI-compatible providers and Virginia Tech ARC. Credentials are supplied at runtime; they must not be committed to the repository or inserted into project manifests.

## Research and access boundaries

SUGAR is designed for ordinary public or explicitly authorized access. It does **not** solve CAPTCHAs, manufacture authentication/session state, spoof devices, rotate proxies/accounts to evade limits, reproduce anti-bot signatures to defeat access controls, or bypass platform restrictions. When a source denies access, requires unsupported login/verification, or rate-limits collection, the collector must fail or defer explicitly rather than converting that failure into evidence of zero activity.

The State workflow is a research methodology and product for the Diplomacy Lab project. It is not a Department of State security authorization, ATO, official intelligence product, procurement approval, or AI certification.

## Repository architecture

The supported implementation lives in `sugar_core/`. Historical pre-package monoliths have been removed from the working tree; Git history remains the source of truth for prior migrations.

See [`docs/architecture.md`](docs/architecture.md) for module boundaries, frontend/core dependency rules, bridge architecture, and test expectations.

## Documentation

- [`docs/classroom-preview.md`](docs/classroom-preview.md) — classroom usability test and zero-credential starting path
- [`docs/architecture.md`](docs/architecture.md) — current system architecture and engineering rules
- [`docs/project-workspaces.md`](docs/project-workspaces.md) — persistent project-workspace contract
- [`docs/collector-interface.md`](docs/collector-interface.md) — collector capabilities and normalization contract
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

## Development and contribution

Before opening a pull request:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

CI runs the Python suite on Ubuntu, macOS, and Windows with Python 3.11–3.13 and separately builds/smoke-tests the packaged macOS and Windows applications. Classroom CI publishes validated macOS and single-executable Windows artifacts from the same Git source revision so testers can identify exactly which build they used.

See [`CONTRIBUTING.md`](CONTRIBUTING.md), [`SECURITY.md`](SECURITY.md), and [`CHANGELOG.md`](CHANGELOG.md).
