# Server-provisionering og git-baseret opdateringsflow – Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Byg den komplette deployment-pakke (scripts + bundlede installere) der gør det muligt at sætte Lønsystem op som en NSSM Windows-tjeneste på en ny, dedikeret server-laptop, og herefter opdatere/rulle tilbage via et git-baseret flow over et delt netværksdrev.

**Architecture:** Ét PowerShell-provisioneringsscript (`deploy/provision-server.ps1`) sætter serveren op fra bunden (statisk IP, Python, Git, NSSM-tjeneste, firewall, strømstyring, delt bart git-repo, backup-opgave). To små driftsscripts (`update.ps1`, `rollback.ps1`) styrer den løbende drift på serveren. Et hjælpescript (`publish-update.ps1`) på udviklingsmaskinen sender kode til serveren. Se [designspecen](../specs/2026-08-27-server-deployment-design.md) for fuld baggrund.

**Tech Stack:** PowerShell 5.1, Python 3.13.15, Git for Windows 2.55.0.5, NSSM 2.24, SQLite (uændret), FastAPI/uvicorn (uændret).

## Global Constraints

- Serveren har ingen internetadgang under opsætning – alt (Python, Git, NSSM) skal være bundlet i `deploy/tools/` (allerede hentet og SHA256-verificeret).
- Serveren må kun tilgås fra kontorets LAN – ingen VPN/internet-eksponering. Firewall-reglen må kun gælde `Private`/`Domain`-profiler, aldrig `Public`.
- `app/.env` og `app/database/lonsystem.db` må ALDRIG spores i git eller lægges i en netværksdelt/OneDrive-synkroniseret mappe (allerede rettet i tidligere commit – denne plan må ikke genindføre det).
- Installationsmappen (`$InstallRoot`) skal ligge uden for enhver OneDrive-synkroniseret sti.
- Netværksdelinger må kun eksponere det bare deploy-repo (`deploy.git`), ALDRIG hele installationsmappen (den indeholder den levende database).
- Alle scripts skal være idempotente – sikre at køre flere gange uden at ødelægge en allerede fungerende opsætning.
- Ingen ægte destruktive kommandoer (`git push --force`, sletning af database) i noget script.

---

## Fil-oversigt

- Modificer: `backup/backup.py` – konfigurerbar backup-mappe via miljøvariabel
- Opret: `deploy/provision-server.ps1` – engangsopsætning på serveren
- Opret: `deploy/update.ps1` – opdaterer og genstarter tjenesten (køres PÅ serveren)
- Opret: `deploy/rollback.ps1` – ruller tilbage til en tidligere commit (køres PÅ serveren)
- Opret: `deploy/publish-update.ps1` – sender kode til serveren (køres på UDVIKLINGSmaskinen)
- Opret: `deploy/README.md` – samlet runbook for hele flowet

---

### Task 1: Konfigurerbar backup-mappe i backup.py

**Files:**
- Modify: `backup/backup.py:8-20`
- Test: manuel verifikation via PowerShell (ingen eksisterende pytest-infrastruktur for dette script)

**Interfaces:**
- Produces: `backup.py` respekterer miljøvariablen `LONSYSTEM_BACKUP_DIR` (fallback til nuværende `backup/arkiv/`-sti hvis ikke sat). Bruges af `provision-server.ps1` (Task 2) til at pege backup-scheduled-task på en cloud-mappe.

- [x] **Step 1: Skriv testscript der viser nuværende (manglende) adfærd**

Opret en midlertidig testmappe og kør backup.py uden miljøvariabel sat, for at bekræfte dagens adfærd (skriver til `backup/arkiv/`):

```powershell
cd "C:\Users\SofieThraneSkjødt\OneDrive - Poul Schou A S\Skrivebord\Lønsystem"
Remove-Item Env:\LONSYSTEM_BACKUP_DIR -ErrorAction SilentlyContinue
python backup/backup.py
Get-ChildItem backup/arkiv | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

Expected: en ny zip-fil dukker op i `backup/arkiv/` (bekræfter nuværende default-adfærd, som skal bevares).

- [x] **Step 2: Modificér `backup/backup.py` til at læse miljøvariabel**

Erstat linje 8-20:

```python
import os
import sqlite3
import zipfile
import logging
from pathlib import Path
from datetime import datetime, timedelta

