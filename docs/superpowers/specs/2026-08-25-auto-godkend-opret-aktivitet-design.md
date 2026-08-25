# Auto-godkendelse ved oprettelse af aktivitet – Design

**Dato:** 2026-08-25
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

I dag sætter opret-endepunktet (`POST /api/activities`, `create_manual_activity()` i
`app/routers/activities.py`) automatisk `status=approved` for fraværstyper (fx sygdom,
ferie), men "normal" arbejdstid oprettet manuelt får `status=pending` og skal
efterfølgende godkendes separat via `POST /api/activities/{id}/approve`.

Det godkendelses-endpoint kræver i dag en begrundelse i kommentarfeltet, hvis
aktivitetens varighed er under 4 timer (og den ikke når 4 timer sammen med andre
allerede godkendte aktiviteter samme kalenderdag for medarbejderen).

**Ønsket ændring:** Når en bruger med den rette rettighed opretter en aktivitet via
opret-aktivitet-modalen, skal den automatisk godkendes med det samme (uanset type).
Hvis aktiviteten er under 4 timer og brugeren ikke selv har udfyldt en kommentar,
skal kommentarfeltet automatisk sættes til brugerens initialer i stedet for at kræve
en manuel begrundelse.

## Beslutning: permission i stedet for hardcoded rollenavne

Systemet har allerede en dynamisk rolle/rettigheds-arkitektur (`Role`-tabel,
`ALL_PERMISSIONS`, `require_permission()`/`user_has_permission()` i `app/auth.py`).
For at undgå at hardcode rollenavne (`"admin"`, `"lonbogholder"`) i
aktivitets-routeren, og for at gøre det muligt for en admin senere at til/fravælge
adfærden per rolle uden kodeændring, indføres en ny permission:

- **Navn:** `auto_approve_manual_activities`
- **Label (dansk):** "Auto-godkend ved oprettelse"

### Default-tildeling

| Rolle         | Har permissionen som default? |
|---------------|-------------------------------|
| `admin`       | Ja – automatisk, fordi `admin` er en systemrolle (`is_system=True`). `_role_has_permission()` returnerer altid `True` for systemroller uanset permissions-listen, så `admin` behøver ikke permissionen eksplicit i sin liste. |
| `lonbogholder`| Ja – tilføjes til default-permissions i `_seed_roles()` |
| `disponent`   | Nej – ikke tilføjet. Kan tildeles senere af en admin via rollestyrings-UI'en. |

En admin kan senere ændre dette for `lonbogholder` og `disponent` via den eksisterende
rolle-editor, uden kodeændring, da permissionen behandles som enhver anden
ikke-system-permission.

## Ændringer

### 1. `app/auth.py`
Tilføj `"auto_approve_manual_activities": "Auto-godkend ved oprettelse"` til
`ALL_PERMISSIONS`.

### 2. `app/static/js/app.js`
Tilføj samme label til `PERMISSION_LABELS`, så rollestyrings-UI'en viser den korrekt.

### 3. `app/database/session.py`
- `_seed_roles()`: tilføj `"auto_approve_manual_activities"` til `lonbogholder`s
  default-permissions-liste (linje ~190). `admin` og `disponent`s lister ændres ikke.
- Ny idempotent migrationsfunktion `_ensure_auto_approve_permission()` (samme mønster
  som `_ensure_activity_permissions()`), der tilføjer permissionen til den eksisterende
  `lonbogholder`-rolle i en allerede-kørende produktions-DB, hvis den ikke allerede er
  der. Kaldes fra `init_db()` sammen med de øvrige `_ensure_*`-migrationer.

### 4. `app/routers/activities.py` – `create_manual_activity()`
1. Beregn `can_auto_approve = user_has_permission(db, current_user, "auto_approve_manual_activities")`
   tidligt i funktionen.
