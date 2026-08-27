<#
Lønsystem – update.ps1
Køres PÅ SERVEREN efter at udviklingsmaskinen har kørt publish-update.ps1.
#>
param(
    [string]$Ref = "master"
)

$ErrorActionPreference = "Stop"
$InstallRoot = "C:\Lønsystem"
$AppDir      = Join-Path $InstallRoot "app"
$ServiceName = "LonsystemService"
$PythonExe   = "C:\Program Files\Python313\python.exe"
$GitExe      = "C:\Program Files\Git\cmd\git.exe"

Write-Host "=== Opdaterer Lønsystem ===" -ForegroundColor Cyan

$prevCommit = & $GitExe -C $AppDir rev-parse HEAD
Write-Host "Nuværende version: $prevCommit"

Write-Host "Stopper tjenesten..."
Stop-Service -Name $ServiceName

Write-Host "Henter seneste kode ($Ref)..."
& $GitExe -C $AppDir fetch origin
& $GitExe -C $AppDir checkout $Ref
& $GitExe -C $AppDir pull origin $Ref

$reqChanged = & $GitExe -C $AppDir diff --name-only $prevCommit HEAD -- requirements.txt
if ($reqChanged) {
    Write-Host "requirements.txt ændret - geninstallerer Python-pakker..."
    & $PythonExe -m pip install -r (Join-Path $AppDir "requirements.txt")
}

Write-Host "Genstarter tjenesten..."
Start-Service -Name $ServiceName

$newCommit = & $GitExe -C $AppDir rev-parse HEAD
Write-Host ""
Write-Host "=== Opdatering færdig ===" -ForegroundColor Green
Write-Host "Forrige version: $prevCommit"
Write-Host "Ny version:      $newCommit"
Write-Host ""
Write-Host "Fortryd med:  .\rollback.ps1 -CommitOrTag $prevCommit"
