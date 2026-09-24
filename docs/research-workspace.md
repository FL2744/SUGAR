# Persistent research workspace

SUGAR's Research Workspace combines persistent project memory, evidence-backed reference entities, inspectable datasets, reusable map layers, conversation context, and scheduled public-source monitoring. It is an external-environment research layer: it helps an analyst document institutions, programs, audiences, partners, public activity, change, overlap, and information gaps. It does not recreate OASIS or MODE, connect to State systems without an authorized adapter, or infer program outcomes from public activity.

Both desktop clients use the same `sugar_core.workspace_hub` operations through `sugar_bridge.py`. A project is still an ordinary workspace directory with readable files and an artifact catalog; the local SQLite index is rebuildable.

## Start a project

Create a project and optional research tracks with the `sugar-project` command:

```powershell
sugar-project init .\sugar-projects\project-564 --name "Project 564" --description "External public-diplomacy environment"
sugar-project subproject .\sugar-projects\project-564 "Country A — education centers"
sugar-project projects .\sugar-projects
sugar-project dashboard .\sugar-projects\project-564
sugar-project history .\sugar-projects\project-564
```

The desktop **Research Workspace** page supports project switching, recent-project discovery, status, history, new subprojects, rerunning a recorded search, and bundle import/export. A child project has its own files, registry, monitor definitions, history, map inputs, and outputs; a parent-child relation records its connection to the broader research question. Imported projects are linked under the selected parent when requested, and the import destination must be inside that parent's project folder.

Ordinary bridge-run workflows are recorded with actor, start/end time, command, safe parameters, query terms, effective source platforms, date window, collection coverage, output paths, and row counts when the output format allows counting. Search-plan changes and workspace actions are separate append-only history events. Runtime secret fields are filtered before project history is written. Search errors are recorded with status and sanitized error text.

History supports reproducibility and review; reruns create new records and outputs. It does not rewrite prior runs. Rerunning a saved search uses its stored safe configuration and a new output directory.

## Institution and service registry

The registry is generic. Its entity types include networks, organizations, institutions, sites, programs, accounts, events, and services. A record can include:

- stable ID, primary name, aliases, entity type, network, and description;
- location, coordinates, location precision, and service geography;
- active, closed, renamed, relocated, or unknown status and lifecycle dates;
- programs/services, supported audiences, and physical/mobile/virtual/hybrid/digital delivery;
- public URLs and handles, host and partner entities, and explicitly typed relationships;
- source-linked claims, review states, conflicts, analyst notes, and change history.

Claims retain the source URL, retrieval time, dataset, row identity, and evidence reference. Raw program, audience, and delivery wording is stored separately from normalized categories. Normalization uses a versioned exact-label vocabulary and only explicitly supplied fields; unknown labels remain visible in the source wording without being guessed into a category. SUGAR never infers an audience from an institution or program title. Conflicting field claims are preserved for review rather than silently overwritten. Registry import diffs report new records, field changes, lifecycle events, conflict flags, and similar-name candidates. A similarity candidate is not an automatic merge. Relationship records require evidence. Source-supported exact host/partner matches can create typed relationships during import; ambiguous names are left unresolved.

The initial program vocabulary is language_learning, education_advising, vocational_technical_training, entrepreneurship, professional_development, cultural_programming, alumni_networking, information_media, steam, academic_exchange, public_dialogue, and civil_society_engagement. Audiences include secondary students, university students, technical/vocational students, educators, academics/researchers, young professionals, entrepreneurs, emerging leaders, opinion leaders, media, government officials, civil-society groups, underserved communities, and the general public. Delivery modes are physical, mobile, virtual, hybrid, and digital. Matching is exact after case and punctuation normalization; an unknown label remains only in its source-description field until an analyst or later taxonomy release resolves it.

