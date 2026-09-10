![sugar logo](sugar-logo.png)

# SUGAR

**System for User-Generated Content Gathering, Analysis, and Representation**

SUGAR helps researchers collect public social-media content, organize and translate it, infer broad geographic context, build maps, and create descriptive analytical reports. It is being developed for Virginia Tech Diplomacy Lab work on public diplomacy and cultural-influence networks.

The current supported sources are **X, Bluesky, and Mastodon**. SUGAR can be used through the native macOS app or from the Python command line.

## Quick start for macOS users

If you received a SUGAR `.app` or `.dmg` build from the project team, you do **not** need to install Python or use Terminal.

### 1. Check your Mac first

The current SUGAR GUI requires **macOS 13 Ventura or newer**.

To check:

1. Open the Apple menu.
2. Choose **About This Mac**.
3. Note your **macOS version**.
4. Note whether the machine uses an **Apple chip** (M1, M2, M3, M4, etc.) or an **Intel processor**.

If SUGAR does not launch, include both of those details when reporting the problem. Architecture compatibility is still being tested across team machines, so do not assume that an app build produced on one Mac will necessarily work on every Intel and Apple Silicon Mac.

### 2. Open SUGAR

Open the supplied SUGAR application normally.

Some development/test builds are not publicly notarized. If macOS says that the developer cannot be verified or blocks the app, only override that warning if the copy came from a trusted project source. If you are unsure, stop and ask the project maintainer rather than bypassing the warning.

### 3. Enter credentials if your task requires them

Open **Settings** inside SUGAR. Credentials entered in the macOS app are stored in macOS Keychain rather than in the project folder.

| What you want to do | What you may need |
| --- | --- |
| Search X | X API bearer token |
| Search Bluesky public results | No Bluesky login is required for the public search path |
| Use authenticated Bluesky search | Bluesky identifier + app password |
| Search Mastodon | Depends on the server; a token may improve or enable search behavior |
| Translate or infer locations with an LLM | OpenAI, Virginia Tech ARC, or compatible API key |
| Map an existing SUGAR CSV/XLSX | No social-media API credential |
| Analyze an existing SUGAR CSV/XLSX | No social-media API credential |

### 4. Run your first search

Open **Search** and:

1. Choose one or more sources: **X**, **Bluesky**, or **Mastodon**.
2. Enter one or more search terms, separated by commas.
3. Optionally set a start and end date in `YYYY-MM-DD` format.
4. Choose how many posts/pages you want to request.
5. Turn translation, location inference, and repost inclusion on or off as needed.
6. Choose an output folder.
7. Click **Run Search**.

The **Activity** panel at the bottom of the app shows whether SUGAR is running and lists generated output files when the task finishes.

### 5. Work with the results

A normal search can create:

- `social_search_posts_<timestamp>.csv` — plain tabular results.
- `social_search_posts_<timestamp>.xlsx` — Excel version of the same results.
- `social_search_posts_<timestamp>.metadata.json` — run metadata and provenance information.

Use the **Map** tab to create an interactive HTML map from an existing CSV/XLSX file.

Use the **Analysis** tab to create Word and/or PDF descriptive reports from an existing CSV/XLSX file. Mapping and analysis do not rerun social-media collection.

## Troubleshooting

### SUGAR will not open at all

First collect these three details:

- Mac model/chip: Apple Silicon or Intel.
- macOS version.
- Exact message shown by macOS, or what happens when you click the app.

Examples of useful reports:

`2020 MacBook Pro — Intel — macOS 13.7 — icon bounces once and closes`

`MacBook Air M2 — macOS 15.6 — "developer cannot be verified"`

That information is much more useful than reporting only that "SUGAR does not work."

### macOS says the system version is unsupported

The current native GUI declares **macOS 13.0 or newer** as its minimum. macOS 12 Monterey and older are not currently supported by the GUI build.

### macOS says the developer cannot be verified

This usually indicates a signing/notarization issue with a development build rather than a SUGAR data-processing error. Confirm that the app came from the project team before overriding any Gatekeeper warning.

### The app opens, but a search fails

Check the **Activity** panel and copy the error message. Common causes include:

- missing or invalid API credentials;
- X API access, billing, or rate-limit restrictions;
- source-specific search limitations;
- network connectivity problems;
- the bundled backend failing to start.

When reporting the problem, include the source you were searching, whether the app itself opened successfully, and the exact error text. Do **not** send API keys or passwords in a bug report.

### The search runs but returns no posts

A zero-result search does not always mean SUGAR is broken. Search coverage differs by platform:

