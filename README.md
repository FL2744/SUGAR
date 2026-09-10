![sugar logo](sugar-logo.png)

# SUGAR

**System for User-Generated Content Gathering, Analysis, and Representation**

SUGAR is a research pipeline for repeatable collection, normalization, AI-assisted enrichment, mapping, and descriptive analysis of public digital content. The current supported core collects from X, Bluesky, and Mastodon and is being developed for Virginia Tech Diplomacy Lab work on public diplomacy and cultural-influence networks.

## Stable architecture

The supported implementation lives in `sugar_core/`. The original `SUGAR.py` monolith is retained as the historical prototype, but new work should target the stable package.

The pipeline is:

**Collect → Normalize → AI enrich/triage → Human review → Dataset → Map/analysis → Refresh**

The stable schema is platform-neutral. It records native IDs, canonical URLs, authors, publication and collection times, original text, language, query provenance, canonical engagement metrics, location evidence, collector/schema versions, and raw platform metrics. Backward-compatible aliases are still exported for older SUGAR workbooks.

## Installation

Python 3.11–3.13 is supported.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For development/testing:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

SUGAR never installs or upgrades packages at runtime.

## ARC / Open OnDemand

On Virginia Tech ARC, create/activate a virtual environment in your project space, install the repository once, and run the same CLI. The stable analysis path contains no hard-coded macOS font dependency.

ARC's OpenAI-compatible LLM endpoint is supported with provider `arc`. Supply a personal ARC API key through `SUGAR_LLM_API_KEY` or the macOS application's Keychain-backed settings.

## CLI examples

Search X with translation/location enrichment:

```bash
export SUGAR_X_BEARER_TOKEN='...'
export SUGAR_LLM_API_KEY='...'
python -m sugar_core search "Confucius Institute" --sources x --since 2026-01-01 --until 2026-09-10
```

Use Virginia Tech ARC for enrichment:

```bash
python -m sugar_core search "孔子学院" --sources x,bluesky \
  --provider arc --model gpt-oss-120b --since 2026-01-01 --until 2026-09-10
```

Collection without LLM enrichment:

```bash
python -m sugar_core search "democracy" --sources bluesky --no-translate --no-location
```

Create a map from an existing SUGAR CSV/XLSX:

```bash
python -m sugar_core map social_search_posts_YYYYMMDD_HHMMSS.csv
```

Create deterministic Word/PDF analysis:

```bash
python -m sugar_core analysis social_search_posts_YYYYMMDD_HHMMSS.csv --format both
```

## Credentials

Credentials are never committed to the repository or written into result files. Supported environment variables are:

- `SUGAR_X_BEARER_TOKEN`
- `SUGAR_LLM_API_KEY`
- `SUGAR_BLUESKY_IDENTIFIER`
- `SUGAR_BLUESKY_APP_PASSWORD`
- `SUGAR_MASTODON_TOKEN`

The native macOS application stores these in macOS Keychain and passes them to the bundled backend only for execution.

## Collection semantics

### X

SUGAR uses X API v2 recent or full-archive search. Full archive depends on the account's X API access/billing. Selected language filters are added to the X query. Start and end dates are inclusive.

### Bluesky

SUGAR uses `app.bsky.feed.searchPosts` through the public AppView or, when credentials are supplied, an authenticated PDS proxy. Query syntax/coverage are not assumed to be equivalent to X.

### Mastodon

Mastodon search is instance-scoped, not a global Fediverse index. Search coverage depends on the selected server and its indexing settings. Favorites, replies, and reblogs are mapped into SUGAR's canonical engagement fields for cross-platform analysis.

## Provenance and deduplication

One content object can match multiple queries. SUGAR stores a single normalized record while preserving every matching query in `query_matches`. This prevents deduplication from silently destroying search provenance.

Every export also records the collection time, collector version, schema version, source URL, raw metrics, and a run-level `.metadata.json` sidecar.

## AI enrichment

LLM enrichment is optional. Source text is treated as untrusted data and is separated from model instructions. Location inference is broad and exploratory: SUGAR will not choose a country from language alone and does not infer private or street-level locations.

LLM and geocoding results are cached under `.sugar-cache/` so reruns can reuse deterministic prior work and reduce cost.

## Outputs

A search writes:

- `social_search_posts_<timestamp>.csv`
- `social_search_posts_<timestamp>.xlsx`
- `social_search_posts_<timestamp>.metadata.json`

Mapping writes an interactive HTML file. Analysis writes DOCX and/or PDF reports from an existing CSV/XLSX without rerunning collection.

## Native macOS application

`SUGAR-macOS/` provides the SwiftUI UI. Its backend is `sugar_bridge.py`, which now calls `sugar_core` rather than importing the legacy monolith. Existing build/sign/notarization scripts remain under `SUGAR-macOS/scripts/`.

## Development rule

Do not add another platform by adding another large function to `SUGAR.py`. New collectors should normalize into `sugar_core.models.PostRecord`, preserve native/raw fields, and include tests for pagination, date semantics, deduplication/provenance, and engagement normalization.

See `STABILIZATION.md` for the v1.1 stabilization baseline.