# ── Konfiguration ───────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent   # Lønsystem/
APP        = ROOT / "app"
DB_PATH    = APP / "database" / "lonsystem.db"
BACKUP_DIR = Path(os.environ.get("LONSYSTEM_BACKUP_DIR") or (Path(__file__).resolve().parent / "arkiv"))
LOG_FILE   = Path(__file__).resolve().parent / "backup.log"
KEEP_DAYS  = 5   # Antal dage backup-historik bevares
```

- [x] **Step 3: Kør testen igen uden miljøvariabel – bekræft uændret default-adfærd**

```powershell
Remove-Item Env:\LONSYSTEM_BACKUP_DIR -ErrorAction SilentlyContinue
python backup/backup.py
Get-ChildItem backup/arkiv | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

Expected: samme adfærd som Step 1 – ny zip i `backup/arkiv/`.

- [x] **Step 4: Kør testen med miljøvariabel sat – bekræft override virker**

```powershell
$testDir = Join-Path $env:TEMP "lonsystem-backup-test"
New-Item -ItemType Directory -Force -Path $testDir | Out-Null
$env:LONSYSTEM_BACKUP_DIR = $testDir
python backup/backup.py
Get-ChildItem $testDir
Remove-Item Env:\LONSYSTEM_BACKUP_DIR
Remove-Item -Recurse -Force $testDir
```

Expected: zip-filen ligger i `$testDir`, IKKE i `backup/arkiv/`.

- [x] **Step 5: Commit**

```bash
git add backup/backup.py
git commit -m "feat: gør backup-mappe konfigurerbar via LONSYSTEM_BACKUP_DIR"
```

---

### Task 2: provision-server.ps1 – engangsopsætning på serveren

**Files:**
- Create: `deploy/provision-server.ps1`

**Interfaces:**
- Consumes: `deploy/tools/python-3.13.15-amd64.exe`, `deploy/tools/Git-2.55.0.5-64-bit.exe`, `deploy/tools/win32/nssm.exe`, `deploy/tools/win64/nssm.exe`, `app/.env.example` (Task fra tidligere commit), `LONSYSTEM_BACKUP_DIR`-understøttelse fra Task 1.
- Produces: Windows-tjenesten `LonsystemService`, det bare repo `$InstallRoot\deploy.git`, netværksdelingen `lonsystem-deploy` (peger KUN på `deploy.git`), en registreret scheduled task `"Lønsystem Backup"`. Disse navne/stier bruges af Task 3 (`update.ps1`/`rollback.ps1`) og Task 4 (`publish-update.ps1`).

**Forudsætning før scriptet køres på serveren:** Hele projektmappen (inkl. `.git/`, `app/`, `backup/`, `deploy/`) er kopieret til `$InstallRoot` (fx `C:\Lønsystem`) via USB eller netværksdrev.

- [x] **Step 1: Opret scriptet med konfigurationsblok, admin-tjek og forudsætnings-tjek**

