# "Øvrig overtid for alle timer" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give individual medarbejdere en togglebar særaftale, hvor alle deres arbejdstimer udløser normal løn (kode 1) OG Øvrig overtid (kode 9) — aldrig Overtid 1-3 timer (kode 8), uanset dagtype, tidspunkt eller det sædvanlige daglige loft.

**Architecture:** Nyt boolean-felt `Employee.ot_extra_alle_timer` (samme mønster som `afloeser`/`fast_bil`). En ny, lille post-processing-funktion `override_ot_extra_alle_timer()` i `calculators/overtime.py` omskriver et allerede-beregnet `OvertimeResult` (fra enten `calculate_flat_hours()` eller `calculate_special_day_overtime()`), og kaldes fra `_calculate_employee()` i `payroll_router.py` når flaget er sat på medarbejderen. Kode 4/63 (SH-garantibetaling, `compute_sh_hours()`) er allerede ubetinget beregnet tidligere i samme funktion og påvirkes slet ikke.

**Tech Stack:** Python (FastAPI, SQLAlchemy), SQLite, pytest. Vanilla JS/HTML frontend (ingen build-step).

**Spec:** `docs/superpowers/specs/2026-09-10-ot-extra-alle-timer-design.md`

## Global Constraints

- Særaftalen erstatter de normale tids-tillæg (nat/aften/"1 time før", OT 1-3/kode 8) — lægges ikke oveni dem.
- Intet loft: fuld normalløn (kode 1) for alle arbejdstimer, uanset det sædvanlige daglige loft.
- Gælder alle dagtyper (hverdag, lørdag, søndag, alle helligdagstyper inkl. 1. maj og Grundlovsdag).
- Kode 8 (Overtid 1-3 timer) gives ALDRIG til en medarbejder med flaget sat.
- Kode 4/63 (SH-garantibetaling, `compute_sh_hours()`) beregnes helt uændret og må ikke påvirkes.
- Ingen ny løntypekode, ingen ny permission, ingen hardcoding af medarbejder-id — rent generisk per-medarbejder-flag.
- Alle nye Python-filer/kodeændringer skal følge eksisterende mønstre i `app/database/models.py`, `app/database/schemas.py`, `app/database/session.py`, `app/routers/employees.py`, `app/routers/payroll_router.py`, `app/calculators/overtime.py`.

---

### Task 1: Datamodel — `Employee.ot_extra_alle_timer`-felt + migration

**Files:**
- Modify: `app/database/models.py:89` (Employee-klassen)
- Modify: `app/database/session.py:247-253` (`_migrate()`, employees-tabel-migrationer)
- Test: `tests/test_ot_extra_alle_timer_model.py`

**Interfaces:**
- Produces: `Employee.ot_extra_alle_timer: bool` (default `False`) — bruges af Task 2 (schemas/response) og Task 4 (payroll-beregning).

- [ ] **Step 1: Write the failing test**

Opret `tests/test_ot_extra_alle_timer_model.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


def test_employee_ot_extra_alle_timer_defaults_to_false(db, employee):
    assert employee.ot_extra_alle_timer is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ot_extra_alle_timer_model.py -v`
Expected: FAIL med `AttributeError: 'Employee' object has no attribute 'ot_extra_alle_timer'`

- [ ] **Step 3: Tilføj kolonnen til `Employee`-modellen**

I `app/database/models.py`, linje 89 (lige efter `afloeser`-linjen), tilføj:
```python
    afloeser = Column(Boolean, default=False, nullable=False)
    ot_extra_alle_timer = Column(Boolean, default=False, nullable=False)
```
(kun linjen `ot_extra_alle_timer = Column(...)` er ny — `afloeser`-linjen vises for kontekst).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ot_extra_alle_timer_model.py -v`
Expected: PASS

- [ ] **Step 5: Tilføj idempotent migration**

I `app/database/session.py`, i `_migrate()`-funktionen, lige efter den eksisterende blok (linje 251-253):
```python
        if "fast_bil_vehicle_id" not in emp_cols3:
            conn.execute("ALTER TABLE employees ADD COLUMN fast_bil_vehicle_id INTEGER")
            conn.commit()
