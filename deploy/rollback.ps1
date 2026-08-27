<#
Lønsystem – rollback.ps1
Køres PÅ SERVEREN for at rulle tilbage til en tidligere version.
Brug: .\rollback.ps1 -CommitOrTag <commit-hash eller tag>
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$CommitOrTag
)

$ErrorActionPreference = "Stop"
$InstallRoot = "C:\Lønsystem"
$AppDir      = Join-Path $InstallRoot "app"
$ServiceName = "LonsystemService"
$GitExe      = "C:\Program Files\Git\cmd\git.exe"

Write-Host "=== Ruller Lønsystem tilbage til $CommitOrTag ===" -ForegroundColor Cyan

Write-Host "Stopper tjenesten..."
Stop-Service -Name $ServiceName

Write-Host "Går tilbage til $CommitOrTag..."
& $GitExe -C $AppDir checkout $CommitOrTag

Write-Host "Genstarter tjenesten..."
Start-Service -Name $ServiceName

$current = & $GitExe -C $AppDir rev-parse HEAD
Write-Host ""
Write-Host "=== Rollback færdig ===" -ForegroundColor Green
Write-Host "Nuværende version: $current"
