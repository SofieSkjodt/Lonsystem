# Sikkerhedsrapport – PS Lønsystem
**Dato:** 21. juni 2026  
**Udført af:** Claude (Sonnet 4.6) via /superpowers  
**Metode:** Manuel parallel agentgennemgang (4 agenter: auth/RBAC, API-endpoints, kodekvalitet, frontend)  
**Status ved rapport-afslutning:** Alle Kritisk/Høj/Middel-fund rettet undtagen ét (se note)

---

## Oversigt

| Klassifikation | Antal | Rettet | Sprunget over |
|---|---|---|---|
| Kritisk | 5 | 4 | 1 |
| Høj | 5 | 5 | 0 |
| Middel | 6 | 6 | 0 |
| Lav | 4 | 0 | 4 (lavprioritet) |
| **Total** | **20** | **15** | **5** |

---

## Kritisk (5 fund)

### K1 – SESSION_SECRET ikke konfigureret
**Fil:** `app/main.py`  
**Problem:** `SessionMiddleware` brugte en hardkodet, forudsigelig nøgle direkte i kildekoden. En angriber med adgang til kildekoden kunne forfalske session-cookies og logge ind som enhver bruger.  
**Rettelse:** `SESSION_SECRET` hentes nu fra `.env` med `os.getenv()`. Stærk tilfældig nøgle genereret og gemt i `.env`. Hærdet yderligere efter denne rapport: appen rejser nu en `RuntimeError` og starter slet ikke, hvis nøglen mangler (`app/main.py:30-34`) – ikke blot en logging-advarsel.  
**Status:** ✅ Rettet

### K2 – Ingen security headers (CSP, clickjacking, MIME-sniffing)
**Fil:** `app/main.py`  
**Problem:** Ingen HTTP-sikkerhedsheadere. Muliggjorde clickjacking (`X-Frame-Options` manglede), MIME-sniffing (`X-Content-Type-Options` manglede) og XSS via manglende Content Security Policy.  
**Rettelse:** `_SecurityHeaders`-middleware tilføjet med:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://login.microsoftonline.com; frame-src https://login.microsoftonline.com;` (de to sidste direktiver tilføjet senere for Entra ID SSO – se `app/main.py:42-49` for den aktuelle streng)

Note: `'unsafe-inline'` er nødvendigt fordi appen bruger mange inline `onclick="..."` handlere. XSS-beskyttelse håndteres i stedet af escapeHtml() i JavaScript.  
**Status:** ✅ Rettet

### K3 – XSS via usaniteret brugerdata i innerHTML
**Fil:** `app/static/js/app.js`  
**Problem:** Brugerdata (navne, initialer, overenskomsttyper m.fl.) blev indsat direkte i `innerHTML` uden HTML-escapeing. En angriber med et ondsindet navn som `<img src=x onerror=alert(1)>` i databasen ville kunne eksekvere JavaScript i alle brugeres browsere.  
**Rettelse:** `escapeHtml(str)` / `h()` hjælper tilføjet øverst i app.js. Anvendt på alle innerHTML-steder med brugerdata (8 lokationer).  
**Status:** ✅ Rettet

### K4 – XSS via inline onclick med brugerdata
**Fil:** `app/static/js/app.js`  
**Problem:** `sendTimeseddel` kaldtes med `onclick="sendTimeseddel(${emp.employee_id}, '${emp.employee_name}')"`. Et navn med `'` eller `)` ville bryde ud af strengen og eksekvere vilkårlig kode.  
**Rettelse:** `sendTimeseddel` modtager nu kun `employeeId` (et sikkert heltal). Navn slås op fra `state.payrollData` internt i funktionen.  
**Status:** ✅ Rettet

### K5 – Default "admin" adgangskode
**Fil:** Database (AppUser-tabel)  
**Problem:** Standard admin-bruger oprettet med adgangskoden "admin".  
**Rettelse:** BEVIDST SPRUNGET OVER – testversion på internt netværk.  
**⚠️ Handling krævet:** Skift adgangskoden INDEN systemet tages i brug for rigtige data eller åbnes for netværksadgang udefra. Brug admin-UI'et til at sætte en stærk adgangskode.  
**Status:** ❌ Ikke rettet

---

## Høj (5 fund)

