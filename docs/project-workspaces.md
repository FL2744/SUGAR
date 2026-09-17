# SUGAR project workspaces

SUGAR 1.2 introduces a persistent project workspace so a research effort can keep its evidence, reference layers, reviewed assessments, maps, reports, and analytic outputs together without collapsing them into one opaque database.

## Design goals

A workspace is intentionally boring and inspectable:

- `sugar-project.json` is the portable project manifest. It contains identity, schema version, description, and canonical directory layout. It must never contain API keys, passwords, cookies, session tokens, or other secrets.
- `sugar-artifacts.json` is the portable artifact catalog. It records the artifact kind, portable path, label, timestamps, metadata, workspace/schema versions, and SUGAR software version needed to interpret the project on another machine.
- `.sugar/workspace.sqlite3` is a local mutable index over that artifact catalog. It is optimized for normal lookup/discovery but is rebuildable from `sugar-artifacts.json` and is not required to preserve the evidentiary record.
- Research products remain ordinary files. CSV, XLSX, JSONL, GeoJSON, HTML, Word, PDF, and other outputs are not hidden inside SQLite.
- Paths inside the workspace are stored relatively so the project directory can be moved between machines. External reference files are allowed but are explicitly reported as external/non-portable artifacts.
- Missing registered files remain visible in workspace status rather than silently disappearing from project history.
- Canonical layout paths must remain inside the project root. SUGAR rejects absolute or `..`-escaping layout entries rather than creating project directories elsewhere on the machine.

## Default layout

Creating a workspace produces:

```text
project/
├── sugar-project.json
├── sugar-artifacts.json
├── .sugar/
│   ├── workspace.sqlite3
│   └── cache/
├── data/
│   ├── raw/
│   └── observations/
├── references/
├── state/
└── outputs/
    ├── maps/
    ├── reports/
    ├── intelligence/
    └── exports/
```

The intent of each directory is stable:

- `data/raw` — collected/normalized source exports and harvest products.
- `data/observations` — `ResearchObservation` datasets derived from source material.
- `references` — American Spaces, EducationUSA, monitored-entity registries, or other attributable comparison layers.
- `state` — State-specific assessment snapshots, review workbooks, audits, query plans, and freshness/gap products.
- `outputs/maps` — rendered research maps.
- `outputs/reports` — Word/PDF/briefing outputs.
- `outputs/intelligence` — deterministic packets, synthesis, hypotheses, tradecraft audits, and longitudinal comparisons.
- `outputs/exports` — other collaboration/export artifacts.
- `.sugar/cache` — project-local caches that can be regenerated.

## Command-line use

Create a workspace:

```bash
sugar-project init ./research --name "Public Diplomacy Research" --description "public-diplomacy research"
```

Inspect it:

```bash
sugar-project status ./team4
sugar-project status ./team4 --json
```

Resolve a canonical directory:

```bash
sugar-project path ./team4 observations
```

Register an output manually when needed:

```bash
sugar-project register ./team4 observations data/observations/example host country.xlsx \
  --label "example host country reviewed observations" \
  --metadata '{"operation":"triage","review_round":1}'
```

List registered files:

```bash
sugar-project list ./team4
sugar-project list ./team4 --kind observations --json
```

Inspect the portable artifact catalog directly:

```bash
sugar-project catalog ./team4
sugar-project catalog ./team4 --json
```

`SugarWorkspace.discover()` locates a workspace by walking upward from a nested project directory. The normal `sugar` and `sugar-state` CLIs use the same behavior, so users working anywhere inside a project normally do not need to repeat `--workspace`.

`--exist-ok` is non-destructive: if a workspace already exists, SUGAR reopens it rather than replacing its project identity or manifest.

## Automatic workflow routing

A workspace is now an active execution context rather than only an artifact catalog. When a normal workflow runs inside a project and an explicit output path is not supplied, SUGAR routes the result to the canonical project directory and registers it automatically.

Current routing is:

