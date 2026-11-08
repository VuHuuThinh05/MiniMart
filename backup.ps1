$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force .\backups | Out-Null
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
docker compose -p minimart_demo exec -T postgres pg_dump -U minimart -d minimart -Fc -f /tmp/minimart.dump
if ($LASTEXITCODE -ne 0) { throw 'Backup failed' }
docker compose -p minimart_demo cp postgres:/tmp/minimart.dump ".\backups\minimart_$stamp.dump"
if ($LASTEXITCODE -ne 0) { throw 'Copy backup failed' }
Get-Item ".\backups\minimart_$stamp.dump"
