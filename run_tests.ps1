$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
# This is a separate temporary PostgreSQL service, never the demo database.
docker compose -p minimart_demo --profile test run --rm test
if ($LASTEXITCODE -ne 0) { throw 'Integration tests failed; see evidence/tests/integration.json' }
