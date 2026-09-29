$ErrorActionPreference = "Stop"
$DesktopDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $DesktopDir "..")).Path
$BinaryDir = Join-Path $DesktopDir "src-tauri\binaries"
$PythonCommand = Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1
$PythonExe = $PythonCommand.Source
& $PythonExe -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Push-Location $RepoRoot
    try {
        & $PythonExe -m pip install -e ".[windows]"
        if ($LASTEXITCODE -ne 0) { throw "Could not install the Python bridge packaging dependencies" }
    } finally { Pop-Location }
}
$HostLine = (& rustc -vV | Select-String '^host:').ToString()
if (-not $HostLine) { throw "Could not determine the Rust target triple. Install the Rust toolchain first." }
$RustTarget = $HostLine.Split(':', 2)[1].Trim()
if ($RustTarget -ne "x86_64-pc-windows-msvc" -and $RustTarget -ne "aarch64-pc-windows-msvc") {
    throw "This script expects a Windows MSVC target, received $RustTarget."
}
$PythonMachine = (& $PythonExe -c "import platform; print(platform.machine())").Trim().ToUpperInvariant()
if (($RustTarget.StartsWith("x86_64") -and $PythonMachine -notin @("AMD64", "X86_64")) -or
    ($RustTarget.StartsWith("aarch64") -and $PythonMachine -notin @("ARM64", "AARCH64"))) {
    throw "The Python bridge architecture ($PythonMachine) must match the Rust target ($RustTarget)."
}
$PythonBasePrefix = (& $PythonExe -c "import sys; print(sys.base_prefix)").Trim()
$OriginalPath = $env:PATH
$PathEntries = @((Split-Path $PythonExe -Parent), $PythonBasePrefix, (Join-Path $env:WINDIR "System32"), $env:WINDIR) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
$env:PATH = [string]::Join([IO.Path]::PathSeparator, [string[]]$PathEntries)
try {
    New-Item -ItemType Directory -Force -Path $BinaryDir | Out-Null
    $BridgeName = "sugar-bridge-$RustTarget"
    & $PythonExe -m PyInstaller --noconfirm --clean --console --onefile --name $BridgeName `
        --distpath $BinaryDir --workpath (Join-Path $DesktopDir "build\bridge") `
        --specpath (Join-Path $DesktopDir "build") --paths $RepoRoot (Join-Path $RepoRoot "sugar_bridge.py")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller sidecar build failed with exit code $LASTEXITCODE" }
    $env:PATH = $OriginalPath
    Push-Location $DesktopDir
    try {
        if (-not (Test-Path (Join-Path $DesktopDir "node_modules"))) { npm install; if ($LASTEXITCODE -ne 0) { throw "npm install failed" } }
        npm run tauri -- build --bundles msi
        if ($LASTEXITCODE -ne 0) { throw "Tauri Windows build failed with exit code $LASTEXITCODE" }
    } finally { Pop-Location }
    Write-Host "Unified SUGAR desktop package created under $DesktopDir\src-tauri\target\release\bundle"
} finally {
    $env:PATH = $OriginalPath
}
