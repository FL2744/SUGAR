# Research workbench

The workbench converts a normal research request into an inspectable, executable, and reproducible collection run.

## Flow

1. **Interpret.** `POST /api/interpret` turns text into a `ResearchPlanSpec` (`sugar_core/research_plan.py`). Validation runs on the structured plan, never on the sentence.
   - *LLM* (`mode=auto` with a provider): JSON-schema output → safe repair → validate → retry with feedback (bounded) → fall back to the deterministic interpreter → manual structured entry.
   - *Deterministic* (`nl_interpreter.py`): offline and reproducible; extracts topic, places (built-in gazetteer, unknown capitalised places accepted with an assumption), platforms (`all platforms`, named platforms, unsupported ones reported), date ranges, languages, depth, exclusions, monitoring intent. Every default it applied is listed as an assumption.
   - Clarification is requested only when the topic cannot be inferred.
2. **Preview.** The UI shows the plan, assumptions, and planned searches; run now, edit, or open advanced configuration.
3. **Run.** `ResearchPipeline` searches platforms in parallel (registered collectors, no second engine), ingests items (filters, de-duplication, language detection, extraction), translates through the provider, and finalises a `Run`.
4. **Inspect.** Results group by platform, language, geography, query, or author, toggle original/translation, and expose provenance and the evidence chain.
5. **Export.** `research/exports/<run>/` holds `plan.json`, `run-manifest.json` (SHA-256 of every file), `sources.csv`, `results.csv`, `corpus.jsonl`, `translations.jsonl`, `activity-log.jsonl`, `report.md`, and `geo.geojson` when coordinates exist, plus a `.zip`.

## Plan defaults (documented)

| Field | Default |
|---|---|
| timeframe | no restriction |
| languages | automatic (detect per item) |
| platforms | all enabled (keyword-search collector + credentials) |
| collection mode | discovery |
| depth | standard — 6 queries, 25 posts/query, 1 page |
| translation | automatic when a provider is configured, into English |
| de-duplication | on, near-duplicate threshold 0.90 |
| concurrency | up to 4 platforms in parallel |
| retry | 3 attempts, exponential backoff from 30 s |
| refresh | manual |

Unknown fields survive round trips in `extra`, so the schema can grow without UI rewrites.

## Refresh semantics

| Operation | Effect |
|---|---|
| Reinterpret request | re-run interpretation on the stored request; returns a proposal |
| Rebuild plan | regenerate queries (analyst-added queries are kept); returns a proposal |
| Refresh sources | search again; items flagged new / known / changed against earlier runs |
| Reprocess results | repeat language detection, extraction, translation without collecting |
| Rerun | execute the recorded plan again exactly |

## Activity events

`GET /api/workspaces/{id}/runs/{run}/events?after=<seq>` (polling) and `/stream` (Server-Sent Events). Types include `research.plan.created`, `query.generated`, `source.search.started|completed`, `item.discovered`, `item.download.started|completed`, `language.detected`, `translation.started|completed|failed|skipped`, `extraction.started|completed`, `duplicate.detected`, `item.rejected`, `item.excluded`, `item.changed`, `provider.rate_limited`, `source.failed|skipped`, `source.retry.scheduled`, `run.paused|resumed|cancelled|failed`, `pipeline.completed`. Debug Mode adds `provider.call`, `collector.request`, `parser.decision`, `timing.recorded`. `item.download.*` events mark retrieval into the run; collectors fetch content with the search call, so they carry `mode: "batched_with_search"`.

## Failures

`fatal` (run cannot continue), `source_specific` (credential rejected, access blocked — other platforms continue), `retryable` (rate limit / transient — retried with backoff, reported if exhausted), `skipped` (missing credential, unsupported), `warning` (e.g. a translation failed). The run records `completeness` and states explicitly when collection is incomplete.

## Providers and credentials

Provider → Credential → Model → Advanced options. Types: `openai`, `openai_compatible`, `anthropic`, `arc`, `local`. *Test connection* checks reachability, credential, model availability, and a real inference call, returning stage-specific messages. Secrets are stored by `CredentialStore` (OS vault with the optional `keyring` extra, otherwise an owner-only file under `~/.sugar`), are resolved from `SUGAR_*` environment variables or an ignored `.env.local` first (see `.env.local.example`), and are referenced — never embedded — by projects and runs. The file backend is protected by permissions, not encryption.

## Project data model

`research/project.json` (metadata, current plan, members, settings), `research/plans/<id>.v<N>.json` (immutable versions), `research/runs/<run>/` (`run.json`, `events.jsonl`, `items.jsonl`, `translations.jsonl`), `notes.jsonl`, `findings.jsonl`; the timeline reuses `.sugar/project-history.jsonl`. Members carry roles (owner/editor/commenter/viewer) and plans carry `refresh` (scheduled/watch, watch queries, change detection), so sharing, comments, map layers (items carry geography tags and optional coordinates), and listening posts build on the same plan rather than a separate architecture.

## Performance

Timing is recorded for interpretation, search, download, parsing, extraction, translation, model calls, de-duplication, serialization, and UI event delivery, and is shown in Debug Mode.
