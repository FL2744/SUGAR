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
- `.sugar/cache` — project-local caches that can be regenerated.

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

Register an output:

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

`SugarWorkspace.discover()` can locate a workspace by walking upward from a nested project directory. This is useful for future desktop and automation flows where users should not need to re-select the manifest every time.

`--exist-ok` is non-destructive: if a workspace already exists, SUGAR reopens it rather than replacing its project identity or manifest.

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

Bridge protocol 3 adds these typed operations:

- `workspace-init`
- `workspace-status`
- `workspace-register`

They use the same workspace implementation as the Python API and `sugar-project` CLI. Desktop applications should consume these operations rather than reimplementing manifest or SQLite logic.

## Portability and collaboration

The manifest is designed to be safe to share with the rest of a research team. The SQLite registry is local mutable metadata by default and is ignored by the repository's standard `.gitignore`; a team can still transfer it deliberately when that is appropriate. It may contain paths to intentionally external files.

Before moving a project between systems, `sugar-project status` should show zero missing artifacts and ideally zero external artifacts unless those references are deliberately machine-specific.

A workspace is not a security boundary. SUGAR still relies on the operating system, approved storage, and normal access controls to protect research data. Credentials remain environment-, Keychain-, or session-managed and must not be placed in the workspace manifest or registry metadata.

## Schema evolution

There are two versioned contracts:

- workspace manifest schema: `1.0`;
- workspace SQLite schema: `1` (stored in SQLite `PRAGMA user_version`).

SUGAR fails closed when opening an unknown future manifest schema or database schema instead of guessing how to interpret it. Future changes should include an explicit migration path and regression fixtures before either version is advanced.
