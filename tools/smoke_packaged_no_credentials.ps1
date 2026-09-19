param(
    [Parameter(Mandatory = $true)]
    [string]$Bridge,
    [string]$WorkRoot = (Join-Path $env:TEMP "sugar-packaged-no-credentials")
)

$ErrorActionPreference = "Stop"
foreach ($name in @(
    "SUGAR_LLM_API_KEY",
    "SUGAR_X_BEARER_TOKEN",
    "SUGAR_BLUESKY_IDENTIFIER",
    "SUGAR_BLUESKY_APP_PASSWORD",
    "SUGAR_MASTODON_TOKEN",
    "SUGAR_WEIBO_COOKIE"
)) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

Remove-Item -Recurse -Force $WorkRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $WorkRoot | Out-Null
$project = Join-Path $WorkRoot "project"

@{ workspace = $project; name = "Packaged State Smoke" } |
    ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $WorkRoot "workspace.json")
& $Bridge workspace-init --config (Join-Path $WorkRoot "workspace.json")
if ($LASTEXITCODE -ne 0) { throw "workspace-init failed" }

@{
    workspace = $project
    question = "What public program activity is documented?"
    geographies = @("Exampleland")
    target_audiences = @("students")
    known_entities = @("Example Center")
    languages = @("en")
    collection_mode = "quick"
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $WorkRoot "requirement.json")
& $Bridge research-requirement --config (Join-Path $WorkRoot "requirement.json")
if ($LASTEXITCODE -ne 0) { throw "research-requirement failed" }

@{ workspace = $project; ai_expand = $false } |
    ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $WorkRoot "compile.json")
& $Bridge research-compile --config (Join-Path $WorkRoot "compile.json")
if ($LASTEXITCODE -ne 0) { throw "research-compile failed" }

@{
    workspace = $project
    decision = "approved"
    reviewer = "Packaged Smoke Analyst"
    review_note = "Deterministic packaged workflow validation."
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $WorkRoot "strategy-approve.json")
& $Bridge research-strategy-update --config (Join-Path $WorkRoot "strategy-approve.json")
if ($LASTEXITCODE -ne 0) { throw "research-strategy-update failed" }

@{ workspace = $project } |
    ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $WorkRoot "plan.json")
& $Bridge research-plan --config (Join-Path $WorkRoot "plan.json")
if ($LASTEXITCODE -ne 0) { throw "research-plan failed" }

@'
platform,native_id,canonical_url,original_text,usage_restrictions
partner,1,https://example.invalid/1,Example public program record,Research use only
'@ | Set-Content -Encoding UTF8 (Join-Path $WorkRoot "partner.csv")
@{
    workspace = $project
    source_file = (Join-Path $WorkRoot "partner.csv")
    source_system = "partner-export"
    output_file = (Join-Path $project "raw\partner")
} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $WorkRoot "import.json")
& $Bridge research-import --config (Join-Path $WorkRoot "import.json")
if ($LASTEXITCODE -ne 0) { throw "research-import failed" }
& $Bridge workspace-status --config (Join-Path $WorkRoot "workspace.json")
if ($LASTEXITCODE -ne 0) { throw "workspace-status failed" }

foreach ($required in @(
    (Join-Path $project "sugar-project.json"),
    (Join-Path $project "state\research-requirement.json"),
    (Join-Path $project "state\research-strategy.json"),
    (Join-Path $project "state\search-plan.json"),
    (Join-Path $project "raw\partner.jsonl"),
    (Join-Path $project "raw\partner.import.json")
)) {
    if (-not (Test-Path $required)) {
        throw "Packaged no-credential workflow missing output: $required"
    }
}

Write-Host "PASS: packaged no-credential research workflow"
