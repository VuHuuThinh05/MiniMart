param([switch]$ReloadData)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Run-Docker { & docker @args; if ($LASTEXITCODE -ne 0) { throw 'Docker command failed; stop and inspect the error above.' } }
Run-Docker compose -p minimart_demo up -d --wait --wait-timeout 120 postgres
Run-Docker compose -p minimart_demo build dashboard
if ($ReloadData) { Run-Docker compose -p minimart_demo run --rm tools python -u scripts/etl.py --force }
else { Run-Docker compose -p minimart_demo run --rm tools python -u scripts/etl.py }
Run-Docker compose -p minimart_demo up -d dashboard
$port = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { '8502' }
Start-Process "http://localhost:$port"
