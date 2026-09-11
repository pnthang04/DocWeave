$ErrorActionPreference = "Stop"

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$cacheHome = Join-Path $repoRoot ".cache\home"
New-Item -ItemType Directory -Force -Path $cacheHome | Out-Null
$env:USERPROFILE = $cacheHome

uv run babeldoc @args
