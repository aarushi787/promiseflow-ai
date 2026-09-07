$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtimePath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePath)) { throw 'Run the setup steps in README.md first.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend\dist\index.html'))) { throw 'Build the frontend first: npm.cmd run build' }
Write-Host 'PromiseFlow AI: http://127.0.0.1:8017'
& $runtimePath -m uvicorn backend.app:app --host 127.0.0.1 --port 8017