The desktop registry can be filtered, opened as a profile, exported, compared, updated with sourced claims, connected through evidence-backed relationships, and used to prepare monitor terms. Relationship entry accepts optional source-backed `valid_from` and `valid_to` calendar dates plus a review state; leave dates blank when the source does not establish the period. The temporal evidence graph consumes these relationships and registry lifecycle events, retains their citations and review state, and keeps capture timestamps separate from valid time. Comparison reports geographic, audience, program/service, delivery, institutional, and temporal dimensions separately. Missing coverage is not zero; proximity is not competition. Popularity, effectiveness, outcomes, and causal influence are not computed by this comparison.

### Import a reference dataset

The import flow accepts CSV, TSV, XLSX, XLS, JSON FeatureCollections, and GeoJSON. It displays the columns, sample rows, detected mappings, row errors, and valid/invalid counts before import. The user confirms the mapping and supplies a dataset name, network, geographic/temporal scope, known limits, and license/permitted-use notes. Partial imports require an explicit choice; excluded rows and reasons are recorded. Source URLs may be mapped per row. Coordinates must be paired and within valid ranges; supplied locations retain a precision label instead of implying address-level accuracy.

Use **Create template** to generate a blank schema for American Spaces, EducationUSA, language education centers, technical training workshops, or a custom engagement network. These are schemas only: SUGAR does not ship a verified, current, comprehensive inventory of those networks. Populate them from a documented source and bound any completeness claim by the recorded source, date, geography, and known coverage limits. American Spaces and EducationUSA should remain separate reference networks even when one site hosts both.

The CLI supports registry inspection, import, and export:

```powershell
sugar-project registry .\sugar-projects\project-564 --network "Language education network" --status active
sugar-project registry-preview .\references\institutions.xlsx
sugar-project registry-import .\sugar-projects\project-564 .\references\institutions.xlsx `
  --mapping '{"name":"Institution","status":"Status","country":"Country","source_url":"Source URL"}' `
  --dataset-name "Reviewed source inventory" --network "Language education network" `
  --geographic-scope "Documented coverage in selected countries" `
  --coverage-limits "Not a census; source coverage varies" --license-notes "Review source terms before reuse"
sugar-project registry-export .\sugar-projects\project-564 .\exports\registry.csv --format csv
sugar-project reference-template .\sugar-projects\project-564 language_education_centers
```

Use `registry-preview` to inspect a dataset without importing it. `registry-import` validates it again and requires an explicit canonical name-column mapping; invalid rows stop import unless `--accept-partial` is deliberately supplied. Review and preserve source-specific reuse terms before distributing an imported dataset.

## Inspectable data and maps

The **Data** tab accepts dropped or selected CSV, TSV, XLSX, XLS, JSON, GeoJSON, JSONL, and NDJSON files. Analysts can inspect columns and rows, filter a selected field, and export the matching rows as CSV, XLSX, JSONL, JSON, or GeoJSON. The view is bounded for responsiveness; export applies the filter to the complete input rather than just the displayed preview.

The **Maps** tab builds an interactive HTML map from an optional activity/service dataset, the canonical registry, and any number of CSV/XLSX/JSON/GeoJSON reference layers. Registry popups include available lifecycle state, location precision, program and audience fields, relationships, and evidence links. Closed and uncertain records use distinct marker styling and retain source-backed closure details. An as-of date filters by documented activity and lifecycle dates; it does not reconstruct former coordinates or fill missing dates. A map is a view of supplied records, not a census of all network locations.

Map density means record density. Distance means distance. Neither is a measure of influence, competition, popularity, effectiveness, or causal impact. Inspect the underlying rows and coverage metadata before drawing a service-gap conclusion.

## Listening posts

A listening post stores its name, terms and target entities/accounts, supported source platforms, geography and date filters, collection limits, cadence, status, revision, and run history. Runs use configured public or authorized collectors and follow their existing access and rate-limit behavior. No model enrichment is requested by default. Each run writes ordinary collection output, coverage information, run history, and a deduplicated feed of new, changed, and unchanged records. New or changed items return to `unreviewed`; analysts can mark them human verified, needs follow-up, rejected, or unreviewed and add a note. These decisions are timestamped with analyst identity.

