# Design: "Aftale" flyttes fra hardcoded liste til Stamdata

**Dato:** 2026-08-24
**Status:** Godkendt til implementeringsplan

## Baggrund

Under "Tilføj medarbejder" vælges "Aftale" i dag fra en hardcoded `<select>`
med to muligheder (`index.html`, `emp-agreement-kind`):

- `hourly_fixed` — Timelønnet, fast arbejdstid
- `hourly_flexible` — Timelønnet, ikke fastlagt arbejdstid

De samme to værdier findes som Python-enum'et `AgreementKind`
(`database/models.py`). Værdien er ikke bare en label — den styrer direkte
hvilken overtidsberegning der bruges i `calculators/overtime.py`:
`hourly_fixed` giver et *dagligt* OT-loft (nulstilles hver dag),
`hourly_flexible` giver en *ugentlig pulje* (37t/5t).

Ønsket er at kunne vedligeholde denne liste under Stamdata, samt kunne
tilføje en tredje (og evt. flere) Aftale-type, som ikke er en del af den
eksisterende overtidsberegning, men i stedet skal bruges til at afgøre
hvilken gruppe en medarbejder tilhører, og om Overenskomsttype er påkrævet.
Den præcise "gruppe"-logik for nye typer er **ikke** en del af dette design
— det kommer som en senere udvidelse, når Aftale ikke længere er hardcoded.

## Beslutninger (afklaret med bruger)

1. De to eksisterende Aftale-typer bevares og kan ikke slettes, men deres
   **label kan redigeres** frit.
2. Der skal kunne **tilføjes flere Aftale-typer** ud over de to
   eksisterende, administreret under Stamdata (samme mønster som
   Fraværstyper).
3. En ny/brugeroprettet Aftale-type kan styre om "Overenskomsttype" er
   påkrævet at udfylde for medarbejderen eller ej.
4. Overtidsberegningen (`overtime.py`) kender fortsat kun de to faste
   nøgler `hourly_fixed`/`hourly_flexible`. For medarbejdere med en ny,
   brugeroprettet Aftale-type **springes automatisk OT-beregning helt
   over** — ingen fejl, ingen OT-tillæg, indtil videre logik defineres i en
   senere opgave.
5. Den underliggende nøgle (`key`) for en Aftale-type er fast fra
   oprettelsen og kan ikke ændres bagefter — kun label, aktiv-status og
   "kræver overenskomsttype" er redigerbare. Dette er en hård begrænsning,
   fordi `overtime.py` grener direkte på nøgleværdierne
   `hourly_fixed`/`hourly_flexible`; hvis nøglen kunne ændres, ville
   lønberegningen for eksisterende medarbejdere kunne knække.

## Arkitektur

### Datamodel

Ny tabel `master_agreement_kinds` (samme mønster som
`master_absence_types` i `database/models.py`):

```python
class MasterAgreementKind(Base):
    __tablename__ = "master_agreement_kinds"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False)
    label = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False)
    requires_agreement_type = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
```

Seedes ved opstart (i `session.py`, samme sted som anden seed-logik) med:

| key | label | is_user_created | requires_agreement_type |
|---|---|---|---|
| `hourly_fixed` | Timelønnet, fast arbejdstid | false | true |
| `hourly_flexible` | Timelønnet, ikke fastlagt arbejdstid | false | true |

**`Employee.agreement_kind`:** ændres fra `Column(Enum(AgreementKind))` til
`Column(String(50), nullable=False, default="hourly_fixed")`. Ingen
DB-migration nødvendig — den eksisterende SQLite-kolonne er allerede
`VARCHAR(15)` uden CHECK-constraint (bekræftet via `sqlite_master`), og
SQLite håndhæver ikke VARCHAR-længde. Python-enum'et `AgreementKind`
bevares i `models.py` som reference for de to systemnøgler (bruges af
`overtime.py` og seed-scripts), men er ikke længere kolonnetypen.

**`Employee.agreement_type`:** kolonnen forbliver `NOT NULL` i databasen
(en `ALTER COLUMN` for at fjerne NOT NULL kræver tabel-genopbygning i
SQLite, hvilket vurderes unødvendigt risikabelt for denne opgave). I
stedet gemmes tom streng `""`, når den valgte Aftale-types
`requires_agreement_type=false`. API-laget behandler `""` som
"ikke udfyldt/ikke relevant" og viser feltet tomt i UI.

### Backend

**`stamdata.py`** — ny CRUD-sektion "Aftaletyper", kodet efter samme
mønster som `absence-types`:

- `GET /stamdata/agreement-kinds` — alle rækker (til Stamdata-tabellen)
- `POST /stamdata/agreement-kinds` — opret ny (`label`,
  `requires_agreement_type`); `key` udledes af label med samme
  normaliserings-tilgang som `_normalize_absence_key` for Fraværstyper,
  skal være unik; `is_user_created=True` sættes altid ved oprettelse via
  denne endpoint.
