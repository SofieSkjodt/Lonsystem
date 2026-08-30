# Lonsystem - aabner den indgaaende firewall-port til produktionsserveren.
# Koeres EN GANG paa produktionsmaskinen, i en PowerShell aabnet "Som administrator".
# Kan koeres igen uden problemer - fjerner en evt. gammel regel foerst.

$ErrorActionPreference = "Stop"
$RuleName = "Lonsystem"
$Port = 8000

Remove-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue

New-NetFirewallRule `
    -DisplayName $RuleName `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort $Port `
    -Action Allow | Out-Null

Write-Host "Firewall-regel '$RuleName' oprettet for indgaaende TCP-trafik paa port $Port." -ForegroundColor Green
