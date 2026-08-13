# Medarbejdertillæg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lade lønbogholderi tildele et fast kr/time-tillæg pr. medarbejder, historisk sporet, som automatisk lægges til grundsatsen i lønberegningen (kode 1/normaltid, afspadsering, SH-betaling m.fl.) i både beregning og CSV-eksport.

**Architecture:** Ny tabel `employee_supplements` med gyldighedsperioder (start/slut-dato, standard åbentstående til 9999-12-31). Status (Aktiv/Inaktiv) beregnes ved visning ud fra dags dato — intet lagret statusfelt. Ved lønberegning slås det tillæg op, hvis gyldighedsperiode overlapper den beregnede periode (nyeste vinder ved flere overlap), og lægges til `hourly_rate`-variablen i `_calculate_employee()`, hvorved det automatisk slår igennem alle steder den variabel allerede bruges. Frontend: nyt sidebar-punkt "Tillæg" med søgefelt, historik-tabel og opret-modal, samt en read-only boks i medarbejder-modalen.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), Pydantic, vanilla JS (ingen frontend-testframework i dette repo — frontend-opgaver verificeres manuelt via curl/browser i stedet for automatiserede tests, jf. eksisterende kodebase-praksis).

## Global Constraints

- Værdien (`value`) skal være > 0 — kun positive tillæg, aldrig fradrag.
- `name` er altid `"Ikke overenskomstmæssigt tillæg"` og `type` er altid `"Timebaseret"` — hardcoded server-side, ikke redigerbare noget sted i UI.
- Ingen redigering eller sletning af eksisterende rækker — kun oprettelse af nye (som lukker den forrige åbentstående række).
- Status er ikke lagret — beregnes ved visning: Aktiv (grøn tekst) hvis dags dato ligger i `[start_date, end_date]`, ellers Inaktiv (rød tekst, `var(--danger)`).
- Lønberegning: én sats for hele den beregnede periode. Overlapper flere tillæg perioden (nyt tillæg oprettet midt i perioden), bruges rækken med nyeste `start_date` for hele perioden.
- Nyt sidebar-punkt "Tillæg" er sit eget topniveau-punkt (ikke en underfane i Vognpark-viewet).
- Én permission, `manage_employee_supplements`, gater alle tre endpoints, sidebar-synlighed og "Tilføj"-knappen.
- Spec: `docs/superpowers/specs/2026-08-13-medarbejder-tillaeg-design.md`

---

## Task 1: Datamodel, schema og permission-plumbing

**Files:**
- Modify: `app/database/models.py` (tilføj `EmployeeSupplement`-klasse efter `EmployeeBaseline`, ca. linje 354)
- Modify: `app/database/schemas.py` (tilføj `EmployeeSupplementCreate`, `EmployeeSupplementResponse` efter `VehicleResponse`)
- Modify: `app/auth.py` (tilføj `"manage_employee_supplements"` til `ALL_PERMISSIONS`, linje 9-24)
- Modify: `app/database/session.py` (tilføj `_ensure_employee_supplements_permission()`, kald den i `init_db()`)
- Test: `tests/test_employee_supplements.py` (ny fil)

**Interfaces:**
- Produces: `EmployeeSupplement` ORM-model (felter: `id`, `employee_id`, `name`, `type`, `value: Decimal`, `start_date: date`, `end_date: date`, `created_at`, relationship `employee`)
- Produces: `EmployeeSupplementCreate(employee_id: int, start_date: date, value: float)` — Pydantic, `value` valideret `> 0`
- Produces: `EmployeeSupplementResponse(id, employee_id, employee_number: str, employee_name: str, name: str, type: str, value: float, start_date: date, end_date: date, is_active: bool)`

- [ ] **Step 1: Skriv fejlende test for modellens standardværdier**

