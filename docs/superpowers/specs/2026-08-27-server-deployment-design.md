# Design: Flytning af Lønsystem til dedikeret server-laptop

**Dato:** 2026-08-27
**Status:** Godkendt (via chat-dialog), afventer skriftlig gennemgang

## Baggrund og formål

Lønsystemet kører i dag lokalt på Sofies udviklingsmaskine, i en OneDrive-synkroniseret
mappe. Det skal flyttes til en dedikeret, "altid tændt" bærbar computer på Poul Schou A/S'
kontornetværk, så andre medarbejdere kan tilgå det fra deres egne PC'er via browser.
Udviklingsmaskinen (denne) skal ikke længere være nødvendig for at systemet kører.

**Hvorfor:** Systemet er allerede arkitektonisk designet til centraliseret drift
(FastAPI + SQLite, tilgået via browser – se `docs/ARCHITECTURE.md`), men har aldrig
været sat op på en rigtig server. Flere brugere skal kunne tilgå det samtidigt, uden
afhængighed af én persons private maskine.

## Afklarede rammer (fra brainstorm-dialog)

- **Servertype:** Ny, dedikeret bærbar computer, "altid tændt", på firmaets interne netværk.
- **Serverstatus:** Anskaffes/klargøres fra bunden – frisk Windows 10/11, intet forudinstalleret.
- **Netværksadgang:** Kun fra kontorets interne netværk (LAN). Ingen VPN eller
  internet-eksponering. `SessionMiddleware` kører allerede med `https_only=False`,
  så almindelig HTTP over LAN fungerer uden ændringer.
- **Claude Codes rolle:** Ingen direkte fjernadgang til server-laptoppen. Alt forberedes
  her (scripts, guide, deployment-pakke), og brugeren kører det selv på laptoppen.
- **Opdateringsflow:** Udviklingsmaskinen er typisk på samme kontornetværk som serveren,
  så et delt netværksdrev kan bruges til at overføre opdateringer (se nedenfor).
- **Backup-destination:** Backup-zip'er (ikke selve den levende database) skal ende i en
  separat cloud-mappe (OneDrive/SharePoint), adskilt fra den levende data.
- **Fast IP:** Sættes som statisk IP direkte på laptoppen (ikke DHCP-reservation på routeren).

## Fundne og rettede problemer (gennemført 2026-08-27)

Under forberedelsen blev det opdaget at `app/.env` (hemmeligheder: `SESSION_SECRET`,
SMTP-login m.m.) og `app/database/lonsystem.db` (+ `-shm`/`-wal`) var sporet i git, på
trods af at `.gitignore` nævnte dem. Det er rettet:

- Filerne er fjernet fra git-sporing (`git rm --cached`), men findes stadig lokalt.
- `.gitignore` udvidet med `*.db`.
- `app/.env.example` tilføjet som skabelon – hver maskine har fremover sin egen `.env`.
- Historiske commits indeholder stadig gamle værdier af `.env` – **ikke** rettet (ville
  kræve destruktiv omskrivning af 295 commits og påvirke `claude/*`-worktree-branches).
  Anbefaling: generér nye `SESSION_SECRET`/SMTP-kodeord til serveren, så de gamle
  værdier i historikken bliver ubrugelige.

Denne rettelse var en forudsætning for det git-baserede opdateringsflow nedenfor – uden
den ville et `git pull` på serveren kunne overskrive den levende database.

## Arkitektur

```
[Server-laptop, altid tændt, på kontor-LAN]
├── C:\Lønsystem\app\              ← git-clone af koden (kører som Windows-tjeneste)
│    ├── database\lonsystem.db     ← lokal, IKKE synkroniseret (ikke OneDrive)
│    └── .env                      ← server-specifik, IKKE i git
├── C:\Lønsystem\deploy.git\       ← bart git-repo, delt som netværksmappe (deploy-mål)
├── NSSM-tjeneste "LonsystemService" → kører `uvicorn main:app --host 0.0.0.0 --port 8000`
├── Statisk IP på netværkskortet
├── Windows Firewall-regel: tillad indgående TCP 8000 (kun LAN-profil)
├── Strømindstillinger: aldrig dvale, "gør intet" ved låg-lukning (tændt)
└── Scheduled Task: backup 4x dagligt → zip → kopieres til cloud-backup-mappe

[Udviklingsmaskine (Sofie)]
├── Normal git-repo (som i dag)
├── Git-remote "server" → \\<server-ip>\deploy\deploy.git
└── publish-update.ps1 (valgfri hjælper til `git push server master`)

[Klient-PC'er på kontoret]
└── Browser → http://<server-static-ip>:8000
```

## Komponenter

