# installer.ps1
# Registrerer "Lønsystem Backup" som en Windows Task Scheduler-opgave.
# Opgaven kører kl. 00:00, 06:00, 12:00 og 18:00 hver dag.
#
# Kør dette script ÉN gang som Administrator:
#   Højreklik på installer.ps1 → Kør som administrator
#
# Test manuelt bagefter:
#   Start-ScheduledTask -TaskName "Lønsystem Backup"

$TaskName  = "Lønsystem Backup"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Script    = Join-Path $ScriptDir "backup.py"

# ── Find Python ─────────────────────────────────────────────────────────────
$PythonExe = "C:\Users\SofieThraneSkjødt\AppData\Local\Programs\Python\Python313\python.exe"

if (-not (Test-Path $PythonExe)) {
    # Forsøg at finde Python i PATH
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) {
        $PythonExe = $found.Source
        Write-Host "Python fundet i PATH: $PythonExe"
    } else {
        Write-Error @"
Python ikke fundet på den forventede sti:
  $PythonExe

Opdater variablen `$PythonExe øverst i dette script til den rigtige Python-sti
og kør scriptet igen.
"@
        exit 1
    }
}

Write-Host "Bruger Python: $PythonExe"
Write-Host "Backup-script: $Script"

# ── Opgaveindstillinger ──────────────────────────────────────────────────────
$action = New-ScheduledTaskAction `
    -Execute  $PythonExe `
    -Argument "`"$Script`"" `
    -WorkingDirectory $ScriptDir

# 4 daglige triggere
$triggers = @(
    New-ScheduledTaskTrigger -Daily -At "00:00",
    New-ScheduledTaskTrigger -Daily -At "06:00",
    New-ScheduledTaskTrigger -Daily -At "12:00",
    New-ScheduledTaskTrigger -Daily -At "18:00"
)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

# Kør som SYSTEM – kræver ingen gemt adgangskode og kører selv når ingen er logget ind
$principal = New-ScheduledTaskPrincipal `
    -UserId    "NT AUTHORITY\SYSTEM" `
    -RunLevel  Highest `
    -LogonType ServiceAccount

# ── Registrer opgaven ────────────────────────────────────────────────────────
Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $action `
    -Trigger   $triggers `
    -Settings  $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host ""
Write-Host "Opgaven '$TaskName' er registreret." -ForegroundColor Green
Write-Host "Kører automatisk kl. 00:00, 06:00, 12:00 og 18:00 hver dag."
Write-Host ""
Write-Host "Test den med det samme:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Cyan
Write-Host ""
Write-Host "Se status:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo" -ForegroundColor Cyan
Write-Host ""
Write-Host "Afinstaller hvis nødvendigt:"
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Cyan
