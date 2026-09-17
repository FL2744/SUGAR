param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"
$WindowsDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $WindowsDir "..")).Path
$DistDir = Join-Path $WindowsDir "dist"
$BuildDir = Join-Path $WindowsDir "build"
$VersionLine = Select-String -Path (Join-Path $RepoRoot "pyproject.toml") -Pattern '^version = "([^"]+)"' | Select-Object -First 1
$Version = if ($VersionLine) { [regex]::Match($VersionLine.Line, '^version = "([^"]+)"').Groups[1].Value } else { "" }
$ProtocolLine = Select-String -Path (Join-Path $RepoRoot "sugar_bridge.py") -Pattern '^BRIDGE_PROTOCOL_VERSION = (\d+)' | Select-Object -First 1
$BridgeProtocol = if ($ProtocolLine) { [regex]::Match($ProtocolLine.Line, '^BRIDGE_PROTOCOL_VERSION = (\d+)').Groups[1].Value } else { "" }
if ([string]::IsNullOrWhiteSpace($Version) -or [string]::IsNullOrWhiteSpace($BridgeProtocol)) {
    throw "Could not determine the package version or bridge protocol from the canonical sources."
}

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

$VersionInfo = @{
    version = $Version
    built_at_utc = [DateTime]::UtcNow.ToString("o")
    python = (python --version 2>&1 | Out-String).Trim()
    architecture = $env:PROCESSOR_ARCHITECTURE
    bridge_protocol = [int]$BridgeProtocol
} | ConvertTo-Json -Depth 3
$VersionInfo | Set-Content -Encoding UTF8 (Join-Path $AppDir "build-info.json")

$ZipPath = Join-Path $DistDir "SUGAR-Windows-x64.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $ZipPath
Compress-Archive -Path $AppDir -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "Windows package created: $AppDir"
Write-Host "Portable ZIP created: $ZipPath"
