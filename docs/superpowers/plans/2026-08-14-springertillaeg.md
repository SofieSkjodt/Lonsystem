# Springertillæg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Springertillæg" as a new løntypekode with its own sats, gated per medarbejder per lønperiode by a checkbox in aktivitetsoversigten, exported to the Danløn CSV with the same hour count as løntypekode 1 (Normal tid) whenever the checkbox is set and the hour count is non-zero.

**Architecture:** Follows the existing "Overnatning" pattern (a flat rate from `MasterSupplementRate` + a `MasterPayType` row with a dedicated `csv_rate_source`), hardcoded into `_calculate_employee()`/CSV export rather than the generic `_user_pay_type_rows()` mechanism — springertillæg is not tied to an `Activity` record. The per-period gate is a brand-new table, `employee_springer_flags`, keyed on `(employee_id, pay_period_id)`.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy (SQLite) backend, vanilla JS + server-rendered HTML frontend, pytest.

## Global Constraints

- Timeantal i CSV = altid `calc["normal_hours"]` (samme som løntypekode 1) for den pågældende medarbejder/periode — aldrig en separat beregning.
- Linjen udelades fra CSV hvis fluebenet ikke er sat ELLER timetallet er 0.
- Fluebenet nulstilles automatisk hver ny lønperiode (ingen række i `employee_springer_flags` = ikke sat).
- Fluebenet vises for ALLE medarbejdere i aktivitetsoversigten, ikke kun dem med aktiviteter i perioden.
- Fluebenet kan ikke ændres når perioden er låst (`PayPeriodStatus.closed`) — hverken i UI eller backend.
- Ny permission `toggle_springer` gives til ALLE eksisterende roller (system og ikke-system) ved migrering.
- Reference: `docs/superpowers/specs/2026-08-14-springertillaeg-design.md` (godkendt spec).

---

## Task 1: Datamodel — `EmployeeSpringerFlag`

**Files:**
- Modify: `app/database/models.py` (tilføj ny klasse efter `EmployeeSupplement`, linje 378)
- Test: `tests/test_springertillaeg.py` (ny fil)

**Interfaces:**
- Produces: `EmployeeSpringerFlag` model med felter `id, employee_id, pay_period_id, enabled, updated_at, updated_by` og unikt indeks `uq_employee_springer_flags_emp_period` på `(employee_id, pay_period_id)`.

- [ ] **Step 1: Write the failing test**

Opret `tests/test_springertillaeg.py`:

```python
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from database.models import AppUser, EmployeeSpringerFlag
from calculators.pay_period import get_or_create_period_for_date


def _dummy_user():
    """Ugemt AppUser til at kalde route-funktioner direkte i tests uden en
    rigtig session — samme mønster som i tests/test_employee_supplements.py."""
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_unique_constraint_prevents_duplicate_employee_period_row(db, employee):
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=True))
    db.commit()
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=False))
    with pytest.raises(Exception):  # IntegrityError fra det unikke indeks
        db.commit()
    db.rollback()


def test_different_periods_can_both_have_a_row_for_same_employee(db, employee):
    period1 = get_or_create_period_for_date(date(2026, 1, 1), db)
    period2 = get_or_create_period_for_date(date(2026, 1, 15), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period1.id, enabled=True))
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period2.id, enabled=True))
    db.commit()  # skal IKKE kaste IntegrityError
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -v`
Expected: FAIL with `ImportError: cannot import name 'EmployeeSpringerFlag' from 'database.models'`

- [ ] **Step 3: Write minimal implementation**

I `app/database/models.py`, tilføj lige efter `EmployeeSupplement`-klassen (efter linje 378, før `class MasterBaseline`/næste klasse):

```python
class EmployeeSpringerFlag(Base):
    __tablename__ = "employee_springer_flags"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False, index=True)
    enabled = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(String, nullable=True)

    employee = relationship("Employee")
    pay_period = relationship("PayPeriod")

    __table_args__ = (
        Index("uq_employee_springer_flags_emp_period", "employee_id", "pay_period_id", unique=True),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/database/models.py tests/test_springertillaeg.py
git commit -m "feat: tilføj EmployeeSpringerFlag-tabel til springertillæg"
```

---

## Task 2: Permission `toggle_springer`

**Files:**
- Modify: `app/auth.py` (`ALL_PERMISSIONS`, linje 9-25)
- Modify: `app/static/js/app.js` (`PERMISSION_LABELS`, linje 32-48)
- Modify: `app/database/session.py` (`init_db()` linje 41-56 + ny funktion)
- Test: `tests/test_springertillaeg.py`

**Interfaces:**
- Produces: permission-nøgle `"toggle_springer"` i `ALL_PERMISSIONS`; funktion `_ensure_toggle_springer_permission()` der tilføjer den til ALLE roller (idempotent).

- [ ] **Step 1: Write the failing test**

Tilføj til `tests/test_springertillaeg.py`:

