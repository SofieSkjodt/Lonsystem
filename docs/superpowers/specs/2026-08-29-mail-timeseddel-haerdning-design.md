# Sikker mailafsendelse fra PDF-timeseddel-knapperne

**Dato:** 2026-08-29
**Status:** Godkendt

## Baggrund

Systemet har allerede fuld funktionalitet til at sende timesedler som mail:

- Per-medarbejder **"✉ Send"**-knap i lønkørsel → `POST /api/timeseddel/{employee_id}/send`
- Batch **"Send Timeseddel"** i PDF-Timesedler-modal → `POST /api/timeseddel/send-all`

Begge bruger [`app/utils/email_sender.py`](../../../app/utils/email_sender.py) til selve SMTP-afsendelsen (STARTTLS på port 587), med indstillinger hentet fra `app/.env` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`). Der er ikke behov for ny funktionalitet eller nye knapper — opgaven er at gøre den eksisterende funktionalitet klar til reel brug og hærde fejlhåndteringen.

I dag er `SMTP_PASSWORD` i `app/.env` en placeholder (`<Indsæt kodeord>`), så afsendelse fejler i praksis. Fejlhåndteringen i `/send`-endpointet returnerer desuden den rå exception-tekst til klienten (`f"E-mail kunne ikke sendes: {e}"`), hvilket ikke matcher resten af kodebasens mønster for fejlbeskeder (se fx `payroll_router.py:308`), hvor interne detaljer logges server-side og kun en generisk besked vises til brugeren.

## Mål

1. Fejlhåndtering ved mailafsendelse hærdes, så interne SMTP-fejl (forbindelsesfejl, auth-fejl, mv.) aldrig lækkes til klienten — kun logges internt.
2. `SMTP_PASSWORD` udfyldes med en reel adgangskode, så afsendelse rent faktisk virker.
3. End-to-end-test: både enkelt-afsendelse (✉ Send) og batch-afsendelse (Send Timeseddel i PDF-Timesedler-modal) verificeres i browseren.

## Ikke omfattet

- Understøttelse af implicit SSL / port 465 (fravalgt — Microsoft 365 bruger STARTTLS/587, og det er tilstrækkeligt for nu).
- Ny UI eller nye knapper — de to eksisterende indgange er dem der skal virke.
- Ændring af hvilken postkasse der bruges i test (skj@poulschou.dk bruges til intern systemtest; selve mailadressen er allerede fuldt konfigurerbar via `.env` og kræver ingen kodeændring ved skift).

## Ændringer

### 1. `app/routers/timeseddel_router.py` — `/send`-endpoint

Exception fra `_send_email(...)` fanges som i dag, men:
- Den fulde exception logges internt med `logging.error(...)` (inkl. medarbejdernavn/id for sporbarhed).
- Klienten får en generisk `HTTPException(500, "Mailen kunne ikke sendes – kontakt administrator")` i stedet for den rå exception-tekst.

### 2. `app/routers/timeseddel_router.py` — `/send-all`-endpoint

`failed`-listen, der bygges op i løkken over medarbejdere, indeholder i dag `{"name": ..., "error": str(e)}` med den rå exception-tekst. Dette ændres til:
- Den fulde exception logges internt med `logging.error(...)` pr. medarbejder.
- `failed`-listen returnerer stadig medarbejdernavnet, men med en generisk fejltekst (fx `"Kunne ikke sendes"`) i stedet for den rå exception-streng, så SMTP-interne detaljer ikke eksponeres i UI'et — heller ikke til en administrator, i tilfælde af at fejlbeskeden indeholder følsomme forbindelsesoplysninger.

### 3. `app/.env`

Tilføjer en kort kommentarlinje over SMTP-blokken der gør eksplicit, at `SMTP_USER`/`SMTP_FROM` skal udskiftes ved skift til en anden afsender-postkasse, og at `SMTP_PASSWORD` er en app-adgangskode/almindelig adgangskode til den konto der er sat i `SMTP_USER`.

`SMTP_PASSWORD` udfyldes af brugeren direkte i filen (ikke via chat).

### 4. Test

Når `SMTP_PASSWORD` er udfyldt:
- Test ✉ Send for én medarbejder med en gyldig e-mailadresse — bekræft succes-toast og at mailen rent faktisk sendes (via SMTP-log/response, evt. bekræftet af bruger at mailen er modtaget).
- Test batch-afsendelse via PDF-Timesedler-modalens "Send Timeseddel" for en periode med mindst én medarbejder — bekræft `sent`/`skipped_no_email`/`skipped_no_activities`/`failed`-optællingen i toasten.
- Test fejlscenarie (fx forkert adgangskode midlertidigt) for at bekræfte at klienten kun ser den generiske besked, mens den fulde fejl står i serverloggen.

## Nøgle-filer

| Fil | Ændring |
|-----|---------|
| `app/routers/timeseddel_router.py` | Generisk fejlbesked + intern logging i `/send` og `/send-all` |
| `app/.env` | Forklarende kommentar over SMTP-blok; `SMTP_PASSWORD` udfyldes af bruger |