```powershell
<#
Lønsystem – provision-server.ps1
Kør SOM ADMINISTRATOR på den nye server-laptop, ÉN gang.

Forudsætning: Hele projektmappen (inkl. .git, app/, backup/, deploy/) er
allerede kopieret til $InstallRoot (fx via USB eller netværksdrev), FØR
dette script køres.
#>

# ============ KONFIGURATION – UDFYLD FØR KØRSEL ============
$InstallRoot     = "C:\Lønsystem"
$StaticIP        = "SÆT-IP-HER"           # fx 192.168.1.50
$SubnetPrefix    = 24                      # fx 24 for 255.255.255.0
$Gateway         = "SÆT-GATEWAY-HER"       # fx 192.168.1.1
$DnsServer       = "SÆT-DNS-HER"           # fx 192.168.1.1
$InterfaceAlias  = "SÆT-NETVÆRKSKORT-HER"  # tjek navn med: Get-NetAdapter
$AppPort         = 8000
$ServiceName     = "LonsystemService"
$BackupCloudDir  = "SÆT-BACKUP-STI-HER"    # fx en OneDrive-mappe kun til backup
$DeployShareUser = "SÆT-BRUGER-HER"        # Windows-konto der må pushe opdateringer, fx "KONTOR\sofie"
# =============================================================

$ErrorActionPreference = "Stop"

# --- 0. Forudsætninger ---
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Dette script skal køres som Administrator (højreklik -> 'Kør som administrator')."
}

if ($InstallRoot -like "*OneDrive*") {
    throw "InstallRoot ligger i en OneDrive-synkroniseret sti - vælg en lokal sti som C:\Lønsystem."
}

$DeployDir = Join-Path $InstallRoot "deploy"
$AppDir    = Join-Path $InstallRoot "app"
$ToolsDir  = Join-Path $DeployDir "tools"

if (-not (Test-Path $AppDir)) {
    throw "Fandt ikke $AppDir. Kopiér hele projektmappen til $InstallRoot før du kører dette script."
}

Write-Host "=== Provisionering starter: $InstallRoot ===" -ForegroundColor Green
```

- [x] **Step 2: Verificér syntaks (før resten af scriptet tilføjes)**

```powershell
$scriptPath = "deploy\provision-server.ps1"
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $scriptPath), [ref]$null, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) { $parseErrors } else { "OK - ingen syntaksfejl" }
```

Expected: `OK - ingen syntaksfejl`

- [x] **Step 3: Tilføj statisk IP, Python- og Git-installation**

Tilføj efter Step 1's indhold (før "Provisionering starter"-linjen fjernes ikke, tilføjes bare efter):

```powershell
# --- 1. Statisk IP ---
Write-Host "=== Sætter statisk IP ===" -ForegroundColor Cyan
if ($StaticIP -eq "SÆT-IP-HER") {
    throw "Udfyld `$StaticIP, `$Gateway, `$DnsServer og `$InterfaceAlias øverst i scriptet først."
}
Get-NetIPAddress -InterfaceAlias $InterfaceAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.PrefixOrigin -eq "Dhcp" } |
    Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
New-NetIPAddress -InterfaceAlias $InterfaceAlias -IPAddress $StaticIP -PrefixLength $SubnetPrefix -DefaultGateway $Gateway | Out-Null
Set-DnsClientServerAddress -InterfaceAlias $InterfaceAlias -ServerAddresses $DnsServer
Write-Host "Statisk IP sat til $StaticIP"

# --- 2. Installer Python ---
Write-Host "=== Installerer Python 3.13 ===" -ForegroundColor Cyan
$PythonExe = "C:\Program Files\Python313\python.exe"
if (-not (Test-Path $PythonExe)) {
    Start-Process -FilePath (Join-Path $ToolsDir "python-3.13.15-amd64.exe") `
        -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=0 Include_test=0" -Wait
}
if (-not (Test-Path $PythonExe)) {
    throw "Python-installation fejlede - $PythonExe findes ikke."
}
Write-Host "Python installeret: $PythonExe"

