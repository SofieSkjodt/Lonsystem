# Lønsystem – deploy-script til PRODUKTIONSMASKINEN.
#
# Forudsætninger:
#   - Repoet er klonet lokalt på produktionsmaskinen UDEN for OneDrive (fx C:\Lonsystem).
#   - app/.env findes allerede på denne maskine (kopieret fra app/.env.example, ikke sporet i git).
#   - Serveren kører som en Windows-service (fx via NSSM) med navnet angivet i $ServiceName.
#
# Kør fra selve produktionsmaskinen, eller eksternt via:
#   ssh produktionsmaskine "cd C:\Lonsystem; powershell -File deploy\deploy.ps1"

$ErrorActionPreference = "Stop"
$ServiceName = "Lonsystem"   # ret til det faktiske NSSM/Task Scheduler-servicenavn

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1/5: Tager backup af databasen =="
python backup\backup.py

Write-Host "== 2/5: Stopper servicen =="
try { Stop-Service -Name $ServiceName -Confirm:$false } catch { Write-Warning "Kunne ikke stoppe '$ServiceName' (kører den ikke som service endnu?)" }

Write-Host "== 3/5: Henter seneste kode fra GitHub (main) =="
git fetch origin
git checkout main
git reset --hard origin/main

Write-Host "== 4/5: Installerer evt. nye Python-afhængigheder =="
python -m pip install -r app\requirements.txt

Write-Host "== 5/5: Genstarter servicen =="
Start-Service -Name $ServiceName

Write-Host "Deploy færdig. Tjek http://localhost:8001 og servicens log."