```
tilføj:
```python
        if "ot_extra_alle_timer" not in emp_cols3:
            conn.execute("ALTER TABLE employees ADD COLUMN ot_extra_alle_timer BOOLEAN NOT NULL DEFAULT 0")
            conn.commit()
```
(Bemærk: denne ALTER TABLE-migration rammer kun en eksisterende produktions-SQLite-fil ved opstart — den er, ligesom `afloeser`/`fast_bil`s tilsvarende migrationer, ikke dækket af pytest, da test-fixturen `db` altid opretter det fulde, aktuelle skema direkte via `Base.metadata.create_all()`.)

- [ ] **Step 6: Commit**

```bash
git add app/database/models.py app/database/session.py tests/test_ot_extra_alle_timer_model.py
git commit -m "feat: tilføj Employee.ot_extra_alle_timer-felt"
```

---

### Task 2: Schemas + API-response for `ot_extra_alle_timer`

**Files:**
- Modify: `app/database/schemas.py:33-58` (`EmployeeCreate`), `:61-86` (`EmployeeUpdate`), `:89-123` (`EmployeeResponse`)
- Modify: `app/routers/employees.py:75-113` (`_to_response()`)
- Test: `tests/test_employee_ot_extra_alle_timer_endpoint.py`

**Interfaces:**
- Consumes: `Employee.ot_extra_alle_timer` (Task 1).
- Produces: `EmployeeCreate.ot_extra_alle_timer: bool`, `EmployeeUpdate.ot_extra_alle_timer: Optional[bool]`, `EmployeeResponse.ot_extra_alle_timer: bool` — bruges af frontend (Task 5) og af enhver kode der læser `EmployeeResponse`.

- [ ] **Step 1: Write the failing test**

Opret `tests/test_employee_ot_extra_alle_timer_endpoint.py` (mønster fra `tests/test_employee_fast_bil_endpoint.py`):
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

from database.models import AppUser
from database.schemas import EmployeeCreate, EmployeeUpdate, WorkSchedule


def _admin():
    return AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")


def _seed_agreement(db):
    from database.models import MasterAgreementType, MasterAgreementKind
    from decimal import Decimal
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.commit()


def _base_employee_body(**overrides):
    data = dict(
        employee_number="3001", first_name="Test", last_name="Saeraftale",
        agreement_kind="hourly_fixed", agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1), work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    return EmployeeCreate(**data)


def test_create_employee_with_ot_extra_alle_timer(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(_base_employee_body(ot_extra_alle_timer=True),
                            current_user=_admin(), db=db)
    assert resp.ot_extra_alle_timer is True


def test_employee_defaults_to_ot_extra_alle_timer_false(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(_base_employee_body(), current_user=_admin(), db=db)
    assert resp.ot_extra_alle_timer is False


def test_update_employee_ot_extra_alle_timer(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    resp = update_employee(employee.id, EmployeeUpdate(ot_extra_alle_timer=True),
                            current_user=_admin(), db=db)
    assert resp.ot_extra_alle_timer is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_employee_ot_extra_alle_timer_endpoint.py -v`
Expected: FAIL med pydantic `ValidationError` (ukendt felt `ot_extra_alle_timer` på `EmployeeCreate`).

- [ ] **Step 3: Tilføj feltet til de tre schemas**

I `app/database/schemas.py`:

`EmployeeCreate` (efter linje 57 `fast_bil: bool = False`):
```python
    afloeser: bool = False
    fast_bil: bool = False
    ot_extra_alle_timer: bool = False
    fast_bil_vehicle_id: Optional[int] = None
```

`EmployeeUpdate` (efter linje 85 `fast_bil: Optional[bool] = None`):
```python
    afloeser: Optional[bool] = None
    fast_bil: Optional[bool] = None
    ot_extra_alle_timer: Optional[bool] = None
    fast_bil_vehicle_id: Optional[int] = None
```

`EmployeeResponse` (efter linje 119 `fast_bil: bool`):
```python
    afloeser: bool
    fast_bil: bool
    ot_extra_alle_timer: bool
    fast_bil_vehicle_id: Optional[int] = None
```

