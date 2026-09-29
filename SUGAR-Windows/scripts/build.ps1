$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$UnifiedBuilder = Join-Path $RepoRoot "SUGAR-Desktop\scripts\build-windows.ps1"
& $UnifiedBuilder
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "The shared SUGAR Desktop build failed with exit code $LASTEXITCODE"
}
