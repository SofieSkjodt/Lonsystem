# Dynamisk Sats-kilde Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gør "Sats-kilde"-feltet på brugeroprettede løntypekoder dynamisk, så det kan pege på ALLE nuværende rækker i Overtidssatser og Tillæg (ikke kun et fast, hardcodet sæt), og så nye rækker automatisk bliver valgbare fremover uden kodeændring.

**Architecture:** `MasterPayType.csv_rate_source` skifter fra faste nøgleord (`ot_before`, `salt`, ...) til et generisk id-baseret skema (`overtime:<id>`, `supplement:<id>`), med en engangs-migration af eksisterende data. `_resolve_rate()` udvides til at slå op i to nye id→sats-dicts der indeholder ALLE rækker fra de to tabeller. Frontend-dropdownet bygges dynamisk fra de samme data Stamdata-fanerne allerede henter.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), vanilla JS.

## Global Constraints

- Eksisterende løntypekoder skal efter migrationen pege på nøjagtig den samme sats som før — ingen funktionel ændring for dem.
- Reference sker via internt id (`overtime:<id>` / `supplement:<id>`), ikke label — overlever at en rækkes navn ændres.
- `hourly` bevares uændret som værdi for "Timesats (overenskomst)".
- De gamle faste værdier (`ot_before`, `ot_13`, `ot_extra`, `salt`, `overnight`, `dagpenge`, `springer`) skal fortsat give korrekt resultat i `_resolve_rate()` som et sikkerhedsnet, også efter migrationen er indført (defense-in-depth, matcher kodebasens øvrige fallback-mønster).
- Sletning af en Overtidssats-/Tillæg-række der er i brug som sats-kilde for en løntypekode skal blokeres (400) med en fejlbesked der navngiver den blokerende løntypekode.
- Kun brugeroprettede rækker (`is_user_created=True`) kan overhovedet slettes — uændret fra i dag.
- Spec: `docs/superpowers/specs/2026-08-19-dynamisk-sats-kilde-design.md`

---

## Task 1: Id-baseret satsopslag, `_resolve_rate()`-udvidelse og migration

**Files:**
- Modify: `app/calculators/rates_loader.py` (tilføj to nye funktioner efter `load_dagpenge_rate_from_db()`, linje 174-180)
- Modify: `app/routers/payroll_router.py` (import-blok linje 41-49; `_resolve_rate()` linje 108-124; `_calculate_employee()` linje 299-303 og return-dict linje 592-623)
- Modify: `app/database/session.py` (`_migrate()`, tilføj migrationsblok før funktionens afslutning, linje 142)
- Test: `tests/test_rate_source.py` (ny fil)

