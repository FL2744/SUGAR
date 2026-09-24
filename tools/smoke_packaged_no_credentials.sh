#!/bin/sh
set -eu

BRIDGE="${1:?usage: smoke_packaged_no_credentials.sh /path/to/sugar-bridge [workdir]}"
ROOT="${2:-/tmp/sugar-packaged-no-credentials}"
PROJECT="$ROOT/project"

unset SUGAR_LLM_API_KEY SUGAR_X_BEARER_TOKEN SUGAR_BLUESKY_IDENTIFIER
unset SUGAR_BLUESKY_APP_PASSWORD SUGAR_MASTODON_TOKEN SUGAR_WEIBO_COOKIE

rm -rf "$ROOT"
mkdir -p "$ROOT"

printf '{"workspace":"%s","name":"Packaged State Smoke"}\n' "$PROJECT" > "$ROOT/workspace.json"
"$BRIDGE" workspace-init --config "$ROOT/workspace.json"

printf '{"workspace":"%s","question":"What public program activity is documented?","geographies":["Exampleland"],"target_audiences":["students"],"known_entities":["Example Center"],"languages":["en"],"collection_mode":"quick"}\n' "$PROJECT" > "$ROOT/requirement.json"
"$BRIDGE" research-requirement --config "$ROOT/requirement.json"

printf '{"workspace":"%s","ai_expand":false}\n' "$PROJECT" > "$ROOT/compile.json"
"$BRIDGE" research-compile --config "$ROOT/compile.json"

printf '{"workspace":"%s","decision":"approved","reviewer":"Packaged Smoke Analyst","review_note":"Deterministic packaged workflow validation."}\n' "$PROJECT" > "$ROOT/strategy-approve.json"
"$BRIDGE" research-strategy-update --config "$ROOT/strategy-approve.json"

printf '{"workspace":"%s"}\n' "$PROJECT" > "$ROOT/plan.json"
"$BRIDGE" research-plan --config "$ROOT/plan.json"

cat > "$ROOT/partner.csv" <<'CSV'
platform,native_id,canonical_url,original_text,usage_restrictions
partner,1,https://example.invalid/1,Example public program record,Research use only
CSV
printf '{"workspace":"%s","source_file":"%s/partner.csv","source_system":"partner-export","output_file":"%s/raw/partner"}\n' "$PROJECT" "$ROOT" "$PROJECT" > "$ROOT/import.json"
"$BRIDGE" research-import --config "$ROOT/import.json"
printf '{"workspace":"%s"}\n' "$PROJECT" > "$ROOT/prepare-review.json"
"$BRIDGE" research-prepare-review --config "$ROOT/prepare-review.json"
printf '{"workspace":"%s","name":"first-run-handoff"}\n' "$PROJECT" > "$ROOT/handoff.json"
"$BRIDGE" research-handoff --config "$ROOT/handoff.json"
printf '{"bundle_directory":"%s/exports/first-run-handoff"}\n' "$PROJECT" > "$ROOT/verify.json"
"$BRIDGE" research-handoff-verify --config "$ROOT/verify.json"
"$BRIDGE" workspace-status --config "$ROOT/workspace.json"

test -s "$PROJECT/sugar-project.json"
test -s "$PROJECT/state/research-requirement.json"
test -s "$PROJECT/state/research-strategy.json"
test -s "$PROJECT/state/search-plan.json"
test -s "$PROJECT/raw/partner.jsonl"
test -s "$PROJECT/raw/partner.import.json"
test -s "$PROJECT/state/research-observations.csv"
test -s "$PROJECT/state/state-assessments.jsonl"
test -s "$PROJECT/exports/first-run-handoff/verification.json"
grep -q '"status": "pass"' "$PROJECT/exports/first-run-handoff/verification.json"

echo "PASS: packaged no-credential research workflow"
