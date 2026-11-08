$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
docker compose -p minimart_demo run --rm tools python -u scripts/benchmark.py
if ($LASTEXITCODE -ne 0) { throw 'BM01 failed' }
docker compose -p minimart_demo run --rm tools python -u scripts/benchmark_design.py
if ($LASTEXITCODE -ne 0) { throw 'BM02/BM03 failed' }