- X results depend on the API tier and whether recent or full-archive search is available.
- Bluesky search coverage and query behavior are not identical to X.
- Mastodon search is server/instance scoped and is not a complete global Fediverse search.

Try a broader query and verify that the target platform itself contains recent public material matching the term.

### I do not know where the output went

The Search screen lets you choose an output directory. Completed files are also listed in the **Activity** panel. The Map and Analysis screens allow you to choose their output paths separately.

### I am reporting a launch problem to the team

Please include:

1. Mac model or chip.
2. macOS version.
3. Whether the SUGAR window ever appears.
4. Exact warning/error text.
5. Whether the failure occurs at launch or only after clicking **Run Search**, **Create Map**, or **Create Analysis**.

Do not include credentials, tokens, passwords, or other secrets.

## What SUGAR is doing under the hood

The supported implementation lives in `sugar_core/`. The original `SUGAR.py` monolith is retained as the historical prototype, but new work should target the stable package.

The research pipeline is:

**Collect → Normalize → AI enrich/triage → Human review → Dataset → Map/analysis → Refresh**

The stable schema is platform-neutral. It records native IDs, canonical URLs, authors, publication and collection times, original text, language, query provenance, canonical engagement metrics, location evidence, collector/schema versions, and raw platform metrics. Backward-compatible aliases are still exported for older SUGAR workbooks.

## Collection behavior

### X

SUGAR uses X API v2 recent or full-archive search. Full archive depends on the account's X API access/billing. Selected language filters are added to the X query. Start and end dates are inclusive.

### Bluesky

SUGAR uses `app.bsky.feed.searchPosts` through the public AppView or, when credentials are supplied, an authenticated PDS proxy. Query syntax and coverage are not assumed to be equivalent to X.

### Mastodon

Mastodon search is instance-scoped, not a global Fediverse index. Search coverage depends on the selected server and its indexing settings. Favorites, replies, and reblogs are mapped into SUGAR's canonical engagement fields for cross-platform analysis.

## AI enrichment

LLM enrichment is optional. Source text is treated as untrusted data and is separated from model instructions. Location inference is broad and exploratory: SUGAR will not choose a country from language alone and does not infer private or street-level locations.

LLM and geocoding results are cached under `.sugar-cache/` so reruns can reuse prior work and reduce cost.

## Provenance and deduplication

One content object can match multiple queries. SUGAR stores a single normalized record while preserving every matching query in `query_matches`. This prevents deduplication from silently destroying search provenance.

Every export also records the collection time, collector version, schema version, source URL, raw metrics, and a run-level `.metadata.json` sidecar.

## Command-line installation

The sections below are for developers, ARC users, and anyone intentionally running SUGAR from Python rather than the macOS GUI.

Python **3.11–3.13** is supported.

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

Collect without LLM enrichment:

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

## Virginia Tech ARC / Open OnDemand

On Virginia Tech ARC, create and activate a virtual environment in your project space, install the repository once, and run the same CLI. The stable analysis path contains no hard-coded macOS font dependency.

ARC's OpenAI-compatible LLM endpoint is supported with provider `arc`. Supply a personal ARC API key through `SUGAR_LLM_API_KEY` or the macOS application's Keychain-backed settings.

## Credentials for command-line use

Credentials are never committed to the repository or written into result files. Supported environment variables are:

- `SUGAR_X_BEARER_TOKEN`
- `SUGAR_LLM_API_KEY`
- `SUGAR_BLUESKY_IDENTIFIER`
- `SUGAR_BLUESKY_APP_PASSWORD`
- `SUGAR_MASTODON_TOKEN`

The native macOS application stores these in macOS Keychain and passes them to the bundled backend only for execution.

## Native macOS application development

`SUGAR-macOS/` contains the SwiftUI UI. Its backend is `sugar_bridge.py`, which calls `sugar_core`. Build, signing, packaging, and notarization scripts live under `SUGAR-macOS/scripts/`.

The current GUI deployment target is macOS 13.0. Before claiming wider architecture or older-macOS compatibility for a release, test the packaged application and bundled backend on the intended target machines.

See `SUGAR-macOS/README.md` for build and distribution details.

## Contributing

Please keep changes reviewable and preserve the research/provenance guarantees in the stable core.

Do not add another platform by adding another large function to `SUGAR.py`. New collectors should normalize into `sugar_core.models.PostRecord`, preserve native/raw fields, and include tests for pagination, date semantics, deduplication/provenance, and engagement normalization.

For larger architectural changes, prefer a focused design discussion or staged pull requests rather than replacing multiple components at once.

See `STABILIZATION.md` for the v1.1 stabilization baseline.
