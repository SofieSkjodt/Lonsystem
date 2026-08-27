<#
Lønsystem – publish-update.ps1
Køres PÅ UDVIKLINGSMASKINEN efter en rettelse er committet lokalt.
Sender koden til serverens delte deploy-repo. Gør IKKE ændringen live -
kør update.ps1 PÅ SERVEREN bagefter for det.
#>
param(
    [string]$ServerRemote = "server",
    [string]$Branch = "master"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

$status = git -C $RepoRoot status --porcelain
if ($status) {
    Write-Error "Der er ikke-committede ændringer. Commit eller stash dem først."
    exit 1
}

Write-Host "Sender $Branch til serveren ($ServerRemote)..." -ForegroundColor Cyan
git -C $RepoRoot push $ServerRemote $Branch

Write-Host ""
Write-Host "Kode er nu på serverens delte repo." -ForegroundColor Green
Write-Host "Kør update.ps1 PÅ SERVEREN for at gøre den live." -ForegroundColor Yellow