- [ ] **Step 4: Tilføj feltet til `_to_response()`**

I `app/routers/employees.py`, i `_to_response()` (efter linje 109 `afloeser=emp.afloeser,`):
```python
        afloeser=emp.afloeser,
        ot_extra_alle_timer=emp.ot_extra_alle_timer,
        fast_bil=emp.fast_bil,
```

Bemærk: `create_employee`/`update_employee` kræver INGEN ændring — begge bruger allerede en generisk `body.model_dump(...)`-flow (linje 201 hhv. 343), som automatisk tager det nye felt med, præcis som `afloeser`/`fast_bil` allerede gør.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_employee_ot_extra_alle_timer_endpoint.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/database/schemas.py app/routers/employees.py tests/test_employee_ot_extra_alle_timer_endpoint.py
git commit -m "feat: eksponer ot_extra_alle_timer i medarbejder-API"
```

---

### Task 3: Beregningslogik — `override_ot_extra_alle_timer()`

**Files:**
- Modify: `app/calculators/overtime.py` (tilføj ny funktion efter `calculate_flat_hours()`, linje 249)
- Test: `tests/test_ot_extra_alle_timer_override.py`

**Interfaces:**
- Consumes: `OvertimeResult` (fra `calculate_flat_hours()` i `calculators/overtime.py` eller `calculate_special_day_overtime()` i `calculators/day_type.py`), `OT_EXTRA_KEY` (`calculators/overtime.py`).
- Produces: `override_ot_extra_alle_timer(result: OvertimeResult, is_special_day: bool, rates: dict) -> OvertimeResult` — bruges af Task 4 i `payroll_router.py`.

- [ ] **Step 1: Write the failing tests**

Opret `tests/test_ot_extra_alle_timer_override.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime
from decimal import Decimal

from calculators.overtime import (
    calculate_flat_hours, override_ot_extra_alle_timer, OT_EXTRA_KEY,
)
from calculators.day_type import calculate_special_day_overtime, DayType

_RATES = {OT_EXTRA_KEY: Decimal("50")}


def test_flat_hours_override_moves_everything_to_normal_plus_ot_extra():
    """Hverdag/lørdag: 10 timer (ville normalt give aften/nat-tillæg) -> alt bliver normal + kode 9."""
    result = calculate_flat_hours(
        datetime(2026, 9, 10, 6, 0), datetime(2026, 9, 10, 16, 0),  # 10 timer
    )
    overridden = override_ot_extra_alle_timer(result, is_special_day=False, rates=_RATES)

    assert overridden.total_hours == Decimal("10")
    assert overridden.normal_hours == Decimal("10")
    assert overridden.ot_before_hours == Decimal("0")
    assert overridden.ot_13_hours == Decimal("0")
    assert overridden.ot_extra_hours == Decimal("10")
    assert overridden.supplements[OT_EXTRA_KEY] == Decimal("500")  # 10 * 50


def test_special_day_override_forces_kode9_for_whole_day_never_kode8():
    """1. maj: vagt 08-16 (4t før, 4t efter kl. 12) -> uden override ville de 4
    eftermiddagstimer normalt give kode 8 (op til 3t) + kode 9 (resten).
    Med override: ALLE 8 timer -> kode 9, aldrig kode 8."""
    result = calculate_special_day_overtime(
        datetime(2026, 5, 1, 8, 0), datetime(2026, 5, 1, 16, 0),
        DayType.HOLIDAY_HALF_1MAJ,
    )
    # Uden override: kode8=3, kode9=1 (kontrollerer testens forudsætning)
    assert result.sh_kode8_hours == Decimal("3")
    assert result.sh_kode9_hours == Decimal("1")

    overridden = override_ot_extra_alle_timer(result, is_special_day=True, rates=_RATES)

    assert overridden.total_hours == Decimal("8")
    assert overridden.normal_hours == Decimal("8")
    assert overridden.sh_kode8_hours == Decimal("0")
    assert overridden.sh_kode9_hours == Decimal("8")
    assert overridden.ot_extra_hours == Decimal("0")  # denne sti bruger sh_kode9, ikke ot_extra
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ot_extra_alle_timer_override.py -v`
Expected: FAIL med `ImportError: cannot import name 'override_ot_extra_alle_timer'`

- [ ] **Step 3: Implementér funktionen**

I `app/calculators/overtime.py`, tilføj efter `calculate_flat_hours()` (efter linje 249):
```python


