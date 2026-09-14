$ErrorActionPreference = "Stop"
$WindowsDir = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$RepoRoot = (Resolve-Path (Join-Path $WindowsDir "..")).Path
$env:PYTHONPATH = "$RepoRoot;$WindowsDir"
python (Join-Path $WindowsDir "app.py") @args