### H1 – Ingen rate limiting på login-endpoint
**Fil:** `app/routers/auth.py`  
**Problem:** Ingen begrænsning på loginforsøg. En angriber kunne forsøge millioner af adgangskoder (brute-force) mod enhver bruger.  
**Rettelse:** In-memory rate limiter tilføjet: maks. 5 forsøg per IP per 60 sekunder. Returnerer HTTP 429 ved overskridelse.  
**Status:** ✅ Rettet

### H2 – Path traversal i output_folder
**Fil:** `app/routers/payroll_router.py`  
**Problem:** `output_folder` fra request-body blev brugt direkte som sti til at gemme filer. En angriber kunne angive `../../../../Windows/System32/` og overskrive systemfiler.  
**Rettelse:** `Path(body.output_folder).resolve()` bruges nu, som kanoniserer stien og fjerner `../`-segmenter.  
**Status:** ✅ Rettet

### H3 – Path traversal i import_ddd
**Fil:** `app/routers/import_ddd.py`  
**Problem:** Samme problem som H2 — brugerkontrollerede stier til `.ddd`-filer blev ikke valideret. Kunne bruges til at læse vilkårlige filer.  
**Rettelse:** `Path(...).resolve()` på alle stier. Filtype-validering tilføjet: kun `.ddd`-filer accepteres.  
**Status:** ✅ Rettet

### H4 – Email header injection
**Fil:** `app/utils/email_sender.py`  
**Problem:** Brugerdata (medarbejdernavn, lønperiode) indsættes direkte i e-mail Subject-headeren. Indeholder disse `\r\n`, kan en angriber injicere ekstra headers og manipulere e-mailens routing eller indhold.  
**Rettelse:** `_sanitize_header(value)` fjerner `\r`, `\n` og `\0` fra alle headerverdier.  
**Status:** ✅ Rettet

### H5 – Ingen permission-validering på ukendte rettigheder
**Fil:** `app/routers/roles.py`  
**Problem:** Roller kunne oprettes/opdateres med vilkårlige permission-strenge der ikke eksisterer i systemet. Forårsagede uforudsigelig adfærd.  
**Rettelse:** Validering mod `ALL_PERMISSIONS`-dict tilføjet. HTTP 400 ved ukendte rettigheder.  
**Status:** ✅ Rettet

---

## Middel (6 fund)

### M1 – Cascade-problem ved sletning af vogn
**Fil:** `app/routers/vehicles.py`  
**Problem:** En vogn med tilknyttede aktiviteter kunne slettes, hvilket efterlod aktiviteter med dangling references.  
**Rettelse:** Tjek tilføjet: HTTP 400 hvis aktiviteter tilknyttet vognen eksisterer.  
**Status:** ✅ Rettet

### M2 – WAL-opsætning uden fejlhåndtering
**Fil:** `app/database/session.py`  
**Problem:** `PRAGMA journal_mode=WAL` og `PRAGMA foreign_keys=ON` kaldtes uden try/except. Fejl her crashede applikationen ved opstart.  
**Rettelse:** Indpakket i try/except med `logging.error`.  
**Status:** ✅ Rettet

### M3 – Database rollback manglede
**Fil:** `app/database/session.py`  
**Problem:** `get_db()` lukker databasesessionen men rollback'ede ikke ved exception, hvilket kunne efterlade en halvt udført transaktion.  
**Rettelse:** `except Exception: db.rollback(); raise` tilføjet.  
**Status:** ✅ Rettet

### M4 – Stack traces lækket til bruger
**Fil:** `app/routers/employees.py` (og andre)  
**Problem:** Interne fejlbeskeder (filstier, stack traces) blev returneret til klienten. En angriber kan bruge disse oplysninger til at kortlægge serveren.  
**Rettelse:** Generiske fejlbeskeder til klienten + `logging.error()` til server-log.  
**Status:** ✅ Rettet

### M5 – XSS i PDF-indhold
**Fil:** `app/routers/timeseddel_router.py`  
**Problem:** Brugerdata (navne, overenskomsttyper) indsættes i PDF uden escapeing. I reportlab kan dette i teorien manipulere PDF-indholdet.  
**Rettelse:** `html.escape()` (importeret som `_esc`) anvendt på al brugerdata i PDF-generering.  
**Status:** ✅ Rettet

