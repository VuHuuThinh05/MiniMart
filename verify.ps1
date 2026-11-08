$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
docker compose -p minimart_demo run --rm tools python -u scripts/verify.py
if ($LASTEXITCODE -ne 0) { throw 'Verification failed' }
