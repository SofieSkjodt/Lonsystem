# Opsætning af produktionsmaskinen fra bar Windows 11

Denne guide antager: den bærbare (denne maskine) er udviklingsmaskinen, og den nye
maskine ved siden af er tom (kun Windows 11) og skal være produktionsserveren.
Alt køres i almindelig PowerShell/cmd — ingen venv, ligesom udviklingsmaskinen i dag.

## Del 1 – Én gang, på DENNE (bærbare) maskine

1. Opret en konto på github.com hvis du ikke har en, og opret et **privat** repo,
   fx `lonsystem`. Kopiér repoets URL (fx `https://github.com/SofieSkjodt/Lonsystem.git`).
2. Kør i denne mappe:
   ```
   git remote add origin https://github.com/SofieSkjodt/Lonsystem.git
   git push -u origin main
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
cd C:\Users\LoenPC
git clone https://github.com/SofieSkjodt/Lonsystem.git Lonsystem
cd C:\Users\LoenPC\Lonsystem
```
Placér den her — **ikke** i en OneDrive-mappe (se forklaring i tidligere svar:
OneDrive-synkronisering af en levende database er risikabelt). Undgå bevidst danske
bogstaver (æøå) i selve mappenavnet — det gav en tegnsæt-fejl i PowerShell tidligere.

### 2.4 Installér Python-pakkerne
```
cd C:\Users\LoenPC\Lonsystem\app
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
cd C:\Users\LoenPC\Lonsystem\app
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```
Åbn en browser på samme maskine: `http://localhost:8000`. Virker det, luk med Ctrl+C.

### 2.7 Åbn porten i firewallen (så kolleger kan tilgå den fra deres egne PC'er)
Kør i en PowerShell **som administrator**:
```
New-NetFirewallRule -DisplayName "Lonsystem" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```
Find maskinens lokale IP-adresse med `ipconfig` (feltet "IPv4-adresse"). Kolleger
tilgår herefter systemet på `http://<den-ip-adresse>:8000`. Overvej at bede jeres
netværksansvarlige om at reservere en fast IP til denne maskine i routeren, så
adressen ikke ændrer sig efter en genstart.

## Del 3 – Gør det til en vedvarende opgave (kører uden åbent vindue, starter ved boot)

Helt native Windows — ingen tredjeparts-software. [setup_scheduled_task.ps1](setup_scheduled_task.ps1)
finder selv den fulde sti til `python.exe` (mere robust end at stole på at `python`/`py`
er på PATH for SYSTEM-kontoen) og opretter serveren som en Task Scheduler-opgave, der
kører `python.exe` direkte — Task Scheduler genstarter den selv op til 999 gange
(1 minuts mellemrum) hvis processen nogensinde stopper uventet.

1. Åbn PowerShell i `C:\Users\LoenPC\Lonsystem` — scriptet tjekker selv om du er
   administrator, og hvis ikke, åbner det automatisk et nyt, forhøjet vindue (du skal
   bare acceptere UAC-prompten).
2. Kør opsætnings-scriptet:
   ```
   powershell -ExecutionPolicy Bypass -File deploy\setup_scheduled_task.ps1
   ```
   Det opretter TRE opgaver: "Lonsystem" (selve serveren, starter ved boot, fjerner
   Windows' normale 3-dages køretidsgrænse så den ikke bliver slået ihjel om natten,
   genstarter automatisk ved crash), "LonsystemAutoDeploy" (tjekker GitHub hvert
   5. minut for evigt, se Del 4), og "LonsystemBackup" (backup af database og
   satsfiler kl. 00:00/06:00/12:00/18:00, se Del 6). Scriptet kan køres igen når
   som helst — det opdaterer bare de eksisterende opgaver.