```python
def test_ensure_toggle_springer_permission_adds_to_all_roles(db, monkeypatch):
    from database.models import Role
    from database.session import _ensure_toggle_springer_permission
    import database.session as session_module

    # _ensure_toggle_springer_permission bruger sin egen SessionLocal, ikke test-db'en –
    # patch den (auto-reverteres af monkeypatch efter testen) til test-enginens
    # sessionmaker så funktionen skriver til samme in-memory DB.
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=["payroll"]))
    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False, permissions=["payroll"]))
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()

    _ensure_toggle_springer_permission()

    for role in db.query(Role).all():
        db.refresh(role)
        assert "toggle_springer" in role.permissions

    # Idempotent — kald igen ændrer ikke noget/fejler ikke
    _ensure_toggle_springer_permission()
    for role in db.query(Role).all():
        db.refresh(role)
        assert role.permissions.count("toggle_springer") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py::test_ensure_toggle_springer_permission_adds_to_all_roles -v`
Expected: FAIL with `ImportError: cannot import name '_ensure_toggle_springer_permission'`

- [ ] **Step 3: Write minimal implementation**

I `app/auth.py`, tilføj til `ALL_PERMISSIONS`-dict (linje 9-25), som ny sidste linje før den lukkende `}`:
```python
    "toggle_springer":    "Sæt springertillæg",
```

I `app/static/js/app.js`, tilføj til `PERMISSION_LABELS`-dict (linje 32-48), som ny linje før den lukkende `};`:
```js
  toggle_springer:     "Sæt springertillæg",
```

I `app/database/session.py`, tilføj ny funktion lige efter `_ensure_employee_supplements_permission()` (efter linje 505):

```python
def _ensure_toggle_springer_permission():
    """Tilføjer toggle_springer til ALLE roller (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        for role in db.query(Role).all():
            perms = list(role.permissions or [])
            if "toggle_springer" not in perms:
                perms.append("toggle_springer")
                role.permissions = perms
        db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af toggle_springer-tilladelse: {e}")
    finally:
        db.close()
```

Kald den fra `init_db()` (linje 41-56), tilføj som ny linje efter `_ensure_employee_supplements_permission()`:
```python
    _ensure_toggle_springer_permission()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/auth.py app/static/js/app.js app/database/session.py tests/test_springertillaeg.py
git commit -m "feat: ny permission toggle_springer, gives til alle roller"
```

---

## Task 3: Seed sats og løntypekode

**Files:**
- Modify: `app/calculators/pay_rates.py` (ny konstant)
- Modify: `app/database/session.py` (ny idempotent seed-funktion + `init_db()`)
- Test: `tests/test_springertillaeg.py`

**Interfaces:**
- Produces: `DANLOEN_CODE_SPRINGERTILLAEG` konstant; funktion `_ensure_springer_pay_type()` der seeder én `MasterSupplementRate(label="Springertillæg")`-række og én `MasterPayType(code_key="SPRINGERTILLAEG")`-række (idempotent).

- [ ] **Step 1: Write the failing test**

Tilføj til `tests/test_springertillaeg.py`:

```python
def test_ensure_springer_pay_type_seeds_rate_and_paytype(db, monkeypatch):
    from database.models import MasterSupplementRate, MasterPayType
    from database.session import _ensure_springer_pay_type
    import database.session as session_module
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    _ensure_springer_pay_type()

    rate_row = db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "Springertillæg").first()
    assert rate_row is not None
    assert rate_row.rate == 0

    pt_row = db.query(MasterPayType).filter(MasterPayType.code_key == "SPRINGERTILLAEG").first()
    assert pt_row is not None
    assert pt_row.csv_quantity_type == "hours"
    assert pt_row.csv_rate_source == "springer"
    assert pt_row.include_in_csv is True

    # Idempotent
    _ensure_springer_pay_type()
    assert db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "Springertillæg").count() == 1
    assert db.query(MasterPayType).filter(MasterPayType.code_key == "SPRINGERTILLAEG").count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py::test_ensure_springer_pay_type_seeds_rate_and_paytype -v`
Expected: FAIL with `ImportError: cannot import name '_ensure_springer_pay_type'`

- [ ] **Step 3: Write minimal implementation**

I `app/calculators/pay_rates.py`, tilføj efter `DANLOEN_CODE_BARN_1SYGEDAG`-linjen (linje 24):
```python
DANLOEN_CODE_SPRINGERTILLAEG = "1"  # Danløn-kode for springertillæg – oplyses af lønafdelingen
```

I `app/database/session.py`, tilføj ny funktion lige efter `_ensure_sh_pay_types()` (efter linje 371):

```python
def _ensure_springer_pay_type():
    """Seeder Springertillæg-sats og -løntypekode til eksisterende databaser (idempotent)."""
    from decimal import Decimal
    from database.models import MasterSupplementRate, MasterPayType
    from calculators.pay_rates import DANLOEN_CODE_SPRINGERTILLAEG
    db = SessionLocal()
    try:
        if not db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "Springertillæg").first():
            db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("0")))
        if not db.query(MasterPayType).filter(MasterPayType.code_key == "SPRINGERTILLAEG").first():
            db.add(MasterPayType(
                code_key="SPRINGERTILLAEG", label="Springertillæg",
                danloen_code=DANLOEN_CODE_SPRINGERTILLAEG,
                include_in_csv=True, sort_order=16,
                csv_quantity_type="hours", csv_rate_source="springer",
                csv_include_rate=True, csv_include_total=False,
            ))
        db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved seeding af Springertillæg: {e}")
    finally:
        db.close()
```

