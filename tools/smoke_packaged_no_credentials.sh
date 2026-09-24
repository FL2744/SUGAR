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
printf '{"bundle_directory":"%s/outputs/exports/first-run-handoff"}\n' "$PROJECT" > "$ROOT/verify.json"
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
test -s "$PROJECT/outputs/exports/first-run-handoff/verification.json"
grep -q '"status": "pass"' "$PROJECT/outputs/exports/first-run-handoff/verification.json"

printf '{"workspace":"%s","max_queries":5,"max_records_per_query":50}\n' "$PROJECT" > "$ROOT/next-evidence.json"
"$BRIDGE" intel-next-evidence --config "$ROOT/next-evidence.json"
printf '{"workspace":"%s"}\n' "$PROJECT" > "$ROOT/content-lineage.json"
"$BRIDGE" intel-content-lineage --config "$ROOT/content-lineage.json"
"$BRIDGE" intel-evidence-graph --config "$ROOT/content-lineage.json"
"$BRIDGE" intel-robustness --config "$ROOT/content-lineage.json"
printf '{"workspace":"%s","query":"education program students","top_k":5}\n' "$PROJECT" > "$ROOT/semantic-search.json"
"$BRIDGE" intel-semantic-search --config "$ROOT/semantic-search.json"

cat > "$ROOT/public-page.html" <<'HTML'
<html><head><title>Public program page</title><script>notStored()</script></head>
<body><h1>Public program</h1><p>Applications are open to students.</p></body></html>
HTML
printf '{"workspace":"%s","html_file":"%s/public-page.html","source_url":"https://example.invalid/program"}\n' "$PROJECT" "$ROOT" > "$ROOT/capture.json"
"$BRIDGE" intel-capture-page --config "$ROOT/capture.json"

python3 - "$ROOT/program.wav" <<'PY'
import sys
import wave

with wave.open(sys.argv[1], "wb") as audio:
    audio.setnchannels(1)
    audio.setsampwidth(2)
    audio.setframerate(8000)
    audio.writeframes(b"\0\0" * 8000 * 5)
PY
cat > "$ROOT/program.vtt" <<'VTT'
WEBVTT

00:00:02.000 --> 00:00:04.000
The speaker describes the program.
VTT
printf '{"workspace":"%s","media_file":"%s/program.wav","transcript":"%s/program.vtt","source_url":"https://example.invalid/video"}\n' "$PROJECT" "$ROOT" "$ROOT" > "$ROOT/media.json"
"$BRIDGE" intel-media-ingest --config "$ROOT/media.json"
MEDIA_MANIFEST=$(find "$PROJECT/media" -type f -name 'media_*.json' | head -n 1)
OBSERVATION_ID=$(python3 - "$PROJECT/state/research-observations.csv" <<'PY'
import csv
import sys

with open(sys.argv[1], encoding="utf-8-sig", newline="") as stream:
    print(next(csv.DictReader(stream))["observation_id"])
PY
)
printf '{"workspace":"%s","media_manifest":"%s","observation_id":"%s","media_start":"00:02","media_end":"00:04","quote":"The speaker describes the program."}\n' "$PROJECT" "$MEDIA_MANIFEST" "$OBSERVATION_ID" > "$ROOT/media-attach.json"
"$BRIDGE" intel-media-attach --config "$ROOT/media-attach.json"
"$BRIDGE" intel-evidence-graph --config "$ROOT/content-lineage.json"

test -s "$PROJECT/outputs/intelligence/next_evidence_recommendation.json"
test -s "$PROJECT/outputs/intelligence/content_lineage.json"
test -s "$PROJECT/outputs/intelligence/temporal_evidence_graph.json"
test -s "$PROJECT/outputs/intelligence/finding_robustness.json"
test -s "$PROJECT/outputs/intelligence/semantic_evidence_search.json"
test -n "$MEDIA_MANIFEST"
test -s "$PROJECT/outputs/intelligence/temporal_evidence_graph.json"

echo "PASS: packaged no-credential research workflow and research intelligence operations"
