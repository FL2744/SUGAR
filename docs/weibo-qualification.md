# Weibo qualification workflow

`weibo-qualify` evaluates whether a large Weibo research collection is reproducible, well-provenanced, and suitable for downstream analysis.

It combines fresh collection replicates, checkpoint metrics, real-post validation, and a human relevance audit. A resumed checkpoint is not counted as a reproducibility replicate.

Default project checks include unique record count, task completion/failure, access-limited tasks, query coverage, identity/provenance/timestamp/text coverage, duplicate pressure, real seed/comment retrieval, fresh-run Jaccard overlap, and human audit labels.

Example:

```bash
sugar weibo-qualify \
  --terms-file examples/weibo_research_query_plan.txt \
  --seeds-file examples/weibo_smoke_seeds.txt \
  --replicates 2 \
  --target 5000 \
  --pages-per-task 2 \
  --max-pages-per-query 25 \
  --task-delay 2 \
  --audit-size 100 \
  --name weibo_acceptance \
  --output ./runs/weibo_acceptance
```

Outputs include independent SQLite harvest checkpoints, real-post investigation outputs, a JSON qualification result, a Markdown report, and a deterministic human-audit CSV.

Fill `human_relevant` and `human_provenance_ok` in the audit CSV, then rerun with `--audit-file` to include the human review in the acceptance result.

`PASS` means the configured SUGAR project thresholds were met for the surfaces actually observed. It does not mean complete recall of Weibo, representative public opinion, or proof of influence. `CONDITIONAL` means automated requirements passed but advisory or human-review gates remain. `FAIL` means at least one required project threshold failed.

This is a project research-quality profile, not an external certification or security authorization.