**Interfaces:**
- Produces: `load_overtime_rates_by_id_from_db(db) -> dict[int, Decimal]` — alle rækker i `master_overtime_rates`, nøglet på id
- Produces: `load_supplement_rates_by_id_from_db(db) -> dict[int, Decimal]` — alle rækker i `master_supplement_rates`, nøglet på id
- Produces: `_resolve_rate(rate_src: str, calc: dict) -> float` genkender nu også `"overtime:<id>"` og `"supplement:<id>"` (brugt af Task 2's tests, uændret signatur)
- Consumes: `calc["ot_rates_by_id"]` og `calc["supplement_rates_by_id"]` — nye nøgler i det dict `_calculate_employee()` returnerer

- [ ] **Step 1: Skriv fejlende test for de to nye loader-funktioner**

```python
# tests/test_rate_source.py
from decimal import Decimal

from database.models import MasterOvertimeRate, MasterSupplementRate
from calculators.rates_loader import (
    load_overtime_rates_by_id_from_db,
    load_supplement_rates_by_id_from_db,
)


def test_load_overtime_rates_by_id_returns_all_rows(db):
    r1 = MasterOvertimeRate(label="Overtid 1 time før", rate=Decimal("44.54"))
    r2 = MasterOvertimeRate(label="Øvrigt overtid", rate=Decimal("109.40"))
    db.add(r1)
    db.add(r2)
    db.commit()
    db.refresh(r1)
    db.refresh(r2)

    result = load_overtime_rates_by_id_from_db(db)

    assert result == {r1.id: Decimal("44.54"), r2.id: Decimal("109.40")}


def test_load_supplement_rates_by_id_returns_all_rows(db):
    r1 = MasterSupplementRate(label="Salttillæg", rate=Decimal("12.50"))
    r2 = MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True)
    db.add(r1)
    db.add(r2)
    db.commit()
    db.refresh(r1)
    db.refresh(r2)

    result = load_supplement_rates_by_id_from_db(db)

    assert result == {r1.id: Decimal("12.50"), r2.id: Decimal("597.00")}


def test_load_functions_return_empty_dict_when_no_rows(db):
    assert load_overtime_rates_by_id_from_db(db) == {}
    assert load_supplement_rates_by_id_from_db(db) == {}
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `pytest tests/test_rate_source.py -v`
Expected: FAIL med `ImportError: cannot import name 'load_overtime_rates_by_id_from_db'`

- [ ] **Step 3: Tilføj de to loader-funktioner**

I `app/calculators/rates_loader.py`, tilføj efter `load_dagpenge_rate_from_db()` (efter linje 180):

```python
def load_overtime_rates_by_id_from_db(db) -> dict[int, Decimal]:
    """Alle overtidssatser nøglet på id (ikke kun de tre faste) — bruges af
    _resolve_rate() til at slå brugerdefinerede sats-kilder op dynamisk."""
    from database.models import MasterOvertimeRate
    return {r.id: Decimal(str(r.rate)) for r in db.query(MasterOvertimeRate).all()}


def load_supplement_rates_by_id_from_db(db) -> dict[int, Decimal]:
    """Alle tillægssatser nøglet på id (ikke kun de fast navngivne) — bruges af
    _resolve_rate() til at slå brugerdefinerede sats-kilder op dynamisk."""
    from database.models import MasterSupplementRate
    return {r.id: Decimal(str(r.rate)) for r in db.query(MasterSupplementRate).all()}
```

- [ ] **Step 4: Kør testen og bekræft at den passerer**

Run: `pytest tests/test_rate_source.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Skriv fejlende test for `_resolve_rate()`s nye grene**

Tilføj til `tests/test_rate_source.py`:

```python
from routers.payroll_router import _resolve_rate
from calculators.overtime import OT_BEFORE_KEY


def test_resolve_rate_overtime_prefix_looks_up_by_id():
    calc = {"ot_rates_by_id": {7: Decimal("44.54")}, "hourly_rate": Decimal("150.00")}
    assert _resolve_rate("overtime:7", calc) == 44.54


def test_resolve_rate_supplement_prefix_looks_up_by_id():
    calc = {"supplement_rates_by_id": {5: Decimal("597.00")}, "hourly_rate": Decimal("150.00")}
    assert _resolve_rate("supplement:5", calc) == 597.00


def test_resolve_rate_unknown_id_in_prefix_returns_zero():
    calc = {"ot_rates_by_id": {}, "supplement_rates_by_id": {}, "hourly_rate": Decimal("150.00")}
    assert _resolve_rate("overtime:999", calc) == 0
    assert _resolve_rate("supplement:999", calc) == 0


def test_resolve_rate_legacy_fixed_values_still_work():
    calc = {
        "ot_rates": {OT_BEFORE_KEY: Decimal("44.54")},
        "salt_rate": Decimal("12.50"),
        "hourly_rate": Decimal("150.00"),
    }
    assert _resolve_rate("ot_before", calc) == 44.54
    assert _resolve_rate("salt", calc) == 12.50


def test_resolve_rate_hourly_and_unknown_fall_back_to_hourly_rate():
    calc = {"hourly_rate": Decimal("150.00")}
    assert _resolve_rate("hourly", calc) == 150.00
    assert _resolve_rate("noget_ukendt", calc) == 150.00
```

- [ ] **Step 6: Kør testene og bekræft at de nye prefix-tests fejler, de øvrige passerer**

Run: `pytest tests/test_rate_source.py -v`
Expected: FAIL på `test_resolve_rate_overtime_prefix_looks_up_by_id` og `test_resolve_rate_supplement_prefix_looks_up_by_id` (falder tilbage til `hourly_rate` i stedet for den forventede sats); de øvrige 5 tests PASS

- [ ] **Step 7: Udvid `_resolve_rate()` med de to nye grene**

I `app/routers/payroll_router.py`, ret linje 108-124 fra:

```python
def _resolve_rate(rate_src: str, calc: dict) -> float:
    """Opslår en sats fra calc-dict baseret på rate_src-streng."""
    if rate_src == "ot_before":
        return float(calc["ot_rates"][OT_BEFORE_KEY])
    if rate_src == "ot_13":
        return float(calc["ot_rates"][OT_13_KEY])
    if rate_src == "ot_extra":
        return float(calc["ot_rates"][OT_EXTRA_KEY])
    if rate_src == "salt":
        return float(calc.get("salt_rate", 0))
    if rate_src == "overnight":
        return float(calc.get("overnight_rate", 0))
    if rate_src == "dagpenge":
        return float(calc.get("dagpenge_sats", 137.43))
    if rate_src == "springer":
        return float(calc.get("springer_rate", 0))
    return float(calc["hourly_rate"])
```

til:

```python
def _resolve_rate(rate_src: str, calc: dict) -> float:
    """Opslår en sats fra calc-dict baseret på rate_src-streng."""
    if rate_src.startswith("overtime:"):
        rid = int(rate_src.split(":", 1)[1])
        return float(calc.get("ot_rates_by_id", {}).get(rid, 0))
    if rate_src.startswith("supplement:"):
        rid = int(rate_src.split(":", 1)[1])
        return float(calc.get("supplement_rates_by_id", {}).get(rid, 0))
    # Gamle faste værdier – bevaret som sikkerhedsnet efter migrationen til id-baserede referencer.
    if rate_src == "ot_before":
        return float(calc["ot_rates"][OT_BEFORE_KEY])
    if rate_src == "ot_13":
        return float(calc["ot_rates"][OT_13_KEY])
    if rate_src == "ot_extra":
        return float(calc["ot_rates"][OT_EXTRA_KEY])
    if rate_src == "salt":
        return float(calc.get("salt_rate", 0))
    if rate_src == "overnight":
        return float(calc.get("overnight_rate", 0))
    if rate_src == "dagpenge":
        return float(calc.get("dagpenge_sats", 137.43))
    if rate_src == "springer":
        return float(calc.get("springer_rate", 0))
    return float(calc["hourly_rate"])
```

- [ ] **Step 8: Kør testene og bekræft at alle passerer**

Run: `pytest tests/test_rate_source.py -v`
Expected: PASS (8 tests)

- [ ] **Step 9: Læg de to nye id-dicts ind i `_calculate_employee()`s beregning og retur**

I `app/routers/payroll_router.py`, udvid import-blokken (linje 41-49) fra `calculators.rates_loader` med de to nye funktioner:

```python
from calculators.rates_loader import (
    load_agreement_types_from_db,
    load_overtime_rates_from_db,
    load_salt_supplement_rate_from_db,
    load_overnight_rate_from_db,
    load_dagpenge_rate_from_db,
    load_springer_rate_from_db,
    load_overtime_rates_by_id_from_db,
    load_supplement_rates_by_id_from_db,
    get_active_supplement_for_period,
)
```

Tilføj i `_calculate_employee()` efter linje 303 (`springer_rate = load_springer_rate_from_db(db)`):

```python
    ot_rates_by_id = load_overtime_rates_by_id_from_db(db)
    supplement_rates_by_id = load_supplement_rates_by_id_from_db(db)
```

Tilføj i retur-dictet (efter linje 600, `"ot_rates": {k: float(v) for k, v in ot_rates.items()},`):

```python
        "ot_rates_by_id":     {k: float(v) for k, v in ot_rates_by_id.items()},
        "supplement_rates_by_id": {k: float(v) for k, v in supplement_rates_by_id.items()},
```

- [ ] **Step 10: Skriv fejlende integrationstest for at det nye opslag virker gennem hele beregningen**

Tilføj til `tests/test_rate_source.py`:

```python
from datetime import date
from database.models import MasterAgreementType
from routers.payroll_router import _calculate_employee


def test_calculate_employee_exposes_rate_dicts_by_id(db, employee):
    ot = MasterOvertimeRate(label="Overtid 1 time før", rate=Decimal("44.54"))
    supp = MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True)
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    db.add(ot)
    db.add(supp)
    db.commit()
    db.refresh(ot)
    db.refresh(supp)

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["ot_rates_by_id"][ot.id] == pytest.approx(44.54)
    assert calc["supplement_rates_by_id"][supp.id] == pytest.approx(597.00)
```

Tilføj `import pytest` øverst i testfilen hvis det ikke allerede er der.

- [ ] **Step 11: Kør testen og bekræft at den fejler, ret, kør igen**

Run: `pytest tests/test_rate_source.py -v`
Expected: FAIL (`KeyError: 'ot_rates_by_id'`) før Step 9's ændring er anvendt — da Step 9 allerede er udført i denne opgave, kør testen nu og bekræft PASS i stedet:
Expected: PASS (9 tests)

- [ ] **Step 12: Tilføj migration af eksisterende data i `_migrate()`**

I `app/database/session.py`, tilføj i `_migrate()` lige før funktionens afsluttende `conn.commit()` (efter linje 141, `"ON employee_supplements(employee_id)"` + `)`, før den sidste `conn.commit()` på linje 142):

```python
        # Migrer eksisterende faste sats-kilde-værdier til det nye id-baserede skema
        # (overtime:<id> / supplement:<id>) – idempotent, rammer kun rækker der
        # stadig har en af de gamle faste værdier.
        _legacy_rate_src_map = {
            "ot_before": ("master_overtime_rates", "Overtid 1 time før"),
            "ot_13": ("master_overtime_rates", "Overtid 1-3 timer efter"),
            "ot_extra": ("master_overtime_rates", "Øvrigt overtid"),
            "salt": ("master_supplement_rates", "Salttillæg"),
            "overnight": ("master_supplement_rates", "Overnatning"),
            "dagpenge": ("master_supplement_rates", "Dagpenge §56"),
            "springer": ("master_supplement_rates", "Springertillæg"),
        }
        for old_value, (table, label) in _legacy_rate_src_map.items():
            found = conn.execute(f"SELECT id FROM {table} WHERE label = ?", (label,)).fetchone()
            if found:
                prefix = "overtime" if table == "master_overtime_rates" else "supplement"
                conn.execute(
                    "UPDATE master_pay_types SET csv_rate_source = ? WHERE csv_rate_source = ?",
                    (f"{prefix}:{found[0]}", old_value),
                )
        conn.commit()
```

- [ ] **Step 13: Verificér migrationen manuelt mod den eksisterende database**

`_migrate()` forbinder altid til den faktiske `app/database/lonsystem.db` (ikke en test-database), så migrationen kan ikke dækkes af et automatiseret pytest-testcase — verificér i stedet manuelt, samme fremgangsmåde som blev brugt til at verificere `employee_supplements`-migrationen (`2026-08-13-medarbejder-tillaeg.md`, Task-fix-runde 2):

Kør fra `app/`-mappen:
```bash
python -c "
from database.session import init_db, SessionLocal
init_db()
db = SessionLocal()
import sqlite3
c = sqlite3.connect('database/lonsystem.db')
rows = c.execute(\"SELECT id, label, csv_rate_source FROM master_pay_types WHERE is_user_created=1\").fetchall()
for r in rows:
    print(r)
db.close()
"
```

Expected: ingen rækker viser en af de gamle faste værdier (`ot_before`, `ot_13`, `ot_extra`, `salt`, `overnight`, `dagpenge`, `springer`) i `csv_rate_source`-kolonnen — enten `hourly`, eller `overtime:<tal>`/`supplement:<tal>`. Kør kommandoen én gang til og bekræft at output er identisk (idempotens — ingen fejl, ingen ændring anden gang).

- [ ] **Step 14: Kør hele testsuiten og bekræft ingen regressioner**

Run: `pytest tests/ -v`
Expected: PASS (alle eksisterende + de 9 nye tests)

- [ ] **Step 15: Commit**

```bash
git add app/calculators/rates_loader.py app/routers/payroll_router.py app/database/session.py tests/test_rate_source.py
git commit -m "feat: id-baseret satsopslag for løntypekoders sats-kilde + migration"
```

---

## Task 2: Beskyt sletning af en sats der er i brug

**Files:**
- Modify: `app/routers/stamdata.py` (`delete_overtime_rate` linje 186-200, `delete_supplement` linje 254-268)
- Test: `tests/test_rate_source.py` (udvid)

**Interfaces:**
- Consumes: `MasterPayType.csv_rate_source`-værdierne `"overtime:<id>"`/`"supplement:<id>"` fra Task 1
- Produces: intet nyt for andre opgaver

- [ ] **Step 1: Skriv fejlende test for at sletning blokeres når en sats er i brug**

```python
# Tilføj til tests/test_rate_source.py
from fastapi import HTTPException
from routers.stamdata import delete_overtime_rate, delete_supplement
from database.models import MasterPayType


def test_delete_overtime_rate_blocked_when_referenced_by_pay_type(db):
    ot = MasterOvertimeRate(label="Ekstra overtid", rate=Decimal("50.00"), is_user_created=True)
    db.add(ot)
    db.commit()
    db.refresh(ot)
    db.add(MasterPayType(
        code_key="TEST_TYPE", label="Testtype", csv_rate_source=f"overtime:{ot.id}",
        is_user_created=True,
    ))
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_overtime_rate(ot.id, current_user=None, db=db)
    assert exc_info.value.status_code == 400
    assert "Testtype" in exc_info.value.detail


def test_delete_overtime_rate_allowed_when_not_referenced(db):
    ot = MasterOvertimeRate(label="Ubrugt overtid", rate=Decimal("50.00"), is_user_created=True)
    db.add(ot)
    db.commit()
    db.refresh(ot)

    delete_overtime_rate(ot.id, current_user=None, db=db)

    assert db.query(MasterOvertimeRate).filter(MasterOvertimeRate.id == ot.id).first() is None


def test_delete_supplement_blocked_when_referenced_by_pay_type(db):
    supp = MasterSupplementRate(label="Ekstra tillæg", rate=Decimal("30.00"), is_user_created=True)
    db.add(supp)
    db.commit()
    db.refresh(supp)
    db.add(MasterPayType(
        code_key="TEST_TYPE2", label="Testtype 2", csv_rate_source=f"supplement:{supp.id}",
        is_user_created=True,
    ))
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_supplement(supp.id, current_user=None, db=db)
    assert exc_info.value.status_code == 400
    assert "Testtype 2" in exc_info.value.detail


def test_delete_supplement_allowed_when_not_referenced(db):
    supp = MasterSupplementRate(label="Ubrugt tillæg", rate=Decimal("30.00"), is_user_created=True)
    db.add(supp)
    db.commit()
    db.refresh(supp)

    delete_supplement(supp.id, current_user=None, db=db)

    assert db.query(MasterSupplementRate).filter(MasterSupplementRate.id == supp.id).first() is None
```

- [ ] **Step 2: Kør testene og bekræft at "blocked"-testene fejler**

Run: `pytest tests/test_rate_source.py -k blocked -v`
Expected: FAIL — sletningen gennemføres i dag uden at tjekke om satsen er i brug, så der rejses ingen `HTTPException`

- [ ] **Step 3: Tilføj brugstjek i `delete_overtime_rate`**

I `app/routers/stamdata.py`, ret `delete_overtime_rate` (linje 186-200) fra:

```python
@router.delete("/overtime-rates/{rate_id}", status_code=204)
def delete_overtime_rate(
    rate_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterOvertimeRate).filter(MasterOvertimeRate.id == rate_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if not row.is_user_created:
        raise HTTPException(400, "Systemsatser kan ikke slettes")
    log_action(db, current_user, "stamdata_delete", "overtime_rate", row.id,
               f"Slettet overtidssats: {row.label}")
    db.delete(row)
    db.commit()
```

til:

```python
@router.delete("/overtime-rates/{rate_id}", status_code=204)
def delete_overtime_rate(
    rate_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterOvertimeRate).filter(MasterOvertimeRate.id == rate_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if not row.is_user_created:
        raise HTTPException(400, "Systemsatser kan ikke slettes")
    in_use = db.query(MasterPayType).filter(MasterPayType.csv_rate_source == f"overtime:{rate_id}").first()
    if in_use:
        raise HTTPException(400, f"Kan ikke slettes – bruges som sats-kilde af løntypekoden '{in_use.label}'")
    log_action(db, current_user, "stamdata_delete", "overtime_rate", row.id,
               f"Slettet overtidssats: {row.label}")
    db.delete(row)
    db.commit()
```

- [ ] **Step 4: Tilføj tilsvarende brugstjek i `delete_supplement`**

I `app/routers/stamdata.py`, ret `delete_supplement` (linje 254-268) fra:

```python
@router.delete("/supplements/{supplement_id}", status_code=204)
def delete_supplement(
    supplement_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterSupplementRate).filter(MasterSupplementRate.id == supplement_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if not row.is_user_created:
        raise HTTPException(400, "Systemtillæg kan ikke slettes")
    log_action(db, current_user, "stamdata_delete", "supplement_rate", row.id,
               f"Slettet tillæg: {row.label}")
    db.delete(row)
    db.commit()
```

til:

```python
@router.delete("/supplements/{supplement_id}", status_code=204)
def delete_supplement(
    supplement_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterSupplementRate).filter(MasterSupplementRate.id == supplement_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if not row.is_user_created:
        raise HTTPException(400, "Systemtillæg kan ikke slettes")
    in_use = db.query(MasterPayType).filter(MasterPayType.csv_rate_source == f"supplement:{supplement_id}").first()
    if in_use:
        raise HTTPException(400, f"Kan ikke slettes – bruges som sats-kilde af løntypekoden '{in_use.label}'")
    log_action(db, current_user, "stamdata_delete", "supplement_rate", row.id,
               f"Slettet tillæg: {row.label}")
    db.delete(row)
    db.commit()
```

- [ ] **Step 5: Kør testene og bekræft at alle passerer**

Run: `pytest tests/test_rate_source.py -v`
Expected: PASS (13 tests)

- [ ] **Step 6: Kør hele testsuiten og bekræft ingen regressioner**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/routers/stamdata.py tests/test_rate_source.py
git commit -m "feat: bloker sletning af overtidssats/tillæg der er i brug som sats-kilde"
```

---

## Task 3: Frontend — dynamisk dropdown og visningslabel

**Files:**
- Modify: `app/templates/index.html` (linje 1490-1502 og 1572-1584 — de to `<select>`-blokke)
- Modify: `app/static/js/app.js` (`loadStamdataOvertimeRates()` linje 3514-3534, `loadStamdataSupplements()` linje 3536-3556, `_RATE_SRC_LABELS`/`loadStamdataPayTypes()` linje 3558-3596, `openStamdataPayTypeModal()` linje 3661-3671, `openNewPayTypeModal()` linje 3733-3742)

**Interfaces:**
- Consumes: `GET /api/stamdata/overtime-rates` og `GET /api/stamdata/supplements` (eksisterende, uændrede endpoints, returnerer `{id, label, rate, is_user_created}`)
- Produces: `state.stamdataOvertimeRates` / `state.stamdataSupplements` (nye state-felter, bruges kun internt i denne fil)

Dette repo har intet frontend-testframework — verifikation sker manuelt i browseren.

- [ ] **Step 1: Cache Overtidssatser/Tillæg i `state` når de indlæses**

I `app/static/js/app.js`, ret `loadStamdataOvertimeRates()` (linje 3514-3534) — tilføj `state.stamdataOvertimeRates = rows;` lige efter `const rows = await GET("/api/stamdata/overtime-rates");` (linje 3519):

```js
async function loadStamdataOvertimeRates() {
  const tbody = document.getElementById("stamdata-overtime-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/overtime-rates");
    state.stamdataOvertimeRates = rows;
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${r.rate.toFixed(2).replace(".", ",")} kr</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataRateModal(${r.id}, ${jq(r.label)}, ${r.rate}, 'overtime')">Rediger</button>
          ${r.is_user_created ? `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataRate(${r.id}, ${jq(r.label)}, 'overtime')">Slet</button>` : ""}
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}
```

Ret tilsvarende `loadStamdataSupplements()` (linje 3536-3556) — tilføj `state.stamdataSupplements = rows;` lige efter `const rows = await GET("/api/stamdata/supplements");` (linje 3541):

```js
async function loadStamdataSupplements() {
  const tbody = document.getElementById("stamdata-supplement-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/supplements");
    state.stamdataSupplements = rows;
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${r.rate.toFixed(2).replace(".", ",")} kr</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataRateModal(${r.id}, ${jq(r.label)}, ${r.rate}, 'supplement')">Rediger</button>
          ${r.is_user_created ? `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataRate(${r.id}, ${jq(r.label)}, 'supplement')">Slet</button>` : ""}
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}
```

- [ ] **Step 2: Erstat `_RATE_SRC_LABELS` med en opslagsfunktion, og brug den i `loadStamdataPayTypes()`**

I `app/static/js/app.js`, ret linje 3558-3562 fra:

```js
const _RATE_SRC_LABELS = {
  hourly: "Timesats", ot_before: "OT 1t før", ot_13: "OT 1-3t",
  ot_extra: "Øvrig OT", salt: "Salt", overnight: "Overnatning", dagpenge: "Dagpenge §56",
  springer: "Springertillæg",
};
```

til:

```js
function _rateSourceLabel(rateSrc) {
  if (!rateSrc || rateSrc === "hourly") return "Timesats";
  const sepIdx = rateSrc.indexOf(":");
  if (sepIdx === -1) return rateSrc; // gammel fast værdi (ikke migreret, eller ukendt) – vis rå streng
  const kind = rateSrc.slice(0, sepIdx);
  const id = parseInt(rateSrc.slice(sepIdx + 1));
  const list = kind === "overtime" ? state.stamdataOvertimeRates : state.stamdataSupplements;
  const row = list?.find(r => r.id === id);
  return row ? row.label : rateSrc;
}
```

Ret linje 3575 (inde i `loadStamdataPayTypes()`) fra:

```js
      const rateLabel = _RATE_SRC_LABELS[r.csv_rate_source] || r.csv_rate_source;
```

til:

```js
      const rateLabel = _rateSourceLabel(r.csv_rate_source);
```

- [ ] **Step 3: Tilføj fælles funktion til at bygge dropdown-options dynamisk**

I `app/static/js/app.js`, tilføj lige før `function openStamdataPayTypeModal(...)` (før linje 3661):

```js
function _buildRateSourceOptions(selectId, selectedValue) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  let optionsHtml = `<option value="hourly">Timesats (overenskomst)</option>`;
  if (state.stamdataOvertimeRates?.length) {
    optionsHtml += `<optgroup label="Overtidssatser">` +
      state.stamdataOvertimeRates.map(r => `<option value="overtime:${r.id}">${h(r.label)}</option>`).join("") +
      `</optgroup>`;
  }
  if (state.stamdataSupplements?.length) {
    optionsHtml += `<optgroup label="Tillæg">` +
      state.stamdataSupplements.map(r => `<option value="supplement:${r.id}">${h(r.label)}</option>`).join("") +
      `</optgroup>`;
  }
  sel.innerHTML = optionsHtml;
  sel.value = selectedValue || "hourly";
}
```

- [ ] **Step 4: Kald den nye funktion fra begge modal-åbnere i stedet for at sætte `.value` direkte**

I `app/static/js/app.js`, ret `openStamdataPayTypeModal()` (linje 3661-3671) — erstat linjen `document.getElementById("stamdata-paytype-ratesrc").value = rateSrc || "hourly";` med et kald til den nye funktion:

```js
function openStamdataPayTypeModal(id, label, code, inCsv, qtyType, rateSrc, incRate, incTotal) {
  document.getElementById("stamdata-paytype-id").value = id;
  document.getElementById("stamdata-paytype-label").value = label || "";
  document.getElementById("stamdata-paytype-code").value = code || "";
  document.getElementById("stamdata-paytype-incsv").checked = !!inCsv;
  document.getElementById("stamdata-paytype-qtytype").value = qtyType || "hours";
  _buildRateSourceOptions("stamdata-paytype-ratesrc", rateSrc);
  document.getElementById("stamdata-paytype-incrate").checked = incRate !== false;
  document.getElementById("stamdata-paytype-inctotal").checked = !!incTotal;
  openModal("modal-stamdata-paytype");
}
```

Ret `openNewPayTypeModal()` (linje 3733-3742) — erstat linjen `document.getElementById("new-paytype-ratesrc").value = "hourly";` med:

```js
function openNewPayTypeModal() {
  document.getElementById("new-paytype-label").value = "";
  document.getElementById("new-paytype-code").value  = "";
  document.getElementById("new-paytype-incsv").checked = true;
  document.getElementById("new-paytype-qtytype").value = "hours";
  _buildRateSourceOptions("new-paytype-ratesrc", "hourly");
  document.getElementById("new-paytype-incrate").checked = true;
  document.getElementById("new-paytype-inctotal").checked = false;
  openModal("modal-stamdata-new-paytype");
}
```

- [ ] **Step 5: Fjern de hardcodede `<option>`-lister fra HTML'en**

I `app/templates/index.html`, ret linje 1490-1502 fra:

```html
      <div class="form-group">
        <label>Sats-kilde i CSV</label>
        <select id="new-paytype-ratesrc" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:14px">
          <option value="hourly">Timesats (overenskomst)</option>
          <option value="ot_before">Overtid 1 time før</option>
          <option value="ot_13">Overtid 1-3 timer</option>
          <option value="ot_extra">Øvrig overtid</option>
          <option value="salt">Salttillæg</option>
          <option value="overnight">Overnatning</option>
          <option value="dagpenge">Dagpenge §56</option>
          <option value="springer">Springertillæg</option>
        </select>
      </div>