Kald den fra `init_db()`, tilføj efter `_ensure_toggle_springer_permission()`:
```python
    _ensure_springer_pay_type()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/calculators/pay_rates.py app/database/session.py tests/test_springertillaeg.py
git commit -m "feat: seed Springertillæg-sats og løntypekode"
```

---

## Task 4: Satsopslag — `load_springer_rate_from_db()` + `_resolve_rate()`

**Files:**
- Modify: `app/calculators/rates_loader.py` (ny funktion efter `load_overnight_rate_from_db()`)
- Modify: `app/routers/payroll_router.py` (`_resolve_rate()`, linje 107-121)
- Test: `tests/test_springertillaeg.py`

**Interfaces:**
- Consumes: `MasterSupplementRate` (Task 1/3).
- Produces: `load_springer_rate_from_db(db) -> Decimal`; `_resolve_rate("springer", calc)` slår `calc["springer_rate"]` op.

- [ ] **Step 1: Write the failing test**

Tilføj til `tests/test_springertillaeg.py`:

```python
def test_load_springer_rate_from_db_returns_seeded_rate(db):
    from decimal import Decimal
    from database.models import MasterSupplementRate
    from calculators.rates_loader import load_springer_rate_from_db
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("25.50")))
    db.commit()
    assert load_springer_rate_from_db(db) == Decimal("25.50")


def test_load_springer_rate_from_db_returns_zero_when_missing(db):
    from decimal import Decimal
    from calculators.rates_loader import load_springer_rate_from_db
    assert load_springer_rate_from_db(db) == Decimal("0")


def test_resolve_rate_springer_reads_calc_dict():
    from routers.payroll_router import _resolve_rate
    calc = {"springer_rate": 25.5, "hourly_rate": 150.0}
    assert _resolve_rate("springer", calc) == 25.5


def test_resolve_rate_springer_defaults_to_zero_when_missing():
    from routers.payroll_router import _resolve_rate
    calc = {"hourly_rate": 150.0}
    assert _resolve_rate("springer", calc) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -k "springer_rate or resolve_rate_springer" -v`
Expected: FAIL with `ImportError: cannot import name 'load_springer_rate_from_db'`

- [ ] **Step 3: Write minimal implementation**

I `app/calculators/rates_loader.py`, tilføj lige efter `load_overnight_rate_from_db()` (efter linje 165):

```python
def load_springer_rate_from_db(db) -> Decimal:
    from database.models import MasterSupplementRate
    row = db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "Springertillæg").first()
    return Decimal(str(row.rate)) if row else Decimal("0")
```

I `app/routers/payroll_router.py`, `_resolve_rate()` (linje 107-121), tilføj ny gren før `return float(calc["hourly_rate"])`:

```python
    if rate_src == "springer":
        return float(calc.get("springer_rate", 0))
```

Tilføj `load_springer_rate_from_db` til import-blokken (linje 41-48):
```python
from calculators.rates_loader import (
    load_agreement_types_from_db,
    load_overtime_rates_from_db,
    load_salt_supplement_rate_from_db,
    load_overnight_rate_from_db,
    load_dagpenge_rate_from_db,
    load_springer_rate_from_db,
    get_active_supplement_for_period,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add app/calculators/rates_loader.py app/routers/payroll_router.py tests/test_springertillaeg.py
git commit -m "feat: satsopslag for springertillæg (load_springer_rate_from_db + _resolve_rate)"
```

---

## Task 5: `_calculate_employee()` — springer_enabled/springer_rate

**Files:**
- Modify: `app/routers/payroll_router.py` (`_calculate_employee()`, linje 251-540 + import linje 49)
- Test: `tests/test_springertillaeg.py`

**Interfaces:**
- Consumes: `EmployeeSpringerFlag` (Task 1), `load_springer_rate_from_db()` (Task 4), `get_or_create_period_for_date()` (allerede importeret).
- Produces: `calc["springer_enabled"]: bool`, `calc["springer_rate"]: float` i returdict fra `_calculate_employee()`.

**Note:** perioden slås op internt via `get_or_create_period_for_date(start, db)` i stedet for at tilføje en ny parameter til `_calculate_employee()` — funktionen kaldes fra 8 steder i `payroll_router.py`/`timeseddel_router.py`, og nogle af dem (tidssedler/preview) bruger et frit `from_date`/`to_date`-interval uden noget naturligt periode-id. For CSV-/lønkørsel-kald er `start` allerede periodens egen `start_date`, så opslaget rammer altid den korrekte periode.

- [ ] **Step 1: Write the failing test**

Tilføj til `tests/test_springertillaeg.py`:

