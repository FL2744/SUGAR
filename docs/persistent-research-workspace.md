# Persistent research workspaces

SUGAR projects now preserve analyst workflow state in addition to evidence artifacts. The portable file `sugar-research.json` sits beside `sugar-project.json` and `sugar-artifacts.json`; local SQLite remains rebuildable runtime state.

## What persists

- **Subprojects** — nested research tracks inside one project, with status and tags.
- **Search history** — executed quick searches and approved research-plan branches, including terms, sources, timestamps, result counts, coverage state, and requirement context.
- **Listening posts** — reusable monitored query sets that can be rerun through the normal collection pipeline. Runs feed new evidence and search history back into the same project.
- **Reference layers** — reusable CSV, Excel, JSON, JSONL, or GeoJSON datasets for institutions, sites, events, boundaries, or custom map context.
- **Collaboration metadata** — named project participants/review roles without storing credentials.
- **Conversation products** — readable thread views that preserve distinct handles/speakers and explicit reply relationships.

The public SUGAR engine remains target-neutral. Project-specific target lists—such as a comprehensive Confucius Institute/Center registry—belong in project reference data rather than being hard-coded into the application.

## Institution lifecycle data

The monitored-entity schema supports:

- `active`
- `closed`
- `renamed`
- `relocated`
- `planned`
- `unknown`

Institution records can also store opening/closure dates, coordinates, handles, source references, aliases, parent entities, and notes. Historical institutions should be retained rather than deleted. A closed site on a reference map is a historical fact, not evidence that related personnel, programs, partnerships, narratives, or online activity disappeared.

The reference-map product uses a distinct closed-site symbol by default and preserves source links in the popup when supplied.

## Reference layers and maps

In the Windows workbench, drop one or more supported datasets into **Research Project → Project workspace → Reference layers**. macOS supports multi-file layer selection from the same research-project workflow.

Common fields are detected automatically:

- name: `canonical_name`, `name`, `institution`, `title`, `site_name`
- latitude: `latitude`, `lat`, `y`
- longitude: `longitude`, `lon`, `lng`, `x`
- lifecycle: `lifecycle_status`, `status`, `state`

A custom field mapping can be stored with a layer when the dataset uses different names.

Reference maps are descriptive. A point, density, or proximity does not by itself establish coordination, competition, reach, or influence.

## Listening posts

A listening post stores a name, source set, query terms or watched entities, cadence label, subproject, and run history. Running a post reuses SUGAR's normal collectors and therefore preserves the same provenance, access limitations, normalization, and project search history as an ordinary collection.

Cadence is stored as project intent. SUGAR does not silently create an operating-system background service; analysts can rerun a post from the desktop or automate the CLI in an authorized environment.

## Conversations

`workspace-conversation-view` turns supported project records into an HTML dialogue view. SUGAR keeps authors/handles visually separate and orders records from explicit reply/thread relationships plus timestamps where those fields are available. It does not infer private identity behind public handles.

## Whole-project sharing

Evidence handoffs and project sharing serve different purposes:

- **Research handoff** packages the evidence and analytic context needed for a reviewable research product.
- **Project share** transfers the continuing workspace itself, including project state, search history, subprojects, reference layers, and ordinary portable project files.

Project-share ZIPs include SHA-256 hashes and can be verified before import. The local `.sugar` runtime directory and runtime credentials are excluded. External files remain external unless explicitly included.

### CLI examples

```bash
sugar-project research-status ./team4 --json

sugar-project subproject-add ./team4 "Kyrgyzstan" \
  --tag institutions --tag central-asia

sugar-project listening-add ./team4 "Institution watch" \
  --term "Confucius Institute" \
  --term "孔子学院" \
  --source weibo \
  --source bilibili \
  --cadence weekly

sugar-project layer-add ./team4 ./reference-data/institutions.csv \
  --name "Institution registry" \
  --type institution

sugar-project share-export ./team4 ./team4-share.zip
sugar-project share-verify ./team4-share.zip
sugar-project share-import ./team4-share.zip ./imports
```

## Recommended institutional reference columns

For comprehensive institution lists, use at least:

```text
entity_id
canonical_name
entity_type
aliases
native_names
country
city
parent_entity_id
official_urls
social_urls
languages
query_terms
priority
active
lifecycle_status
opened_at
closed_at
latitude
longitude
handles
source_refs
notes
```

The structured data should remain inspectable and exportable; maps are a view over the data, not a replacement for it.
