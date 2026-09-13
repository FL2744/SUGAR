# Weibo qualification workflow

`weibo-qualify` evaluates whether a large Weibo research collection is reproducible, well-provenanced, and suitable for downstream analysis.

It combines fresh collection replicates, checkpoint metrics, real-post validation, and a human relevance/provenance audit. A resumed checkpoint is not counted as a reproducibility replicate.

Default project checks include unique record count, task completion/failure, access-limited tasks, query coverage, identity/provenance/timestamp/text coverage, duplicate pressure, real seed/comment retrieval, fresh-run Jaccard overlap, and human audit labels.

## Inputs

Create a UTF-8 query file with one project-approved term per line and a seed file with one known public Weibo URL/ID per line. Blank lines and lines beginning with `#` are ignored.

Example command:

```bash
sugar weibo-qualify \
  --terms-file ./weibo_terms.txt \
  --seeds-file ./weibo_seeds.txt \
  --replicates 2 \
  --target 5000 \
  --pages-per-task 2 \
  --max-pages-per-query 25 \
  --task-delay 2 \
  --audit-size 100 \
  --name weibo_acceptance \
  --output ./runs/weibo_acceptance
```

For qualification, `--target` is a minimum unique-record acceptance floor. It does **not** stop collection early: the complete bounded query/page plan is run so later queries are not silently excluded from coverage measurement.

Outputs include independent SQLite harvest checkpoints, real-post investigation outputs, a JSON qualification result, a Markdown report, and a deterministic human-audit CSV.

Fill `human_relevant` and `human_provenance_ok` in the audit CSV, then rerun with `--audit-file` to include the human review in the acceptance result.

## Current access boundary

Weibo surfaces can have different access requirements at the same time. SUGAR therefore records status/search/comments/reposts/account-history separately. In current bounded live testing, a known public status and its first public comment page were anonymously retrievable while anonymous keyword search, repost history, and account history were access-limited. A legitimate team-supplied session may be used where Weibo requires it; SUGAR does not automate login, create visitor credentials, extract browser credentials, solve verification challenges, rotate identities, or bypass platform controls.

This means an anonymous campaign can correctly fail the search-coverage acceptance checks while seed-led public investigation remains operational. That is an observed access condition, not a scraper error and not evidence that zero matching posts exist.

`PASS` means the configured SUGAR project thresholds were met for the surfaces actually observed. It does not mean complete recall of Weibo, representative public opinion, or proof of influence. `CONDITIONAL` means automated requirements passed but advisory or human-review gates remain. `FAIL` means at least one required project threshold failed.

This is a project research-quality profile, not an external certification or security authorization.
