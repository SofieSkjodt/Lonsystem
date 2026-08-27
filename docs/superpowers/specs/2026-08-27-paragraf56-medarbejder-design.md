# §56-felt i medarbejder-modalen – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Medarbejder-modalen (opret/rediger, `modal-employee`) skal have et nyt afkrydsningsfelt "§56". Krydses det af, skal der vises en start- og slutdato for "§56 syg" i modalen. Feltet skal gemmes i databasen på selve medarbejderen (ikke på en aktivitet). Den forretningsmæssige betydning/funktion af feltet er endnu ikke beskrevet af brugeren – denne opgave dækker udelukkende UI + datalagring i medarbejder-modalen, ingen kobling til lønberegning eller den eksisterende `§56 syg`-fraværstype/aktivitetslogik (den findes allerede som en almindelig fraværsregistrering med egen Danløn-kode, se `PARAGRAF_56` i `calculators/pay_rates.py` – urelateret til denne opgave).

Afklaret under brainstorming:
- Feltet skal persisteres i databasen (ikke kun et UI-shell).
- Slutdato er **påkrævet** når §56 er krydset af (intet åbent/løbende forløb).
- Placering: ved siden af "Aktiv"/"Fuldlønnet" i modalen, med dato-felterne i en ny række lige nedenunder når afkrydset.

## 1. Datamodel

**`Employee`** (`app/database/models.py`), tre nye kolonner:
```python
paragraf_56 = Column(Boolean, default=False, nullable=False)
paragraf_56_start_date = Column(Date, nullable=True)
paragraf_56_end_date = Column(Date, nullable=True)
```

**Migration** (`app/database/session.py: _migrate()`), idempotent, samme mønster som de øvrige `employees`-kolonne-tilføjelser (fx `dispatcher_group_id`):
```python
if "paragraf_56" not in emp_cols:
    conn.execute("ALTER TABLE employees ADD COLUMN paragraf_56 BOOLEAN NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE employees ADD COLUMN paragraf_56_start_date DATE")
    conn.execute("ALTER TABLE employees ADD COLUMN paragraf_56_end_date DATE")
    conn.commit()
```
Placeres i samme `if "dispatcher_group_id" not in emp_cols:`-blok's stil, efter den eksisterende `emp_cols`-opslag.

## 2. Schemas (`app/database/schemas.py`)

- `EmployeeCreate`: `paragraf_56: bool = False`, `paragraf_56_start_date: Optional[date] = None`, `paragraf_56_end_date: Optional[date] = None`
- `EmployeeUpdate`: samme tre felter, alle `Optional` (default `None`)
- `EmployeeResponse`: samme tre felter (non-optional `paragraf_56: bool`, de to datoer `Optional[date] = None`)

## 3. Backend-validering (`app/routers/employees.py`)

Ny hjælpefunktion, kaldt fra både `create_employee` og `update_employee`:
```python
def _validate_paragraf_56(active: bool, start: date | None, end: date | None) -> tuple[date | None, date | None]:
    if not active:
        return None, None
    if not start or not end:
        raise HTTPException(400, "Start- og slutdato for §56 skal udfyldes")
    if end < start:
        raise HTTPException(400, "§56 slutdato skal være efter startdato")
    return start, end
```

**`create_employee`**: efter eksisterende validering, kald `_validate_paragraf_56(body.paragraf_56, body.paragraf_56_start_date, body.paragraf_56_end_date)` og sæt de returnerede værdier på `body`/`data` før `Employee(**data)` oprettes (fields er allerede en del af `EmployeeCreate` og dumpes automatisk med i `data`, så det er selve de renset-til-None-værdier der skal overskrive `body`-feltet inden `model_dump()`).

**`update_employee`**: `paragraf_56`, `paragraf_56_start_date`, `paragraf_56_end_date` udelukkes fra den generiske `body.model_dump(exclude_none=True, exclude={...})`-loop (samme begrundelse som `dispatcher_group_id` – ellers kan felterne ikke nulstilles via PATCH). Håndteres eksplicit:
```python
if "paragraf_56" in body.model_fields_set:
    start, end = _validate_paragraf_56(body.paragraf_56, body.paragraf_56_start_date, body.paragraf_56_end_date)
    emp.paragraf_56 = body.paragraf_56
    emp.paragraf_56_start_date = start
    emp.paragraf_56_end_date = end
```

**`_to_response()`**: tilføj `paragraf_56=emp.paragraf_56`, `paragraf_56_start_date=emp.paragraf_56_start_date`, `paragraf_56_end_date=emp.paragraf_56_end_date`.

