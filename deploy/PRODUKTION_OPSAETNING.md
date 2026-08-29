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

## Del 3 – Gør det til en vedvarende opgave (kører uden åbent vindue, starter ved boot)

Helt native Windows — ingen tredjeparts-software. Et lille batch-script
([run_production.bat](run_production.bat)) starter serveren og genstarter den
automatisk hvis processen nogensinde stopper; en Task Scheduler-opgave sørger for
at batch-scriptet selv starter ved boot, uden at nogen skal være logget ind.

1. Åbn PowerShell **som administrator** i `C:\Users\LoenPC\Lonsystem`.
2. Kør opsætnings-scriptet én gang:
   ```
   powershell -ExecutionPolicy Bypass -File deploy\setup_scheduled_task.ps1
   ```
   Det opretter TO opgaver: "Lonsystem" (selve serveren, starter ved boot, fjerner
   Windows' normale 3-dages køretidsgrænse så den ikke bliver slået ihjel om natten)
   og "LonsystemAutoDeploy" (tjekker GitHub hvert 5. minut, se Del 4). Begge startes
   med det samme.
3. Tjek at den kører: `http://<ip-adresse>:8001` i en browser fra en anden PC.
4. Nyttige kommandoer fremover:
   ```
   Get-ScheduledTask -TaskName Lonsystem | Get-ScheduledTaskInfo   # status
   Stop-ScheduledTask -TaskName Lonsystem                           # stop
   Start-ScheduledTask -TaskName Lonsystem                          # (gen)start
   ```
   Serveren starter nu automatisk ved genstart af maskinen, og genstarter selv ved
   crash (batch-scriptets egen løkke). Output fra hver kørsel kan ses ved at åbne
   Aktivitetsstyring, eller ved midlertidigt at køre `run_production.bat` direkte
   i et vindue for at se live output.

## Del 4 – Automatisk deploy ved push til GitHub

Opgaven "LonsystemAutoDeploy" (oprettet i Del 3) kører [auto_deploy_check.ps1](auto_deploy_check.ps1)
hvert 5. minut: den henter status fra GitHub, og hvis der er nye commits på `main`
siden sidst, kører den [deploy.ps1](deploy.ps1) automatisk (backup, ny kode, nye
Python-pakker, genstart af serveren). Er der intet nyt, gør den ingenting.

**Vigtigt:** et `git push` til `main` er fra nu af reelt et deploy til produktion —
inden for højst 5 minutter. Test derfor altid grundigt lokalt (udviklings-configen,
`--reload`, port 8000) før du pusher.

Se status/log for seneste kørsel:
```
Get-ScheduledTask -TaskName LonsystemAutoDeploy | Get-ScheduledTaskInfo
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

## Opsummeret arbejdsgang fremover
1. Udvikl og test på den bærbare (`--reload`, port 8000).
2. `git push` til `main` på GitHub når det er testet.
3. Kør `deploy.ps1` mod produktionsmaskinen (lokalt eller via ssh) — tager backup,
   henter koden, opdaterer pakker, genstarter servicen.
