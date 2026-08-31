# Lonsystem - genstarter produktionsserveren, saa den indlaeser den nyeste kode
# der er hentet ned af pull_update.ps1 siden sidste genstart.
#
# Efter genstart verificeres at serveren rent faktisk svarer paa /health.
# Svarer den ikke inden for et par forsoeg, rulles automatisk tilbage til den
# sidst bekraeftede koersende commit (deploy/last_known_good.txt, kun
# opdateret naar et helbredstjek er lykkedes) og genstartes igen. Uden dette
# ville en fejlbehaeftet commit fra den automatiske GitHub-pull (hvert 5.
# minut, ingen test-koersel undervejs) kunne slaa produktionen ned kl. 23:00
# uden at nogen faar besked foer naeste morgen.
#
# Koeres automatisk hver nat kl. 23:00 af Task Scheduler-opgaven
# "LonsystemNightlyRestart" (se deploy/setup_scheduled_task.ps1). Kan ogsaa
# koeres manuelt naar som helst for en oejeblikkelig genstart.

$ErrorActionPreference = "Stop"
$TaskName     = "Lonsystem"
$Root         = Split-Path -Parent $PSScriptRoot
$LogFile      = Join-Path $PSScriptRoot "restart.log"
$LastGoodFile = Join-Path $PSScriptRoot "last_known_good.txt"
$HealthUrl    = "http://localhost:8000/health"

# Git er installeret paa bruger-niveau og staar derfor kun paa denne brugers
# PATH - ikke SYSTEM's. Uden den fulde sti kan opgaven (som koerer som SYSTEM)
# slet ikke finde "git".
$Git = "C:\Users\LoenPC\AppData\Local\Programs\Git\cmd\git.exe"

function Write-Log($Message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp - $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
    Write-Host $Message
}

function Test-ServerHealthy {
    param([int]$Retries = 6, [int]$DelaySeconds = 5)
    for ($i = 1; $i -le $Retries; $i++) {
        Start-Sleep -Seconds $DelaySeconds
        try {
            $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) { return $true }
        } catch {
            Write-Log "  Helbredstjek forsoeg $i/$Retries fejlede: $($_.Exception.Message)"
        }
    }
    return $false
}

function Restart-LonsystemTask {
    Write-Log "Stopper opgaven '$TaskName'..."
    try { Stop-ScheduledTask -TaskName $TaskName } catch { Write-Log "Advarsel: kunne ikke stoppe opgaven '$TaskName' (er den oprettet endnu?)" }
    Start-Sleep -Seconds 2
    Write-Log "Starter opgaven '$TaskName'..."
    Start-ScheduledTask -TaskName $TaskName
}

function Get-CurrentCommit {
    Push-Location $Root
    try { return (& $Git rev-parse HEAD).Trim() }
    finally { Pop-Location }
}

Write-Log "=== Genstart startet ==="
Restart-LonsystemTask

if (Test-ServerHealthy) {
    Write-Log "Serveren svarer korrekt paa $HealthUrl."
    $currentCommit = Get-CurrentCommit
    Set-Content -Path $LastGoodFile -Value $currentCommit -Encoding utf8
    Write-Log "Commit $($currentCommit.Substring(0,7)) gemt som sidst bekraeftede koersende version."
    Write-Log "=== Genstart faerdig - OK ==="
    exit 0
}

Write-Log "ALVORLIG FEJL: Serveren svarede IKKE paa $HealthUrl efter genstart."

if (-not (Test-Path -LiteralPath $LastGoodFile)) {
    Write-Log "Ingen last_known_good.txt fundet endnu (foerste koersel siden denne rettelse) - kan ikke rulle automatisk tilbage. Kraever manuel handling."
    exit 1
}

$lastGoodCommit = (Get-Content -Path $LastGoodFile -Raw).Trim()
$currentCommit  = Get-CurrentCommit

if ($lastGoodCommit -eq $currentCommit) {
    Write-Log "Sidst bekraeftede version er den samme som den nuvaerende ($($currentCommit.Substring(0,7))) - en rollback vil ikke hjaelpe. Kraever manuel handling."
    exit 1
}

Write-Log "Ruller tilbage til sidst bekraeftede version $($lastGoodCommit.Substring(0,7))..."
Push-Location $Root
try {
    & $Git reset --hard $lastGoodCommit
} finally {
    Pop-Location
}

Restart-LonsystemTask

if (Test-ServerHealthy) {
    Write-Log "Rollback lykkedes - serveren svarer nu korrekt paa den tidligere version $($lastGoodCommit.Substring(0,7))."
    exit 0
} else {
    Write-Log "ALVORLIG FEJL: Serveren svarer stadig ikke, selv efter rollback til $($lastGoodCommit.Substring(0,7)). Kraever oejeblikkelig manuel handling."
    exit 1
}
