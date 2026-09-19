# SUGAR intelligence and workload benchmark

SUGAR has separate checks for analytic quality and operational capacity. The report keeps these
dimensions separate; there is no single "intelligence score" that can hide poor evidence handling
behind throughput or good classification behind unsupported claims.

## What is measured

| Dimension | Measures | Evidence needed |
| --- | --- | --- |
| Collection fidelity | Returned records, unique identity, duplicate fraction, populated IDs/URLs/timestamps/text, query/source provenance, errors, rate-limit headers, latency and records per second | Bounded live API report |
| Checkpoint reliability | Insert/update counts and exact normalized-record round trip through SQLite | Bounded live API report and offline stress reports |
| Relevance judgment | Three-class accuracy and macro F1, confusion matrix, abstention rate, selective accuracy, 95% Wilson intervals | At least 50 independently sampled, adjudicated records per task profile |
| Controlled labels | Micro/macro F1 for multi-label classification | Gold labels from independent reviewers |
| Confidence calibration | Brier score and 10-bin expected calibration error against whether the predicted relevance class was correct | Numeric confidence values and adjudicated labels |
| Evidence integrity | Human-rated fully/partly/unsupported source spans and material judgments; valid supporting-reference coverage | Human evidence review |
| Analyst value | Separate 1–5 usefulness, actionability, and novelty ratings, with distributions and sample sizes | Human review of the generated judgments |
| Forecast quality | Brier score and log loss on numerical forecasts after their stated resolution date | Forecast probabilities and adjudicated outcomes |
| Capacity | SQLite upsert/read, export, map generation, peak Python allocation, disk use, and elapsed time at controlled record counts | Offline synthetic workload |

Collection counts are not recall: the live platform does not reveal the complete set of posts that
matched a query. Search results are not a representative sample of a platform or public opinion.

## Bounded live API sample

The live script exercises SUGAR's Bluesky AppView adapter through its public read API. [Bluesky
documents](https://docs.bsky.app/docs/api/app-bsky-feed-get-feed) anonymous `GET` calls against
`public.api.bsky.app`. [Mastodon documents](https://docs.joinmastodon.org/methods/search/) status
search as instance-dependent and requires an authorized user token with `read:search` for full-text
status search; without `SUGAR_MASTODON_TOKEN`, SUGAR records `credential_required` and does not send
a Mastodon request. The script makes at most one request per configured service, asks for at most
five results, uses one page, does not follow redirects or retry, performs no writes, and stores
returned normalized records only in a temporary SQLite file. Its report contains aggregates and a
hash of the query, not post text, post IDs, account names, or credentials.

Run locally:

```bash
python tools/live_public_api_benchmark.py --output ./benchmark/live-public-api.json
```

GitHub Actions does not run live platform calls on every push. The separate **Authorized public API
benchmark** workflow requires a manual dispatch and an explicit confirmation; its sanitized report
is retained as a short-lived artifact. An access failure or zero results is not proof that no
matching posts exist; a live request can only report the response visible through that service's
authorized search surface.

The existing Weibo and Bilibili collectors are not used for this benchmark. [Weibo's service
agreement](https://weibo.com/signup/v5/protocol) requires prior written permission for automated
collection. [Bilibili's Open Platform developer agreement](https://open.bilibili.com/agreement/developer-service)
governs access through that service. Run source-specific live qualification only with the access and
permissions required by that source. An open endpoint or a successful HTTP response alone is not
permission to collect at scale.

## Offline capacity workload

The stress runner backports the existing open-PR scale harness to current `main`. CI runs 5,000
synthetic records with conservative time, disk, and Python-allocation budgets. The normal run is
offline. Increase scale locally in isolated output directories:

```bash
python tools/stress_test.py --records 50000 --skip-export --skip-map --output-dir ./benchmark/stress-50k
python tools/stress_matrix.py --scales 1000,10000,100000 --output-dir ./benchmark/stress-matrix
python tools/soak_test.py --records 1000 --iterations 10 --output-dir ./benchmark/soak
```

`stress_matrix.py` can measure through 1,000,000 checkpoint rows with a bounded in-memory sample.
Million-row and long-duration runs are operator-invoked because their disk and runtime cost depends
on the host. Export and map probes should be run separately; XLSX and one-file interactive maps are
review outputs, not bulk checkpoint formats. Compare measurements only on the same host and Python
runtime. Offline scale results do not justify sending industrial traffic to a platform.

## Human calibration input

Start from [`tools/benchmark-template.json`](../tools/benchmark-template.json), then create the
JSON review file after blind, independent review and adjudication. The empty template intentionally
scores as `INSUFFICIENT_SAMPLE`; it is not a zero-quality score. The calibration unit should be
sampled before reviewers see SUGAR's labels. Use two reviewers for at least 80% of items; record both
relevance labels and the adjudicated label. Keep a held-out set that is not used to revise prompts.
The default minimum is 50 items and reviewer Cohen's kappa must be at least 0.60 before the report
is marked `SCORABLE_NOT_PASS`. That status means the measurements can be interpreted; it does not
mean SUGAR passed a project requirement. Set acceptance thresholds before looking at the holdout
results.

Example input:

```json
{
  "schema_version": 1,
  "run": {"profile": "public-activity-triage", "provider": "configured-provider", "model": "configured-model", "holdout": true},
  "items": [
    {
      "item_id": "sha256-of-stable-source-key",
      "reviewer1_relevance": "relevant",
      "reviewer2_relevance": "uncertain",
      "gold_relevance": "relevant",
      "predicted_relevance": "relevant",
      "predicted_confidence": 0.82,
      "gold_labels": ["education", "program_activity"],
      "predicted_labels": ["education"],
      "evidence_checks": [{"verdict": "supported"}, {"verdict": "partly_supported"}],
      "judgments": [{"verdict": "supported", "usefulness": 4, "actionability": 3, "novelty": 4, "supporting_refs_valid": true}],
      "forecasts": [{"probability": 0.7, "outcome": true}]
    }
  ]
}
```

Allowed relevance values are `relevant`, `uncertain`, and `not_relevant`. Evidence and judgment
verdicts are `supported`, `partly_supported`, `unsupported`, or `unverifiable`. A forecast outcome
is scored only after the event has been adjudicated; omit unresolved forecasts. Use stable pseudonymous
item IDs and omit raw post content from this score file.

Score it and optionally attach the operational reports:

```bash
python tools/intelligence_benchmark.py \
  --input ./benchmark/adjudicated-holdout.json \
  --collection-report ./benchmark/live-public-api.json \
  --stress-report ./benchmark/stress-matrix/stress-matrix-report.json \
  --output ./benchmark/scorecard.json
```

Accuracy intervals use the Wilson 95% interval. Confidence is evaluated as the model's probability
that its predicted relevance class is correct, so the Brier/ECE figures test confidence calibration
rather than probability of relevance. Forecast scoring uses the explicit probability supplied for
each resolved event. Evidence and usefulness ratings remain human-coded. The report deliberately
returns `INSUFFICIENT_SAMPLE` until the sample and double-review requirements are met, and always
leaves the composite score null.

## Current limits

The live API sample measures connectivity and normalized data quality, not analysis correctness. A
model must run on the collected corpus and reviewers must produce an adjudicated holdout before
SUGAR's intelligence can be called calibrated. Load testing against live services remains capped by
their documented interfaces and access permissions; larger traffic profiles run against local,
synthetic data or an explicitly authorized replay environment.
