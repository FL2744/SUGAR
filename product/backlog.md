# Persistent external-environment research workspace

This document captures the product direction for SUGAR, combining the ECA/American Spaces sponsor problem with analyst meeting feedback. The workspace capabilities described here form the SUGAR 1.3 implementation baseline. See the implementation-status section at the end for explicit data, integration, and collaboration boundaries; the blank schemas are not claims of a maintained institution inventory.

## Product direction

SUGAR should help an analyst maintain an evidence-backed picture of the public-diplomacy environment around a network: which organizations, sites, programs, partners, audiences, channels, and places are involved; how the environment changes; where service, audience, or geographic overlap is supported; what remains unknown; and what evidence should be collected next.

The durable product is a repeatable research capability: method, reference data, evidence and review rules, persistent project history, monitoring, analyst workflow, and portable handoff. SUGAR is its implementation. It complements American Spaces and EducationUSA work and existing Department systems. It does not reproduce OASIS or MODE, assume access to internal State systems, or calculate ECA outcomes from public social-media data.

## Sponsor problem and research target

The Diplomacy Lab research problem is to assess international cultural and educational networks alongside American Spaces and EducationUSA. It calls for a replicable, resource-efficient way to compare audiences, programming, and observable activity, identify intersections, and maintain an evidence-backed resource for human public-diplomacy analysis.

This should be treated as an external-environment evidence problem. The system needs to organize what is observable around a public-diplomacy network and show where evidence is strong, where coverage is incomplete, and what a human should investigate next. It must not substitute its own interpretation for a post's local knowledge or an authorized resource-allocation decision.

American Spaces and EducationUSA are related but separate service networks. A physical American Space may host an EducationUSA advising center; virtual advising can serve an area without a corresponding physical site. The registry and comparison model therefore preserves network identity, delivery mode, service geography, audience, program domain, and institutional relationships independently. A city-level co-location is a geographic fact, not a competition score.

SUGAR supplies evidence about the public environment around the Department's work. OASIS-style operational counts and MODE/evaluation evidence remain separate, authorized inputs. Public posts, site counts, and engagement cannot establish comparative effectiveness, attitude change, or causal influence.

The research loop is:

```text
priority audience and research question
                 |
                 v
known U.S. service context       external networks and public evidence
  American Spaces                         institutions / programs
  EducationUSA                            audiences / partners / channels
  other supplied context                 activity / change / geography
                 \                            /
                  \                          /
                   v                        v
                    supported overlap, gaps,
                    change, and uncertainty
                              |
                              v
                   analyst review and next
                      evidence decision
                              |
                              v
                authorized follow-up and refresh
```

## Method and data rules

- Model external networks generically. The current Diplomacy Lab case is an initial focus; the model should also accommodate other national, educational, and cultural engagement networks without assuming every co-location is a rivalry.
- Treat American Spaces and EducationUSA as distinct, overlapping service networks. Represent physical sites, hosted advising centers, virtual coverage, and other supplied service footprints separately.
- Keep institution, program, host/partner organization, account/channel, event, observation, and source evidence distinguishable and explicitly related.
- Preserve source descriptions alongside normalized program/service domains. Record audiences only when sources support them; do not infer audience from a program title alone.
- Represent physical, virtual, hybrid, mobile, and digital delivery, along with the service geography each source actually supports. A point location is not automatically the full audience geography.
- Preserve lifecycle history. Active, closed, renamed, relocated, and unknown are states with sourced dates and evidence, not reasons to delete a record.
- Keep presence, activity, reach, engagement, outcome evidence, and causal influence evidence separate. Public activity and engagement do not establish changed attitudes, comparative effectiveness, persuasion, or causation.
- Report geographic, audience, program/service, institutional, and delivery overlap as separate dimensions. Distinguish “no relationship observed within documented coverage” from “no relationship exists.” Do not roll the dimensions into a competition or influence score.
- Keep evidence lineage, conflicting sources, collection coverage, review state, and unknown values visible in exports and analyst views.
- Treat OASIS/MODE or other first-party Department information as authorized inputs or handoff context only when supplied through an approved route. Do not recreate internal reporting or imply access to internal data.

