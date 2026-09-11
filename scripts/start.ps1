param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')
uv run docweave --port $Port
exit $LASTEXITCODE
