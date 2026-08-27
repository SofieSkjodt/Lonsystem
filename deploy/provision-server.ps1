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
