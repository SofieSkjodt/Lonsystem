# Global til/fra-kontakt for auto-godkendelse – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Systemet har i dag to uafhængige mekanismer der auto-godkender aktiviteter:

1. **Statistisk baseline-godkendelse** (`app/calculators/auto_approval.py`,
   `should_auto_approve()`) – kører ved DDD-import (`import_ddd.py`) og ved
   bulk-knappen "Autogodkend aktiviteter" (`POST /api/activities/auto-approve-pending`).
   Godkender kun `normal`-type tachograf-aktiviteter der matcher medarbejderens
   historiske mønster (se `docs/AUTO_APPROVAL.md`).
2. **Permission-baseret godkendelse ved manuel oprettelse**
   (`app/routers/activities.py`, `create_manual_activity()`) – brugere med
   permissionen `auto_approve_manual_activities` får deres manuelt oprettede
   `normal`-aktiviteter godkendt med det samme (se
   `docs/superpowers/specs/2026-08-25-auto-godkend-opret-aktivitet-design.md`).

**Ønsket ændring:** En admin (eller bruger med en ny dedikeret permission) skal
kunne slå BEGGE disse processer fra globalt via én kontakt i systemet. Når slået
fra, forbliver `normal`-aktiviteter `pending` uanset baseline-match eller
brugerens permission, og skal godkendes manuelt.

**Ikke omfattet:** Fraværstypers (ferie, sygdom, barsel osv.) automatiske
godkendelse ved manuel oprettelse er grundlæggende adfærd for de typer, uafhængig
af `auto_approve_manual_activities`-permissionen, og påvirkes IKKE af kontakten –
de godkendes fortsat øjeblikkeligt som i dag, uanset kontaktens tilstand.

## Datamodel

Ny singleton-tabel `SystemSettings` i `app/database/models.py`:

```python
class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)  # altid 1 – singleton
    auto_approval_enabled = Column(Boolean, default=True, nullable=False, server_default="1")
    updated_by = Column(String, nullable=True)   # initialer på seneste bruger der ændrede
    updated_at = Column(DateTime, nullable=True)
```

**Begrundelse for dedikeret tabel fremfor generisk key-value:** Kodebasen bruger
konsekvent eksplicitte, typede kolonner og idempotente `_ensure_*()`-migrations-
funktioner til skemaændringer (fx `_ensure_auto_approve_permission()`,
`_ensure_activity_permissions()`). En generisk key-value-tabel ville kræve
streng-parsing af boolean-værdier ved hvert opslag og introducerer et nyt mønster
kodebasen ikke bruger andre steder. Fremtidige indstillinger tilføjes som nye
kolonner via samme idempotente migrations-mønster.

**Seeding/migration:** `_ensure_system_settings()` i `app/database/session.py`
(kaldt fra `init_db()`, samme sted som øvrige `_ensure_*`-kald) opretter
singleton-recorden med `id=1, auto_approval_enabled=True` hvis den ikke findes.
Idempotent – kørt to gange opretter ikke en ekstra record.

## Permission

Ny permission i `ALL_PERMISSIONS` (`app/auth.py`) og `PERMISSION_LABELS`
(`app/static/js/app.js`):

- **Navn:** `manage_auto_approval`
- **Label (dansk):** "Slå auto-godkendelse til/fra"

**Default-tildeling:**

| Rolle | Har permissionen som default? |
|---|---|
| `admin` | Ja – implicit, systemrolle (`_role_has_permission()` returnerer altid `True`) |
| `lonbogholder` | Nej |
| `disponent` | Nej |

Kan tildeles andre roller senere via rolle-editoren uden kodeændring, som alle
øvrige ikke-system-permissions.

## Backend-logik

### `app/calculators/auto_approval.py` – `should_auto_approve()`
Tjekker `SystemSettings.auto_approval_enabled` **først**, før nogen baseline-
opslag:
```python
settings = db.query(SystemSettings).get(1)
if settings is None or not settings.auto_approval_enabled:
    return False, ["Automatisk godkendelse er slået fra i systemindstillinger"]
```

### `app/calculators/baseline_updater.py` – `update_baseline_from_activity()`
Tjekker samme flag tidligt i funktionen og returnerer uden at røre
`EmployeeBaseline` hvis slået fra – **uanset om aktiviteten godkendes manuelt
eller automatisk**. Baseline-læring er dermed fuldstændig sat på pause mens
kontakten er fra, ikke kun selve auto-godkendelses-beslutningen.

### `app/routers/activities.py` – `create_manual_activity()`
```python
can_auto_approve = user_has_permission(db, current_user, "auto_approve_manual_activities") \
                    and _auto_approval_globally_enabled(db)
```
Påvirker kun `normal`-grenen (`is_absence`-grenen er uændret – se "Ikke omfattet"
ovenfor).

