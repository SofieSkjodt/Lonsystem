# Lonsystem - opretter de planlagte opgaver: produktionsserver, auto-deploy
# (kun pull), genstart hver nat kl. 23:00, og backup. Scriptet kan koeres igen;
# eksisterende opgaver opdateres med -Force.
 
[CmdletBinding()]
param()
 
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
 
# Register-ScheduledTask med SYSTEM/Highest kraever administratorrettigheder.
$CurrentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$CurrentPrincipal = [Security.Principal.WindowsPrincipal]::new($CurrentIdentity)
$IsAdministrator = $CurrentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
 
if (-not $IsAdministrator) {
    Write-Host "Administratorrettigheder er paakraevet. Aabner et nyt PowerShell-vindue..." -ForegroundColor Yellow
    $ElevatedArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $ElevatedArguments
    exit 0
}
 
$DeployDirectory = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $DeployDirectory
$AppDirectory = Join-Path $ProjectRoot "app"
$AutoCheckPath = Join-Path $DeployDirectory "auto_deploy_check.ps1"
$RestartScript = Join-Path $DeployDirectory "restart_server.ps1"
$BackupScript = Join-Path $ProjectRoot "backup\backup.py"
$BackupDir = "C:\Users\LoenPC\OneDrive - Poul Schou A S\LonsystemBackup"

foreach ($RequiredPath in @($AppDirectory, $AutoCheckPath, $RestartScript, $BackupScript)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        throw "Den paakraevede sti findes ikke: $RequiredPath"
    }
}