def override_ot_extra_alle_timer(
    result: OvertimeResult, is_special_day: bool, rates: dict,
) -> OvertimeResult:
    """
    Særaftale (Employee.ot_extra_alle_timer): normal løn for alle arbejdstimer
    OG Øvrig overtid (kode 9) for alle arbejdstimer - aldrig Overtid 1-3 timer
    (kode 8). Kode 4/63 (SH-garanti) beregnes i compute_sh_hours() og påvirkes
    ikke af denne funktion.

    is_special_day=False (hverdag/lørdag, `result` fra calculate_flat_hours()):
    ot_extra_hours sættes til alle timer.
    is_special_day=True (søndag/helligdag, `result` fra
    calculate_special_day_overtime()): sh_kode8_hours nulstilles og
    sh_kode9_hours sættes til alle timer - normal_hours er i forvejen altid
    alle kørte timer for særlige dage.
    """
    result.ot_before_hours = Decimal("0")
    result.ot_13_hours = Decimal("0")
    if is_special_day:
        result.sh_kode8_hours = Decimal("0")
        result.sh_kode9_hours = result.total_hours
    else:
        result.ot_extra_hours = result.total_hours
        result.supplements = {OT_EXTRA_KEY: result.ot_extra_hours * rates.get(OT_EXTRA_KEY, Decimal("0"))}
        for bucket in result.by_date.values():
            bucket["ot_extra"] = bucket["total_hours"]
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ot_extra_alle_timer_override.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/calculators/overtime.py tests/test_ot_extra_alle_timer_override.py
git commit -m "feat: tilføj override_ot_extra_alle_timer() beregningsfunktion"
```

---

### Task 4: Wire ind i `_calculate_employee()`

**Files:**
- Modify: `app/routers/payroll_router.py:27-34` (import), `:590-626` (aktivitets-beregningsgren)
- Test: `tests/test_ot_extra_alle_timer_payroll.py`

**Interfaces:**
- Consumes: `Employee.ot_extra_alle_timer` (Task 1), `override_ot_extra_alle_timer()` (Task 3), eksisterende `_calculate_employee(emp, start, end, db) -> dict` med nøglerne `normal_hours`, `ot_13_hours`, `ot_extra_hours`, `sh_kode8_hours`, `sh_kode9_hours`, `sh_fuldloennet_hours`, `sh_timeloennet_hours`, `total_hours` (uændrede nøglenavne).

- [ ] **Step 1: Write the failing tests**

Opret `tests/test_ot_extra_alle_timer_payroll.py` (mønster fra `tests/test_afloeser.py`):
```python
from datetime import datetime, date

from database.models import Employee, ActivitySource, ActivityStatus, Holiday
from routers.payroll_router import _calculate_employee
from conftest import make_activity

# 2026-09-13 er en søndag, 2026-09-12 en lørdag, 2026-09-11 en fredag (hverdag)
_SUNDAY = date(2026, 9, 13)
_SATURDAY = date(2026, 9, 12)
_WEEKDAY = date(2026, 9, 11)
_1MAJ = date(2026, 5, 1)          # fredag
_GRUNDLOVSDAG = date(2026, 6, 5)  # fredag

_SCHEDULE = {
    "even": [8, 8, 8, 8, 8, 0, 8],
    "odd":  [8, 8, 8, 8, 8, 0, 8],
}