## Product work sequence

Priorities below order product work; they do not replace the State product contract's existing release priorities.

### P0 — Evidence-backed entity and reference registry

Create a reusable registry for institutions and related entities, rather than a one-off network spreadsheet. Each canonical record should support stable identity, entity type, primary name, aliases and languages, parent/host/partner relationships, network affiliation, location and location precision, physical or virtual service scope, status and sourced lifecycle dates, public links/accounts, source references, analyst notes, and review state.

Acceptance criteria:

- A record can have multiple evidence-backed names, locations, relationships, and lifecycle events without overwriting its history.
- Conflicting status, location, sponsor, or date claims remain visible with their sources and review state.
- Closed, renamed, relocated, and unknown records remain in the registry and can be queried as of a chosen time.
- Each reference-data release records its sources, retrieval/update date, geographic and network scope, and known coverage limits; “comprehensive” claims are bounded to that documented scope.
- Refreshes can surface additions, changed fields, lifecycle events, and unresolved conflicts while retaining earlier snapshots and evidence.
- Similar-name candidates can be reviewed; the system does not silently merge ambiguous institutions or accounts.
- The same schema supports multiple international education, cultural, and service networks through data and configuration rather than a country-specific entity type.

### P0 — Inspectable research data and reference-layer exchange

Make the data behind maps and assessments an ordinary part of the analyst workflow. Analysts should be able to browse, filter, inspect, and export source records, registry entities, program/service observations, U.S. reference coverage, overlap results, search runs, and evidence gaps.

Acceptance criteria:

- Tables expose the underlying values, source citations, timestamps, coverage limits, and review state behind a visualization or summary.
- Users can filter and export a selected dataset or view in documented interoperable formats such as CSV, JSONL, and GeoJSON where appropriate.
- Drag-and-drop import supports CSV, XLSX, and GeoJSON with a preview, field mapping, validation, and rejected-row report.
- Import can suggest likely name, address, latitude, and longitude fields, but the analyst confirms mappings and geographic precision before records become reference locations.
- Imported datasets retain source, license/usage notes, import time, and contributor provenance. They do not silently replace reviewed canonical data.
- Reference datasets can be reused as named map layers, including multiple overlapping networks and historical records.

### P0 — Multidimensional American Spaces / EducationUSA context

Make the comparison answer the sponsor's question without duplicating State's own operating or outcome systems. Maintain American Spaces and EducationUSA separately, with sourced service tags, audiences, delivery modes, physical locations, and service geography.

Acceptance criteria:

- An American Space can be represented with or without a hosted EducationUSA center; virtual EducationUSA coverage can exist without a physical center.
- An analyst can distinguish geographic co-presence, supported audience overlap, partial or direct program/service overlap, institutional relationships, and delivery-mode overlap.
- Each dimension has its own evidence and coverage basis. Missing or incomplete reference data is shown as unknown or not assessed.
- Results never treat distance alone as competition or label overlap as popularity, effectiveness, or influence.
- Authorized first-party outcome data, if supplied, remain separately identified from public external-environment evidence.

### P1 — Persistent multi-project workspace and subprojects

Make projects the durable container for requirements, plans, searches, evidence, reference data, maps, notes, assessments, and exports. Provide a landing view for switching among active/recent projects and seeing basic status.

Acceptance criteria:

- The project dashboard shows project name, parent/child relationship, last activity, latest successful run, pending review, and known collection issues.
- A project can contain named subprojects or research tracks, such as a country, institution, network, or audience study.
- Each track can keep its own requirements, search plan/history, evidence, map layers, assessments, and outputs while retaining a link to its parent question.
- Existing project/workspace files and handoff packages remain inspectable and portable; project hierarchy does not hide provenance or create duplicate source evidence.