# --- 3. Installer Git ---
Write-Host "=== Installerer Git ===" -ForegroundColor Cyan
$GitExe = "C:\Program Files\Git\cmd\git.exe"
if (-not (Test-Path $GitExe)) {
    Start-Process -FilePath (Join-Path $ToolsDir "Git-2.55.0.5-64-bit.exe") `
        -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP-" -Wait
}
if (-not (Test-Path $GitExe)) {
    throw "Git-installation fejlede - $GitExe findes ikke."
}
Write-Host "Git installeret: $GitExe"

# --- 4. Python-afhængigheder ---
Write-Host "=== Installerer Python-pakker ===" -ForegroundColor Cyan
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r (Join-Path $AppDir "requirements.txt")
```

- [x] **Step 4: Verificér syntaks igen**

```powershell
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "deploy\provision-server.ps1"), [ref]$null, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) { $parseErrors } else { "OK - ingen syntaksfejl" }
```

Expected: `OK - ingen syntaksfejl`

- [x] **Step 5: Tilføj .env-generering, firewall og strømstyring**

```powershell
# --- 5. .env til serveren ---
$envPath = Join-Path $AppDir ".env"
if (-not (Test-Path $envPath)) {
    Write-Host "=== Opretter .env ===" -ForegroundColor Cyan
    $sessionSecret = & $PythonExe -c "import secrets; print(secrets.token_hex(32))"
    $envTemplate = Get-Content (Join-Path $AppDir ".env.example") -Raw
    $envTemplate = $envTemplate -replace "SESSION_SECRET=", "SESSION_SECRET=$sessionSecret"
    Set-Content -Path $envPath -Value $envTemplate -Encoding utf8
    Write-Host ".env oprettet med ny SESSION_SECRET. Udfyld SMTP-felter manuelt hvis mail skal bruges."
} else {
    Write-Host ".env findes allerede - rører den ikke."
}

# --- 6. Firewall (kun LAN-profiler) ---
Write-Host "=== Åbner firewall for port $AppPort ===" -ForegroundColor Cyan
if (-not (Get-NetFirewallRule -DisplayName "Lønsystem" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "Lønsystem" -Direction Inbound -Protocol TCP `
        -LocalPort $AppPort -Action Allow -Profile Private,Domain | Out-Null
}

# --- 7. Strøm: aldrig dvale, gør intet ved låg-lukning ---
Write-Host "=== Konfigurerer strømstyring ===" -ForegroundColor Cyan
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /setacvalueindex SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936 0
powercfg /setactive SCHEME_CURRENT
```

- [x] **Step 6: Verificér syntaks igen**

```powershell
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "deploy\provision-server.ps1"), [ref]$null, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) { $parseErrors } else { "OK - ingen syntaksfejl" }
```

Expected: `OK - ingen syntaksfejl`

- [x] **Step 7: Tilføj NSSM-tjeneste, bart deploy-repo (kun det deles!) og backup-opgave**

```powershell
# --- 8. NSSM-tjeneste ---
Write-Host "=== Opsætter Windows-tjeneste (NSSM) ===" -ForegroundColor Cyan
$nssmSource = if ([Environment]::Is64BitOperatingSystem) { Join-Path $ToolsDir "win64\nssm.exe" } else { Join-Path $ToolsDir "win32\nssm.exe" }
$NssmExe = Join-Path $InstallRoot "nssm.exe"
Copy-Item $nssmSource $NssmExe -Force

$logsDir = Join-Path $InstallRoot "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    Write-Host "Tjenesten findes allerede - stopper og fjerner den først."
    Stop-Service -Name $ServiceName -ErrorAction SilentlyContinue
    & $NssmExe remove $ServiceName confirm
}

& $NssmExe install $ServiceName $PythonExe "-m uvicorn main:app --host 0.0.0.0 --port $AppPort"
& $NssmExe set $ServiceName AppDirectory $AppDir
& $NssmExe set $ServiceName AppStdout (Join-Path $logsDir "service-out.log")
& $NssmExe set $ServiceName AppStderr (Join-Path $logsDir "service-err.log")
& $NssmExe set $ServiceName Start SERVICE_AUTO_START
& $NssmExe set $ServiceName AppRestartDelay 5000
Start-Service -Name $ServiceName
Write-Host "Tjenesten '$ServiceName' er startet."

# --- 9. Bart deploy-repo + netværksdeling (KUN deploy.git, ALDRIG hele InstallRoot) ---
Write-Host "=== Opretter delt deploy-repo ===" -ForegroundColor Cyan
$DeployGit = Join-Path $InstallRoot "deploy.git"
if (-not (Test-Path $DeployGit)) {
    & $GitExe clone --bare $AppDir $DeployGit
    & $GitExe -C $AppDir remote set-url origin $DeployGit
}
$shareName = "lonsystem-deploy"
if ($DeployShareUser -eq "SÆT-BRUGER-HER") {
    Write-Warning "DeployShareUser er ikke udfyldt - netværksdeling oprettes IKKE. Ret variablen og kør scriptet igen."
} elseif (-not (Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue)) {
    New-SmbShare -Name $shareName -Path $DeployGit -FullAccess $DeployShareUser | Out-Null
    Write-Host "Delt som \\<denne-maskines-navn>\$shareName (kun deploy.git, IKKE den levende database)."
}

