# Lonsystem - genstarter produktionsserveren, saa den indlaeser den nyeste kode
# der er hentet ned af pull_update.ps1 siden sidste genstart.
#
# Koeres automatisk hver nat kl. 23:00 af Task Scheduler-opgaven
# "LonsystemNightlyRestart" (se deploy/setup_scheduled_task.ps1). Kan ogsaa
# koeres manuelt naar som helst for en oejeblikkelig genstart.

$ErrorActionPreference = "Stop"
$TaskName = "Lonsystem"

Write-Host "Stopper opgaven '$TaskName'..."
try { Stop-ScheduledTask -TaskName $TaskName } catch { Write-Warning "Kunne ikke stoppe opgaven '$TaskName' (er den oprettet endnu?)" }

Start-Sleep -Seconds 2

Write-Host "Starter opgaven '$TaskName'..."
Start-ScheduledTask -TaskName $TaskName

Write-Host "Genstart faerdig. Tjek http://localhost:8000 om lidt."
