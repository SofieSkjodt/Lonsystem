# Opsætning af produktionsmaskinen fra bar Windows 11

Denne guide antager: den bærbare (denne maskine) er udviklingsmaskinen, og den nye
maskine ved siden af er tom (kun Windows 11) og skal være produktionsserveren.
Alt køres i almindelig PowerShell/cmd — ingen venv, ligesom udviklingsmaskinen i dag.

## Del 1 – Én gang, på DENNE (bærbare) maskine

1. Opret en konto på github.com hvis du ikke har en, og opret et **privat** repo,
   fx `lonsystem`. Kopiér repoets URL (fx `https://github.com/<bruger>/lonsystem.git`).
2. Kør i denne mappe:
   ```
   git remote add origin https://github.com/<bruger>/lonsystem.git
   git push -u origin master
   ```
   Nu ligger koden centralt på GitHub. `.env` og databasen bliver IKKE sendt med
   (de står i `.gitignore`) — det er meningen.

## Del 2 – På den NYE (tomme) maskine

### 2.1 Installér Python
- Gå til python.org → Downloads → hent nyeste 3.13.x til Windows.
- Kør installeren. **Vigtigt:** sæt flueben i "Add python.exe to PATH" på første skærm.
- Verificér i PowerShell:
  ```
  python --version
  ```

### 2.2 Installér Git
- Gå til git-scm.com → Download for Windows.
- Kør installeren, tag standardvalgene hele vejen igennem.
- Verificér:
  ```
  git --version
  ```

### 2.3 Hent koden
```
cd C:\
git clone https://github.com/<bruger>/lonsystem.git Lonsystem
cd C:\Lonsystem
```
Placér den her — **ikke** i en OneDrive-mappe (se forklaring i tidligere svar:
OneDrive-synkronisering af en levende database er risikabelt).

### 2.4 Installér Python-pakkerne
```
cd C:\Lonsystem\app
python -m pip install -r requirements.txt
```

### 2.5 Opret produktionens egen .env
```
copy .env.example .env
notepad .env
```
Udfyld:
- `SESSION_SECRET` — generér en ny unik værdi (kør på denne maskine):
  ```
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` — de rigtige
  driftsoplysninger til udsendelse af mails.
- Lad `ENTRA_*` stå tomme indtil SSO evt. tages i brug.

### 2.6 Testkør manuelt (før vi gør det til en service)
```
cd C:\Lonsystem\app
python -m uvicorn main:app --host 0.0.0.0 --port 8001
```
Åbn en browser på samme maskine: `http://localhost:8001`. Virker det, luk med Ctrl+C.

### 2.7 Åbn porten i firewallen (så kolleger kan tilgå den fra deres egne PC'er)
Kør i en PowerShell **som administrator**:
```
New-NetFirewallRule -DisplayName "Lonsystem" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow
```
Find maskinens lokale IP-adresse med `ipconfig` (feltet "IPv4-adresse"). Kolleger
tilgår herefter systemet på `http://<den-ip-adresse>:8001`. Overvej at bede jeres
netværksansvarlige om at reservere en fast IP til denne maskine i routeren, så
adressen ikke ændrer sig efter en genstart.

## Del 3 – Gør det til en rigtig service (kører uden åbent vindue, starter ved boot)

1. Hent NSSM fra nssm.cc (zip, ingen installer — pak ud fx til `C:\nssm`).
2. Åbn PowerShell **som administrator**:
   ```
   cd C:\nssm\win64
   .\nssm.exe install Lonsystem
   ```
   En dialog åbner:
   - **Path:** stien til `python.exe` (find den med `where python` i en almindelig
     PowerShell, fx `C:\Users\<bruger>\AppData\Local\Programs\Python\Python313\python.exe`)
   - **Startup directory:** `C:\Lonsystem\app`
   - **Arguments:** `-m uvicorn main:app --host 0.0.0.0 --port 8001`
   - Klik "Install service".
3. Start servicen:
   ```
   Start-Service Lonsystem
   ```
4. Tjek at den kører: `http://<ip-adresse>:8001` i en browser fra en anden PC.
5. Servicen starter nu automatisk ved genstart af maskinen. Log findes via
   `Get-Service Lonsystem` / Windows Logbog, eller tilføj `AppStdout`/`AppStderr`
   i NSSM (`nssm edit Lonsystem`) for en logfil.

## Del 4 – (Når du er klar) Direkte deploy fra den bærbare

1. På produktionsmaskinen: Indstillinger → Apps → Valgfrie funktioner → Tilføj en
   funktion → søg "OpenSSH Server" → Installer.
2. Start tjenesten og sæt den til autostart (PowerShell som administrator):
   ```
   Start-Service sshd
   Set-Service -Name sshd -StartupType Automatic
   New-NetFirewallRule -DisplayName "OpenSSH Server" -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow
   ```
3. Fra den bærbare kan du nu, når du har testet en ændring og pushet den til
   `main` på GitHub, køre:
   ```
   ssh <bruger>@<produktions-ip> "cd C:\Lonsystem; powershell -File deploy\deploy.ps1"
   ```
   Se [deploy.ps1](deploy.ps1) — ret `$ServiceName` heri til `Lonsystem` (matcher
   NSSM-servicenavnet ovenfor).

## Opsummeret arbejdsgang fremover
1. Udvikl og test på den bærbare (`--reload`, port 8000).
2. `git push` til `main` på GitHub når det er testet.
3. Kør `deploy.ps1` mod produktionsmaskinen (lokalt eller via ssh) — tager backup,
   henter koden, opdaterer pakker, genstarter servicen.