```python
# tests/test_employee_supplements.py
from datetime import date
from decimal import Decimal

import pytest

from database.models import EmployeeSupplement


def test_supplement_defaults_to_open_ended_with_hardcoded_name_and_type(db, employee):
    row = EmployeeSupplement(employee_id=employee.id, value=Decimal("10.00"), start_date=date(2026, 1, 1))
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.end_date == date(9999, 12, 31)
    assert row.name == "Ikke overenskomstmæssigt tillæg"
    assert row.type == "Timebaseret"
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `pytest tests/test_employee_supplements.py -v`
Expected: FAIL med `ImportError: cannot import name 'EmployeeSupplement'`

- [ ] **Step 3: Tilføj `EmployeeSupplement`-modellen**

I `app/database/models.py`, indsæt efter `EmployeeBaseline`-klassen (efter linje 354, `employee = relationship("Employee", back_populates="baselines")`):

```python
class EmployeeSupplement(Base):
    __tablename__ = "employee_supplements"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    name = Column(String(200), nullable=False, default="Ikke overenskomstmæssigt tillæg")
    type = Column(String(50), nullable=False, default="Timebaseret")
    value = Column(Numeric(10, 2), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False, default=date(9999, 12, 31))
    created_at = Column(DateTime, server_default=func.now())

    employee = relationship("Employee")
```

(`date`, `Column`, `Integer`, `String`, `Numeric`, `ForeignKey`, `DateTime`, `func`, `relationship` er allerede importeret i toppen af filen.)

- [ ] **Step 4: Kør testen og bekræft at den nu passerer**

Run: `pytest tests/test_employee_supplements.py -v`
Expected: PASS

- [ ] **Step 5: Tilføj Pydantic-schemas**

I `app/database/schemas.py`, indsæt efter `VehicleResponse`-klassen (sidst i filen):

```python
class EmployeeSupplementCreate(BaseModel):
    employee_id: int
    start_date: date = Field(default_factory=date.today)
    value: Annotated[float, Field(gt=0)]


class EmployeeSupplementResponse(BaseModel):
    id: int
    employee_id: int
    employee_number: str
    employee_name: str
    name: str
    type: str
    value: float
    start_date: date
    end_date: date
    is_active: bool

    model_config = {"from_attributes": True}
```

- [ ] **Step 6: Skriv test der bekræfter validering af `value`**

Tilføj til `tests/test_employee_supplements.py`:

```python
from database.schemas import EmployeeSupplementCreate


def test_schema_rejects_non_positive_value():
    with pytest.raises(Exception):
        EmployeeSupplementCreate(employee_id=1, start_date=date(2026, 1, 1), value=0)


def test_schema_accepts_positive_value():
    body = EmployeeSupplementCreate(employee_id=1, start_date=date(2026, 1, 1), value=12.5)
    assert body.value == 12.5
```

- [ ] **Step 7: Kør testene og bekræft at de passerer**

Run: `pytest tests/test_employee_supplements.py -v`
Expected: PASS (4 tests)

- [ ] **Step 8: Tilføj permission-nøglen**

I `app/auth.py`, tilføj til `ALL_PERMISSIONS`-dict (linje 9-24), som ny linje efter `"manage_vehicles": "Tilføj vogn",`:

```python
    "manage_employee_supplements": "Administrér medarbejdertillæg",
