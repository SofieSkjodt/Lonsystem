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
3. Hent Caddy (TLS-reverse proxy foran uvicorn) fra
   https://caddyserver.com/download (vælg "windows/amd64", ingen ekstra
   moduler), og læg den umodificerede `caddy.exe` i `deploy/tools/caddy.exe`
   FØR provisionering køres - den er ikke bundlet i repoet.
4. Find ledig statisk IP, gateway, DNS og netværkskort-navn
   (`Get-NetAdapter` viser navnet) på kontorets netværk.
5. Beslut hvilken cloud-mappe (fx en dedikeret OneDrive/SharePoint-mappe)
   backup-zips skal ende i, og hvilken Windows-konto der skal have
   lov at pushe opdateringer til serveren.
6. Åbn `provision-server.ps1` og udfyld konfigurationsblokken øverst
   (`$StaticIP`, `$Gateway`, `$DnsServer`, `$InterfaceAlias`,
   `$BackupCloudDir`, `$DeployShareUser`).
7. Højreklik `provision-server.ps1` → "Kør med PowerShell som administrator".
8. Verificér:
   - `Get-Service LonsystemService` og `Get-Service LonsystemCaddy` viser
     begge `Running`
   - `https://localhost` svarer på selve laptoppen (browseren viser en
     certifikat-advarsel, indtil Caddys interne CA er betroet - se
     "Driftsopmærksomhed" nedenfor)
   - `https://<StaticIP>` svarer fra en ANDEN pc på kontornetværket
   - `http://<StaticIP>:8000` svarer IKKE fra en anden pc (uvicorn er nu
     kun bundet til localhost - appen kan kun nås via Caddy/HTTPS)
9. Kør den fulde verifikationstjekliste (se nedenfor), før serveren tages i
   permanent brug.
10. På udviklingsmaskinen: tilføj serveren som git-remote (kør én gang):

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

- **Certifikat-advarsel i browseren.** Caddy genererer selv et lokalt
  CA-certifikat ("tls internal") - der er ikke brugt et offentligt betroet
  certifikat, da serveren kun er tilgængelig på kontornetværket. Kør
  `& "C:\Lønsystem\caddy.exe" trust` i en admin-PowerShell PÅ SERVEREN for at
  stole på certifikatet der, eller eksportér CA-certifikatet fra
  `caddy-data\caddy\pki\authorities\local\root.crt` og distribuér det til
  hver kontor-pc's rodcertifikat-lager (fx via gruppepolitik), hvis
  advarslen skal væk for alle. Indtil da virker siden fint, browseren viser
  bare en "usikker forbindelse"-advarsel, man skal klikke forbi.
- **Skift til Caddy på en EKSISTERENDE server:** kør `provision-server.ps1`
  igen - den opdaterer firewall-reglen og genopretter `LonsystemService`
  til at binde til localhost. Tilføj `HTTPS_ONLY=true` i `app/.env` manuelt
  bagefter (scriptet rører ikke en eksisterende `.env`), ellers virker login
  ikke længere, da cookien forventer HTTPS.
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