```python
def _setup_rates(db, employee, hourly=Decimal("150.00")):
    from database.models import MasterAgreementType, MasterOvertimeRate
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=hourly))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()


def test_calculate_employee_springer_disabled_by_default(db, employee):
    from routers.payroll_router import _calculate_employee
    _setup_rates(db, employee)
    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 14), db)
    assert calc["springer_enabled"] is False


def test_calculate_employee_springer_enabled_when_flag_set(db, employee):
    from database.models import EmployeeSpringerFlag, MasterSupplementRate
    from routers.payroll_router import _calculate_employee
    _setup_rates(db, employee)
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("20.00")))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=True))
    db.commit()

    calc = _calculate_employee(employee, period.start_date, period.end_date, db)
    assert calc["springer_enabled"] is True
    assert calc["springer_rate"] == pytest.approx(20.00)


def test_calculate_employee_springer_flag_does_not_carry_to_next_period(db, employee):
    from database.models import EmployeeSpringerFlag
    from routers.payroll_router import _calculate_employee
    _setup_rates(db, employee)
    period1 = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period1.id, enabled=True))
    db.commit()

    period2 = get_or_create_period_for_date(date(2026, 1, 15), db)
    calc = _calculate_employee(employee, period2.start_date, period2.end_date, db)
    assert calc["springer_enabled"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -k springer_enabled -v`
Expected: FAIL with `KeyError: 'springer_enabled'`

- [ ] **Step 3: Write minimal implementation**

I `app/routers/payroll_router.py`, tilføj `EmployeeSpringerFlag` til import (linje 49):
```python
from database.models import Activity, ActivityStatus, Employee, EmployeeSpringerFlag, Holiday, MasterCvrNumber, PayPeriod, PayPeriodStatus
```

I `_calculate_employee()`, efter linje 280 (`dagpenge_sats = load_dagpenge_rate_from_db(db)`):
```python
    springer_rate = load_springer_rate_from_db(db)
    _springer_period = get_or_create_period_for_date(start, db)
    springer_enabled = db.query(EmployeeSpringerFlag).filter(
        EmployeeSpringerFlag.employee_id == emp.id,
        EmployeeSpringerFlag.pay_period_id == _springer_period.id,
        EmployeeSpringerFlag.enabled == True,
    ).first() is not None
```

I returdict (efter linje 527, `"overnight_kr": ...`), tilføj:
```python
        "springer_rate":      float(springer_rate),
        "springer_enabled":   springer_enabled,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/payroll_router.py tests/test_springertillaeg.py
git commit -m "feat: beregn springer_enabled/springer_rate i _calculate_employee"
```

---

## Task 6: CSV-eksport — `_springer_row()` + wiring i begge `raw_rows`

**Files:**
- Modify: `app/routers/payroll_router.py` (ny helper + begge `raw_rows`-lister, linje 778-795 og 883-900)
- Test: `tests/test_springertillaeg.py`

**Interfaces:**
- Consumes: `calc["normal_hours"]`, `calc["springer_enabled"]`, `calc["springer_rate"]` (Task 5).
- Produces: `_springer_row(calc: dict) -> tuple[str, float, float]`.

- [ ] **Step 1: Write the failing test**

Tilføj til `tests/test_springertillaeg.py`. `export_csv_post()` skriver CSV-filen til `body.output_folder` (linje ~912-914 i `payroll_router.py`: `filename = f"danloen_{...}.csv"`, `(save_dir / filename).write_text(...)`) — testene bruger derfor pytests indbyggede `tmp_path`-fixture som `output_folder` og læser filen tilbage derfra:

```python
def test_springer_row_uses_normal_hours_when_enabled():
    from routers.payroll_router import _springer_row
    calc = {"normal_hours": 74.0, "springer_enabled": True, "springer_rate": 20.0}
    assert _springer_row(calc) == ("SPRINGERTILLAEG", 74.0, 20.0)


def test_springer_row_zero_when_disabled():
    from routers.payroll_router import _springer_row
    calc = {"normal_hours": 74.0, "springer_enabled": False, "springer_rate": 20.0}
    assert _springer_row(calc) == ("SPRINGERTILLAEG", 0, 20.0)


def test_export_csv_post_includes_springer_line_when_enabled(db, employee, tmp_path):
    from decimal import Decimal
    from datetime import datetime
    from database.models import EmployeeSpringerFlag, MasterSupplementRate, MasterPayType, ActivityStatus
    from calculators.pay_rates import DANLOEN_CODE_SPRINGERTILLAEG
    from routers.payroll_router import export_csv_post, ExportCsvRequest
    from conftest import make_activity

    employee.cvr_number = "13246505"
    _setup_rates(db, employee)
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("20.00")))
    db.add(MasterPayType(
        code_key="SPRINGERTILLAEG", label="Springertillæg", danloen_code=DANLOEN_CODE_SPRINGERTILLAEG,
        include_in_csv=True, sort_order=16, csv_quantity_type="hours", csv_rate_source="springer",
        csv_include_rate=True, csv_include_total=False,
    ))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=True))
    db.commit()
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    body = ExportCsvRequest(period_start="2026-01-01", output_folder=str(tmp_path))
    export_csv_post(body, current_user=_dummy_user(), db=db)

    csv_files = list(tmp_path.glob("danloen_*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text(encoding="utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    # Medarbejderen har kun én aktivitet (8 arbejdstimer, ingen overtid/salt/fravær) – med
    # flueben sat giver det præcis 2 linjer (NORMAL + SPRINGERTILLAEG), begge med kvantitet 800
    # (8 timer * 100, jf. fmt()). NORMAL og SPRINGERTILLAEG deler samme placeholder Danløn-kode
    # ("1"), så linjerne kan ikke skelnes på kolonne C – antallet af linjer er det robuste tjek.
    assert len(lines) == 2
    assert all(line.split(";")[3] == "800" for line in lines)


def test_export_csv_post_omits_springer_line_when_disabled(db, employee, tmp_path):
    from decimal import Decimal
    from datetime import datetime
    from database.models import MasterSupplementRate, MasterPayType, ActivityStatus
    from calculators.pay_rates import DANLOEN_CODE_SPRINGERTILLAEG
    from routers.payroll_router import export_csv_post, ExportCsvRequest
    from conftest import make_activity

    employee.cvr_number = "13246505"
    _setup_rates(db, employee)
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("20.00")))
    db.add(MasterPayType(
        code_key="SPRINGERTILLAEG", label="Springertillæg", danloen_code=DANLOEN_CODE_SPRINGERTILLAEG,
        include_in_csv=True, sort_order=16, csv_quantity_type="hours", csv_rate_source="springer",
        csv_include_rate=True, csv_include_total=False,
    ))
    # Ingen EmployeeSpringerFlag-række oprettet — fluebenet er IKKE sat
    db.commit()
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    body = ExportCsvRequest(period_start="2026-01-01", output_folder=str(tmp_path))
    export_csv_post(body, current_user=_dummy_user(), db=db)

    csv_files = list(tmp_path.glob("danloen_*.csv"))
    content = csv_files[0].read_text(encoding="utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    assert len(lines) == 1  # kun NORMAL – ingen SPRINGERTILLAEG-linje uden flueben
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -k "springer_row or export_csv_post" -v`
Expected: FAIL with `ImportError: cannot import name '_springer_row'`