### `app/routers/activities.py` – `bulk_auto_approve()` (`POST /auto-approve-pending`)
Tjekker global setting ved kaldets start:
```python
if not _auto_approval_globally_enabled(db):
    raise HTTPException(400, "Automatisk godkendelse er slået fra i systemindstillinger")
```
Forsvar i dybden – UI skjuler knappen, men endpointet er stadig direkte kaldbart.

### `app/routers/import_ddd.py`
Ingen kodeændring nødvendig – `should_auto_approve()` håndterer det globale tjek
internt, og import-flowet reagerer allerede korrekt på `(False, flags)`.

En lille delt hjælpefunktion `_auto_approval_globally_enabled(db) -> bool` tilføjes
(fx i `auto_approval.py`) og genbruges de tre steder ovenfor, så selve
opslagslogikken kun findes ét sted.

## API-endpoints

Tilføjes i eksisterende `app/routers/auto_approval_router.py`:

| Metode | URL | Beskrivelse | Tilladelse |
|---|---|---|---|
| `GET` | `/api/auto-approval/settings` | Returnerer `{"enabled": bool}` | Enhver godkendt bruger |
| `POST` | `/api/auto-approval/settings` | Body `{"enabled": bool}` – opdaterer singleton, sætter `updated_by`/`updated_at`, logger til hændelseslog (`log_action`) | `manage_auto_approval` |

`GET` er åben for alle godkendte brugere (ikke kun permission-indehavere), fordi
frontend skal kunne skjule bulk-knappen for alle, uanset rolle.

## Frontend

### Ny fane under Stamdata
`app/templates/index.html` – ny fane-knap `sd-tab-autoapproval` med
`data-perm-require="manage_auto_approval"` (samme mønster som
`sd-tab-holiday` med `manage_holidays`) – kun brugere med permissionen ser
fanen. Panel med:
- Toggle-kontakt der viser nuværende tilstand
- Kort forklarende tekst om konsekvens (DDD-import og manuel oprettelse
  påvirkes, fraværstyper ikke)
- Ved klik: `POST /api/auto-approval/settings`, opdater UI og
  `state.autoApprovalEnabled`

### Bulk-knap i aktivitetsoversigten
`state.autoApprovalEnabled` hentes ved app-bootstrap via
`GET /api/auto-approval/settings` (kaldes for alle brugere, uafhængigt af
permission). `btn-auto-approve`-knappen (`app/templates/index.html:161`) skjules
helt (`style.display = "none"`) når `false`, i samme funktion/flow som
`applyRoleVisibility()` håndterer `data-perm-require` i dag – fx en parallel
`applySystemSettingsVisibility()` kaldt samme sted i bootstrap-sekvensen.

## Test-dækning (til implementeringsplan)

- `GET /settings` uden ændringer returnerer `{"enabled": true}` (default efter seeding)
- `POST /settings` uden `manage_auto_approval` → 403
- `POST /settings` med permission → opdaterer flag, logger hændelse, `GET` bagefter afspejler ændringen
- DDD-import: aktivitet der ellers ville match baseline (opfylder alle 4 betingelser) forbliver `pending` med flag "Automatisk godkendelse er slået fra..." når kontakten er fra
- `should_auto_approve()` rører ikke `EmployeeBaseline` når kontakten er fra (ingen sample_count-ændring)
- Manuel godkendelse (`POST /{id}/approve`) opdaterer IKKE `EmployeeBaseline` når kontakten er fra, selvom aktiviteten normalt ville bidrage
- Bruger med `auto_approve_manual_activities` opretter `normal`-aktivitet mens kontakten er fra → `status=pending` (ikke auto-godkendt), ingen kommentar-fallback
- Bruger uden `auto_approve_manual_activities` opretter fraværstype (fx `ferie`) mens kontakten er fra → `status=approved` uændret (ikke omfattet)
- `POST /auto-approve-pending` mens kontakten er fra → 400
- `admin` (systemrolle) kan tilgå og ændre indstillingen uden at permissionen er tilføjet eksplicit til admins permissions-liste
- Migration: `_ensure_system_settings()` kørt to gange opretter ikke dubletter; kørt på eksisterende DB uden tabellen opretter den med default `True`

## Ikke i scope

- Ingen ændring af fraværstypers eksisterende auto-godkendelses-adfærd ved oprettelse.
- Ingen ændring af `approve_activity()` (det almindelige manuelle godkendelses-flow) andet end at baseline-opdateringen deri nu respekterer den globale kontakt.
- Ingen generel systemindstillings-infrastruktur (key-value-tabel, indstillings-UI-framework) – kun det ene boolean-flag.
- Ingen retroaktiv effekt på allerede godkendte/flaggede aktiviteter når kontakten slås til/fra igen.
