# Lonsystem - opretter de planlagte opgaver til produktionsserver og auto-deploy.
# Scriptet kan koeres igen; eksisterende opgaver opdateres med -Force.
 
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
 
foreach ($RequiredPath in @($AppDirectory, $AutoCheckPath)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        throw "Den paakraevede sti findes ikke: $RequiredPath"
    }
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
        -Description "Lonsystem - tjekker GitHub hvert 5. minut og deployer nye aendringer" `
        -Force `
        -ErrorAction Stop | Out-Null
 
    Write-Host "Opgaven '$AutoTaskName' er oprettet og koerer hvert 5. minut uden slutdato." -ForegroundColor Green
 
    # Start serveren med det samme. Auto-deploy starter senest om et minut.
    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
 
    Start-Sleep -Seconds 2
    Write-Host "`nStatus:" -ForegroundColor Cyan
    foreach ($Name in @($TaskName, $AutoTaskName)) {
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