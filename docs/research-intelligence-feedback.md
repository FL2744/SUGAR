# Research intelligence feedback

SUGAR exposes inspectable research-intelligence operations to help analysts decide what to collect, trace evidence, compare projects, and find material again. Outputs are reviewable files that can be included in a handoff.

## Recommend the next collection action

```bash
sugar-intel next-evidence requirement.json search-plan.json \
  --hypotheses synthesis.json \
  --max-queries 10 \
  --max-records-per-query 300 \
  --output next-evidence.json
```

The optional hypotheses input can be a competing-hypothesis matrix or synthesis JSON. Each `collection_needed` item is proposed as a candidate query. Existing planned, approved, and paused branches are ranked alongside those proposals.

The report exposes six components and their weights:

| Component | Weight | Basis |
| --- | ---: | --- |
| Uncovered scope match | 0.25 | Candidate mentions requirement geography, audience, language, or known entity not represented by a completed branch with records. |
| Hypothesis discrimination | 0.30 | Candidate matches collection-needed or discriminator text, including its originating hypothesis. |
| Observed novelty | 0.15 | New concepts per relevant item when the branch has a populated novelty counter, capped at 1. |
| Observed relevance | 0.15 | Relevant assessments divided by assessed items on a measured branch. |
| Observed source diversity | 0.10 | Distinct observed source count scaled to four. This does not assert source independence. |
| Observed duplicate avoidance | 0.05 | One minus the measured duplicate rate when duplicate counts were populated. |

Unmeasured components are omitted and the other weights are renormalized. `available_weight` shows how much measured information supports each priority. Default zero novelty/duplicate counters are treated as unmeasured because the current plan schema does not distinguish an observed zero from an unset value. The report explains each recommendation and its metric basis. If a candidate has no measurements, it can use completed branches from the same search family and language, then falls back to family, language, or all completed branches. It reports the selected cohort size, historical median record yield, observed range, and pooled decisive-triage rate; these are planning references, not calibrated predictions. Relevance rates count observations while yield counts records, so SUGAR reports them separately. Accessibility and runtime or compute cost remain unestimated. The record maximum is an analyst-set cap.

Running the operation records a `next_evidence_recommendation` event in the search plan. A new hypothesis-derived query is added as a **paused** branch, where the analyst can edit it and approve it using the ordinary plan review controls. No collection starts from this operation.

## Find content-lineage candidates

```bash
sugar-intel content-lineage records.csv --output content-lineage.json
```

SUGAR normalizes Unicode text and compares character seven-gram Jaccard and containment. Exact normalized matches and near-duplicate candidates are linked into review groups. When `original_text` is absent, translated text can be compared and is explicitly labeled as a fallback.

The output shows source URLs, hosts, platforms, languages, publication times, and pair-level similarity. Similarity does not prove copying or a shared origin. Distinct hosts and platforms do not establish independent corroboration. The method does not infer cross-lingual semantic matches.

## Build an evidence-linked temporal graph

```bash
sugar-intel graph observations.csv --assessments reviewed.jsonl \
  --entity-aliases entity-aliases.json --workspace ./team-project \
  --output evidence-graph.json
```

The graph contains entity, observation/event, claim, and lifecycle nodes. With `--workspace` (or the project selected in either desktop), it also loads the project's source-backed registry claims, relationships, and lifecycle history. Explicit registry relationships become direct entity-to-entity edges with their review state and evidence references; co-appearance in an observation never creates such an edge. Unique registry names and unambiguous human-verified registry aliases can join observations to registry entities. An optional JSON alias registry can map a canonical name to analyst-reviewed aliases:

```json
{"entities":[{"canonical_name":"American University of Central Asia","aliases":["AUCA","АУЦА"]}]}
```

Only unambiguous supplied aliases are joined. Ambiguous alias keys are reported and left separate. Registry claims and relationships keep their review state, reviewer, and cited evidence. ISO calendar dates entered as relationship bounds or lifecycle effective dates populate `valid_from` and `valid_to`; invalid, reversed, or absent dates remain visibly unavailable. Observation and registry capture timestamps remain separate from valid time. Relationships whose endpoint entities are missing are reported rather than silently dropped.

## Test finding sensitivity

```bash
sugar-intel robustness observations.csv reviewed.jsonl --output robustness.json
```

The baseline includes only observations marked `human_verified` whose State assessment is `brief_eligible`. The report removes one recorded platform, source type, source host, language, actor, or AI-provenance category at a time, then reports changes in verified observation count and corpus breadth. An observation remains in a source-removal cohort when it has another recorded evidence reference.

This is descriptive corpus sensitivity, not a universal confidence score or causal test. Missing source metadata limits what can be tested. Actor removal tests whether the coded portfolio depends on records naming that actor; it does not test whether the actor caused an outcome.

## Desktop use

Both the Windows and macOS clients expose these operations under **Intelligence → Research Quality** or the corresponding section in the Research Project workflow. The graph automatically includes the selected project's entity registry, evidence-backed relationships, and lifecycle dates, and records those registry files as pipeline inputs. The optional hypothesis JSON can be selected explicitly. Results are written to the project's intelligence output directory and registered in its artifact catalog.

## Optional DuckDB and Parquet analytics

For large canonical datasets, install the optional analytics dependency and build a Parquet dataset without materializing a pandas DataFrame:

```bash
python -m pip install 'sugar-osint[analytics]'
sugar-intel columnar-build records.csv --output-dir evidence-parquet
sugar-intel columnar-query evidence-parquet \
  --sql "SELECT platform, COUNT(*) AS records FROM evidence GROUP BY platform ORDER BY platform"
```