# Backup-scriptet laeser LONSYSTEM_BACKUP_DIR fra miljoevariabler. Sat paa
# maskine-niveau (ikke bruger-niveau), saa den ogsaa er synlig for opgaver der
# koerer som SYSTEM, og for deploy.ps1's egen backup-kald ved hvert deploy.
[Environment]::SetEnvironmentVariable("LONSYSTEM_BACKUP_DIR", $BackupDir, "Machine")
if (-not (Test-Path -LiteralPath $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

# Brug den rigtige python.exe direkte. Python-launcheren "py" kan ikke finde
# brugerinstallerede Python-versioner, naar opgaven senere koerer som SYSTEM.
$PythonPath = (& py -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1).Trim()
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python kunne ikke findes. Kontroller at kommandoen 'py' virker for denne bruger."
}
 
$Principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest
 
# ExecutionTimeLimit = 0 betyder, at langvarige opgaver ikke stoppes automatisk.
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew
 
# Serverprocessen skal genstartes af Task Scheduler, hvis Python/Uvicorn stopper.
$ServerSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# Backup-opgaven er kortvarig og skal ikke koere paa ubestemt tid hvis den haenger.
$BackupSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew
 
try {
    # Opgave 1: produktionsserveren starter ved Windows-opstart og har ingen slutdato.
    $TaskName = "Lonsystem"
    $Action = New-ScheduledTaskAction `
        -Execute $PythonPath `
        -Argument "-m uvicorn main:app --host 0.0.0.0 --port 8000" `
        -WorkingDirectory $AppDirectory
    $Trigger = New-ScheduledTaskTrigger -AtStartup
 
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $ServerSettings `
        -Description "Lonsystem produktionsserver - starter automatisk ved boot" `
        -Force `
        -ErrorAction Stop | Out-Null
 
    Write-Host "Opgaven '$TaskName' er oprettet med Python: $PythonPath" -ForegroundColor Green
 
    # Opgave 2: auto-deploy hvert 5. minut, uden slutdato for opgaven.
    # Task Scheduler gentager i en daglig cyklus paa 1 doegn. En ny cyklus
    # starter hver dag, saa opgaven fortsaetter, indtil den deaktiveres/slettes.
    $AutoTaskName = "LonsystemAutoDeploy"
    $PowerShellPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $AutoAction = New-ScheduledTaskAction `
        -Execute $PowerShellPath `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$AutoCheckPath`"" `
        -WorkingDirectory $ProjectRoot
 
    $FirstAutoRun = (Get-Date).AddMinutes(1)
    $RepeatTemplate = New-ScheduledTaskTrigger `
        -Once `
        -At $FirstAutoRun `
        -RepetitionInterval (New-TimeSpan -Minutes 5) `
        -RepetitionDuration (New-TimeSpan -Days 1)
    $AutoTrigger = New-ScheduledTaskTrigger -Daily -At $FirstAutoRun
    $AutoTrigger.Repetition = $RepeatTemplate.Repetition
 
    Register-ScheduledTask `
        -TaskName $AutoTaskName `
        -Action $AutoAction `
        -Trigger $AutoTrigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description "Lonsystem - tjekker GitHub hvert 5. minut og henter nye aendringer (genstarter IKKE serveren)" `
        -Force `
        -ErrorAction Stop | Out-Null

    Write-Host "Opgaven '$AutoTaskName' er oprettet og koerer hvert 5. minut uden slutdato." -ForegroundColor Green

    # Opgave 3: genstart af serveren hver nat kl. 23:00, saa koden hentet i
    # loebet af dagen af LonsystemAutoDeploy rent faktisk bliver taget i brug.
    $RestartTaskName = "LonsystemNightlyRestart"
    $RestartAction = New-ScheduledTaskAction `
        -Execute $PowerShellPath `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$RestartScript`"" `
        -WorkingDirectory $ProjectRoot
    $RestartTrigger = New-ScheduledTaskTrigger -Daily -At "23:00"

    Register-ScheduledTask `
        -TaskName $RestartTaskName `
        -Action $RestartAction `
        -Trigger $RestartTrigger `
        -Principal $Principal `
        -Settings $BackupSettings `
        -Description "Lonsystem - genstarter serveren hver nat kl. 23:00 for at tage ny kode i brug" `
        -Force `
        -ErrorAction Stop | Out-Null

    Write-Host "Opgaven '$RestartTaskName' er oprettet (koerer hver nat kl. 23:00)." -ForegroundColor Green

    # Opgave 4: backup 4 gange dagligt (00:00, 06:00, 12:00, 18:00).
    $BackupTaskName = "LonsystemBackup"
    $BackupAction = New-ScheduledTaskAction `
        -Execute $PythonPath `
        -Argument "`"$BackupScript`"" `
        -WorkingDirectory (Split-Path -Parent $BackupScript)
    $BackupTriggers = @(
        (New-ScheduledTaskTrigger -Daily -At "00:00"),
        (New-ScheduledTaskTrigger -Daily -At "06:00"),
        (New-ScheduledTaskTrigger -Daily -At "12:00"),
        (New-ScheduledTaskTrigger -Daily -At "18:00")
    )

    Register-ScheduledTask `
        -TaskName $BackupTaskName `
        -Action $BackupAction `
        -Trigger $BackupTriggers `
        -Principal $Principal `
        -Settings $BackupSettings `
        -Description "Lonsystem - backup af database og satsfiler 4 gange dagligt" `
        -Force `
        -ErrorAction Stop | Out-Null

    Write-Host "Opgaven '$BackupTaskName' er oprettet (koerer 00:00/06:00/12:00/18:00), gemmer til: $BackupDir" -ForegroundColor Green

    # Start serveren med det samme. Auto-deploy og backup starter selv efter deres triggere.
    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop

    Start-Sleep -Seconds 2
    Write-Host "`nStatus:" -ForegroundColor Cyan
    foreach ($Name in @($TaskName, $AutoTaskName, $RestartTaskName, $BackupTaskName)) {
        $Task = Get-ScheduledTask -TaskName $Name -ErrorAction Stop
        $Info = $Task | Get-ScheduledTaskInfo -ErrorAction Stop
        [PSCustomObject]@{
            TaskName    = $Name
            State       = $Task.State
            LastRunTime = $Info.LastRunTime
            NextRunTime = $Info.NextRunTime
            LastResult  = $Info.LastTaskResult
        }
    }
}
catch {
    Write-Error "Opsaetningen mislykkedes: $($_.Exception.Message)"
    exit 1
}