- [ ] **Step 3: Write minimal implementation**

I `app/routers/payroll_router.py`, tilføj ny helper lige efter `_user_pay_type_rows()` (efter linje 147):

```python
def _springer_row(calc: dict) -> tuple:
    """CSV-tuple for springertillæg: samme timetal som løntypekode 1 (Normal tid),
    men kun hvis flaget er sat for medarbejderens periode (calc['springer_enabled'])."""
    qty = calc["normal_hours"] if calc.get("springer_enabled") else 0
    return ("SPRINGERTILLAEG", qty, calc.get("springer_rate", 0))
```

Erstat `raw_rows`-listen i `export_csv()` (linje 778-795) med (kun første linje efter `raw_rows = [` er ny, resten er uændret):

```python
        raw_rows = [
            ("NORMAL",         calc["normal_hours"],                                               calc["hourly_rate"]),
            _springer_row(calc),
            ("OT_BEFORE",      calc["ot_before_hours"],                                            calc["ot_rates"][OT_BEFORE_KEY]),
            ("OT_13",          calc["ot_13_hours"] + calc.get("sh_kode8_hours", 0),               calc["ot_rates"][OT_13_KEY]),
            ("OT_EXTRA",       calc["ot_extra_hours"] + calc.get("sh_kode9_hours", 0),            calc["ot_rates"][OT_EXTRA_KEY]),
            ("SH_FULDLOENNET", calc.get("sh_fuldloennet_hours", 0),                               calc["hourly_rate"]),
            ("SH_TIMELOENNET", calc.get("sh_timeloennet_hours", 0),                               calc["hourly_rate"]),
            ("SALT",           calc.get("salt_hours", 0),                                         calc.get("salt_rate", 0)),
            ("OVERNATNING",    calc.get("overnight_count", 0),                                    calc.get("overnight_rate", 0)),
            ("AFSPADSERING",   calc["afspadsering_hours"],                                        calc["hourly_rate"]),
            ("SYGDOM",         calc["sygdom_hours"],                                              calc["hourly_rate"]),
            ("PARAGRAF_56",    calc["paragraf_56_syg_hours"],                                     calc.get("dagpenge_sats", 137.43)),
            ("BARN_1SYGEDAG",  calc["barn_1sygedag_u_loen_hours"],                                calc.get("dagpenge_sats", 137.43)),
            ("FERIEFRI",       _builtin_absence_qty(pt, "FERIEFRI", "feriefri", calc["feriefri_hours"],
                                                      emp.id, period.start_date, period.end_date, db), calc["hourly_rate"]),
            ("BARSEL",         calc["barsel_hours"],                                              calc["hourly_rate"]),
            ("SKOLE_KURSUS",   calc["skole_kursus_hours"],                                        calc["hourly_rate"]),
        ] + _user_pay_type_rows(emp.id, period.start_date, period.end_date, calc, db)
```

Erstat den identiske `raw_rows`-liste i `export_csv_post()` (linje 883-900) med præcis samme ændring (indsæt `_springer_row(calc),` lige efter `("NORMAL", ...)`-linjen):

