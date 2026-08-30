# Lonsystem - tjekker om der er nyt paa GitHub, og deployer kun hvis der er.
# Koeres automatisk hvert 5. minut af Task Scheduler-opgaven "LonsystemAutoDeploy"
# (se deploy/setup_scheduled_task.ps1). Skriver alt til deploy/auto_deploy.log.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$LogFile = "$root\deploy\auto_deploy.log"

function Write-Log($message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $message" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

Write-Log "Tjek om der er aendringer"

git fetch origin --quiet

$local = git rev-parse HEAD
$remote = git rev-parse origin/main

if ($local -eq $remote) {
    Write-Log "Ingen aendringer"
    exit 0
}

Write-Log "Aendringer fundet til Lonsystem ($($local.Substring(0,7)) -> $($remote.Substring(0,7)))"
Write-Log "Starter git pull og deploy"

try {
    $output = & "$root\deploy\deploy.ps1" 2>&1 | Out-String
    foreach ($line in ($output -split "`r?`n")) {
        if ($line.Trim()) { Write-Log $line.Trim() }
    }
    Write-Log "Succes - opdateret til $($remote.Substring(0,7))"
} catch {
    Write-Log "FEJL under deploy: $_"
    throw
}