CSV and JSONL/NDJSON inputs are supported. If a `platform` column exists, output files are partitioned by platform and use Zstandard compression. The `evidence` view supports analyst-supplied `SELECT`/`WITH` queries with a default 1,000-row result cap. SQL functions that read external files, attach databases, or load extensions are rejected. This is an optional analytical store; project/workspace metadata and portable interchange formats remain unchanged.

## Search the evidence corpus

Offline keyword retrieval stays local:

```bash
sugar-intel semantic-search records.csv --query "student scholarships in Bishkek" --top-k 20
```

For multilingual retrieval, build and reuse a compressed vector index:

```bash
sugar-intel semantic-index records.csv --output evidence-index.json.gz --allow-remote-content
sugar-intel semantic-search records.csv --index evidence-index.json.gz \
  --query "student scholarships in Bishkek" --allow-remote-content --top-k 20
```

Set `SUGAR_LLM_API_KEY` for the configured OpenAI-compatible embedding endpoint. Corpus text is sent when the index is built and for changed records; the query is sent for each remote search. The index stores vectors and text needed to return excerpts, never credentials. The desktop checkbox is off by default and explains this transmission. Vectors only rank retrieval candidates; the report keeps source URL, original language, and whether the excerpt is original or translated text. The offline lexical mode is not advertised as cross-lingual semantic matching.

## Preserve multimodal evidence

SUGAR can keep an analyst-supplied local image, audio, or video with SHA-256 identity and optional `ffprobe` metadata. Transcription and OCR files can be attached with their language and unreviewed status. SUGAR does not run transcription, OCR, or keyframe generation itself.

```bash
sugar-intel media-ingest interview.mp4 --workspace ./team-project \
  --source-url https://public.example/item --parent-record-id record-123 \
  --transcript interview.vtt --language ru
sugar-intel media-attach ./team-project/media/media_<id>.json observations.csv \
  --observation-id obs_123 --start 01:13 --end 01:22.500 \
  --quote "The speaker names the program" --output observations-with-media.csv
```

The attachment carries the artifact ID and exact timestamp into `ResearchObservation` evidence. The same workflow is available in both desktop clients. Media access and supplied derivatives remain subject to the analyst's authority and storage rules.

## Capture a page viewed by an analyst

When an analyst can legitimately view a page but an automated collector is unsupported, save the page as `.html` through the browser and import the file:

```bash
sugar-intel capture-page saved-page.html --source-url https://public.example/item --workspace ./team-project
```

SUGAR keeps sanitized visible text and public media references; it removes scripts, form controls, hidden elements, frames, and credential-like values and does not keep the original HTML file. This is a manual import workflow, not a browser extension or a login/access-control workaround.

## Merge analyst projects

```bash
sugar-project merge ./merged-project ./analyst-a ./analyst-b --name "Diplomacy Lab merge"
```

Original contributor artifacts and provenance are preserved. Canonical rows with the same platform/native ID are combined with a contributor list, identical artifact bytes are deduplicated, reused queries are surfaced, and conflicting review assessments stay in their original files and are excluded from the combined non-conflicting assessment view. The merge report distinguishes corpus distribution from collection-attempt coverage; it does not pretend that missing coverage sidecars mean a successful zero-result search.

## Pipeline freshness and calibration

Desktop analytic operations record input/output hashes and parameters in project metadata. The report propagates stale states to downstream registered derivations and lists an upstream-first rebuild order:

```bash
sugar-project pipeline ./team-project
sugar-intel calibrate --output calibration-report.json
```

The pipeline report never replays an operation automatically. Only derivations registered with inputs participate; external paths must still exist to recheck hashes. The fixed offline calibration suite tests six known behaviors: duplicate candidate precision/recall, graph citation completeness, verified-only robustness, hypothesis/scope targeting, and paused-branch review gating. It is a deterministic regression suite, not field calibration, live retrieval scoring, or a measure of analyst accuracy.

## Status against the 12 research-capability goals

| Goal | Available now | Remaining boundary |
| --- | --- | --- |
| Next-best evidence | Inspectable weighted components and paused analyst proposals | Expected live yield, access, and real cost remain explicitly unestimated |
| Temporal graph | Entity, event, reviewed-claim, lifecycle, explicit relationship, evidence, sourced valid-time, and manual alias nodes | No automatic multilingual entity resolution; unknown or unsupported dates remain unknown |
| Multimodal evidence | Local hash preservation, metadata probe, supplied OCR/transcripts, timestamped observation citations | No built-in OCR/ASR/keyframes or automatic visual entity extraction |
| Hypothesis collection loop | Discriminating collection needs become bounded paused branches | Collection and reassessment still require analyst action |
| Multi-analyst merge | Project merge, canonical-record deduplication, provenance, review conflict report | No shared live/cloud editing |
| Content lineage | Exact and near-duplicate text candidates | No cross-lingual lineage, URL-chain discovery, or independent-origin verdict |
| Parquet/DuckDB | Optional streamed build and bounded SQL query | Existing operations are not all migrated to SQL |
| Robustness | Verified-only leave-one-factor-out corpus sensitivity | Descriptive breadth/count changes are not a probability of correctness |
| Analyst capture | Sanitized saved-HTML import and local media preservation | No installed browser extension/share target |
| Semantic search | Local lexical retrieval and opt-in embedding-based multilingual retrieval | Embeddings require a configured compatible remote endpoint |
| Pipeline DAG | Hash freshness, stale propagation, and rebuild ordering for registered desktop derivations | Does not execute incremental rebuilds and does not cover every CLI artifact |
| Calibration lab | Fixed six-case offline gold set | Does not establish real-world retrieval, synthesis, or analyst performance |
