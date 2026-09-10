# Grounded AI triage

SUGAR's AI triage step turns an existing normalized post dataset into a structured observation dataset for human review. It is a prioritization and extraction layer, not an automated finding-verification system.

## Command-line use

After collecting posts with SUGAR:

```bash
sugar triage social_search_posts_20260910_120000.csv \
  --provider openai \
  --model gpt-5.6-luna
```

For Virginia Tech ARC's OpenAI-compatible endpoint:

```bash
sugar triage social_search_posts_20260910_120000.csv \
  --provider arc \
  --model <ARC_MODEL_NAME>
```

The command writes:

- `<source>_observations.csv`
- `<source>_observations.xlsx`
- `<source>_observations.metadata.json`

The input can be a current SUGAR CSV/XLSX export or a compatible legacy SUGAR export containing the older alias columns.

The LLM key is read from `SUGAR_LLM_API_KEY` when set; otherwise the CLI prompts for it without echoing the value.

## Project scope

The default project context is designed for the current Diplomacy Lab research problem: overt, public PRC government-supported cultural, educational, technical, commercial, and public-diplomacy activity outside mainland China, with emphasis on current program activity, audiences, geographic concentration, narratives, explicit anti-U.S. content, joint activity, and explicit U.S. public-diplomacy overlap.

A different project context can be supplied without changing code:

```bash
sugar triage results.csv --project-context-file my_scope.txt
```

The exact project context is recorded in the output metadata for reproducibility.

## Grounding rules

The model is instructed to treat all collected source text as untrusted data rather than instructions. It must return structured JSON and short exact evidence spans copied from the source or its stored translation.

SUGAR then checks those spans against the actual record. A model-generated span that cannot be found in the source is discarded.

Several high-consequence labels require their own validated evidence span and are removed otherwise:

- `anti_us_explicit`
- `china_russia_joint_activity`
- `third_country_joint_activity`
- `us_overlap_explicit`

An AI result marked `relevant` with no valid evidence span is automatically downgraded to `uncertain`, its relevance confidence is capped below 0.5, and `needs_context` is added.

A location suggested by AI triage is used only when the model also supplies a valid source span labeled `location`. Existing collector/enrichment location evidence is not overwritten.

## Controlled labels

The initial triage vocabulary is intentionally small:

- institution, program, and event activity
- narrative signals
- education
- technology/innovation
- commercial diplomacy
- strategic audiences: students, emerging leaders, entrepreneurs, technical professionals
- explicit anti-U.S. content
- China-Russia joint activity
- third-country joint activity
- explicit U.S. overlap
- needs-context / triage-error states

These are triage labels, not influence scores. Adding or changing labels should be treated as a methodology change and tested against reviewed examples.

## Human review

Successful AI-triaged observations enter `verification_state = ai_triaged`. A human reviewer then examines the source, grounded spans, extracted fields, and surrounding context.

Only an explicit human action with a named reviewer can move an observation to `human_verified` or `rejected`. Incomplete or contradictory cases can be moved to `needs_followup` and later reopened.

If one record fails AI triage because of malformed model output or another per-record error, the default batch behavior does not discard the rest of the run. The affected record becomes a `needs_followup` observation with `triage_error` and `needs_context` labels. `--fail-fast` is available for testing and debugging.

## What AI triage does not claim

Triage does not determine covert intent, causation, persuasion effects, population-level influence, or a single China-influence score. It structures and prioritizes observable public evidence for human analysts.

The resulting observation dataset is therefore suitable for a review queue and downstream coding, but unverified AI-triaged rows should not automatically be treated as final analytical findings.
