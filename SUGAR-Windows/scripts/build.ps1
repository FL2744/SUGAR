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

Write-Host "Building SUGAR Windows GUI..."
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name SUGAR `
    --distpath $DistDir `
    --workpath (Join-Path $BuildDir "gui") `
    --specpath $BuildDir `
    --paths $RepoRoot `
    --paths $WindowsDir `
    --add-data "$(Join-Path $RepoRoot 'sugar-logo.png');." `
    (Join-Path $WindowsDir "app.py")

Write-Host "Building SUGAR backend bridge..."
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

$AppDir = Join-Path $DistDir "SUGAR"
$BridgeExe = Join-Path $BridgeDist "sugar-bridge.exe"
if (-not (Test-Path $BridgeExe)) { throw "PyInstaller did not create sugar-bridge.exe" }
Copy-Item -Force $BridgeExe (Join-Path $AppDir "sugar-bridge.exe")

Copy-Item -Force (Join-Path $WindowsDir "README.md") (Join-Path $AppDir "README-Windows.md")

# Give classroom testers a useful zero-credential path immediately after launch.
$SamplesDir = Join-Path $AppDir "Samples"
New-Item -ItemType Directory -Force -Path $SamplesDir | Out-Null
Copy-Item -Force (Join-Path $RepoRoot "examples\example-spreadsheet.xlsx") (Join-Path $SamplesDir "example-spreadsheet.xlsx")
Copy-Item -Force (Join-Path $RepoRoot "examples\example-map.html") (Join-Path $SamplesDir "example-map.html")
Copy-Item -Force (Join-Path $RepoRoot "examples\example-analysis.pdf") (Join-Path $SamplesDir "example-analysis.pdf")
Copy-Item -Force (Join-Path $RepoRoot "docs\classroom-preview.md") (Join-Path $SamplesDir "classroom-preview.md")

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
    runtime = "bundled"
    ordinary_users_need_python = $false
} | ConvertTo-Json -Depth 3
$VersionInfo | Set-Content -Encoding UTF8 (Join-Path $AppDir "build-info.json")

$ZipPath = Join-Path $DistDir "SUGAR-Windows-x64.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $ZipPath
Compress-Archive -Path $AppDir -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "Windows package created: $AppDir"
Write-Host "Portable ZIP created: $ZipPath"
Write-Host "Build version: $ProjectVersion ($GitCommit)"