```python
        raw_rows = [
            ("NORMAL",         calc["normal_hours"],                                               calc["hourly_rate"]),
            _springer_row(calc),
            ("OT_BEFORE",      calc["ot_before_hours"],                                            calc["ot_rates"][OT_BEFORE_KEY]),
            ("OT_13",          calc["ot_13_hours"] + calc.get("sh_kode8_hours", 0),               calc["ot_rates"][OT_13_KEY]),
            ("OT_EXTRA",       calc["ot_extra_hours"] + calc.get("sh_kode9_hours", 0),            calc["ot_rates"][OT_EXTRA_KEY]),
            ("SH_FULDLOENNET", calc.get("sh_fuldloennet_hours", 0),                               calc["hourly_rate"]),
            ("SH_TIMELOENNET", calc.get("sh_timeloennet_hours", 0),                               calc["hourly_rate"]),
            ("SALT",           calc.get("salt_hours", 0),                                         calc.get("salt_rate", 0)),
            ("OVERNATNING",    calc.get("overnight_count", 0),                                    calc.get("overnight_rate", 0)),
            ("AFSPADSERING",   calc["afspadsering_hours"],                                        calc["hourly_rate"]),
            ("SYGDOM",         calc["sygdom_hours"],                                              calc["hourly_rate"]),
            ("PARAGRAF_56",    calc["paragraf_56_syg_hours"],                                     calc.get("dagpenge_sats", 137.43)),
            ("BARN_1SYGEDAG",  calc["barn_1sygedag_u_loen_hours"],                                calc.get("dagpenge_sats", 137.43)),
            ("FERIEFRI",       _builtin_absence_qty(pt, "FERIEFRI", "feriefri", calc["feriefri_hours"],
                                                      emp.id, period.start_date, period.end_date, db), calc["hourly_rate"]),
            ("BARSEL",         calc["barsel_hours"],                                              calc["hourly_rate"]),
            ("SKOLE_KURSUS",   calc["skole_kursus_hours"],                                        calc["hourly_rate"]),
        ] + _user_pay_type_rows(emp.id, period.start_date, period.end_date, calc, db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/payroll_router.py tests/test_springertillaeg.py
git commit -m "feat: tilføj springertillæg-linje til Danløn CSV-eksport"
```

---

## Task 7: Backend-endpoints — sæt/hent flueben

**Files:**
- Modify: `app/routers/activities.py` (nye imports + ny `SpringerFlagUpdate`-model + to nye endpoints)
- Test: `tests/test_springertillaeg.py`

**Interfaces:**
- Consumes: `EmployeeSpringerFlag`, `PayPeriod`, `PayPeriodStatus` (Task 1).
- Produces: `POST /api/activities/springer-flag` (kræver `toggle_springer`), `GET /api/activities/springer-flags?pay_period_id=` (kræver kun login).

- [ ] **Step 1: Write the failing test**

Tilføj til `tests/test_springertillaeg.py`:

```python
def test_set_springer_flag_creates_row(db, employee):
    from routers.activities import set_springer_flag, SpringerFlagUpdate
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    body = SpringerFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=True)
    result = set_springer_flag(body, current_user=_dummy_user(), db=db)
    assert result["enabled"] is True

    from database.models import EmployeeSpringerFlag
    row = db.query(EmployeeSpringerFlag).filter(
        EmployeeSpringerFlag.employee_id == employee.id,
        EmployeeSpringerFlag.pay_period_id == period.id,
    ).first()
    assert row.enabled is True


def test_set_springer_flag_toggles_existing_row(db, employee):
    from routers.activities import set_springer_flag, SpringerFlagUpdate
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    set_springer_flag(SpringerFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=True),
                       current_user=_dummy_user(), db=db)
    result = set_springer_flag(SpringerFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=False),
                                current_user=_dummy_user(), db=db)
    assert result["enabled"] is False

    from database.models import EmployeeSpringerFlag
    count = db.query(EmployeeSpringerFlag).filter(
        EmployeeSpringerFlag.employee_id == employee.id,
        EmployeeSpringerFlag.pay_period_id == period.id,
    ).count()
    assert count == 1  # upsert, ikke en ny række


def test_set_springer_flag_rejects_closed_period(db, employee):
    from database.models import PayPeriodStatus
    from routers.activities import set_springer_flag, SpringerFlagUpdate
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    period.status = PayPeriodStatus.closed
    db.commit()
    with pytest.raises(HTTPException):
        set_springer_flag(SpringerFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=True),
                           current_user=_dummy_user(), db=db)


def test_set_springer_flag_rejects_unknown_period(db, employee):
    from routers.activities import set_springer_flag, SpringerFlagUpdate
    with pytest.raises(HTTPException):
        set_springer_flag(SpringerFlagUpdate(employee_id=employee.id, pay_period_id=999999, enabled=True),
                           current_user=_dummy_user(), db=db)


def test_get_springer_flags_returns_only_enabled(db, employee):
    from routers.activities import set_springer_flag, get_springer_flags, SpringerFlagUpdate
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    set_springer_flag(SpringerFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=True),
                       current_user=_dummy_user(), db=db)
    result = get_springer_flags(pay_period_id=period.id, current_user=_dummy_user(), db=db)
    assert result == {employee.id: True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -k springer_flag -v`
Expected: FAIL with `ImportError: cannot import name 'set_springer_flag'`

- [ ] **Step 3: Write minimal implementation**

I `app/routers/activities.py` er `BaseModel` og `Session` allerede importeret (linje 8: `from pydantic import BaseModel`, linje 10: `from sqlalchemy.orm import Session, selectinload`) — ingen ændring nødvendig der. To linjer skal ændres:

Linje 13, tilføj `require_permission`:
```python
from auth import get_current_user, log_action, require_permission
```