## 4. Frontend – `templates/index.html`

Den eksisterende række med Aktiv/Fuldlønnet:
```html
<div class="form-row">
  <div class="form-group">...Aktiv...</div>
  <div class="form-group">...Fuldlønnet...</div>
</div>
```
udvides med inline 3-kolonne-grid (samme ad-hoc inline-style-mønster som resten af filen) og et tredje afkrydsningsfelt:
```html
<div class="form-row" style="grid-template-columns:1fr 1fr 1fr">
  <div class="form-group">...Aktiv...</div>
  <div class="form-group">...Fuldlønnet...</div>
  <div class="form-group">
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
      <input type="checkbox" id="emp-paragraf56" onchange="onParagraf56Change()"> §56
    </label>
  </div>
</div>
<div class="form-row" id="emp-paragraf56-dates" style="display:none">
  <div class="form-group">
    <label>§56 startdato <span style="color:var(--danger)">*</span></label>
    <div id="emp-paragraf56-start"></div>
  </div>
  <div class="form-group">
    <label>§56 slutdato <span style="color:var(--danger)">*</span></label>
    <div id="emp-paragraf56-end"></div>
  </div>
</div>
```

## 5. Frontend – `static/js/app.js`

**Ny funktion**, ved siden af `onAgreementKindChange()`:
```js
function onParagraf56Change() {
  const checked = document.getElementById("emp-paragraf56").checked;
  document.getElementById("emp-paragraf56-dates").style.display = checked ? "" : "none";
}
```

**`openNewEmployeeModal()`**: nulstil checkbox (`checked = false`), skjul datorækken, `buildDatePicker("emp-paragraf56-start", "")` / `buildDatePicker("emp-paragraf56-end", "")`.

**`openEditEmployee(id)`**: sæt checkbox fra `e.paragraf_56`, byg datovælgerne fra `e.paragraf_56_start_date`/`e.paragraf_56_end_date`, kald `onParagraf56Change()` for at vise/skjule rækken korrekt.

**`confirmEmployee()`**: tilføj til `body`:
```js
paragraf_56: document.getElementById("emp-paragraf56").checked,
paragraf_56_start_date: document.getElementById("emp-paragraf56").checked ? readDatePicker("emp-paragraf56-start") : null,
paragraf_56_end_date: document.getElementById("emp-paragraf56").checked ? readDatePicker("emp-paragraf56-end") : null,
```
Klientside-validering (samme sted som det eksisterende `if (!body.employee_number || ...)`-tjek):
```js
if (body.paragraf_56 && (!body.paragraf_56_start_date || !body.paragraf_56_end_date)) {
  toast("Udfyld start- og slutdato for §56", "error");
  return;
}
if (body.paragraf_56 && body.paragraf_56_end_date < body.paragraf_56_start_date) {
  toast("§56 slutdato skal være efter startdato", "error");
  return;
}
```

## 6. Dokumentation

`CODEREF.md` opdateres med de tre nye felter i `Employee`-tabellen. Brugervejledningen (`docs/Brugervejledning.docx`) opdateres **ikke** i denne omgang, da feltets forretningsmæssige betydning endnu ikke er beskrevet.

## Ikke i scope

- Ingen kobling til lønberegning, Danløn CSV, fraværsoversigt eller den eksisterende `§56 syg`-fraværstype/aktivitetslogik.
- Ingen ændring af Brugervejledningen.
- Ingen visning af §56-status andre steder i appen (medarbejderlisten, aktivitetsoversigten m.v.) – kun i selve medarbejder-modalen.

## Test-dækning (til implementeringsplan)

- Migration: `paragraf_56`/`paragraf_56_start_date`/`paragraf_56_end_date` tilføjes idempotent til en eksisterende database uden datatab.
- `create_employee`/`update_employee`: `paragraf_56=true` uden datoer → 400. `paragraf_56=true` med slutdato før startdato → 400. `paragraf_56=true` med gyldige datoer → gemmes korrekt. `paragraf_56=false` → datoer nulstilles til `null` uanset hvad der sendes med.
- `update_employee`: kan skifte fra `paragraf_56=true` (med datoer) til `false` og få datoerne ryddet (regressionstest for `exclude_none`-fælden, samme klasse fejl som blev rettet for `dispatcher_group_id`).
- Frontend: afkrydsning viser datorækken, fjernelse af afkrydsning skjuler den igen. Oprettelse/redigering af en medarbejder med §56 afkrydset uden udfyldte datoer giver klientside-fejl uden at kalde API'et. Redigering af en eksisterende §56-medarbejder viser de gemte datoer korrekt forudfyldt.