3. Tjek at den kører: `http://<ip-adresse>:8000` i en browser fra en anden PC.
4. Nyttige kommandoer fremover:
   ```
   Get-ScheduledTask -TaskName Lonsystem | Get-ScheduledTaskInfo   # status
   Stop-ScheduledTask -TaskName Lonsystem                           # stop
   Start-ScheduledTask -TaskName Lonsystem                          # (gen)start
   ```
   Serveren starter nu automatisk ved genstart af maskinen. Output/fejl fra kørslen
   ses i Task Scheduler (find opgaven → fanen "Historik"), eller ved midlertidigt selv
   at køre `python -m uvicorn main:app --host 0.0.0.0 --port 8000` fra `app`-mappen
   for at se live output i et almindeligt vindue.

## Del 4 – Automatisk deploy ved push til GitHub

Opgaven "LonsystemAutoDeploy" (oprettet i Del 3) kører [auto_deploy_check.ps1](auto_deploy_check.ps1)
hvert 5. minut: den henter status fra GitHub, og hvis der er nye commits på `main`
siden sidst, kører den [deploy.ps1](deploy.ps1) automatisk (backup, ny kode, nye
Python-pakker, genstart af serveren). Er der intet nyt, gør den ingenting.

**Vigtigt:** et `git push` til `main` er fra nu af reelt et deploy til produktion —
inden for højst 5 minutter. Test derfor altid grundigt lokalt (udviklings-configen,
`--reload`, port 8000) før du pusher.

Se status for seneste kørsel:
```
Get-ScheduledTask -TaskName LonsystemAutoDeploy | Get-ScheduledTaskInfo
```

Hver kørsel logges desuden med tidsstempel i `deploy\auto_deploy.log` (i repo-mappen),
fx:
```
2026-08-27 19:50:02 - Tjek om der er aendringer
2026-08-27 19:50:03 - Ingen aendringer
2026-08-27 19:55:02 - Tjek om der er aendringer
2026-08-27 19:55:03 - Aendringer fundet til Lonsystem (a1b2c3d -> e4f5g6h)
2026-08-27 19:55:03 - Starter git pull og deploy
2026-08-27 19:55:05 - Succes - opdateret til e4f5g6h
```
Åbn filen i notepad når som helst for at se historikken:
```
notepad C:\Users\LoenPC\Lonsystem\deploy\auto_deploy.log
```

## Del 5 – (Valgfrit) Øjeblikkeligt deploy fra den bærbare, uden at vente 5 minutter

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
   ssh <bruger>@<produktions-ip> "cd C:\Users\LoenPC\Lonsystem; powershell -File deploy\deploy.ps1"
   ```
   [deploy.ps1](deploy.ps1) bruger allerede opgavenavnet `Lonsystem` (matcher
   Task Scheduler-opgaven ovenfor), så det virker uden ændringer.

## Del 6 – Backup

Opgaven "LonsystemBackup" (oprettet i Del 3) kører [backup/backup.py](../backup/backup.py)
fire gange dagligt (00:00, 06:00, 12:00, 18:00) og zipper databasen samt de tre
Excel-satsfiler. Zip-filerne gemmes i:
```
C:\Users\LoenPC\OneDrive - Poul Schou A S\Dokumenter
```
De seneste 5 dages backups beholdes, ældre slettes automatisk. Backup kører også
automatisk som første skridt i hvert deploy (både manuelt og via auto-deploy).

**Vigtigt:** at filen ligger i en OneDrive-mappe betyder ikke automatisk at den er
uploadet til skyen — selve OneDrive-synkroniseringen kræver at OneDrive-klienten
kører under en logget-ind brugers session. Kører produktionsmaskinen uden nogen
nogensinde logget ind, ligger backuppen kun lokalt indtil nogen logger ind. Tal med
IT om automatisk login til en dedikeret konto er acceptabelt hos jer, hvis
uploaden skal ske uden manuel indblanding.

Test manuelt:
```
Start-ScheduledTask -TaskName LonsystemBackup
Get-ScheduledTask -TaskName LonsystemBackup | Get-ScheduledTaskInfo
```

## Opsummeret arbejdsgang fremover
1. Udvikl og test på den bærbare (`--reload`, port 8000).
2. `git push` til `main` på GitHub når det er testet.
3. Kør `deploy.ps1` mod produktionsmaskinen (lokalt eller via ssh) — tager backup,
   henter koden, opdaterer pakker, genstarter servicen.
