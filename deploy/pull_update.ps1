# Lonsystem - henter ny kode fra GitHub og opdaterer afhaengigheder.
# Genstarter IKKE serveren - den koerende proces bliver ved med at koere med den
# gamle kode i hukommelsen indtil naeste genstart (se deploy/restart_server.ps1,
# koeres hver nat kl. 23:00 af Task Scheduler-opgaven "LonsystemNightlyRestart").
#
# Koeres automatisk af deploy/auto_deploy_check.ps1 hvert 5. minut, naar der er
# nye commits paa main. Kan ogsaa koeres manuelt.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1/3: Tager backup af databasen =="
py backup\backup.py

Write-Host "== 2/3: Henter seneste kode fra GitHub (main) =="
git fetch origin
git checkout main
git reset --hard origin/main

Write-Host "== 3/3: Installerer evt. nye Python-afhaengigheder =="
py -m pip install -r app\requirements.txt

Write-Host "Kode opdateret. Serveren koerer stadig med den gamle kode indtil naeste genstart kl. 23:00 (eller koer restart_server.ps1 manuelt)."
