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

Start-Sleep -Seconds 3
Write-Host "Status:"
Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
