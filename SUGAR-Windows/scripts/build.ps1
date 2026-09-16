param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"
$WindowsDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $WindowsDir "..")).Path
$DistDir = Join-Path $WindowsDir "dist"
$BuildDir = Join-Path $WindowsDir "build"

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $DistDir, $BuildDir
}
New-Item -ItemType Directory -Force -Path $DistDir, $BuildDir | Out-Null

$GitCommit = "unknown"
try {
    $GitCommit = (git -C $RepoRoot rev-parse HEAD 2>$null | Out-String).Trim()
} catch {}
$ProjectVersion = "unknown"
try {
    $ProjectVersion = (python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path(r'$RepoRoot\pyproject.toml').read_text(encoding='utf-8'))['project']['version'])" | Out-String).Trim()
} catch {}

$VersionInfo = @{
    product = "SUGAR"
    version = $ProjectVersion
    git_commit = $GitCommit
    built_at_utc = [DateTime]::UtcNow.ToString("o")
    python = (python --version 2>&1 | Out-String).Trim()
    architecture = $env:PROCESSOR_ARCHITECTURE
    bridge_protocol = 3
    runtime = "bundled-single-exe"
    ordinary_users_need_python = $false
} | ConvertTo-Json -Depth 3
$BuildInfoPath = Join-Path $BuildDir "build-info.json"
$VersionInfo | Set-Content -Encoding UTF8 $BuildInfoPath

# Build the console bridge first, then embed it inside the single GUI executable.
# The GUI extracts this private worker into PyInstaller's temporary bundle directory
# and launches it through QProcess, so users download only SUGAR.exe while long-running
# operations remain cancellable and isolated from the UI event loop.
Write-Host "Building embedded SUGAR backend worker..."
$BridgeDist = Join-Path $BuildDir "bridge-dist"
python -m PyInstaller `
    --noconfirm `
    --clean `
    --console `
    --onefile `
    --name sugar-bridge `
    --distpath $BridgeDist `
    --workpath (Join-Path $BuildDir "bridge") `
    --specpath $BuildDir `
    --paths $RepoRoot `
    (Join-Path $RepoRoot "sugar_bridge.py")

$BridgeExe = Join-Path $BridgeDist "sugar-bridge.exe"
if (-not (Test-Path $BridgeExe)) { throw "PyInstaller did not create the embedded sugar-bridge.exe worker" }

Write-Host "Building single-file SUGAR Windows application..."
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name SUGAR `
    --distpath $DistDir `
    --workpath (Join-Path $BuildDir "gui") `
    --specpath $BuildDir `
    --paths $RepoRoot `
    --paths $WindowsDir `
    --add-binary "$BridgeExe;." `
    --add-data "$(Join-Path $RepoRoot 'sugar-logo.png');." `
    --add-data "$(Join-Path $RepoRoot 'examples\example-spreadsheet.xlsx');Samples" `
    --add-data "$(Join-Path $RepoRoot 'examples\example-map.html');Samples" `
    --add-data "$(Join-Path $RepoRoot 'examples\example-analysis.pdf');Samples" `
    --add-data "$(Join-Path $RepoRoot 'docs\classroom-preview.md');Samples" `
    --add-data "$BuildInfoPath;." `
    (Join-Path $WindowsDir "app.py")

$SingleExe = Join-Path $DistDir "SUGAR.exe"
if (-not (Test-Path $SingleExe)) { throw "PyInstaller did not create SUGAR.exe" }
if ((Get-Item $SingleExe).Length -lt 1000000) { throw "SUGAR.exe is unexpectedly small" }

Write-Host "Single-file Windows application created: $SingleExe"
Write-Host "Users need only this file; Python and a separate bridge executable are not required."
Write-Host "Build version: $ProjectVersion ($GitCommit)"
