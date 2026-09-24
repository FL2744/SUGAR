# Persistent research workspace

SUGAR's base workspace keeps project identity, artifacts, and reproducibility metadata. The research-workspace layer adds the analyst-facing memory requested for recurring public-diplomacy research without changing the underlying evidence model.

## What is portable

A project can now retain:

- nested subprojects or research tracks;
- lifecycle-aware institution/entity records;
- arbitrary CSV, JSONL, JSON/GeoJSON, or XLSX reference layers;
- saved listening-post definitions;
- search history with terms, sources, filters, result counts, and outputs;
- collaborator/reviewer role metadata;
- saved views;
- conversation/thread products;
- generated project maps;
- portable project-share bundles.

The portable state lives in `sugar-research.json`. The existing `sugar-project.json` remains the workspace identity/layout manifest and `sugar-artifacts.json` remains the portable artifact catalog.

Runtime credentials are never stored in the project state.

## Subprojects

Subprojects are lightweight organizational tracks inside one workspace. They can represent a country, institution, program, or analytic question and may be nested through `parent_id`.

```bash
sugar-project subproject-add ./team4 "Kyrgyzstan" --tags "Central Asia"
sugar-project subproject-add ./team4 "AUCA" --parent-id <subproject-id>
```

Subprojects do not duplicate evidence. They provide a durable scope label for monitoring, reference layers, search history, and outputs.

## Institution registry

Institution records preserve more than a current yes/no presence. Supported lifecycle states are:

- `active`
- `closed`
- `renamed`
- `relocated`
- `planned`
- `unknown`

Records may also retain aliases, country/city/address, coordinates, opening/closure dates, parent/successor IDs, official URLs, public social handles, source URLs, and analyst notes.

Import accepts CSV, JSONL, JSON/GeoJSON, and XLSX:

```bash
sugar-project institutions-import ./team4 ./references/institutions.xlsx
```

Common column names are accepted (for example `name` or `canonical_name`, `lat` or `latitude`, and `lon`/`lng`/`longitude`). Rows that cannot be parsed are rejected explicitly rather than silently fabricated.

A sponsor/case-specific institution master list should normally remain project data. The public engine provides the schema and workflow rather than hard-coding one research target.

## Reference layers

Reference layers are ordinary structured files that can be added to a project and displayed independently on the project map.

```bash
sugar-project layer-add ./team4 american-spaces.xlsx --name "American Spaces"
sugar-project layer-add ./team4 universities.geojson --name "Universities"
```

By default SUGAR copies the file into `references/layers/` so project sharing remains portable. The `--external` option records an external reference instead when copying is undesirable.

On Windows, file/path fields accept drag-and-drop as well as the file picker.

## Project map

```bash
sugar-project map ./team4
```

The project map combines lifecycle-aware institution records with all selected reference layers. Closed institutions remain visible by default and use a distinct skull marker (`☠`); other institution states use a separate marker. Every imported reference layer appears as an independently toggleable layer.

This map is a research interface and reference display. Presence, density, and geographic proximity do not constitute an influence measure or causal finding.

## Search history

Normal `sugar search` collection performed inside a workspace now records:

- exact search terms;
- requested sources;
- date bounds;
- per-query/page limits;
- result count;
- generated outputs;
- subproject ID, when supplied;
- listening-post ID, when applicable.

Search the history with:

```bash
sugar-project history ./team4 --query "Bishkek"
```

This history is in addition to the existing search-plan audit history. The two answer different questions: the plan records the analytic/search strategy; project history records what collection was actually run.

## Listening posts

A listening post is a saved monitoring definition made from terms, public handles, and/or linked institution IDs.

```bash
sugar-project listening-add ./team4 "Kyrgyzstan watch" \
  --terms "cultural exchange;language program" \
  --sources "bilibili,weibo" \
  --cadence weekly
```

Run it explicitly with:

```bash
sugar-project listening-run ./team4 <listening-post-id>
```

A run reuses SUGAR's normal collectors, provenance, coverage handling, and access boundaries. It produces ordinary collection artifacts plus a delta file containing newly observed record identities relative to the previous run.

The stored cadence is analyst intent/project metadata. SUGAR does not silently manufacture authentication, evade platform limits, or bypass access controls.

## Conversation view

Platforms that provide conversation, thread, and parent/reply relationships can be rendered without flattening different speakers together:

```bash
sugar-project conversations ./team4 ./data/raw/social_search_posts.csv
```

The output HTML shows each public handle/name separately and indents replies according to known parent ancestry. A JSON companion preserves the structured thread representation.

## Sharing

```bash
sugar-project share ./team4
```

creates a `.sugarproject.zip` containing project-local portable files plus SHA-256 integrity hashes. The bundle excludes:

- runtime credentials;
- `.sugar/workspace.sqlite3` (rebuildable);
- cache files;
- project-external artifacts.

Import and verify a shared project with:

```bash
sugar-project share-import team4.sugarproject.zip ./team4-imported
```

Paths are validated before extraction and every included file is checked against its recorded hash before the workspace is opened.

## End-user support

Run:

```bash
sugar-project help-workflows
```

for embedded workflow guidance. Windows exposes the same guidance from the Projects page; macOS exposes it from Research Project.

The intent is that a receiving analyst can understand the project structure, rerun searches, inspect institution/reference data, monitor saved targets, reconstruct conversations, and share the complete research context without needing the original developer present.