### P1 — Reproducible project and search history

Record what was searched and what happened so analysts can understand, compare, and rerun earlier work.

Acceptance criteria:

- Each run records the parent project/requirement and strategy version, exact search terms or query branches, source/platform, start/end time, filters, date range, access mode, configured limits, results/counts, and success/partial/failure/zero-result state.
- Research-plan edits and analyst decisions are appended with actor, time, and reason; earlier versions remain viewable.
- Rerun starts from the saved query and settings, then creates a new run record rather than rewriting history.
- Credentials and tokens are runtime inputs and are never included in project history or share bundles.
- Run records connect collected observations to the search and source that found them.

### P1 — Map as an analyst workspace

Extend maps from end-of-run visualization into a way to inspect the registry and research evidence.

Acceptance criteria:

- Analysts can toggle, filter, and compare multiple reusable reference and evidence layers.
- Selecting a site opens its registry profile, sourced status/history, programs, partners, related accounts and evidence, location precision, and collection gaps.
- Analysts can launch or save a bounded research question from a selected entity while retaining the entity and parent project as context.
- Map symbology distinguishes current, closed, relocated, and uncertain records without relying on color alone; closed records show closure date and source evidence when known.
- Historical views make clear the “as of” date and do not imply a lifecycle date unsupported by evidence.
- Distance and co-location are described spatially; they are not automatically labeled as competition or strategic impact.

### P1 — Project exchange and collaboration handoff

Promote portable project bundles into a clear user-facing share/import workflow. Initial collaboration can be asynchronous; live multi-user editing is not required for this backlog.

Acceptance criteria:

- Export/import can preserve project structure, subprojects, reference data, search history, evidence, annotations, settings that contain no secrets, map configuration, provenance, and review state.
- A recipient can inspect the bundle and continue research without the original analyst's machine or credentials.
- Contributor identity/provenance and conflicting human review decisions are preserved rather than collapsed into a single winner.
- Import reports missing files, schema differences, duplicate evidence, and incompatible settings before merging.

### P2 — Listening posts and persistent monitoring

Let analysts maintain scoped monitors whose new evidence feeds project review. A listening post is a saved research requirement and collection schedule, not an opaque autonomous agent.

Acceptance criteria:

- A monitor defines entities/accounts/terms, sources, query families, geography, timeframe, cadence, budget, and access constraints.
- Each scheduled or manual run creates the same auditable history and coverage record as an ordinary project search.
- New observations, newly suggested entities, source changes, closures, and other detected changes enter a review queue with evidence links; they do not silently update verified assessments.
- Failed, unavailable, and partial collection states are surfaced and never interpreted as no activity.
- Monitoring can be paused, resumed, edited, and compared with its earlier scope; scope changes are recorded.
- Collection only uses configured public or otherwise authorized source access and obeys source limits.

### P2 — Account identity and conversation context

Improve evidence display for conversations without converting public handles into person dossiers by default.

Acceptance criteria:

- Each social account/handle is displayed as a distinct source actor with platform and stable source identity where available.
- Replies, quotes, reposts, mentions, parent/child links, and collection context remain explicit in a conversation view.
- “Who said what” is readable while preserving original text, translation status, timestamps, and source links.
- Uncertain account-to-organization or account-to-person relationships remain hypotheses until supported and reviewed.
- Conversation views link back to canonical observations and source evidence; they do not replace them.

### P1 — In-product help and analyst onboarding

Make the workflow usable without the original student team explaining it live.

Acceptance criteria:

- First-run onboarding walks through creating a requirement, reviewing a plan, importing/collecting evidence, inspecting a map/table, reviewing a claim, and exporting a project.
- Contextual help explains domain terms, evidence/review states, map precision, overlap dimensions, collection limitations, and how to rerun a search.
- Help includes troubleshooting and links to version-matched documentation.
- Templates can start common work, including an institution/network inventory and an American Spaces / EducationUSA external-environment comparison, without locking SUGAR to one network.
- Keyboard and screen-reader access are considered for dashboard, tables, map controls, and review actions; meaning is not conveyed by color alone.

