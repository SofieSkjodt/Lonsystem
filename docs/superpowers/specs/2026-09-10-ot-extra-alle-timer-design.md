# "Øvrig overtid for alle timer" – særaftale-felt – Design

**Dato:** 2026-09-10
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Én navngiven medarbejder har en individuel særaftale: ALLE hans arbejdstimer skal give Øvrig overtid (kode 9) oveni normal løn – uanset tidspunkt på døgnet, dagtype eller det sædvanlige daglige loft. Dette må ikke hardcodes til en bestemt medarbejder og skal kunne slås fra igen. Løsningen er derfor et generisk, togglebart per-medarbejder-flag, med samme mønster som eksisterende individuelle medarbejderflag (`afloeser`, `fast_bil`, `paragraf_56`).

Afklaret under brainstorming:
- Særaftalen **erstatter** de normale tids-tillæg (nat/aften/"1 time før"-tillæg, OT 1-3/kode 8) – den lægges ikke oveni dem.
- **Intet loft**: han får fuld normalløn (kode 1) for samtlige arbejdstimer, uanset det sædvanlige daglige loft på 7/7,5/8 timer.
- Gælder **alle dage** – hverdag, lørdag, søndag og alle helligdagstyper (inkl. 1. maj og Grundlovsdag).
- **Kode 8 (Overtid 1-3 timer) gives ALDRIG** til ham – kun kode 1 (normal) og kode 9 (Øvrig overtid), begge for samtlige arbejdstimer.
- **Kode 4/63 (SH-garantibetaling)** beregnes helt uændret – denne beregning (`compute_sh_hours()`) er allerede ubetinget og uafhængig af agreement_kind/aktivitets-beregningen, og påvirkes derfor slet ikke af dette flag.

Konsekvens: kl. 12-grænsen på 1. maj/Grundlovsdag bliver reelt irrelevant for denne medarbejder, fordi kode 1 i den eksisterende særdags-beregning allerede altid dækker hele dagen, og kode 9 nu udvides til også at dække hele dagen (i stedet for kun eftermiddagstimerne).

## 1. Datamodel

**`Employee`** (`app/database/models.py`), ny kolonne, samme mønster som `afloeser`:
```python
ot_extra_alle_timer = Column(Boolean, default=False, nullable=False)
```

**Migration** (`app/database/session.py: _migrate()`), idempotent:
```python
if "ot_extra_alle_timer" not in emp_cols:
    conn.execute("ALTER TABLE employees ADD COLUMN ot_extra_alle_timer BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()
```

## 2. Schemas (`app/database/schemas.py`)

- `EmployeeCreate`: `ot_extra_alle_timer: bool = False`
- `EmployeeUpdate`: `ot_extra_alle_timer: Optional[bool] = None`
- `EmployeeResponse`: `ot_extra_alle_timer: bool`

Ingen validering eller afhængige felter nødvendig – indgår i den almindelige `model_dump()`-flow i `create_employee`/`update_employee`, samme som `afloeser`.

## 3. Beregningslogik (`app/calculators/overtime.py`)

Ny, lille post-processing-funktion, der genbruges på tværs af begge aktivitets-beregningsveje. `rates` gives med ind, så `supplements[OT_EXTRA_KEY]` kan genberegnes korrekt ud fra de opdaterede timer (satsen slås allerede op af kalderen, jf. `ot_rates` i `payroll_router.py`):

```python
def override_ot_extra_alle_timer(result: OvertimeResult, is_special_day: bool, rates: dict) -> OvertimeResult:
    """
    Særaftale (Employee.ot_extra_alle_timer): normal løn for alle arbejdstimer
    OG Øvrig overtid (kode 9) for alle arbejdstimer – aldrig Overtid 1-3 timer
    (kode 8). Kode 4/63 (SH-garanti) beregnes et andet sted (compute_sh_hours)
    og påvirkes ikke af denne funktion.
    """
    result.ot_before_hours = Decimal("0")
    result.ot_13_hours = Decimal("0")
    if is_special_day:
        result.sh_kode8_hours = Decimal("0")
        result.sh_kode9_hours = result.total_hours
    else:
        result.ot_extra_hours = result.total_hours
        result.supplements = {OT_EXTRA_KEY: result.ot_extra_hours * rates.get(OT_EXTRA_KEY, Decimal("0"))}
    return result
```

`by_date`-bucket'ene (bruges kun af Lønafregning-fanen) opdateres samtidig for den ikke-særdags-gren:
```python
for bucket in result.by_date.values():
    bucket["ot_extra"] = bucket["total_hours"]
```
(For særdags-grenen sætter `calculate_special_day_overtime()` i forvejen ikke `by_date` – uændret, ingen ekstra håndtering nødvendig.)

## 4. Lønberegning (`app/routers/payroll_router.py`, `_calculate_employee()`)

