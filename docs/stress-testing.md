# Stress testing SUGAR

This document defines the safe offline baseline and the follow-on scale plan for SUGAR. The
offline runner uses deterministic synthetic `PostRecord` objects and does not create collector
sessions, read credentials, or make network requests.

## Reproducible baseline

Use the supported Python 3.11–3.13 runtime. From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest --basetemp ..\pytest-basetemp
.\.venv\Scripts\python.exe tools\stress_test.py --records 5000 --map-records 500 --output-dir .\stress-output
```

The explicit pytest base directory is useful on Windows hosts where the system pytest temp
directory can be locked by another process. `stress-output` is generated output and should not be
committed.

For a storage-only high-scale probe:

```powershell
.\.venv\Scripts\python.exe tools\stress_test.py --records 50000 --skip-export --skip-map --output-dir .\stress-output-50k
```

At million-record scale, the storage probe streams synthetic records into SQLite and limits the
in-memory frame/export sample with `--in-memory-sample`; the report distinguishes full storage
rows from materialized sample rows. This keeps the qualification run bounded while still checking
the full checkpoint row count.

For a map-size probe, keep the source frame modest and increase the embedded point count
deliberately:

```powershell
.\.venv\Scripts\python.exe tools\stress_test.py --records 10000 --map-records 5000 --skip-export --output-dir .\stress-output-map
```

The JSON report records elapsed time, row counts, column counts, artifact sizes, runtime, and the
fact that the probe was offline. Optional `--max-seconds`, `--max-disk-mb`, and
`--max-peak-python-mb` limits are recorded in the report; exceeding a limit returns exit code `2`.
The quality workflow applies conservative wall-time and disk limits to its 5,000-record smoke so a
catastrophic regression becomes a required-check failure. Compare reports from the same machine and
Python environment; wall-clock values are not portable performance guarantees.

The latest local Windows/Python 3.13 storage-only qualification used 1,000,000 rows with a 10,000
row in-memory sample. The normal run completed SQLite upsert in 46.518 s, sampled the restored
checkpoint in 1.852 s, built the tabular sample in 0.916 s, and produced a 1.394 GB SQLite artifact.
A separate `stress_matrix.py` run measured 96.8 MB peak Python allocation; because `tracemalloc`
adds substantial overhead, that instrumented run took 264.328 s for the upsert. These are host
observations, not release thresholds; repeat them on the representative deployment hardware
before setting budgets.

For bounded offline repetition and Python allocation sampling:

```powershell
.\.venv\Scripts\python.exe tools\soak_test.py --records 1000 --iterations 10 --output-dir .\soak-output-10
.\.venv\Scripts\python.exe tools\soak_test.py --records 1000 --duration-seconds 21600 --output-dir .\soak-output-6h
```

The soak report is intentionally bounded: it records completed iterations, interruption state,
per-iteration timings, and a capped ring of peak Python allocation samples. It is an offline
reliability harness, not evidence that live collectors, network resets, or a particular host can
run safely for six or 24 hours. Those qualification runs require the authorized source-specific
environment, a retention plan, and operator review.

Quality CI runs the same deterministic runner at 5,000 records with network access disabled. It
also verifies the supported Python matrix, focused static typing, lint/format cleanliness,
dependency audit, wheel/sdist installation in a fresh environment, and a 75% branch-coverage floor.

## Baseline observed on the initial checkout

At commit `6416381`, using Python 3.13 on Windows, the offline test suite completed with **265
passed, 3 skipped** in 12.26 seconds. The three skipped tests are explicitly opt-in live Weibo
smokes.

Initial synthetic probes showed the following approximate behavior:

| Probe | Scale | Time | Output size |
| --- | ---: | ---: | ---: |
| HarvestStore upsert | 1,000 | 0.019 s | — |
| HarvestStore read | 10,000 | 0.117 s | — |
| `records_to_frame` | 10,000 | 0.422 s | — |
| CSV + XLSX export | 1,000 | 0.953 s | — |
| Interactive map HTML | 1,000 points | 0.961 s | 1.95 MB |

These figures are a starting point, not acceptance thresholds. The map result is intentionally
large because the current implementation embeds a Folium marker and popup for each point.

## Repeatable scale matrix

Run storage probes in isolated directories across the planned scale range. The default matrix is
1,000, 10,000, 100,000, and 1,000,000 records. The 1M scale is a heavy-run ceiling and requires
enough memory and disk:

```powershell
.\\.venv\\Scripts\\python.exe tools\\stress_matrix.py --scales 1000,10000,100000,1000000 --output-dir .\\stress-matrix
```

Add `--include-export` or `--include-map` only after the storage-only matrix is stable. Each scale
gets its own `stress-report.json` with elapsed-time, peak Python-allocation, artifact-size, and
disk-consumption measurements, and the root gets `stress-matrix-report.json`. Compare runs on the same host and Python environment;
these measurements are qualification inputs, not universal performance guarantees.

## Test matrix

### 1. Offline correctness and scale

- Run the normal suite with live tests skipped.
- Run the stress runner at 1k, 10k, 100k, and 1M records with export and map disabled when the host budget allows.
- Confirm checkpoint row counts, restored row counts, and report artifact integrity.
- Repeat the storage probe after an interrupted process to verify resume semantics and no duplicate
  records.

### 2. Export pressure

- Run CSV/XLSX export at 1k, 10k, and 50k records.
- Track elapsed time, peak working-set memory, resulting file sizes, and whether the workbook opens.
- Exercise long text, Unicode, formula-like values, missing coordinates, duplicate query matches, and
  empty optional fields.
- Treat JSONL as the durable large-run format; XLSX is a review/export surface and should not become
  the only checkpoint representation.

### 3. Map pressure

- Run 250, 1k, 5k, and 10k point maps.
- Track HTML size, generation time, browser load time, and interactive responsiveness.
- Test source records and research observations separately, including rejected records, multiple
  locations, reference layers, proximity lines, and heat windows.
- Define a product policy for large maps: aggregation, server-side/vector delivery, or an explicit
  marker limit with a link to the full evidence dataset. SUGAR now fails clearly above the default
  10,000 mappable-row budget; configure `map.max_markers` only when the target environment has been
  tested.

### 4. State and workspace workflows

- Run the deterministic Kyrgyzstan case and compare its summary/guardrail fields with the checked-in
  expectations.
- Scale observation and assessment JSONL/CSV/XLSX inputs independently from 1k through 100k rows.
- Exercise workspace registration, repeated registration, missing artifacts, relative paths, and
  output registration after failed operations.

### 5. Bridge and desktop boundaries

- Run `sugar_bridge.py diagnostics` and assert the advertised protocol and operation set.
- Send valid, missing, malformed, oversized, and unknown-operation configurations through the bridge.
- Verify every failure is a structured error, partial outputs are not mistaken for completion, and
  credentials never appear in events or reports.
- Build the Windows package on Windows and the macOS package on macOS; the current host cannot
  validate the macOS native build.

### 6. Collector contracts and authorized live smoke

- Keep ordinary CI and local regression runs offline with fake sessions/responses.
- Expand fake-session cases for pagination, malformed payloads, HTTP 401/403/429/5xx, timeouts,
  duplicate IDs, missing fields, and server-provided reset headers.
- Verify that every normalized record has an explicit access mode and that observations created from
  records retain source identity, query/collector provenance, raw and normalized metrics, and
  round-trip provenance through CSV, XLSX, and JSONL.
- Run live Weibo tests only when explicitly authorized with `SUGAR_LIVE_WEIBO=1`; keep them bounded
  and separate from high-volume stress. Never use stress testing to evade access controls or rate
  limits.

## Improvement queue informed by the baseline

1. Done: deterministic stress reports now record elapsed time, disk use, and optional peak Python
   allocation; CI enforces wall-time and disk budgets without making live calls.
2. Replace per-record SQLite read/deserialize/update loops with batched or conflict-aware writes
   while preserving query provenance and merge semantics.
3. Stream CSV/JSONL exports and make XLSX generation an explicit bounded review export for large
   collections.
4. Add large-map guardrails and a scalable delivery path that preserves evidence drill-down without
   embedding every popup in one HTML document.
5. Extend single-writer/checkpoint locking and crash-recovery tests for concurrent or interrupted
   harvest processes; legacy workspace migrations now create atomic pre-migration backups.
6. Done in the offline boundary suite: seeded JSON/config, collector metric, import-schema, source-
   conflict, state-assessment, entity-registry, and non-finite numeric cases are exercised without
   network access. Keep extending the corpus when new input boundaries are introduced.
7. Extend memory, timeout, and cancellation budgets from the offline stress runner to workspace,
   state, and desktop operations before attempting multi-user or unattended runs.

All functional or methodology changes should retain the repository’s existing provenance,
fail-closed access behavior, human-review gates, and explicit distinction between descriptive
density/proximity and causal influence.
