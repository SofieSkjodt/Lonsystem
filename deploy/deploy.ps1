# Lonsystem - deploy-script til PRODUKTIONSMASKINEN.
#
# Forudsaetninger:
#   - Repoet er klonet lokalt paa produktionsmaskinen UDEN for OneDrive (fx C:\Lonsystem).
#   - app/.env findes allerede paa denne maskine (kopieret fra app/.env.example, ikke sporet i git).
#   - Serveren koerer som en Task Scheduler-opgave (se deploy/setup_scheduled_task.ps1)
#     med navnet angivet i $TaskName.
#
# Koer fra selve produktionsmaskinen, eller eksternt via:
#   ssh produktionsmaskine "cd C:\Lonsystem; powershell -File deploy\deploy.ps1"

$ErrorActionPreference = "Stop"
$TaskName = "Lonsystem"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1/5: Tager backup af databasen =="
py backup\backup.py

Write-Host "== 2/5: Stopper opgaven (og den koerende server-proces) =="
try { Stop-ScheduledTask -TaskName $TaskName } catch { Write-Warning "Kunne ikke stoppe opgaven '$TaskName' (er den oprettet endnu?)" }
Start-Sleep -Seconds 2

Write-Host "== 3/5: Henter seneste kode fra GitHub (main) =="
git fetch origin
git checkout main
git reset --hard origin/main

Write-Host "== 4/5: Installerer evt. nye Python-afhaengigheder =="
py -m pip install -r app\requirements.txt

Write-Host "== 5/5: Genstarter opgaven =="
Start-ScheduledTask -TaskName $TaskName

Write-Host "Deploy faerdig. Tjek http://localhost:8001 om lidt."