Linje 16, tilføj `EmployeeSpringerFlag, PayPeriod, PayPeriodStatus`:
```python
from database.models import Activity, ActivitySource, ActivityStatus, AppUser, Employee, EmployeeSpringerFlag, PayPeriod, PayPeriodStatus
```

Tilføj lige efter `router = APIRouter(...)` (linje 27):
```python
_toggle_springer_access = require_permission("toggle_springer")


class SpringerFlagUpdate(BaseModel):
    employee_id: int
    pay_period_id: int
    enabled: bool
```

Tilføj de to nye endpoints (fx sidst i filen, eller lige efter `period_info()`):

```python
@router.get("/springer-flags")
def get_springer_flags(pay_period_id: int,
                        current_user: AppUser = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    rows = db.query(EmployeeSpringerFlag).filter(
        EmployeeSpringerFlag.pay_period_id == pay_period_id,
        EmployeeSpringerFlag.enabled == True,
    ).all()
    return {r.employee_id: True for r in rows}


@router.post("/springer-flag")
def set_springer_flag(body: SpringerFlagUpdate,
                       current_user: AppUser = Depends(_toggle_springer_access),
                       db: Session = Depends(get_db)):
    period = db.query(PayPeriod).filter(PayPeriod.id == body.pay_period_id).first()
    if not period:
        raise HTTPException(404, "Lønperiode ikke fundet")
    if period.status == PayPeriodStatus.closed:
        raise HTTPException(400, "Lønperioden er låst – kan ikke ændres")
    row = db.query(EmployeeSpringerFlag).filter(
        EmployeeSpringerFlag.employee_id == body.employee_id,
        EmployeeSpringerFlag.pay_period_id == body.pay_period_id,
    ).first()
    if row:
        row.enabled = body.enabled
        row.updated_by = current_user.initials
    else:
        row = EmployeeSpringerFlag(
            employee_id=body.employee_id, pay_period_id=body.pay_period_id,
            enabled=body.enabled, updated_by=current_user.initials,
        )
        db.add(row)
    db.commit()
    log_action(db, current_user, "springer_flag_set", "employee_springer_flag", body.employee_id,
               f"periode {body.pay_period_id}: {'sat' if body.enabled else 'fjernet'}")
    db.commit()
    return {"employee_id": body.employee_id, "pay_period_id": body.pay_period_id, "enabled": body.enabled}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest ../tests/test_springertillaeg.py -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/activities.py tests/test_springertillaeg.py
git commit -m "feat: endpoints til at sætte/hente springertillæg-flueben"
```

---

## Task 8: Frontend — flueben i aktivitetsoversigten

**Files:**
- Modify: `app/static/js/app.js` (`loadActivities()` linje 196-208, `renderActivitiesTable()` linje 314-343)
- Modify: `app/static/css/style.css` (efter `.emp-cell`, linje 295-302)

**Interfaces:**
- Consumes: `GET /api/activities/springer-flags?pay_period_id=`, `POST /api/activities/springer-flag` (Task 7).
- Produces: `state.springerFlags: {employee_id: true}`.

- [ ] **Step 1: Tilføj CSS**

I `app/static/css/style.css`, lige efter `.grid-table tbody td.emp-cell { ... }` (efter linje 302):

```css
.springer-flag-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 400;
  font-size: 11px;
  color: var(--text-light);
  margin-top: 2px;
  white-space: nowrap;
  cursor: pointer;
}
.springer-flag-label input[disabled] { cursor: not-allowed; }
```

- [ ] **Step 2: Hent flueben-status ved periode-load**

I `app/static/js/app.js`, i `loadActivities()` (linje 196-208), tilføj et tredje kald til det eksisterende `Promise.all([...])`:

```js
    const p = state.periodInfo.period;
    await Promise.all([
      GET(`/api/activities?period_start=${state.currentPeriodStart}`).then(a => { state.activities = a; }),
      loadHolidaysForPeriod(p.start_date, p.end_date),
      GET(`/api/activities/springer-flags?pay_period_id=${p.id}`).then(r => { state.springerFlags = r; }),
    ]);
    renderActivitiesTable();
```

- [ ] **Step 3: Vis flueben i `renderActivitiesTable()`**

I `app/static/js/app.js`, erstat linje 314-316:

```js
  for (const emp of emps) {
    const tr = document.createElement("tr");
    let cells = `<td class="emp-cell" title="${h(emp.name)}">${h(emp.name)}</td>`;
```

med:

```js
  const canToggleSpringer = state.currentUser?.permissions?.includes("toggle_springer");
  const periodLocked = p.status === "closed";

  for (const emp of emps) {
    const tr = document.createElement("tr");
    const springerChecked = state.springerFlags?.[emp.id] === true;
    const springerDisabledAttr = (!canToggleSpringer || periodLocked) ? "disabled" : "";
    let cells = `<td class="emp-cell" title="${h(emp.name)}">
      ${h(emp.name)}
      <label class="springer-flag-label">
        <input type="checkbox" class="springer-flag-checkbox" data-emp-id="${emp.id}"
          ${springerChecked ? "checked" : ""} ${springerDisabledAttr}> Springertillæg
      </label>
    </td>`;
```

- [ ] **Step 4: Event-listener for ændringer**