### 1. Deployment-pakke (forberedes her, køres på laptoppen)

Selvstændig pakke der ikke kræver internetadgang på laptoppen:
- Embedded Python (eller fuld installer, afklares i implementeringsplan)
- Python-afhængigheder fra `app/requirements.txt`
- `deploy/tools/win32/nssm.exe` og `deploy/tools/win64/nssm.exe` (allerede hentet)
- Appkoden (git-clone eller kopi)
- `provision-server.ps1` – ét script, kørt som Administrator, der:
  1. Sætter statisk IP (placeholder-variabler øverst i scriptet, udfyldes af bruger)
  2. Åbner Windows Firewall for port 8000 (LAN-profil)
  3. Installerer Python-afhængigheder
  4. Opretter `C:\Lønsystem\database\` (lokal, ikke-synkroniseret) og flytter/initialiserer db der
  5. Opsætter NSSM-tjenesten (rigtig 64-bit `nssm.exe` medmindre laptoppen er 32-bit)
  6. Slår dvale/lås-ved-låg fra
  7. Opretter det bare git-repo (`deploy.git`) og deler mappen
  8. Registrerer backup-scheduled-task (genbruger eksisterende `backup/backup.py`,
     med `BACKUP_DIR` peget på cloud-backup-mappen)

### 2. NSSM Windows-tjeneste

- Tjenestenavn: `LonsystemService`
- Kommando: `nssm.exe install LonsystemService <python.exe> -m uvicorn main:app --host 0.0.0.0 --port 8000`
- Arbejdsmappe: `C:\Lønsystem\app`
- Genstart automatisk ved crash (NSSM standardopførsel)
- Starter ved boot, uden krav om login

### 3. Git-baseret opdateringsflow

**Engangsopsætning** (del af `provision-server.ps1`):
- Bart repo: `C:\Lønsystem\deploy.git`, delt som SMB-netværksmappe
- Serverens `C:\Lønsystem\app` er et git-clone med `origin` → det lokale bare repo
- Udviklingsmaskinen tilføjer remote: `git remote add server \\<server-ip>\deploy\deploy.git`

**Ved en rettelse:**
1. Ret og test lokalt (normal git-commit, som i dag)
2. `git push server master` fra udviklingsmaskinen
3. På serveren: kør `update.ps1` (skrivebordsgenvej) – stopper NSSM-tjenesten,
   `git pull origin master`, geninstallerer pip-pakker hvis `requirements.txt` er
   ændret, genstarter tjenesten. Database-skema-migrationer sker automatisk ved
   opstart (eksisterende `_migrate()`-mekanisme i `database/session.py`, uændret).
4. Fejl efter opdatering: `rollback.ps1` – `git checkout <forrige-tag>` + genstart.

Dette kræver ingen åbne fjernstyrings-porte (SSH/RDP) på lønsystem-serveren – kun
den eksisterende fildeling på kontornetværket.

### 4. Data- og hemmeligheds-håndtering

- `.env` er maskine-specifik og IKKE i git (rettet ovenfor) – serveren får sin egen,
  udfyldt ud fra `app/.env.example` med nye, unikke værdier.
- Databasen er lokal på serveren, IKKE i git, IKKE i en synkroniseret mappe.
- Første migrering: eksisterende database + Excel-satsfiler kopieres manuelt til
  serveren ved førstegangs-opsætning (via USB eller netværksdrev – engangsopgave,
  ikke en del af det løbende opdateringsflow).

## Test og verifikation

- Efter `provision-server.ps1`: verificér tjenesten kører (`Get-Service LonsystemService`)
  og svarer på `http://localhost:8000` på selve laptoppen.
- Test adgang fra en anden PC på netværket via `http://<static-ip>:8000`.
- Test opdaterings-flowet med en harmløs ændring (fx en tekstændring) end-to-end:
  push → `update.ps1` → verificér ændringen er live.
- Test rollback: kør `rollback.ps1`, verificér forrige version er tilbage.
- Verificér at NSSM genstarter tjenesten automatisk efter en simuleret crash
  (`Stop-Process` på uvicorn-processen).
- Verificér at laptoppen ikke går i dvale (test låg-lukning, mens den er tændt/strøm-tilsluttet).

## Åbne punkter (afklares når laptoppen er fysisk til stede)

- [ ] Statisk IP, subnet, gateway, DNS til laptoppen
- [ ] Endeligt filsti-navn for delt deploy-mappe / drevbogstav
- [ ] Om laptoppen er 32-bit eller 64-bit Windows (afgør hvilken `nssm.exe` der bruges –
      forventeligt 64-bit på enhver nyere maskine)
- [ ] Navn/hostname på laptoppen
