# SUGAR high-volume harvest

SUGAR's `harvest` workflow is the durable collection path for research jobs that need thousands or tens of thousands of normalized public records.

It is intentionally different from trying to make requests as fast as possible. The design goal is **large, reproducible, resumable collection while respecting each source's access controls and rate limits**.

SUGAR does not rotate proxies, accounts, cookies, device identities, user agents, or IP addresses to evade a limit. It does not solve CAPTCHAs or synthesize login / anti-bot state. If a platform says to slow down or stop, the harvest engine waits, defers that task, or records a failure.

## Why use harvest instead of search?

`search` is optimized for an interactive research pass: collect a bounded number of results, optionally translate/geolocate them, and immediately write the finished dataset.

`harvest` is optimized for volume and resilience:

- it decomposes a research plan into deterministic tasks;
- commits completed tasks to a SQLite checkpoint immediately;
- resumes completed work without recollecting it;
- deduplicates records by stable SUGAR `record_key` while preserving every matching query;
- honors rate-limit reset information when the server exposes it;
- uses conservative source-specific waits when a collector reports a rate limit without headers;
- defers long waits instead of throwing away the rest of the research plan;
- exports CSV, XLSX, JSONL, metadata, and a machine-readable harvest manifest;
- performs raw normalized collection first, leaving LLM enrichment and triage for a later batch stage.

This makes a 10,000-record project fundamentally a persistence/planning problem rather than a single fragile HTTP loop.

## Source sharding

Different sources expose different pagination semantics, so SUGAR does not force one sharding strategy onto every platform.

### X and Bluesky

When `--since` and `--until` are ISO dates, SUGAR splits the interval into bounded date windows (seven days by default). The existing collectors send those bounds to the remote search service, so each task covers a genuinely distinct time window.

This also makes dense periods easier to collect without one cursor chain becoming the failure domain for the whole project.

### Bilibili and Weibo

The current public search surfaces are numbered-page based. SUGAR therefore splits each query into durable page ranges. With the default five-page task size and `--max-pages-per-query 100`, a query becomes:

- pages 1–5
- pages 6–10
- pages 11–15
- …
- pages 96–100

If page 43 is rate-limited, pages 1–40 remain checkpointed rather than being recollected on the next run.

These adapters reuse the existing fail-closed public collectors. Page sharding does not change the access model: if Bilibili or Weibo requires login, verification, risk-control state, or another unsupported access mechanism, SUGAR stops/defer-fails rather than attempting to bypass it.

### Mastodon

Mastodon remains instance-scoped. The current search adapter is not date-sharded by default because its date bounds are filtered locally rather than defining independent server-side result partitions. A future bulk adapter should use instance-supported pagination semantics directly rather than repeatedly rescanning the same search result pages.

## Query-plan files

For systematic research, put one search expression per line in a UTF-8 text file. Blank lines and lines beginning with `#` are ignored.

Example `csm_terms_zh.txt`:

```text
# Institutions and program families
孔子学院
鲁班工坊
中国文化中心
汉语桥

# Add project-approved institution/program names and local-language variants below.
```

Run:

```bash
sugar harvest \
  --sources bilibili,weibo \
  --terms-file csm_terms_zh.txt \
  --since 2026-01-01 \
  --until 2026-09-12 \
  --target 10000 \
  --pages-per-task 5 \
  --max-pages-per-query 150 \
  --task-delay 1.5 \
  --name csm_sep12 \
  --output ./runs/csm_sep12
```

Inline terms and one or more `--terms-file` inputs can be combined. Terms are deduplicated while preserving their first-seen order.

A broad query plan is usually methodologically better than driving one keyword hundreds of pages deep. It distributes collection across institution names, program names, languages, regional variants, and topic terms that the team has explicitly approved.

## Checkpoint and outputs

For `--name csm_sep12`, SUGAR creates:

- `csm_sep12.harvest.sqlite3` — durable task/record/event checkpoint;
- `csm_sep12.harvest.json` — harvest plan and completion summary;
- `csm_sep12.csv` — normalized records;
- `csm_sep12.xlsx` — collaboration-friendly workbook;
- `csm_sep12.metadata.json` — export metadata;
- `csm_sep12.jsonl` — newline-delimited normalized records suitable for large downstream jobs.

Re-run the same command with the same output directory and name to resume. Completed tasks are skipped automatically.

SUGAR stores a deterministic plan signature with the checkpoint. If the query set, windows/page plan, or material collector options change, SUGAR refuses to silently mix the new plan into the old checkpoint. Start a new named harvest instead.

Credentials themselves are never written into the harvest database or manifest.

## Rate-limit behavior

When a source returns a recognizable rate-limit response:

1. use `Retry-After` or the source's reset header when available;
2. otherwise apply a conservative source-specific wait;
3. apply exponential backoff across repeated attempts;
4. if the required wait exceeds `--max-inline-wait`, mark the task `deferred` with a `not_before` time and continue safely;
5. resume that task on a later invocation once it is eligible.

This is intentionally **rate-limit-aware**, not rate-limit-free. The external platform remains authoritative about how much access is available.

The manifest records rate-limit event counts and the policy used so collection conditions remain part of research provenance.

## Recommended scale-up procedure

Start with a 5,000-record target and inspect:

- unique records obtained per query/source;
- task failures and deferred tasks;
- duplicate rate;
- date coverage;
- whether deeper pages are still yielding relevant/new records;
- platform-specific access gates;
- source balance in the final dataset.

Then enlarge the query plan, page ceiling, or date coverage deliberately. A higher page ceiling is not useful if later pages yield only duplicates or irrelevant records.

For very large work, keep collection and AI work separate:

```text
HARVEST public records
        ↓
DEDUPLICATE / normalize / checkpoint
        ↓
AI TRIAGE in batches
        ↓
HUMAN VERIFY
        ↓
OBSERVATIONS / spatial analysis / research map
```

This prevents a temporary LLM/API failure from interrupting collection and avoids paying to translate or classify duplicate records.

## Testing strategy

The harvest test suite includes a deterministic 5,000-record orchestration test. It verifies that twenty independent collection shards produce exactly 5,000 unique normalized records, persist to SQLite/JSONL, and then resume with **zero recollection calls** on a second run.

Separate tests simulate HTTP 429 behavior, `Retry-After`, long deferrals, duplicate-query provenance, numbered page checkpoints, and accidental checkpoint reuse with a changed plan.

These load tests validate SUGAR's volume/resume mechanics without hammering live social platforms during CI. Live coverage remains subject to each platform's current public or authorized access surface.