I `app/static/js/app.js`, tilføj lige efter de eksisterende `body.querySelectorAll(...)`-listeners i `renderActivitiesTable()` (efter linje 343, `});` der lukker cellen-klik-listeneren):

```js
  body.querySelectorAll(".springer-flag-checkbox").forEach(el => {
    el.addEventListener("change", async e => {
      e.stopPropagation();
      const checked = el.checked;
      try {
        await POST("/api/activities/springer-flag", {
          employee_id: parseInt(el.dataset.empId),
          pay_period_id: p.id,
          enabled: checked,
        });
      } catch (err) {
        el.checked = !checked;
        toast(err.message, "error");
      }
    });
    el.addEventListener("click", e => e.stopPropagation());
  });
```

- [ ] **Step 5: Manuel verifikation i browser**

Start dev-serveren:
```bash
cd app && python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Åbn `http://localhost:8000`, log ind, gå til "Aktiviteter":
1. Bekræft at hver medarbejderrække nu har et "Springertillæg"-flueben under navnet.
2. Sæt fluebenet for én medarbejder → genindlæs siden → fluebenet er stadig sat (persisteret).
3. Skift til næste periode (pil frem) → fluebenet er IKKE sat for den nye periode → skift tilbage → stadig sat i den oprindelige periode.
4. Lås perioden (kør løn eller sæt status manuelt til closed i DB) → genindlæs → fluebenet er nu disabled og kan ikke klikkes.
5. Åbn devtools-konsollen, tjek at der ingen JS-fejl er ved klik/genindlæsning.

- [ ] **Step 6: Commit**

```bash
git add app/static/js/app.js app/static/css/style.css
git commit -m "feat: flueben til springertillæg i aktivitetsoversigten"
```

---

## Task 9: Dokumentation — CODEREF.md

**Files:**
- Modify: `CODEREF.md`

**Interfaces:**
- Ingen kode — kun dokumentation.

- [ ] **Step 1: Tilføj række til Danløn CSV-tabellen**

I `CODEREF.md`, i tabellen under "## Danløn CSV-struktur" (linje 417-431), tilføj en ny række lige efter `| NORMAL | 1 | timer | |`:

```
| SPRINGERTILLAEG | 1 | timer | kun med hvis flueben sat for medarbejder+periode, se afsnit nedenfor |
```

- [ ] **Step 2: Tilføj nyt afsnit**

I `CODEREF.md`, tilføj nyt afsnit lige efter afsnittet "## Medarbejdertillæg" (efter linje 516, før `---` på linje 517):

```markdown
## Springertillæg (2026-08-14, activities.py + payroll_router.py + session.py)

Ny løntypekode `SPRINGERTILLAEG` (kr/time-sats fra `MasterSupplementRate`, label "Springertillæg") der giver samme timetal som løntypekode 1 (`calc["normal_hours"]`) — men KUN for de medarbejdere, der i den enkelte lønperiode har et flueben sat i aktivitetsoversigten (under navnet, samme række). Mønsteret følger Overnatning: hardcodet i `_resolve_rate()`/`_calculate_employee()`/CSV-raw_rows, ikke den generiske `_user_pay_type_rows()`-mekanisme (springertillæg er ikke knyttet til en `Activity`).

**Datamodel:** ny tabel `employee_springer_flags` (`employee_id`, `pay_period_id`, `enabled`), unikt indeks på `(employee_id, pay_period_id)`. Ingen række = ikke sat — nulstilles derfor automatisk hver ny periode uden seeding.

**Periodeopslag i `_calculate_employee()`:** perioden slås op internt via `get_or_create_period_for_date(start, db)` i stedet for at tilføje en `period_id`-parameter — funktionen har 8 kaldssteder, nogle med frie datointervaller (tidssedler/preview) uden noget naturligt periode-begreb.

**Endpoints** (`activities.py`): `GET /api/activities/springer-flags?pay_period_id=` (login, ingen særskilt permission — samme niveau som resten af aktivitetsoversigten), `POST /api/activities/springer-flag` (kræver `toggle_springer`, upsert, afvises med 400 hvis perioden er `closed`).

**Permission `toggle_springer`:** gives til ALLE roller (system og ikke-system) ved migrering, jf. beslutning om at åbne den for alle roller for nu.
```

- [ ] **Step 3: Commit**

```bash
git add CODEREF.md
git commit -m "docs: dokumentér springertillæg i CODEREF.md"
```

---

## Selv-review — dækning af spec

- Ny tabel med periode-scope → Task 1. ✓
- Egen løntypekode + sats (som overtid) → Task 3. ✓
- Sats-opslag + `_resolve_rate` → Task 4. ✓
- Timetal = løntypekode 1, kun ved flueben+aktivt → Task 5+6. ✓
- 0-timer udelades → dækket af eksisterende `qty == 0`-filter i CSV-løkken (Task 6, ingen ekstra kode nødvendig). ✓
- Flueben under navn, samme række, alle medarbejdere → Task 8. ✓
- Permission `toggle_springer`, alle roller → Task 2. ✓
- Låsning ved lukket periode (UI + backend) → Task 7 (backend 400) + Task 8 (disabled attribut). ✓
- CODEREF.md → Task 9. ✓
