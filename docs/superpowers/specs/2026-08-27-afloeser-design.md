# "Afløser"-felt og undertrykt søn/helligdagstillæg – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Nyt afkrydsningsfelt "Afløser" på medarbejderen. Er det slået til, skal medarbejderen IKKE modtage søn-/helligdagstillæg (SH-betaling, kode 4/63) for søn-/helligdage hvor der ikke er kørsel. Er der kørsel den dag, følges de eksisterende regler for fuldlønnet/timelønnet uændret.

Afklaret under brainstorming: "kørsel" betyder specifikt en godkendt aktivitet med `activity_type = "normal"` den pågældende dag – andre registrerede fraværstyper (sygdom, afspadsering, ferie m.v.) tæller IKKE som kørsel og udløser derfor ikke de normale SH-regler for en afløser.

## 1. Datamodel

**`Employee`** (`app/database/models.py`), ny kolonne, samme mønster som `paragraf_56`:
```python
afloeser = Column(Boolean, default=False, nullable=False)
```

**Migration** (`app/database/session.py: _migrate()`), idempotent:
```python
if "afloeser" not in emp_cols:
    conn.execute("ALTER TABLE employees ADD COLUMN afloeser BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()
```

## 2. Schemas (`app/database/schemas.py`)

- `EmployeeCreate`: `afloeser: bool = False`
- `EmployeeUpdate`: `afloeser: Optional[bool] = None`
- `EmployeeResponse`: `afloeser: bool`

Ingen særlig validering nødvendig (modsat §56 er der ingen afhængige felter) – indgår i den almindelige `model_dump()`-flow i `create_employee`/`update_employee` uden særbehandling.

## 3. Lønberegning (`app/routers/payroll_router.py`, `_calculate_employee()`)

Lige efter den eksisterende linje:
```python
sh_h = compute_sh_hours(day_type, guaranteed_today)
```
tilføjes:
```python
if emp.afloeser and not any(a.activity_type == "normal" for a in acts_today):
    sh_h = Decimal("0")
```
`acts_today` er på dette tidspunkt i løkken allerede beregnet (linje 439) og indeholder kun godkendte aktiviteter for dagen (ekskl. overnatning/DOB-overnatning). Efterfølgende kode (`if sh_h > 0: ... totals["sh_fuldloennet"]/["sh_timeloennet"] += sh_h; total_kr += sh_h * hourly_rate`) er UÆNDRET og virker korrekt med `sh_h = 0` (springes simpelthen over).

**Ingen anden kode ændres.** `_calculate_employee()` er den fælles beregningsmotor bag lønkørsel-preview, prøvekørsel (Excel), PDF-timesedler og Danløn CSV – ændringen slår automatisk igennem alle fire uden yderligere tilpasning. Lørdage er upåvirkede (`compute_sh_hours` returnerer allerede 0 for lørdag, uafhængigt af `afloeser`).

## 4. Frontend

**`templates/index.html`**: Den eksisterende 3-kolonne-række (Aktiv/Fuldlønnet/§56, se `docs/superpowers/specs/2026-08-27-paragraf56-medarbejder-design.md`) udvides til 4 kolonner med et nyt "Afløser"-afkrydsningsfelt (`id="emp-afloeser"`), samme visuelle mønster som de øvrige tre.

**`static/js/app.js`**:
- `openNewEmployeeModal()`: nulstil `emp-afloeser` til `false`.
- `openEditEmployee(id)`: sæt `emp-afloeser` fra `e.afloeser`.
- `confirmEmployee()`: tilføj `afloeser: document.getElementById("emp-afloeser").checked` til `body`.

## 5. Visuel markering af afløsere

Afløsere skal skille sig diskret ud tre steder i UI'et, alle via allerede etablerede brandfarver (`docs/superpowers/specs`-historik: `--primary` #317423, `--accent` #78b21a, #d4edcc (samme farve som allerede bruges i lønkørsel-headeren, blot uden en navngivet CSS-variabel)):

- **Medarbejdere-listen** (`.emp-avatar`, cirklen med initialer): baggrund skiftes fra standard `var(--primary)` (mørkegrøn) til `var(--accent)` (lysere grøn) for afløsere.
- **Vagtplan og Aktivitetsoversigt** (navnecellen `.emp-cell` – begge grids deler denne CSS-klasse i dag): får en let grøn baggrundstoning `#d4edcc` i stedet for standard hvid, når medarbejderen er afløser.

Implementeres som en ny CSS-klasse `.afloeser-highlight` (baggrund `#d4edcc`) genbrugt i begge grids, plus betinget inline-styling af `.emp-avatar` i `renderEmployeeList()`. Rent visuelt – ingen funktionel ændring, ingen ny tilladelse.

## Ikke i scope

- Ingen ændring af Fraværsoversigt, Lønafregning-visningen eller anden rapportering ud over selve kr./timer-beregningen (som allerede går gennem `_calculate_employee()`).
- Ingen ændring af Brugervejledningen i denne omgang.
- Ingen ændring af lørdags-logikken (giver i forvejen aldrig SH-betaling).
- Ingen tekstlabel/badge ("Afløser") ud over selve farvemarkeringen – kun farve, som eksplicit efterspurgt.

## Test-dækning (til implementeringsplan)

- Afløser, søndag/helligdag UDEN "normal"-aktivitet → `sh_h = 0`, ingen kr./timer i `sh_fuldloennet`/`sh_timeloennet`, uanset `fuldloennet`-status.
- Afløser, søndag/helligdag MED en godkendt "normal"-aktivitet → `sh_h` uændret (som en ikke-afløser), fordelt korrekt på kode 4 (fuldlønnet) eller kode 63 (timelønnet).
- Afløser, søndag/helligdag med KUN en anden fraværstype (fx afspadsering) registreret, ingen "normal" → `sh_h = 0` (fraværstypen tæller ikke som kørsel).
- Ikke-afløser (default) → ingen ændring i nogen af ovenstående scenarier, matcher eksisterende (allerede testdækket) adfærd.
- Lørdag, afløser → fortsat 0 (uændret, ikke en del af `compute_sh_hours`s SUNDAY/HOLIDAY-gren).
- `EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse` med `afloeser` – oprettelse, opdatering, default-værdi `false`.
- Migration: `afloeser`-kolonnen tilføjes idempotent til en eksisterende database.