### M6 – Session cookie manglede SameSite
**Fil:** `app/main.py`  
**Problem:** Session-cookie uden `SameSite`-attribut er sårbar over for CSRF (Cross-Site Request Forgery), hvor et ondsindet website sender requests på brugerens vegne.  
**Rettelse:** `same_site="lax"` sat på `SessionMiddleware`.  
**Status:** ✅ Rettet

---

## Lav (4 fund – ikke rettet)

### L1 – localStorage til brugerindstillinger
**Fil:** `app/static/js/app.js`  
**Problem:** `localStorage.setItem("anciennitet_dismissed", ...)` gemmer brugerstate i localStorage. Lav risiko, men sessionStorage er mere korrekt for session-bundet state.  
**Anbefaling:** Skift til `sessionStorage` ved lejlighed.

### L2 – Danløn-koder er placeholders
**Fil:** `app/calculators/pay_rates.py`  
**Problem:** Alle Danløn CSV-koder er midlertidigt sat til "1". Ikke en sikkerhedssårbarhed, men en driftsfejl der vil give forkert lønudbetaling.  
**Anbefaling:** Opdater koder når de kendes fra lønafdelingen.

### L3 – Ingen HTTPS
**Problem:** Systemet kører på HTTP. Adgangskoder og session-cookies transmitteres ukrypteret over netværket.  
**Anbefaling:** Aktiver HTTPS med et certifikat (Let's Encrypt eller internt CA) inden systemet bruges på et netværk med potentielt upålidelige enheder.

### L4 – Audit log dækker ikke alle handlinger
**Fil:** `app/routers/`  
**Problem:** Ikke alle handlinger (f.eks. ændring af overenskomstsatser) logges i audit log.  
**Anbefaling:** Gennemgå og udvid audit log-dækning løbende.

---

## Åbne punkter til næste gennemgang

- [ ] Skift default admin-adgangskode (K5) inden produktionsbrug
- [ ] Aktivér HTTPS (L3) inden netværkseksponering
- [ ] Opdater Danløn-koder (L2) med korrekte koder fra lønafdelingen
- [ ] Skift `localStorage` → `sessionStorage` for anciennitet-flag (L1)
- [x] Test SMTP-afsendelse af timesedler — løst 2026-08-29: Authenticated SMTP genaktiveret og i produktion (`app/.env`: `SMTP_USER`/`SMTP_PASSWORD` sat)

---

## Rettede filer (samlet)

| Fil | Rettelse |
|---|---|
| `app/main.py` | SESSION_SECRET fra .env, _SecurityHeaders middleware, SameSite=lax |
| `app/.env` | SESSION_SECRET tilføjet |
| `app/routers/auth.py` | Rate limiter (5/60s per IP) |
| `app/routers/roles.py` | Permission-validering mod ALL_PERMISSIONS |
| `app/routers/vehicles.py` | Cascade-tjek før sletning |
| `app/database/session.py` | WAL try/except, rollback i get_db |
| `app/routers/employees.py` | Generisk fejlbesked + intern logging |
| `app/routers/payroll_router.py` | Path.resolve() + generiske fejl |
| `app/routers/import_ddd.py` | Path.resolve() + .ddd-validering |
| `app/utils/email_sender.py` | _sanitize_header() mod header injection |
| `app/routers/timeseddel_router.py` | html.escape() på al brugerdata i PDF |
| `app/static/js/app.js` | escapeHtml()/h() + XSS-fix på alle innerHTML-steder |

---

## Vejledning til AI-assistent ved fremtidig sikkerhedsopfølgning

Når du som AI-assistent skal fortsætte sikkerheden i dette system, brug denne rapport som baseline:

1. **Alle fund markeret ✅ er rettet** – spørg ikke om dem igen medmindre koden er ændret
2. **K5 (admin-kode) er bevidst udskudt** – tag det op hvis systemet skal i produktion
3. **L1-L4 er kendte lavprioritetsfund** – tag dem op hvis der er tid
4. **Arkitektur:** FastAPI + SQLite + vanilla JS. Ingen eksterne frameworks i frontend.
5. **Næste naturlige skridt:** HTTPS-opsætning + audit log-udvidelse + Danløn-koder
6. **Testmiljø:** Intern server på lokalt netværk. Ikke eksponeret mod internet.
