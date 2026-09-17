# SUGAR project workspaces

SUGAR 1.2 introduces a persistent project workspace so a research effort can keep its evidence, reference layers, reviewed assessments, maps, reports, and analytic outputs together without collapsing them into one opaque database.

## Design goals

A workspace is intentionally boring and inspectable:

- `sugar-project.json` is the portable project manifest. It contains identity, schema version, description, and canonical directory layout. It must never contain API keys, passwords, cookies, session tokens, or other secrets.
- `.sugar/workspace.sqlite3` is a local artifact registry. It tracks which files belong to the project, their artifact type, labels, timestamps, and small JSON metadata records.
- Research products remain ordinary files. CSV, XLSX, JSONL, GeoJSON, HTML, Word, PDF, and other outputs are not hidden inside SQLite.
- Paths inside the workspace are stored relatively so the project directory can be moved between machines. External reference files are allowed but are explicitly reported as external/non-portable artifacts.
- Missing registered files remain visible in workspace status rather than silently disappearing from project history.
- Canonical layout paths must remain inside the project root. SUGAR rejects absolute or `..`-escaping layout entries rather than creating project directories elsewhere on the machine.

## Default layout

Creating a workspace produces:

```text
project/
├── sugar-project.json
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
- `.sugar/cache` — project-local public-provider caches that can be regenerated. LLM prompts and
  responses are intentionally kept in process memory and are not written here.

## Command-line use

Create a workspace:

```bash
sugar-project init ./team4 --name "Diplomacy Lab Team 4" --description "PRC public-diplomacy research"
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
sugar-project register ./team4 observations data/observations/kyrgyzstan.xlsx \
  --label "Kyrgyzstan reviewed observations" \
  --metadata '{"operation":"triage","review_round":1}'
```

List registered files:

```bash
sugar-project list ./team4
sugar-project list ./team4 --kind observations --json
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

Desktop State/intelligence operations use the same contract. For example, `state-map` can receive only a workspace when that workspace already has registered `observations` and `state_assessments` artifacts.

## Python API

```python
from sugar_core import SugarWorkspace

workspace = SugarWorkspace.create(
    "team4",
    name="Diplomacy Lab Team 4",
    description="PRC public-diplomacy research",
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

The manifest is designed to be safe to share with the rest of a research team. The SQLite registry is local mutable metadata by default and is ignored by the repository's standard `.gitignore`; a team can still transfer it deliberately when that is appropriate. It may contain paths to intentionally external files.

Before moving a project between systems, `sugar-project status` should show zero missing artifacts and ideally zero external artifacts unless those references are deliberately machine-specific.

A workspace is not a security boundary. SUGAR still relies on the operating system, approved storage, and normal access controls to protect research data. Credentials remain environment-, Keychain-, or session-managed and must not be placed in the workspace manifest or registry metadata.

## Portable project archives

Use `sugar-project archive PROJECT ARCHIVE.sugar.zip` to create a versioned ZIP containing the
manifest, workspace registry, and all project-contained files. The archive is written atomically and
uses stable member ordering/timestamps so two unchanged workspaces produce comparable archives.
External artifact references are retained as external registry entries but their files are not copied;
keep the archive and any referenced external sources under the same approved data-handling controls.

Use `sugar-project restore ARCHIVE.sugar.zip NEW_PROJECT` to validate the archive in a staging directory
before publishing it. Unsafe member paths, duplicate entries, mismatched file manifests, oversized
archives, unsupported archive versions, and invalid workspace schemas fail closed. A restore never
overwrites an existing destination. After restoring, run `sugar-project status NEW_PROJECT --json` and
re-run the documented pipeline from the portable inputs to verify analytical reproducibility.

When SUGAR opens a legacy SQLite artifact registry that needs a schema migration, it first creates
an atomic pre-migration copy under `.sugar/migration-backups/`. The backup is retained for recovery
and is reported by `sugar-project status`; if backup creation fails, migration stops before changing
the database.

## Schema evolution

There are two versioned contracts:

- workspace manifest schema: `1.0`;
- workspace SQLite schema: `1` (stored in SQLite `PRAGMA user_version`).

SUGAR fails closed when opening an unknown future manifest schema or database schema instead of guessing how to interpret it. Future changes should include an explicit migration path and regression fixtures before either version is advanced.