## Suggested delivery order

1. Agree the generic entity/reference schema, lifecycle vocabulary, source/evidence links, and multidimensional comparison rules.
2. Make registry and assessment data inspectable; define CSV/XLSX/GeoJSON import and export behavior.
3. Add distinct, source-backed American Spaces and EducationUSA reference models and demonstrate a multidimensional comparison.
4. Connect project dashboard, subprojects, search history, and repeatable runs to the existing workspace/artifact foundation; build first-run onboarding around that workflow.
5. Make reference layers and entity profiles usable from the map; then add persistent listening posts that feed the same review queue.
6. Expose complete project exchange and account/conversation context through the desktop workflow, then finish contextual help and troubleshooting.

## Non-goals and guardrails

- Do not recreate OASIS, MODE, or another Department reporting system.
- Do not assume a Northstar, StateChat, or internal ECA API. Use documented file exchange until an approved interface is provided.
- Do not create a universal competition, influence, popularity, or effectiveness score.
- Do not infer audience, sponsorship, affiliation, institutional continuity, or causal impact from names, geography, engagement, or cultural similarity alone.
- Do not equate public activity indicators with outcomes or use social-media data as a substitute for authorized evaluation evidence.
- Do not delete historical/closed entities or treat incomplete collection as evidence of absence.
- Do not include credentials in project bundles or use monitoring to bypass authentication, anti-bot, rate-limit, or other access controls.

## Example of completion

An analyst can open a project for a defined audience and geography; inspect the distinct American Spaces and EducationUSA reference coverage; load a maintained, evidence-backed external network registry; review a site's programs, partners, channels, lifecycle, and cited sources; compare geographic, audience, service, and institutional relationships separately; see what is unknown and why; rerun or monitor an approved search; review new evidence; and export a package another analyst can reopen. The package supports human investigation and resource discussion while leaving policy, funding, and outcome judgments to authorized State personnel and evidence.

## Implementation status — SUGAR 1.3

The shared backend and both desktop clients now provide the persistent workspace capabilities covered by this backlog: generic source-backed entities and relationships; CSV/TSV/XLSX/XLS/JSON/GeoJSON registry import with preview, mapping, validation, refresh diffs, lifecycle history, and conflict review; filterable/exportable underlying datasets; multi-project dashboards and subprojects; append-only run/search/plan-change history; reusable registry and arbitrary map layers with dated views; portable project bundle export/import; saved listening posts and a reviewed incoming-material feed; actor-aware conversation views; and in-product workflow guidance. `docs/research-workspace.md` defines the operator contract.

The implementation intentionally has these boundaries:

- SUGAR ships blank field schemas, not a current, verified, comprehensive global list of international education centers, technical training workshops, American Spaces, or EducationUSA locations. An analyst must identify an attributable source, obtain reuse rights, record the scope/update date/coverage limits, and import or refresh the resulting data. Completeness is always relative to that declared evidence.
- The public map is an inspectable analysis view with source-backed popups and reference overlays. It does not reconstruct unsupported historical coordinates or synchronize map clicks into a live query editor.
- Project sharing is an integrity-checked asynchronous bundle workflow. Simultaneous multi-analyst editing, server-side collaboration, and automatic merging of conflicting live edits are outside this implementation.
- Listening posts execute only configured supported collectors and their existing authorized-access behavior. In-app due checks are opt-in; unattended cadence requires the analyst's operating-system scheduler and runtime credentials.
- OASIS, MODE, EducationUSA internal systems, other State systems, and internal outcome data are not accessed or recreated. SUGAR can ingest approved exports through documented file interfaces.
- The system documents observable public activity, service/audience overlap, coverage, conflicts, and unknowns. It does not produce comparative popularity/effectiveness or causal influence findings.