# --- 10. Backup: cloud-mappe + planlagt opgave ---
Write-Host "=== Opsætter automatisk backup ===" -ForegroundColor Cyan
if ($BackupCloudDir -eq "SÆT-BACKUP-STI-HER") {
    Write-Warning "BackupCloudDir er ikke udfyldt - backup-opgaven oprettes IKKE. Ret variablen og kør scriptet igen."
} else {
    [Environment]::SetEnvironmentVariable("LONSYSTEM_BACKUP_DIR", $BackupCloudDir, "Machine")
    $backupScript = Join-Path $InstallRoot "backup\backup.py"
    $taskName = "Lønsystem Backup"
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    $action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$backupScript`"" -WorkingDirectory (Join-Path $InstallRoot "backup")
    $triggers = @(
        New-ScheduledTaskTrigger -Daily -At "00:00",
        New-ScheduledTaskTrigger -Daily -At "06:00",
        New-ScheduledTaskTrigger -Daily -At "12:00",
        New-ScheduledTaskTrigger -Daily -At "18:00"
    )
    $taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -RunLevel Highest -LogonType ServiceAccount
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $taskSettings -Principal $taskPrincipal -Force | Out-Null
    Write-Host "Backup-opgave '$taskName' registreret (00/06/12/18)."
    Write-Warning "OneDrive synkroniserer kun mens en bruger er logget ind på laptoppen - se README for anbefaling om automatisk login."
}

Write-Host ""
Write-Host "=== Provisionering færdig ===" -ForegroundColor Green
Write-Host "Test lokalt:        http://localhost:$AppPort"
Write-Host "Test fra netværket: http://${StaticIP}:${AppPort}"
```

- [x] **Step 8: Verificér syntaks på det færdige script**

```powershell
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "deploy\provision-server.ps1"), [ref]$null, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) { $parseErrors } else { "OK - ingen syntaksfejl" }
```

Expected: `OK - ingen syntaksfejl`

- [x] **Step 9: Commit**

```bash
git add deploy/provision-server.ps1
git commit -m "feat: tilføj provision-server.ps1 til engangsopsætning af server"
```

---

### Task 3: update.ps1 og rollback.ps1 – driftsscripts PÅ serveren

**Files:**
- Create: `deploy/update.ps1`
- Create: `deploy/rollback.ps1`

**Interfaces:**
- Consumes: `$ServiceName = "LonsystemService"`, `$InstallRoot = "C:\Lønsystem"`, `$AppDir = "$InstallRoot\app"` (produceret af Task 2), `$PythonExe = "C:\Program Files\Python313\python.exe"` (produceret af Task 2).
- Produces: intet nyt navn/interface andre tasks afhænger af.

- [x] **Step 1: Opret `deploy/update.ps1`**

```powershell
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
```

- [x] **Step 2: Verificér syntaks**

```powershell
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "deploy\update.ps1"), [ref]$null, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) { $parseErrors } else { "OK - ingen syntaksfejl" }
```

Expected: `OK - ingen syntaksfejl`

- [x] **Step 3: Opret `deploy/rollback.ps1`**

```powershell
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
```

- [x] **Step 4: Verificér syntaks**

```powershell
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "deploy\rollback.ps1"), [ref]$null, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) { $parseErrors } else { "OK - ingen syntaksfejl" }
```

Expected: `OK - ingen syntaksfejl`

- [x] **Step 5: Commit**

```bash
git add deploy/update.ps1 deploy/rollback.ps1
git commit -m "feat: tilføj update.ps1 og rollback.ps1 til server-drift"
```

---

### Task 4: publish-update.ps1 – hjælpescript på udviklingsmaskinen

**Files:**
- Create: `deploy/publish-update.ps1`

**Interfaces:**
- Consumes: en git-remote med navnet angivet i `-ServerRemote` (default `"server"`), der skal være tilføjet manuelt én gang på udviklingsmaskinen: `git remote add server \\<server-ip>\lonsystem-deploy`.
- Produces: intet nyt navn andre tasks afhænger af.

- [x] **Step 1: Opret `deploy/publish-update.ps1`**

```powershell
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
```

- [x] **Step 2: Verificér syntaks**

```powershell
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "deploy\publish-update.ps1"), [ref]$null, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count -gt 0) { $parseErrors } else { "OK - ingen syntaksfejl" }
```

Expected: `OK - ingen syntaksfejl`

- [x] **Step 3: Test end-to-end mod et midlertidigt bare-repo (isoleret klon, rører ikke det rigtige repo)**

```powershell
$repoUrl   = "C:\Users\SofieThraneSkjødt\OneDrive - Poul Schou A S\Skrivebord\Lønsystem"
$tempClone = Join-Path $env:TEMP "lonsystem-publish-test-clone"
$tempRemote = Join-Path $env:TEMP "lonsystem-publish-test-remote.git"

Remove-Item -Recurse -Force $tempClone, $tempRemote -ErrorAction SilentlyContinue
git clone $repoUrl $tempClone
git init --bare $tempRemote
git -C $tempClone remote add test-server $tempRemote

& (Join-Path $tempClone "deploy\publish-update.ps1") -ServerRemote "test-server" -Branch "master"

git --git-dir="$tempRemote" log -1 --oneline

Remove-Item -Recurse -Force $tempClone, $tempRemote
```

Expected: scriptet printer "Sender master til serveren (test-server)..." efterfulgt af git's push-output uden fejl, og `git log -1` mod `$tempRemote` viser samme commit som `git -C $repoUrl log -1` gjorde ved test-start.

- [x] **Step 4: Commit**

```bash
git add deploy/publish-update.ps1
git commit -m "feat: tilføj publish-update.ps1 til at sende kode til serveren"
```

---

### Task 5: deploy/README.md – samlet runbook

**Files:**
- Create: `deploy/README.md`

**Interfaces:**
- Consumes: alle scripts og filnavne fra Task 2-4.

- [x] **Step 1: Skriv runbogen**

```markdown
# Deployment – Lønsystem

Denne mappe indeholder alt hvad der skal bruges for at sætte Lønsystem op
på en dedikeret server-laptop, og for løbende at opdatere den.

## Første opsætning (én gang)

1. Kopiér HELE projektmappen (inkl. `.git`, `app`, `backup`, `deploy`) til
   den nye laptop, fx til `C:\Lønsystem`, via USB eller netværksdrev.
   - **Vigtigt:** Stien må IKKE ligge i en OneDrive-synkroniseret mappe.
2. Kopiér den eksisterende database (`app/database/lonsystem.db`) og
   Excel-satsfilerne fra den gamle maskine over i den kopierede mappe,
   hvis de ikke allerede er en del af kopien (databasen er ikke i git).
3. Find ledig statisk IP, gateway, DNS og netværkskort-navn
   (`Get-NetAdapter` viser navnet) på kontorets netværk.
4. Beslut hvilken cloud-mappe (fx en dedikeret OneDrive/SharePoint-mappe)
   backup-zips skal ende i, og hvilken Windows-konto der skal have
   lov at pushe opdateringer til serveren.
5. Åbn `provision-server.ps1` og udfyld konfigurationsblokken øverst
   (`$StaticIP`, `$Gateway`, `$DnsServer`, `$InterfaceAlias`,
   `$BackupCloudDir`, `$DeployShareUser`).
6. Højreklik `provision-server.ps1` → "Kør med PowerShell som administrator".
7. Verificér:
   - `Get-Service LonsystemService` viser `Running`
   - `http://localhost:8000` svarer på selve laptoppen
   - `http://<StaticIP>:8000` svarer fra en ANDEN pc på kontornetværket
8. Kør den fulde verifikationstjekliste (se nedenfor), før serveren tages i
   permanent brug.
9. På udviklingsmaskinen: tilføj serveren som git-remote (kør én gang):

   ```powershell
   git remote add server \\<laptoppens-navn-eller-ip>\lonsystem-deploy
   ```

## Ved en rettelse (løbende brug)

1. Ret og test som normalt på udviklingsmaskinen. Commit ændringen.
2. Kør fra repo-roden:

   ```powershell
   .\deploy\publish-update.ps1
   ```

3. Gå til serveren (eller fjernskrivebord/fysisk) og kør:

   ```powershell
   C:\Lønsystem\deploy\update.ps1
   ```

   Dette stopper tjenesten, henter koden, geninstallerer Python-pakker
   hvis `requirements.txt` er ændret, og genstarter tjenesten.
   Database-migrationer sker automatisk ved opstart.

## Går noget galt

Kør på serveren, med commit-hashet `update.ps1` printede som "Forrige version":

```powershell
C:\Lønsystem\deploy\rollback.ps1 -CommitOrTag <forrige-commit-hash>
```

## Fuld verifikationstjekliste (kør én gang efter første opsætning)

1. **Genstart-ved-crash:** find uvicorn-processens PID (`Get-Process python`)
   og kør `Stop-Process -Id <pid> -Force`. Vent 10 sekunder, tjek at
   `Get-Service LonsystemService` igen viser `Running`, og at siden svarer.
2. **Dvale/låg-test:** luk laptoppens låg mens den er tilsluttet strøm,
   vent et minut, åbn igen - siden skal stadig svare uden at nogen har
   logget ind.
3. **Opdaterings-flow end-to-end:** lav en harmløs tekstændring på
   udviklingsmaskinen, commit, kør `publish-update.ps1`, kør derefter
   `update.ps1` på serveren, og bekræft ændringen er synlig i browseren.
4. **Rollback-test:** kør `rollback.ps1` med commit-hashet fra FØR
   test 3's ændring, bekræft ændringen er væk igen, kør så `update.ps1`
   igen for at komme tilbage til seneste version.
5. **Backup-test:** kør backup-scheduled-tasken manuelt
   (`Start-ScheduledTask -TaskName "Lønsystem Backup"`) og bekræft en ny
   zip-fil dukker op i `$BackupCloudDir`.

## Driftsopmærksomhed

- **OneDrive-backup kræver en logget-ind bruger.** Backup-opgaven kører som
  SYSTEM og skriver filer til `$BackupCloudDir`, men selve OneDrive-
  synkroniseringen kræver at OneDrive-klienten kører under en logget-ind
  brugers session. Sørg for at laptoppen enten aldrig logges helt ud, eller
  overvej automatisk login til en dedikeret lokal konto - tal med IT om
  hvad der er acceptabelt hos jer, da automatisk login gemmer login-
  oplysninger i registreringsdatabasen.
- **Firewall-reglen dækker kun Private/Domain-netværksprofiler**, aldrig
  Public - hvis laptoppens netværkskort af en eller anden grund klassificeres
  som "Public" i Windows, skal profilen rettes (`Get-NetConnectionProfile`),
  ikke firewall-reglen udvides.
- **Netværksdelingen `lonsystem-deploy` peger KUN på `deploy.git`** (koden),
  aldrig på hele `C:\Lønsystem` - den levende database må aldrig være
  tilgængelig via netværksdeling.
```

- [x] **Step 2: Commit**

```bash
git add deploy/README.md
git commit -m "docs: tilføj deployment-runbog til deploy/README.md"
```

---

## Efter planen er gennemført

Alt hvad der kan forberedes uden den fysiske laptop er nu klar. De resterende
punkter fra designspecens "Åbne punkter" (statisk IP, drevbogstav/servernavn,
32-bit vs. 64-bit) afklares og udfyldes i `provision-server.ps1`'s
konfigurationsblok, når laptoppen er fysisk til stede - se `deploy/README.md`
for den fulde trin-for-trin-guide.
