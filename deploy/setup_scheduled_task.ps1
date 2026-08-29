# Lonsystem - opretter Task Scheduler-opgaven der holder produktionsserveren koerende.
# Koeres EN GANG paa produktionsmaskinen, i en PowerShell aabnet "Som administrator".

$TaskName = "Lonsystem"
$BatchPath = "C:\Users\LoenPC\Lonsystem\deploy\run_production.bat"

$Action = New-ScheduledTaskAction -Execute $BatchPath -WorkingDirectory "C:\Users\LoenPC\Lonsystem\app"
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# ExecutionTimeLimit = 0 er kritisk: uden den slaar Task Scheduler processen ihjel
# efter 3 dage (standard-graensen for alle opgaver), hvilket ville lukke serveren ned
# midt om natten uden varsel.
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Principal $Principal -Settings $Settings `
    -Description "Lonsystem produktionsserver - starter automatisk ved boot" -Force

Write-Host "Opgaven '$TaskName' er oprettet. Starter den nu..."
Start-ScheduledTask -TaskName $TaskName

# --- Anden opgave: tjekker hvert 5. minut om der er nyt paa GitHub, og deployer ---
$AutoTaskName = "LonsystemAutoDeploy"
$AutoCheckPath = "C:\Users\LoenPC\Lonsystem\deploy\auto_deploy_check.ps1"

$AutoAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$AutoCheckPath`"" `
    -WorkingDirectory "C:\Users\LoenPC\Lonsystem"
$AutoTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)

Register-ScheduledTask -TaskName $AutoTaskName -Action $AutoAction -Trigger $AutoTrigger `
    -Principal $Principal -Settings $Settings `
    -Description "Lonsystem - tjekker GitHub hvert 5. minut og deployer nye aendringer" -Force

Write-Host "Opgaven '$AutoTaskName' er oprettet (koerer hvert 5. minut)."

Start-Sleep -Seconds 3
Write-Host "Status:"
Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
Get-ScheduledTask -TaskName $AutoTaskName | Get-ScheduledTaskInfo
