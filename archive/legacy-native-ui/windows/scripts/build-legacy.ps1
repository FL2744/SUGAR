param(
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"
$WindowsDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $WindowsDir "..")).Path
$DistDir = Join-Path $WindowsDir "dist"
$BuildDir = Join-Path $WindowsDir "build"
$PythonCommand = Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1
$PythonExe = $PythonCommand.Source
$PythonBasePrefix = (& $PythonExe -c "import sys; print(sys.base_prefix)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $PythonBasePrefix) { throw "Could not determine the Python installation used for this build" }

# PyInstaller resolves native dependencies through PATH. Developer environments can put
# Windows API-set DLLs from another Windows build ahead of the host OS DLLs, which makes
# the frozen QtCore fail to load. Keep the build's DLL search path limited to Python and
# the Windows installation being targeted.
$OriginalPath = $env:PATH
$BuildPathEntries = @(
    (Split-Path $PythonExe -Parent),
    $PythonBasePrefix,
    (Join-Path $env:WINDIR "System32"),
    $env:WINDIR,
    (Join-Path $env:WINDIR "System32\Wbem")
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
$env:PATH = [string]::Join([IO.Path]::PathSeparator, [string[]]$BuildPathEntries)

try {
$WindowsDirPrefix = [IO.Path]::GetFullPath($WindowsDir).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
foreach ($outputDirectory in @($DistDir, $BuildDir)) {
    if (Test-Path $outputDirectory) {
        $resolvedOutputDirectory = (Resolve-Path $outputDirectory).Path
    } else {
        $resolvedOutputDirectory = [IO.Path]::GetFullPath($outputDirectory)
    }
    if (-not $resolvedOutputDirectory.StartsWith($WindowsDirPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a Windows build path outside $($WindowsDir): $resolvedOutputDirectory"
    }
}

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $DistDir, $BuildDir
}
New-Item -ItemType Directory -Force -Path $DistDir, $BuildDir | Out-Null

Write-Host "Building SUGAR Windows GUI..."
& $PythonExe -m PyInstaller `
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
    --add-data "$(Join-Path $RepoRoot 'docs\classroom-quick-start.md');." `
    (Join-Path $WindowsDir "app.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller GUI build failed with exit code $LASTEXITCODE" }

Write-Host "Building SUGAR backend bridge..."
$BridgeDist = Join-Path $BuildDir "bridge-dist"
& $PythonExe -m PyInstaller `
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
if ($LASTEXITCODE -ne 0) { throw "PyInstaller backend bridge build failed with exit code $LASTEXITCODE" }

$AppDir = Join-Path $DistDir "SUGAR"
$BridgeExe = Join-Path $BridgeDist "sugar-bridge.exe"
if (-not (Test-Path $BridgeExe)) { throw "PyInstaller did not create sugar-bridge.exe" }
Copy-Item -Force $BridgeExe (Join-Path $AppDir "sugar-bridge.exe")

$CliWrappers = @{
    "sugar.cmd" = "cli"
    "sugar-project.cmd" = "project"
    "sugar-state.cmd" = "state"
    "sugar-intel.cmd" = "intel"
}
foreach ($wrapper in $CliWrappers.GetEnumerator()) {
    $wrapperText = "@echo off`r`n`"%~dp0sugar-bridge.exe`" $($wrapper.Value) %*`r`n"
    Set-Content -Encoding ASCII -Path (Join-Path $AppDir $wrapper.Key) -Value $wrapperText
}

Copy-Item -Force (Join-Path $WindowsDir "README.md") (Join-Path $AppDir "README-Windows.md")
Copy-Item -Force (Join-Path $RepoRoot "docs\classroom-quick-start.md") (Join-Path $AppDir "CLASSROOM-QUICK-START.md")
Copy-Item -Force (Join-Path $RepoRoot "LICENSE") (Join-Path $AppDir "LICENSE")
Copy-Item -Force (Join-Path $RepoRoot "NOTICE") (Join-Path $AppDir "NOTICE")
Copy-Item -Force (Join-Path $RepoRoot "THIRD_PARTY_NOTICES.md") (Join-Path $AppDir "THIRD_PARTY_NOTICES.md")
Copy-Item -Recurse -Force (Join-Path $RepoRoot "third_party_licenses") (Join-Path $AppDir "third_party_licenses")
& $PythonExe (Join-Path $RepoRoot "tools\collect_third_party_licenses.py") `
    --output (Join-Path $AppDir "licenses") `
    --extra windows
if ($LASTEXITCODE -ne 0) { throw "Third-party license collection failed with exit code $LASTEXITCODE" }

$PythonVersion = (& $PythonExe --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "Could not read the Python build version" }
$VersionInfo = @{
    built_at_utc = [DateTime]::UtcNow.ToString("o")
    python = $PythonVersion
    architecture = $env:PROCESSOR_ARCHITECTURE
    bridge_protocol = 3
} | ConvertTo-Json -Depth 3
$VersionInfo | Set-Content -Encoding UTF8 (Join-Path $AppDir "build-info.json")

$ZipPath = Join-Path $DistDir "SUGAR-Windows-x64.zip"
Remove-Item -Force -ErrorAction SilentlyContinue $ZipPath
Compress-Archive -Path $AppDir -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "Windows package created: $AppDir"
Write-Host "Portable ZIP created: $ZipPath"
} finally {
    $env:PATH = $OriginalPath
}