```

til:

```html
      <div class="form-group">
        <label>Sats-kilde i CSV</label>
        <select id="new-paytype-ratesrc" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:14px"></select>
      </div>
```

Ret linje 1572-1584 tilsvarende fra:

```html
      <div class="form-group">
        <label>Sats-kilde i CSV</label>
        <select id="stamdata-paytype-ratesrc" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:14px">
          <option value="hourly">Timesats (overenskomst)</option>
          <option value="ot_before">Overtid 1 time før</option>
          <option value="ot_13">Overtid 1-3 timer</option>
          <option value="ot_extra">Øvrig overtid</option>
          <option value="salt">Salttillæg</option>
          <option value="overnight">Overnatning</option>
          <option value="dagpenge">Dagpenge §56</option>
          <option value="springer">Springertillæg</option>
        </select>
      </div>
```

til:

```html
      <div class="form-group">
        <label>Sats-kilde i CSV</label>
        <select id="stamdata-paytype-ratesrc" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:14px"></select>
      </div>
```

- [ ] **Step 6: Kør hele testsuiten (backend uændret af denne opgave, men bekræft ingen regressioner)**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Verificér i browseren**

Start serveren (`cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`), log ind, gå til Stamdata → Løntypekoder:
1. Klik "+ Tilføj" — bekræft at "Sats-kilde i CSV"-dropdownet viser "Timesats (overenskomst)" øverst, derefter en gruppe "Overtidssatser" med de tre overtidssatser, og en gruppe "Tillæg" med alle rækker fra Tillæg-fanen (inkl. "DOB_overnatning" eller enhver anden brugeroprettet række).
2. Opret en løntypekode med sats-kilde sat til en Tillæg-række. Bekræft at tabellens "Sats-kilde"-kolonne viser det rigtige navn (ikke en rå kode).
3. Klik "Rediger" på en eksisterende brugeroprettet løntypekode. Bekræft at dropdownet forudvælger den nuværende sats-kilde korrekt.
4. Gå til Stamdata → Tillæg, forsøg at slette den række du netop brugte som sats-kilde i trin 2 — bekræft en fejlbesked der navngiver løntypekoden, og at rækken ikke slettes.

- [ ] **Step 8: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: dynamisk sats-kilde-dropdown for løntypekoder"
```

---

## Selvgennemgang (allerede udført af planforfatteren)

- **Spec-dækning:** Ny reference-model + migration (Task 1), beregning/`_resolve_rate()` (Task 1), sletningsbeskyttelse (Task 2), dynamisk dropdown + visningslabel (Task 3). Alle spec-afsnit har en task.
- **Placeholder-scan:** Ingen TBD/TODO — migrationens manuelle verifikationstrin (Task 1, Step 13) er en bevidst konsekvens af at `_migrate()` forbinder til den faste `DB_PATH` og derfor ikke er unit-testbar i isolation (samme begrænsning og samme løsning som ved `employee_supplements`-migrationen).
- **Type-konsistens:** `_resolve_rate(rate_src: str, calc: dict) -> float` uændret signatur på tværs af Task 1 og Task 2's tests. `calc["ot_rates_by_id"]`/`calc["supplement_rates_by_id"]` navngivet identisk i Task 1's implementering og tests. `state.stamdataOvertimeRates`/`state.stamdataSupplements` navngivet identisk i alle Task 3-steps der læser/skriver dem.