In the desktop, periodic due checks are disabled by default. An analyst may opt in to run due monitors while SUGAR is open. For unattended scheduling, configure each analyst's authorized credentials in their execution environment and invoke the one-shot command from an approved operating-system scheduler:

```powershell
sugar-project monitor-run-due .\sugar-projects\project-564 --max-monitors 10
```

The CLI reads supported credentials from runtime environment variables such as `SUGAR_X_BEARER_TOKEN`, `SUGAR_BLUESKY_IDENTIFIER`, `SUGAR_BLUESKY_APP_PASSWORD`, `SUGAR_MASTODON_TOKEN`, `SUGAR_WEIBO_COOKIE`, and `SUGAR_LLM_API_KEY`. A key is not written into the monitor definition or project history. Supply only credentials and source access authorized for that analyst and environment. A failed, blocked, unavailable, partial, or successful zero-result run stays distinct in coverage and history.

## Accounts and conversations

Canonical source records preserve platform, handle, stable record key, timestamp, original text, canonical URL, conversation/thread IDs, parent/reply key, reply target handle, quote key, mention handles, and repost state where supplied by the source. The conversation view groups records and displays who said what while retaining those fields. It reports a parent as not collected when the referenced source record is absent; it never fabricates a missing reply, quote, mention, or institutional relationship. A handle is not automatically treated as a person or as an institution's account.

Use the desktop Conversations view or:

```powershell
sugar-project conversation-view .\data\raw\posts.csv .\outputs\conversation.json --conversation-id "thread-id"
```

## Portable project exchange

Project export creates a ZIP with a file manifest and SHA-256 checksums. It retains project files, external reference artifacts when they can be copied, search history, review decisions, map inputs, monitor data, and project relations. External copied references are placed under `references/external`; recorded paths are made portable only in path-valued fields. Credential-named paths, local cache/dependency directories, SQLite runtime state, archive nesting, symbolic links, unmanifested files, and JSON documents containing credential fields are excluded or rejected as appropriate.

Import extracts into a new destination through a staging directory, rejects traversal and symbolic links, enforces an uncompressed-size bound, checks the integrity manifest, opens the project manifest, and only then moves the staged project into place. The recipient can continue from that copy and must configure their own authorized credentials. Bundles provide asynchronous handoff; they are not a live multi-user editing or conflict-resolution service.

```powershell
sugar-project export-project .\sugar-projects\project-564 .\exports\project-564.sugar.zip
sugar-project import-project .\exports\project-564.sugar.zip .\sugar-projects\received-project-564
```

## Conversation and evidence rules

SUGAR's external registry complements the Department's authorized internal reporting and outcome systems. It records public or supplied evidence and exposes uncertainty, source coverage, field conflicts, and review history to the analyst. It does not decide policy or funding allocations. If the evidence says only that a site exists, SUGAR does not claim the site reached a specific audience or changed attitudes. If the evidence shows geographic co-presence, SUGAR does not call that competition. Human review and authorized first-party evaluation remain necessary for outcome claims.

## Current scope boundaries

- Blank templates and flexible import are provided; a current, authoritative global institution inventory is not bundled. Dataset completeness must be established and refreshed by analysts from documented sources.
- Project exchange is portable and asynchronous; simultaneous multi-user editing is not implemented.
- The generated map is an inspectable analysis view with sourced popups and layers. It is not a live synchronized project editor or a State-system interface.
- Map comparison, registry comparison, and public monitoring expose evidence and gaps; they do not estimate effectiveness, persuasion, or causal influence.
- OASIS, MODE, EducationUSA internal systems, and other Department platforms are not accessed. Analysts may use authorized exports through documented file interfaces.