- `PATCH /stamdata/agreement-kinds/{id}` — opdaterer `label`, `is_active`,
  `requires_agreement_type`. `key` indgår ikke i body og kan ikke ændres.
- `DELETE /stamdata/agreement-kinds/{id}` — 400 hvis `is_user_created=False`
  (systemtyperne kan ikke slettes); 400 hvis mindst én medarbejder har
  denne `agreement_kind` (i modsætning til Fraværstyper tjekkes brug her,
  fordi `agreement_kind` er et obligatorisk felt på medarbejderen og
  central for lønberegningen).
- Alle endpoints kræver `stamdata`-tilladelsen (`require_permission("stamdata")`),
  som resten af filen.

**`employees.py`** — ny letvægts-endpoint til dropdown, samme mønster som
den eksisterende `GET /employees/agreement-types`:

- `GET /employees/agreement-kinds` — kun `is_active=true`-rækker, åben for
  enhver logget ind bruger (`get_current_user`, ingen særlig tilladelse).
  Returnerer `key`, `label`, `requires_agreement_type` pr. række.
- `create_employee` / `update_employee`: validerer `agreement_kind` mod
  `MasterAgreementKind`-tabellen (samme princip som eksisterende
  `agreement_type`-validering mod `load_agreement_types_from_db`).
  `agreement_type` er kun påkrævet, hvis den valgte Aftale-types
  `requires_agreement_type=True`; ellers accepteres tomt/manglende felt og
  gemmes som `""`.

**`schemas.py`** — `agreement_kind`-felterne i `EmployeeCreate`,
`EmployeeUpdate`, `EmployeeResponse` ændres fra type `AgreementKind` til
`str` (valideres i routeren mod DB-listen i stedet for af Pydantic mod
enum'et).

**`overtime.py` / kaldestedet i `payroll_router.py`:** før
overtidsberegning kaldes for en medarbejder, tjekkes
`emp.agreement_kind in ("hourly_fixed", "hourly_flexible")`. Er
medarbejderens Aftale-type noget andet, springes OT-beregningen for denne
medarbejder helt over (ingen OT-poster genereres). Selve den interne
grenlogik i `overtime.py` ændres ikke — `AgreementKind`-enummet er en
`str`-baseret enum, så eksisterende sammenligninger
(`agreement_kind == AgreementKind.hourly_fixed`) virker uændret, uanset om
den indkommende værdi er enum-medlemmet eller en almindelig streng.

### Frontend

**Ny Stamdata-fane "Aftale"** (`index.html` + `app.js`), placeret ved
siden af de øvrige faner, opbygget efter samme mønster som
Fraværstyper-fanen:

- Tabel med kolonner: Label, Systemtype (badge, ikke redigerbar/sletbar),
  Kræver overenskomsttype (Ja/Nej-badge), Aktiv (Ja/Nej-badge), handlinger
  (Redigér altid; Slet kun når `is_user_created=true`).
- Modal til opret/redigér: tekstfelt til label, checkbox "Kræver
  overenskomsttype", checkbox "Aktiv". Ved redigering af en systemtype
  (`is_user_created=false`) er kun label og aktiv-status redigerbare —
  "kræver overenskomsttype" holdes fast på `true` for de to eksisterende,
  da de allerede semantisk kræver det.
- `loadStamdataAgreementKinds()`, `openStamdataAgreementKindModal()`,
  `confirmStamdataAgreementKind()` tilføjes efter samme navnekonvention som
  de øvrige `stamdata`-funktioner i `app.js`.

**"Tilføj/redigér medarbejder"-modalen:**

- `<select id="emp-agreement-kind">` mister sine hardcodede `<option>`-tags
  og fyldes dynamisk fra `GET /employees/agreement-kinds`, på samme måde
  som `emp-agreement-type` allerede gøres i dag.
- Når brugeren vælger en Aftale-type, slås `requires_agreement_type` op for
  den valgte værdi: er den `false`, markeres Overenskomsttype-feltet som
  valgfrit i UI'et (fjerner den røde `*`, tillader tomt valg) i stedet for
  obligatorisk.

## Ikke i scope

- Den konkrete "gruppe"-logik for nye Aftale-typer (hvilken gruppe
  medarbejderen havner i, og hvad det medfører andre steder i systemet) —
  kommer som en senere, separat opgave, når mere er afklaret.
- Ingen ændring af selve overtidsberegningslogikken for
  `hourly_fixed`/`hourly_flexible` — kun et "spring over"-tjek tilføjes for
  andre Aftale-typer.
- Ingen migration af `agreement_type`-kolonnen til reelt NULL i databasen —
  tom streng bruges som sentinel-værdi for "ikke relevant".
