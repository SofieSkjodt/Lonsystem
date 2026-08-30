# Lonsystem - fuldt, oejeblikkeligt deploy: henter ny kode OG genstarter serveren
# med det samme. Bruges til manuelt/haste-deploy (fx Del 5 i PRODUKTION_OPSAETNING.md).
#
# Den automatiske 5-minutters-tjek (auto_deploy_check.ps1) bruger IKKE denne -
# den kalder kun pull_update.ps1, og lader restart_server.ps1 (kl. 23:00) staa
# for genstarten, saa koerende brugere ikke afbrydes midt paa dagen.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

& "$root\deploy\pull_update.ps1"
& "$root\deploy\restart_server.ps1"