```

- [ ] **Step 9: Tilføj idempotent ensure-funktion i `session.py`**

I `app/database/session.py`, tilføj efter `_ensure_activity_permissions()` (efter linje 477):

```python
def _ensure_employee_supplements_permission():
    """Tilføjer manage_employee_supplements til lonbogholder-rollen (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "lonbogholder").first()
        if role and not role.is_system:
            perms = list(role.permissions or [])
            if "manage_employee_supplements" not in perms:
                perms.append("manage_employee_supplements")
                role.permissions = perms
                db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af manage_employee_supplements-tilladelse: {e}")
    finally:
        db.close()
```

Tilføj kaldet i `init_db()` (linje 41-54), som ny linje efter `_ensure_activity_permissions()`:

```python
    _ensure_employee_supplements_permission()
```

- [ ] **Step 10: Verificér manuelt at ny database får tabellen og permission**

Run: `cd app && python -c "from database.session import init_db; init_db(); from database.session import SessionLocal; from database.models import Role; db = SessionLocal(); print(db.query(Role).filter(Role.name=='lonbogholder').first().permissions); db.close()"`
Expected: output-listen indeholder `"manage_employee_supplements"`

- [ ] **Step 11: Commit**

```bash
git add app/database/models.py app/database/schemas.py app/auth.py app/database/session.py tests/test_employee_supplements.py
git commit -m "feat: datamodel og permission for medarbejdertillæg"
```

---

## Task 2: Satsopslag, livscyklus-logik og API-endpoints

**Files:**
- Create: `app/routers/employee_supplements.py`
- Modify: `app/main.py` (registrér router, linje 15 og 98)
- Test: `tests/test_employee_supplements.py` (udvid)

**Interfaces:**
- Consumes: `EmployeeSupplement` model, `EmployeeSupplementCreate`/`EmployeeSupplementResponse` schemas (Task 1)
- Produces: `get_active_supplement_for_period(db: Session, employee_id: int, period_start: date, period_end: date) -> Optional[EmployeeSupplement]` — bruges af Task 3 (payroll_router.py)
- Produces: `_create_supplement(db: Session, employee_id: int, start_date: date, value: Decimal) -> EmployeeSupplement` — kaster `HTTPException` ved ugyldig værdi/dato/medarbejder
- Produces: `router` (FastAPI `APIRouter`, prefix `/api/employee-supplements`) med `GET ""`, `GET "/active/{employee_id}"`, `POST ""`

- [ ] **Step 1: Skriv fejlende test for overlap-opslaget (intet tillæg)**

Tilføj til `tests/test_employee_supplements.py`:

```python
from routers.employee_supplements import get_active_supplement_for_period, _create_supplement


def test_no_overlap_returns_none(db, employee):
    result = get_active_supplement_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert result is None
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `pytest tests/test_employee_supplements.py::test_no_overlap_returns_none -v`
Expected: FAIL med `ModuleNotFoundError: No module named 'routers.employee_supplements'`

- [ ] **Step 3: Opret routerfilen med satsopslag og livscyklus-funktion**

Create `app/routers/employee_supplements.py`:

```python
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import log_action, require_permission
from database.models import AppUser, Employee, EmployeeSupplement
from database.schemas import EmployeeSupplementCreate, EmployeeSupplementResponse
from database.session import get_db

router = APIRouter(prefix="/api/employee-supplements", tags=["employee-supplements"])

_supplements_access = require_permission("manage_employee_supplements")

_OPEN_ENDED = date(9999, 12, 31)


def get_active_supplement_for_period(
    db: Session, employee_id: int, period_start: date, period_end: date
) -> Optional[EmployeeSupplement]:
    """Finder tillægget hvis gyldighedsperiode overlapper [period_start, period_end].
    Overlapper flere rækker (nyt tillæg oprettet midt i perioden), vinder den
    med nyeste start_date, for hele perioden."""
    return (
        db.query(EmployeeSupplement)
        .filter(
            EmployeeSupplement.employee_id == employee_id,
            EmployeeSupplement.end_date >= period_start,
            EmployeeSupplement.start_date <= period_end,
        )
        .order_by(EmployeeSupplement.start_date.desc())
        .first()
    )


def _create_supplement(db: Session, employee_id: int, start_date: date, value: Decimal) -> EmployeeSupplement:
    if value <= 0:
        raise HTTPException(400, "Værdien skal være et positivt beløb")
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    open_row = (
        db.query(EmployeeSupplement)
        .filter(EmployeeSupplement.employee_id == employee_id, EmployeeSupplement.end_date == _OPEN_ENDED)
        .first()
    )
    if open_row and start_date <= open_row.start_date:
        raise HTTPException(400, f"Startdato skal være efter {open_row.start_date.isoformat()}")
    if open_row:
        open_row.end_date = start_date - timedelta(days=1)
    new_row = EmployeeSupplement(employee_id=employee_id, start_date=start_date, value=value)
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


def _to_response(row: EmployeeSupplement) -> EmployeeSupplementResponse:
    today = date.today()
    return EmployeeSupplementResponse(
        id=row.id,
        employee_id=row.employee_id,
        employee_number=row.employee.employee_number,
        employee_name=row.employee.name,
        name=row.name,
        type=row.type,
        value=float(row.value),
        start_date=row.start_date,
        end_date=row.end_date,
        is_active=row.start_date <= today <= row.end_date,
    )


@router.get("", response_model=list[EmployeeSupplementResponse])
def list_supplements(
    employee_id: Optional[int] = None,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    q = db.query(EmployeeSupplement)
    if employee_id is not None:
        q = q.filter(EmployeeSupplement.employee_id == employee_id)
    if date_from is not None:
        q = q.filter(EmployeeSupplement.end_date >= date_from)
    if date_to is not None:
        q = q.filter(EmployeeSupplement.start_date <= date_to)
    rows = q.order_by(EmployeeSupplement.start_date.desc()).all()
    return [_to_response(r) for r in rows]


@router.get("/active/{employee_id}", response_model=Optional[EmployeeSupplementResponse])
def get_active_supplement(
    employee_id: int,
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    today = date.today()
    row = get_active_supplement_for_period(db, employee_id, today, today)
    return _to_response(row) if row else None


@router.post("", response_model=EmployeeSupplementResponse, status_code=201)
def create_supplement(
    body: EmployeeSupplementCreate,
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    row = _create_supplement(db, body.employee_id, body.start_date, Decimal(str(body.value)))
    log_action(db, current_user, "Oprettede medarbejdertillæg", "employee_supplement", row.id,
               f"{row.value} kr/t fra {row.start_date.isoformat()}")
    db.commit()
    return _to_response(row)
```

- [ ] **Step 4: Kør testen og bekræft at den passerer**

Run: `pytest tests/test_employee_supplements.py::test_no_overlap_returns_none -v`
Expected: PASS

- [ ] **Step 5: Skriv tests for overlap-opslag med data**

Tilføj til `tests/test_employee_supplements.py`:

```python
def test_single_overlap_found(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("15.00"))
    result = get_active_supplement_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert result is not None
    assert result.value == Decimal("15.00")


def test_newest_wins_when_created_mid_period(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2026, 1, 15), Decimal("20.00"))
    result = get_active_supplement_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert result.value == Decimal("20.00")


def test_historical_period_still_finds_old_supplement_after_new_one_added(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2026, 2, 1), Decimal("20.00"))
    result = get_active_supplement_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert result.value == Decimal("10.00")
```

- [ ] **Step 6: Kør testene og bekræft at de passerer**

Run: `pytest tests/test_employee_supplements.py -k overlap -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Skriv tests for livscyklus-reglerne**

Tilføj til `tests/test_employee_supplements.py`:

```python
from fastapi import HTTPException


def test_create_closes_previous_open_row(db, employee):
    first = _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2026, 2, 1), Decimal("20.00"))
    db.refresh(first)
    assert first.end_date == date(2026, 1, 31)


def test_create_rejects_non_positive_value(db, employee):
    with pytest.raises(HTTPException):
        _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("0"))


def test_create_rejects_start_date_not_after_open_row(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 15), Decimal("10.00"))
    with pytest.raises(HTTPException):
        _create_supplement(db, employee.id, date(2026, 1, 10), Decimal("20.00"))


def test_create_rejects_unknown_employee(db):
    with pytest.raises(HTTPException):
        _create_supplement(db, 999999, date(2026, 1, 1), Decimal("10.00"))
```

- [ ] **Step 8: Kør testene og bekræft at de passerer**

Run: `pytest tests/test_employee_supplements.py -k create -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Registrér routeren i `main.py`**

I `app/main.py`, ret importlinjen (linje 15):

```python
from routers import import_ddd, employees, activities, payroll_router, vehicles, employee_supplements
```

Tilføj efter `app.include_router(vehicles.router)` (linje 98):

```python
app.include_router(employee_supplements.router)
```

- [ ] **Step 10: Kør hele testsuiten og bekræft ingen regressioner**

Run: `pytest tests/ -v`
Expected: PASS (alle eksisterende + nye tests)

- [ ] **Step 11: Commit**

```bash
git add app/routers/employee_supplements.py app/main.py tests/test_employee_supplements.py
git commit -m "feat: API og livscyklus-logik for medarbejdertillæg"
```

---

## Task 3: Lønberegnings-integration (kode 1 og afspadsering)

**Files:**
- Modify: `app/routers/payroll_router.py` (linje 269-272)
- Test: `tests/test_employee_supplements.py` (udvid)

**Interfaces:**
- Consumes: `get_active_supplement_for_period` (Task 2)
- Produces: intet nyt — `_calculate_employee()`'s returnerede `calc["hourly_rate"]` er nu forhøjet med et evt. aktivt tillæg

- [ ] **Step 1: Skriv fejlende test for at hourly_rate stiger med tillægget**

Tilføj til `tests/test_employee_supplements.py`:

```python
from database.models import MasterAgreementType, MasterOvertimeRate
from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
from routers.payroll_router import _calculate_employee


def test_calculate_employee_includes_supplement_in_hourly_rate(db, employee):
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("12.50"))

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["hourly_rate"] == pytest.approx(162.50)


def test_calculate_employee_unaffected_when_no_supplement(db, employee):
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["hourly_rate"] == pytest.approx(150.00)
```

- [ ] **Step 2: Kør testene og bekræft at den første fejler**

Run: `pytest tests/test_employee_supplements.py::test_calculate_employee_includes_supplement_in_hourly_rate -v`
Expected: FAIL — `assert 150.0 == 162.5` (tillægget lægges endnu ikke til)

- [ ] **Step 3: Tilføj satsopslaget i `_calculate_employee()`**

I `app/routers/payroll_router.py`, ret linje 269-272 fra:

```python
    try:
        hourly_rate = load_agreement_types_from_db(db).get(emp.agreement_type, Decimal("0"))
    except Exception:
        hourly_rate = Decimal("0")
```

til:

```python
    try:
        hourly_rate = load_agreement_types_from_db(db).get(emp.agreement_type, Decimal("0"))
    except Exception:
        hourly_rate = Decimal("0")
    from routers.employee_supplements import get_active_supplement_for_period
    supplement = get_active_supplement_for_period(db, emp.id, start, end)
    if supplement:
        hourly_rate += supplement.value
```

(Import placeres lokalt i funktionen for at undgå cirkulær import ved modulindlæsning — samme mønster som `_get_pay_type_data()` og `_user_pay_type_rows()` i samme fil, der importerer `MasterPayType` lokalt.)

- [ ] **Step 4: Kør testene og bekræft at begge passerer**

Run: `pytest tests/test_employee_supplements.py -k calculate_employee -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Kør hele testsuiten og bekræft ingen regressioner**

Run: `pytest tests/ -v`
Expected: PASS (alle tests)

- [ ] **Step 6: Commit**

```bash
git add app/routers/payroll_router.py tests/test_employee_supplements.py
git commit -m "feat: tillæg lægges til grundsatsen i lønberegningen"
```

---

## Task 4: Frontend — ny "Tillæg"-side

**Files:**
- Modify: `app/templates/index.html` (sidebar-punkt linje 105-107, ny view efter linje 261, ny modal)
- Modify: `app/static/js/app.js` (setView linje 105-119, nye funktioner)

**Interfaces:**
- Consumes: `GET /api/employee-supplements`, `POST /api/employee-supplements` (Task 2), `buildDatePicker`/`readDatePicker` (eksisterende), `state.employees` (eksisterende, fra `/api/employees`)
- Produces: intet nyt for andre opgaver — Task 5 er uafhængig af denne opgaves JS-funktioner

Dette repo har intet frontend-testframework (intet `package.json`) — verifikation sker manuelt via curl mod API'et og gennemklik i browseren, i stedet for automatiserede tests, jf. resten af kodebasen.

- [ ] **Step 1: Tilføj sidebar-punktet**

I `app/templates/index.html`, tilføj efter `Vognpark`-punktet (efter linje 107):

```html
      <div class="sidebar-item" data-view="employee-supplements" data-perm-require="manage_employee_supplements">
        <span class="icon">💰</span> Tillæg
      </div>
```

- [ ] **Step 2: Tilføj view-blokken**

I `app/templates/index.html`, indsæt efter `<!-- ══ VEHICLES VIEW ══ -->`-blokken (efter linje 261, før `<!-- ══ USERS ADMIN VIEW ══ -->`):

```html
    <!-- ══════════════ EMPLOYEE SUPPLEMENTS VIEW ══════════════ -->
    <div class="view hidden" data-view="employee-supplements">
      <div class="toolbar">
        <h2 style="font-size:16px;font-weight:600">Tillæg</h2>
        <div class="spacer"></div>
        <input type="text" id="supplement-employee-search" placeholder="Søg navn eller lønnr…"
               style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:220px">
        <button class="btn btn-primary" data-perm-require="manage_employee_supplements" onclick="openAddSupplementModal()">+ Tilføj</button>
      </div>
      <div id="supplement-employee-list"></div>

      <div id="supplement-detail" style="display:none;margin-top:20px">
        <div class="toolbar" style="flex-wrap:wrap;gap:8px;align-items:center">
          <h3 id="supplement-detail-name" style="font-size:15px;font-weight:600;white-space:nowrap"></h3>
          <div style="display:flex;align-items:center;gap:10px;font-size:13px">
            <label style="display:flex;align-items:center;gap:5px">Fra:
              <div id="supplement-from-dp" style="width:150px"></div>
            </label>
            <label style="display:flex;align-items:center;gap:5px">Til:
              <div id="supplement-to-dp" style="width:150px"></div>
            </label>
          </div>
          <div class="spacer"></div>
          <button class="btn btn-secondary" onclick="loadSupplementDetail()">&#128260; Opdater</button>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
          <thead>
            <tr style="background:var(--primary);color:#fff">
              <th style="padding:11px 14px;text-align:left;font-weight:600">Status</th>
              <th style="padding:11px 14px;text-align:left;font-weight:600">Lønnummer</th>
              <th style="padding:11px 14px;text-align:left;font-weight:600">Tillægsnavn</th>
              <th style="padding:11px 14px;text-align:left;font-weight:600">Type</th>
              <th style="padding:11px 14px;text-align:left;font-weight:600">Gyldighedsperiode start</th>
              <th style="padding:11px 14px;text-align:left;font-weight:600">Gyldighedsperiode slut</th>
              <th style="padding:11px 14px;text-align:right;font-weight:600">Værdi (kr)</th>
            </tr>
          </thead>
          <tbody id="supplement-detail-tbody">
            <tr><td colspan="7" style="padding:30px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
```

- [ ] **Step 3: Tilføj opret-modalen**

I `app/templates/index.html`, indsæt umiddelbart efter `</div>` der lukker `modal-employee` (efter linje 1234, før `<!-- Advarsel om mulig dublet-medarbejder -->`):

```html
<!-- Employee supplement modal -->
<div id="modal-supplement" class="modal-overlay">
  <div class="modal" style="width:420px">
    <div class="modal-header">
      <h2>Tilføj tillæg</h2>
      <button class="modal-close" onclick="closeModal('modal-supplement')">&#215;</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label>Medarbejder <span style="color:var(--danger)">*</span></label>
        <select id="supplement-employee-select"></select>
      </div>
      <div class="form-group">
        <label>Startdato <span style="color:var(--danger)">*</span></label>
        <div id="supplement-start-dp"></div>
      </div>
      <div class="form-group">
        <label>Værdi (kr) <span style="color:var(--danger)">*</span></label>
        <input type="number" step="0.01" min="0.01" id="supplement-value" placeholder="Fx 12.50">
      </div>
      <div class="form-group">
        <label>Tillægsnavn</label>
        <input type="text" value="Ikke overenskomstmæssigt tillæg" disabled style="background:var(--bg);color:var(--text-light)">
      </div>
      <div class="form-group">
        <label>Type</label>
        <input type="text" value="Timebaseret" disabled style="background:var(--bg);color:var(--text-light)">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-supplement')">Annuller</button>
      <button class="btn btn-primary" onclick="confirmAddSupplement()">Opret</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Registrér view'et i `setView()`**

I `app/static/js/app.js`, ret `setView()` (linje 105-119) — tilføj som ny linje efter `if (view === "vehicles") loadVehicles();` (linje 116):

```js
  if (view === "employee-supplements") loadEmployeeSupplementsView();
```

- [ ] **Step 5: Tilføj JS-funktionerne for siden**

I `app/static/js/app.js`, tilføj til sidst i filen:

```js
// ── Employee supplements ────────────────────────────────────────────────────
state.selectedSupplementEmployeeId = null;

async function loadEmployeeSupplementsView() {
  if (!state.employees.length) {
    state.employees = await GET("/api/employees?active_only=false");
  }
  renderSupplementEmployeeList();
}

function renderSupplementEmployeeList() {
  const query = (document.getElementById("supplement-employee-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("supplement-employee-list");
  container.innerHTML = "";
  let emps = state.employees;
  if (query) {
    emps = emps.filter(e =>
      e.name.toLowerCase().includes(query) ||
      String(e.employee_number).toLowerCase().includes(query)
    );
  }
  emps = emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"));
  if (emps.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">👤</div><h3>Ingen medarbejdere</h3></div>`;
    return;
  }
  for (const e of emps) {
    const initials = `${e.first_name[0] || ""}${e.last_name[0] || ""}`.toUpperCase();
    const div = document.createElement("div");
    div.className = "emp-card";
    div.style.cursor = "pointer";
    div.innerHTML = `
      <div class="emp-avatar">${h(initials)}</div>
      <div class="emp-info">
        <div class="emp-name">${h(e.name)}</div>
        <div class="emp-sub">Lønnr. ${h(e.employee_number)}</div>
      </div>
    `;
    div.addEventListener("click", () => selectSupplementEmployee(e.id, e.name));
    container.appendChild(div);
  }
}

function selectSupplementEmployee(employeeId, employeeName) {
  state.selectedSupplementEmployeeId = employeeId;
  document.getElementById("supplement-detail").style.display = "";
  document.getElementById("supplement-detail-name").textContent = employeeName;
  buildDatePicker("supplement-from-dp", "");
  buildDatePicker("supplement-to-dp", "");
  loadSupplementDetail();
}

async function loadSupplementDetail() {
  const employeeId = state.selectedSupplementEmployeeId;
  if (!employeeId) return;
  const tbody = document.getElementById("supplement-detail-tbody");
  tbody.innerHTML = `<tr><td colspan="7" style="padding:30px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  const from = readDatePicker("supplement-from-dp");
  const to = readDatePicker("supplement-to-dp");
  let qs = `employee_id=${employeeId}`;
  if (from) qs += `&from=${from}`;
  if (to) qs += `&to=${to}`;
  try {
    const rows = await GET(`/api/employee-supplements?${qs}`);
    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="padding:24px;text-align:center;color:var(--text-light)">Ingen tillæg fundet</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px;font-weight:600;color:${r.is_active ? "var(--approved)" : "var(--danger)"}">${r.is_active ? "Aktiv" : "Inaktiv"}</td>
        <td style="padding:10px 14px">${h(r.employee_number)}</td>
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px">${h(r.type)}</td>
        <td style="padding:10px 14px">${formatDateShort(r.start_date)}</td>
        <td style="padding:10px 14px">${r.end_date === "9999-12-31" ? "–" : formatDateShort(r.end_date)}</td>
        <td style="padding:10px 14px;text-align:right">${r.value.toFixed(2)} kr</td>
      </tr>`).join("");
  } catch (e) { toast(e.message, "error"); }
}

function openAddSupplementModal() {
  const sel = document.getElementById("supplement-employee-select");
  sel.innerHTML = state.employees
    .slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
    .map(e => `<option value="${e.id}">${h(e.name)} (Lønnr. ${h(e.employee_number)})</option>`).join("");
  if (state.selectedSupplementEmployeeId) sel.value = state.selectedSupplementEmployeeId;
  document.getElementById("supplement-value").value = "";
  buildDatePicker("supplement-start-dp", new Date().toISOString().slice(0, 10));
  openModal("modal-supplement");
}

async function confirmAddSupplement() {
  const employeeId = parseInt(document.getElementById("supplement-employee-select").value);
  const startDate = readDatePicker("supplement-start-dp");
  const value = parseFloat(document.getElementById("supplement-value").value);
  if (!employeeId || !startDate || !value || value <= 0) {
    toast("Udfyld medarbejder, startdato og en positiv værdi", "error");
    return;
  }
  try {
    await POST("/api/employee-supplements", { employee_id: employeeId, start_date: startDate, value });
    toast("Tillæg oprettet", "success");
    closeModal("modal-supplement");
    if (state.selectedSupplementEmployeeId === employeeId) await loadSupplementDetail();
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 6: Verificér API'et manuelt med curl (backend allerede testet i Task 1-3, dette bekræfter kun HTTP-laget)**

Start serveren: `cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

Log ind og opret et tillæg (erstat `<session-cookie>` og `<employee_id>` med reelle værdier fra en indlogget browser-session):

```bash
curl -X POST http://localhost:8000/api/employee-supplements \
  -H "Content-Type: application/json" \
  -b "session=<session-cookie>" \
  -d '{"employee_id": 1, "start_date": "2026-08-13", "value": 12.5}'
```

Expected: HTTP 201 med JSON-body der indeholder `"is_active": true`, `"value": 12.5`

- [ ] **Step 7: Verificér i browseren**

Åbn appen, log ind, klik "Tillæg" i sidebaren. Søg en medarbejder, klik ind på personen, klik "+ Tilføj", udfyld og opret et tillæg. Bekræft at rækken vises i tabellen med grøn "Aktiv"-tekst og at et tidligere tillæg (hvis oprettet i test-forløbet) nu vises med rød "Inaktiv"-tekst og en udfyldt slutdato.

- [ ] **Step 8: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: frontend for medarbejdertillæg-side"
```

---

## Task 5: Frontend — read-only tillægsboks i medarbejder-modalen

**Files:**
- Modify: `app/templates/index.html` (efter linje 1126, i `modal-employee`)
- Modify: `app/static/js/app.js` (`openNewEmployeeModal()` linje 1984-2001, `openEditEmployee()` linje 2003-2029)

**Interfaces:**
- Consumes: `GET /api/employee-supplements/active/{employee_id}` (Task 2)

- [ ] **Step 1: Tilføj read-only feltet i modalen**

I `app/templates/index.html`, indsæt efter Overenskomsttype-`form-row` (efter linje 1126, før `<div class="form-group">` med Disponentgrupper på linje 1128):

```html
      <div class="form-row">
        <div class="form-group">
          <label>Tillæg (kr/t)</label>
          <input type="text" id="emp-active-supplement" disabled style="background:var(--bg);color:var(--text-light)">
        </div>
      </div>
```

- [ ] **Step 2: Ryd feltet ved oprettelse af ny medarbejder**

I `app/static/js/app.js`, i `openNewEmployeeModal()` (linje 1984-2001), tilføj før `openModal("modal-employee");`:

```js
  document.getElementById("emp-active-supplement").value = "";
```

- [ ] **Step 3: Udfyld feltet ved redigering af medarbejder**

I `app/static/js/app.js`, i `openEditEmployee()` (linje 2003-2029), tilføj efter `await _loadEmpCvrDropdown(e.cvr_number || null);` og før `openModal("modal-employee");`:

```js
  try {
    const supplement = await GET(`/api/employee-supplements/active/${id}`);
    document.getElementById("emp-active-supplement").value = supplement ? `${supplement.value.toFixed(2)} kr/t` : "";
  } catch (_) {
    document.getElementById("emp-active-supplement").value = "";
  }
```

- [ ] **Step 4: Verificér i browseren**

Åbn en medarbejder uden tillæg → feltet skal være tomt. Opret et tillæg til medarbejderen via "Tillæg"-siden (Task 4). Åbn medarbejderen igen → feltet skal nu vise værdien, fx "12.50 kr/t", og skal ikke kunne redigeres.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: read-only tillægsboks i medarbejder-modalen"
```

---

## Selvgennemgang (allerede udført af planforfatteren)

- **Spec-dækning:** Datamodel/livscyklus (Task 1-2), satsopslag/overlap-regel (Task 2-3), payroll-integration (Task 3), frontend-side med søgning/tabel/dato-filter/opret-modal (Task 4), read-only boks i medarbejder-modal (Task 5). Alle spec-afsnit har en task.
- **Placeholder-scan:** Ingen TBD/TODO — alle kodeblokke er komplette og selvstændigt kørbare.
- **Type-konsistens:** `get_active_supplement_for_period(db, employee_id, period_start, period_end)` bruges identisk i Task 2 (test) og Task 3 (payroll_router.py). `_create_supplement(db, employee_id, start_date, value: Decimal)` bruges identisk i Task 2 og Task 3's tests. `EmployeeSupplementResponse`-felterne matcher 1:1 mellem Task 1 (schema) og Task 4 (JS der læser `r.is_active`, `r.employee_number`, `r.value`, `r.start_date`, `r.end_date`, `r.name`, `r.type`).
