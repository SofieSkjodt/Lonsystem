# Lonsystem - tjekker om der er nyt paa GitHub, og deployer kun hvis der er.
# Koeres automatisk hvert 5. minut af Task Scheduler-opgaven "LonsystemAutoDeploy"
# (se deploy/setup_scheduled_task.ps1).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

git fetch origin --quiet

$local = git rev-parse HEAD
$remote = git rev-parse origin/main

if ($local -eq $remote) {
    exit 0
}

Write-Host "$(Get-Date) - Ny kode fundet ($local -> $remote). Deployer..."
& "$root\deploy\deploy.ps1"