def _make_employee(db, ot_extra_alle_timer: bool, employee_number: str = "9601"):
    emp = Employee(
        employee_number=employee_number,
        first_name="Test",
        last_name="Saeraftale",
        agreement_kind="hourly_fixed",
        agreement_type="",
        fuldloennet=True,
        ot_extra_alle_timer=ot_extra_alle_timer,
        hire_date=date(2020, 1, 1),
        work_schedule=_SCHEDULE,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def test_weekday_16_hour_shift_gives_full_normal_and_full_ot_extra(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    make_activity(
        db, emp,
        datetime(2026, 9, 11, 6, 0), datetime(2026, 9, 11, 22, 0),  # 16 timer
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _WEEKDAY, _WEEKDAY, db)
    assert result["normal_hours"] == 16.0
    assert result["ot_extra_hours"] == 16.0
    assert result["ot_13_hours"] == 0.0
    assert result["ot_before_hours"] == 0.0


def test_saturday_shift_gives_full_normal_and_full_ot_extra(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    make_activity(
        db, emp,
        datetime(2026, 9, 12, 6, 0), datetime(2026, 9, 12, 14, 0),  # 8 timer
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _SATURDAY, _SATURDAY, db)
    assert result["normal_hours"] == 8.0
    assert result["ot_extra_hours"] == 8.0
    assert result["ot_13_hours"] == 0.0


def test_sunday_still_gives_kode1_and_kode9_never_kode8(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    make_activity(
        db, emp,
        datetime(2026, 9, 13, 6, 0), datetime(2026, 9, 13, 14, 0),  # 8 timer
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _SUNDAY, _SUNDAY, db)
    assert result["normal_hours"] == 8.0
    assert result["sh_kode9_hours"] == 8.0
    assert result["sh_kode8_hours"] == 0.0


def test_1maj_kode9_covers_whole_day_never_kode8(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    db.add(Holiday(date=_1MAJ, name="1. maj", half_day_from="12:00"))
    db.commit()
    make_activity(
        db, emp,
        datetime(2026, 5, 1, 8, 0), datetime(2026, 5, 1, 16, 0),  # 4t før/4t efter kl. 12
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _1MAJ, _1MAJ, db)
    assert result["normal_hours"] == 8.0
    assert result["sh_kode9_hours"] == 8.0  # ikke kun de 4 eftermiddagstimer
    assert result["sh_kode8_hours"] == 0.0  # aldrig kode 8, heller ikke for 1. maj


def test_grundlovsdag_kode9_covers_whole_day(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    db.add(Holiday(date=_GRUNDLOVSDAG, name="Grundlovsdag", half_day_from="12:00"))
    db.commit()
    make_activity(
        db, emp,
        datetime(2026, 6, 5, 8, 0), datetime(2026, 6, 5, 16, 0),
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _GRUNDLOVSDAG, _GRUNDLOVSDAG, db)
    assert result["normal_hours"] == 8.0
    assert result["sh_kode9_hours"] == 8.0
    assert result["sh_kode8_hours"] == 0.0


def test_kode4_63_guarantee_unaffected_by_flag(db):
    """Kode 4/63 (SH-garanti) skal give samme resultat med og uden flaget."""
    emp_on = _make_employee(db, ot_extra_alle_timer=True, employee_number="9602")
    emp_off = _make_employee(db, ot_extra_alle_timer=False, employee_number="9603")
    result_on = _calculate_employee(emp_on, _SUNDAY, _SUNDAY, db)
    result_off = _calculate_employee(emp_off, _SUNDAY, _SUNDAY, db)
    assert result_on["sh_fuldloennet_hours"] == result_off["sh_fuldloennet_hours"]
    assert result_on["sh_timeloennet_hours"] == result_off["sh_timeloennet_hours"]


def test_flag_off_is_unaffected_regression(db):
    emp = _make_employee(db, ot_extra_alle_timer=False)
    make_activity(
        db, emp,
        datetime(2026, 9, 11, 6, 0), datetime(2026, 9, 11, 22, 0),  # 16 timer
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _WEEKDAY, _WEEKDAY, db)
    # normal_hours er (uændret, som hele tiden) alle arbejdede timer (additiv
    # model, jf. calculate_overtime()) - det er IKKE dette der adskiller
    # særaftalen. Forskellen er ot_13/ot_extra-fordelingen: en almindelig
    # medarbejder med 8t loft (fredag) får her kode 8 (3t, loftet for
    # "1-3 timer") + kode 9 (5t, resten) - IKKE kode 9 for alle 16 timer og
    # ALDRIG kode 8, som en medarbejder med flaget ville få (se
    # test_weekday_16_hour_shift_gives_full_normal_and_full_ot_extra ovenfor).
    assert result["normal_hours"] == 16.0
    assert result["ot_13_hours"] == 3.0
    assert result["ot_extra_hours"] == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ot_extra_alle_timer_payroll.py -v`
Expected: FAIL (fx `test_weekday_16_hour_shift_gives_full_normal_and_full_ot_extra` fejler med `ot_extra_hours == 0.0`, da flaget endnu ikke læses nogen steder).

- [ ] **Step 3: Import den nye funktion**

I `app/routers/payroll_router.py`, linje 27-34, udvid import:
```python
from calculators.overtime import (
    OT_13_KEY,
    OT_13_MAX,
    OT_BEFORE_KEY,
    OT_EXTRA_KEY,
    calculate_overtime,
    calculate_flat_hours,
    override_ot_extra_alle_timer,
)
```

- [ ] **Step 4: Tilføj den nye gren i aktivitets-løkken**

I `app/routers/payroll_router.py`, linje 590-625, den eksisterende:
```python
                    if not is_recognized_agreement_kind:
                        # Aftale-type uden for de to kendte nøgler – ingen
                        # automatisk OT-beregning endnu (se
                        # docs/superpowers/specs/2026-08-24-aftale-stamdata-design.md).
                        ot = calculate_flat_hours(act.start_time, act.end_time, pauses)
                    elif day_type in (DayType.NORMAL, DayType.SATURDAY):
```
erstattes af:
```python
                    if emp.ot_extra_alle_timer and (
                        day_type in (DayType.NORMAL, DayType.SATURDAY)
                        or not is_recognized_agreement_kind
                    ):
                        # Særaftale (docs/superpowers/specs/2026-09-10-ot-extra-alle-timer-design.md):
                        # normal løn + Øvrig overtid for ALLE timer, intet loft,
                        # ingen tids-tillæg.
                        ot = calculate_flat_hours(act.start_time, act.end_time, pauses)
                        ot = override_ot_extra_alle_timer(ot, is_special_day=False, rates=ot_rates)
                    elif not is_recognized_agreement_kind:
                        # Aftale-type uden for de to kendte nøgler – ingen
                        # automatisk OT-beregning endnu (se
                        # docs/superpowers/specs/2026-08-24-aftale-stamdata-design.md).
                        ot = calculate_flat_hours(act.start_time, act.end_time, pauses)
                    elif day_type in (DayType.NORMAL, DayType.SATURDAY):
```

Og den eksisterende (linje 620-625):
```python
                    else:
                        ot = calculate_special_day_overtime(
                            act.start_time, act.end_time,
                            day_type, pauses,
                            kode8_remaining=day_ot13_remaining,
                        )
                        day_ot13_remaining = ot.ot13_remaining_after
```
erstattes af:
```python
                    elif emp.ot_extra_alle_timer:
                        # Særaftale på søndag/helligdag: kode 1 er i forvejen
                        # altid alle kørte timer, kode 9 udvides til at dække
                        # hele dagen (ikke kun eftermiddagen/1-3-timers-loftet),
                        # kode 8 gives aldrig.
                        ot = calculate_special_day_overtime(
                            act.start_time, act.end_time,
                            day_type, pauses,
                            kode8_remaining=day_ot13_remaining,
                        )
                        ot = override_ot_extra_alle_timer(ot, is_special_day=True, rates=ot_rates)
                        day_ot13_remaining = ot.ot13_remaining_after
                    else:
                        ot = calculate_special_day_overtime(
                            act.start_time, act.end_time,
                            day_type, pauses,
                            kode8_remaining=day_ot13_remaining,
                        )
                        day_ot13_remaining = ot.ot13_remaining_after
```

(Den øverste `if emp.ot_extra_alle_timer and (...)`-gren fanger hverdag/lørdag/ikke-genkendt agreement_kind; den nye `elif emp.ot_extra_alle_timer:`-gren fanger søndag/enhver helligdagstype for samme medarbejder. `sh_h`/kode 4-63 på linje 454 ligger uden for denne gren og forbliver fuldstændig uændret.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_ot_extra_alle_timer_payroll.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run hele test-suiten for regression**

Run: `pytest -v`
Expected: PASS — ingen eksisterende test (`test_afloeser.py`, `test_overtime_calculation.py`, `test_payroll_settlement.py` m.fl.) må ændre resultat, da `emp.ot_extra_alle_timer` er `False` som default overalt andetsteds.

- [ ] **Step 7: Commit**

```bash
git add app/routers/payroll_router.py tests/test_ot_extra_alle_timer_payroll.py
git commit -m "feat: anvend ot_extra_alle_timer-særaftale i lønberegningen"
```

---

### Task 5: Frontend — checkbox i medarbejder-modalen

**Files:**
- Modify: `app/templates/index.html:1540` (medarbejder-modal, ny form-row efter den eksisterende 5-checkbox-række)
- Modify: `app/static/js/app.js:3230-3234` (`openNewEmployeeModal`), `:3271-3275` (`openEditEmployee`), `:3319-3322` (`confirmEmployee`)

**Interfaces:**
- Consumes: `EmployeeResponse.ot_extra_alle_timer` (Task 2), body-feltet `ot_extra_alle_timer` på `POST/PUT /api/employees` (Task 2).

- [ ] **Step 1: Tilføj checkbox i `index.html`**

I `app/templates/index.html`, lige efter den eksisterende 5-kolonne-række (efter linje 1540, `</div>` der lukker `form-row style="grid-template-columns:1fr 1fr 1fr 1fr"`), tilføj en ny række:
```html
      <div class="form-row">
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-ot-extra-alle-timer"> Særaftale: Øvrig overtid for alle timer
          </label>
        </div>
      </div>
```

- [ ] **Step 2: Nulstil feltet i `openNewEmployeeModal()`**

I `app/static/js/app.js`, linje 3230-3234, efter:
```javascript
  document.getElementById("emp-afloeser").checked = false;
```
tilføj:
```javascript
  document.getElementById("emp-afloeser").checked = false;
  document.getElementById("emp-ot-extra-alle-timer").checked = false;
```

- [ ] **Step 3: Udfyld feltet i `openEditEmployee()`**

I `app/static/js/app.js`, linje 3271-3275, efter:
```javascript
  document.getElementById("emp-afloeser").checked = e.afloeser;
```
tilføj:
```javascript
  document.getElementById("emp-afloeser").checked = e.afloeser;
  document.getElementById("emp-ot-extra-alle-timer").checked = e.ot_extra_alle_timer;
```

- [ ] **Step 4: Tilføj feltet til payload i `confirmEmployee()`**

I `app/static/js/app.js`, linje 3319-3322, efter:
```javascript
    afloeser: document.getElementById("emp-afloeser").checked,
```
tilføj:
```javascript
    afloeser: document.getElementById("emp-afloeser").checked,
    ot_extra_alle_timer: document.getElementById("emp-ot-extra-alle-timer").checked,
```

- [ ] **Step 5: Manuel verifikation i browser**

Start dev-serveren (jf. `.claude/launch.json`/eksisterende run-kommando), naviger til Medarbejdere-fanen:
1. Åbn "Ny medarbejder" → tjek at checkboxen "Særaftale: Øvrig overtid for alle timer" er synlig og ikke afkrydset som default.
2. Opret en medarbejder med feltet afkrydset → gem → genåbn redigér-modalen → tjek at feltet stadig er afkrydset.
3. Fjern afkrydsningen → gem → genåbn → tjek at feltet nu er af.
4. Åbn browser-devtools netværksfane og bekræft at `POST`/`PUT` til `/api/employees` indeholder `"ot_extra_alle_timer": true/false` korrekt.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: checkbox til ot_extra_alle_timer-særaftale i medarbejder-modalen"
```

---

## Efter implementering

Kør hele test-suiten en sidste gang (`pytest -v`) og bekræft ingen regressioner, før branchen afsluttes (se `superpowers:finishing-a-development-branch`).