| Workflow/product | Default workspace destination |
| --- | --- |
| bounded search, high-volume harvest, Weibo investigation/qualification | `data/raw` |
| general AI triage and spatially enriched observation datasets | `data/observations` |
| monitored-entity and U.S.-presence reference templates | `references` |
| State assessments, review workbooks, audits, rollups, networks, freshness and gap products | `state` |
| general and State research maps | `outputs/maps` |
| analysis Word/PDF products | `outputs/reports` |
| analytic-intelligence packets, synthesis, hypotheses, tradecraft and comparisons | `outputs/intelligence` |
| uncategorized exports | `outputs/exports` |

An explicit `--output` / `--output-stem` remains authoritative. This preserves scripted and standalone workflows while allowing project users to stop hand-assembling directory paths.

Examples from anywhere under the project root:

```bash
sugar harvest "American Space" --sources bilibili,weibo
sugar triage data/raw/social_search_posts_20260914_120000.csv
sugar-state triage data/observations/social_search_posts_20260914_120000_observations.csv
sugar-state map data/observations/social_search_posts_20260914_120000_observations.csv state/state_triage.jsonl
```

The resulting artifacts are registered with an operation name, so desktop and automation flows can discover the latest observations, State assessment snapshot, maps, or intelligence product instead of requiring the user to select every file again.

Workspace discovery skips a newer registered artifact if its file has gone missing and falls back to the most recent existing artifact of that kind. Weibo investigation and qualification products are registered as `raw_collection` artifacts, matching their canonical `data/raw` workspace destination rather than falling through to an uncategorized export.

Desktop State/intelligence operations use the same contract. For example, `state-map` can receive only a workspace when that workspace already has registered `observations` and `state_assessments` artifacts.

## Python API

```python
from sugar_core import SugarWorkspace

workspace = SugarWorkspace.create(
    "team4",
    name="Diplomacy Lab Team 4",
    description="public-diplomacy research",
)

raw_dir = workspace.path_for("raw")
workspace.register_artifact(
    "harvest",
    raw_dir / "weibo_sep14.jsonl",
    metadata={"operation": "harvest"},
)

print(workspace.status())
```

## Desktop bridge

Bridge protocol 3 exposes the workspace primitives:

- `workspace-init`
- `workspace-status`
- `workspace-register`

State/intelligence desktop operations also consume the same workspace implementation. Desktop applications should pass the workspace path and use typed operations rather than reimplementing manifest, artifact-discovery, or SQLite logic.

## Portability and collaboration

The manifest and artifact catalog are designed to travel with the project. Internal artifact paths in `sugar-artifacts.json` are relative to the project root, so moving or copying the entire directory does not require path rewriting. Intentionally external files remain absolute and explicitly marked `external`; if they are unavailable on the destination machine they remain visible as missing rather than being silently discarded.

`.sugar/workspace.sqlite3` is local mutable state and remains ignored by the repository's standard `.gitignore`. If the database is absent after a move, SUGAR automatically recreates it and restores the registered artifacts from `sugar-artifacts.json`. The portable catalog therefore preserves registration of evidence, research requirements, search plans, assessment/review state, limitations, and outputs even when the local SQLite index is not transferred.

Portable handoff bundles created inside a workspace are registered component-by-component rather than only as a ZIP. Their requirement, plan, canonical evidence, observations, review state, limitations, provenance, analytic products, handoff manifest, and archive are consequently visible in the workspace artifact catalog.

Before moving a project between systems, `sugar-project status` should show zero missing artifacts and ideally zero external artifacts unless those references are deliberately machine-specific. After moving it, deleting `.sugar/workspace.sqlite3` is safe from an evidentiary-catalog perspective: opening the workspace rebuilds the index from the portable catalog.

A workspace is not a security boundary. SUGAR still relies on the operating system, approved storage, and normal access controls to protect research data. Credentials remain environment-, Keychain-, or session-managed and must not be placed in the workspace manifest or registry metadata.

## Schema evolution

There are three versioned contracts:

- workspace manifest schema: `1.0`;
- portable artifact catalog schema: `1.0`;
- workspace SQLite schema: `1` (stored in SQLite `PRAGMA user_version`).

SUGAR fails closed when opening an unknown future manifest, portable-catalog, or database schema instead of guessing how to interpret it. Future changes should include an explicit migration path and regression fixtures before any version is advanced.