2. Byg `Activity`-objektet som i dag, men undlad at sætte `status`/`approved_by`/
   `approved_at` ved konstruktion (sæt `status=ActivityStatus.pending` som midlertidig
   placeholder). `db.add(activity)` og `db.flush()` **før** status afgøres, så
   aktiviteten har fået et `id` (nødvendigt fordi `_day_reaches_4h_with_approved()`
   udelukker aktiviteten selv via `Activity.id != a.id`).
3. Afgør endelig status:
   - Hvis `is_absence` **eller** `can_auto_approve`:
     `status = ActivityStatus.approved`, `approved_by = current_user.initials`,
     `approved_at = datetime.utcnow()`
   - Ellers (normal arbejdstid, ingen permission): status forbliver `pending`,
     `approved_by = None`, `approved_at = None` (uændret nuværende adfærd)
4. Kommentar-fallback: **kun hvis** `can_auto_approve` er sand, **og** den endelige
   status blev `approved` i dette kald, **og** varigheden er under 4 timer beregnet
   med samme logik som `is_under_4h` (dvs. `_duration_minutes()` +
   `_day_reaches_4h_with_approved()`), **og** `activity.comment` er tom/`None`:
   sæt `activity.comment = current_user.initials`.
   - Har brugeren selv skrevet en kommentar i opret-modalen, bevares den uændret.
   - Denne fallback udløses ikke for brugere uden permissionen (fx `disponent`), selv
     når en fraværstype under 4 timer auto-godkendes for dem som i dag – det er
     uændret adfærd.
5. `db.commit()`.

**Gælder for:** alle oprettelsesveje gennem dette ene endpoint – almindelig manuel
oprettelse og oprettelse med `source="vagtplan"` – da reglen er baseret på brugerens
permission, ikke på hvordan aktiviteten oprettes. Multi-dags-oprettelse i frontend'en
laver ét `POST`-kald per dag, så samme logik dækker automatisk alle dage uden
frontend-ændringer.

**Ingen ændringer i:** `approve_activity()`, `update_activity()`, eller
frontend-modalens felter/validering.

## Ikke i scope

- Ingen ændring af det eksisterende manuelle godkendelses-flow for brugere uden
  `auto_approve_manual_activities`.
- Ingen ændring af fraværstypers eksisterende auto-godkendelse for roller uden
  permissionen (fx `disponent`) – de forbliver godkendt uden krav om kommentar, som i
  dag.
- Ingen UI-indikation i selve opret-modalen om at aktiviteten vil blive auto-godkendt
  (kan tilføjes senere hvis ønsket).

## Test-dækning (til implementeringsplan)

- Bruger med `auto_approve_manual_activities` (fx lønbogholder) opretter normal
  arbejdstid ≥4 timer → `status=approved`, `approved_by` sat, kommentar uændret
  (tom hvis ikke udfyldt).
- Samme bruger opretter normal arbejdstid <4 timer uden kommentar →
  `status=approved`, `comment = initialer`.
- Samme bruger opretter normal arbejdstid <4 timer **med** kommentar → kommentaren
  bevares uændret, ikke overskrevet.
- Samme bruger opretter <4 timer, men medarbejderen har en anden godkendt aktivitet
  samme dag der tilsammen når 4 timer → kommentar-fallback udløses **ikke**.
- Disponent (uden permission) opretter normal arbejdstid <4 timer → `status=pending`
  som i dag, ingen kommentar-ændring.
- Disponent opretter en fraværstype <4 timer → `status=approved` som i dag (uændret),
  men kommentarfeltet ændres **ikke** til initialer.
- `admin` (systemrolle) opretter normal arbejdstid <4 timer uden kommentar →
  auto-godkendt med initialer som kommentar, uden at permissionen er tilføjet
  eksplicit til admins permissions-liste.
- Migration: eksisterende `lonbogholder`-rolle i DB uden permissionen får den
  tilføjet idempotent ved opstart; kørt to gange giver ikke dubletter.