Den eksisterende gren omkring linje 590 (`if not is_recognized_agreement_kind: ... elif day_type in (NORMAL, SATURDAY): ... else: ...`) udvides med et nyt, øverste tjek:

```python
if emp.ot_extra_alle_timer:
    if day_type in (DayType.NORMAL, DayType.SATURDAY) or not is_recognized_agreement_kind:
        ot = calculate_flat_hours(act.start_time, act.end_time, pauses)
        ot = override_ot_extra_alle_timer(ot, is_special_day=False, rates=ot_rates)
    else:
        ot = calculate_special_day_overtime(
            act.start_time, act.end_time, day_type, pauses,
            kode8_remaining=day_ot13_remaining,
        )
        ot = override_ot_extra_alle_timer(ot, is_special_day=True, rates=ot_rates)
        day_ot13_remaining = ot.ot13_remaining_after
elif not is_recognized_agreement_kind:
    ot = calculate_flat_hours(act.start_time, act.end_time, pauses)
elif day_type in (DayType.NORMAL, DayType.SATURDAY):
    ot = calculate_overtime(...)   # uændret
    ...
else:
    ot = calculate_special_day_overtime(...)   # uændret
    ...
```

`sh_h` (kode 4/63, linje 454) beregnes FØR denne gren og er allerede fuldstændig ubetinget – ingen ændring der.

**Ingen anden kode ændres.** `_calculate_employee()` er den fælles beregningsmotor bag lønkørsel-preview, prøvekørsel (Excel), PDF-timesedler, Lønafregning-fanen og Danløn CSV – ændringen slår automatisk igennem alle uden yderligere tilpasning, da alle læser fra `ot.normal_hours`/`ot.ot_extra_hours`/`ot.sh_kode8_hours`/`ot.sh_kode9_hours`/`totals[...]`.

## 5. Frontend

**`templates/index.html`**: Ny checkbox i medarbejder-modalen, samme visuelle mønster som `emp-afloeser`/`emp-fast-bil`, fx `id="emp-ot-extra-alle-timer"` med label "Særaftale: Øvrig overtid for alle timer".

**`static/js/app.js`**:
- `openNewEmployeeModal()`: nulstil `emp-ot-extra-alle-timer` til `false`.
- `openEditEmployee(id)`: sæt `emp-ot-extra-alle-timer` fra `e.ot_extra_alle_timer`.
- `confirmEmployee()`: tilføj `ot_extra_alle_timer: document.getElementById("emp-ot-extra-alle-timer").checked` til `body`.

Ingen ny permission – gates af samme `manage_employees`/`stamdata`-tilladelse som resten af medarbejder-modalen.

## Ikke i scope

- Ingen ny løntypekode/Danløn-kode – genbruger eksisterende `OT_EXTRA_KEY`/kode 9-infrastruktur.
- Ingen ændring af salt-tillæg eller overnatningstillæg – begge beregnes uafhængigt af overtidsberegningen og er upåvirkede.
- Ingen ændring af kode 4/63-beregningen (`compute_sh_hours`) eller `afloeser`-logikken.
- Ingen visuel markering (farve/badge) af medarbejderen i lister – kun selve beregningsændringen og checkboxen i medarbejder-modalen.
- Ingen ændring af Fraværsoversigt (fravær går ikke gennem denne aktivitets-beregning).

## Test-dækning (til implementeringsplan)

- `override_ot_extra_alle_timer()` enhedstest, ikke-særdag: 8 timers dagvagt → `normal_hours=8`, `ot_extra_hours=8`, `ot_13_hours=0`, `ot_before_hours=0`, `supplements[OT_EXTRA_KEY]` korrekt.
- Samme, særdag (fx søndag): `normal_hours=8` (uændret, som normalt), `sh_kode9_hours=8`, `sh_kode8_hours=0`.
- 1. maj, vagt der spænder over kl. 12: `sh_kode8_hours=0` (aldrig kode 8, heller ikke normalt her), `sh_kode9_hours=` hele dagens timer (ikke kun eftermiddagen).
- Grundlovsdag: samme som 1. maj (var i forvejen uden kode 8, ingen synlig ændring bortset fra kode 9 nu dækker formiddagen også).
- Vagt der krydser midnat, flaget sat: intet loft-relevant carry-over nødvendigt (loft er irrelevant for ham), men `day_ot13_remaining` skal stadig kunne videreføres uden fejl for særdags-grenen.
- Kode 4/63 (`sh_h`/`compute_sh_hours`) uændret uanset flaget, på alle dagtyper.
- Flaget slået fra (default) → ingen ændring i nogen eksisterende scenarie, matcher nuværende adfærd 1:1.
- `EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse` med `ot_extra_alle_timer` – oprettelse, opdatering, default-værdi `false`.
- Migration: kolonnen tilføjes idempotent til en eksisterende database.
