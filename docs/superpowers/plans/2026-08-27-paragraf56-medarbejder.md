# §56-felt i medarbejder-modalen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Medarbejder-modalen (opret/rediger) får et nyt "§56"-afkrydsningsfelt; krydses det af, skal en påkrævet start- og slutdato for §56 udfyldes og gemmes på medarbejderen.

**Architecture:** Tre nye kolonner på `Employee` (`paragraf_56`, `paragraf_56_start_date`, `paragraf_56_end_date`), tilføjet via en idempotent `ALTER TABLE`-migration. Backend validerer at begge datoer er udfyldt (og i korrekt rækkefølge) når feltet er sat, og nulstiller dem til `NULL` når det fjernes igen – både ved oprettelse og ved PATCH (hvor felterne holdes uden for den generiske `exclude_none`-dump, samme mønster som `dispatcher_group_id`, for at kunne nulstilles eksplicit). Frontend tilføjer checkboxen + en skjult/vist daterække i `modal-employee`, med tilsvarende klientside-validering før POST/PATCH.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (backend, testet med pytest), vanilla JS/HTML (frontend, verificeret manuelt i browseren – intet JS-testframework i projektet).

## Global Constraints

- Ingen kobling til lønberegning, Danløn CSV eller den eksisterende `§56 syg`-fraværstype/aktivitetslogik – kun medarbejderstamdata.
- Ingen ændring af Brugervejledningen i denne omgang.
- Slutdato er påkrævet når `paragraf_56=true` (ikke valgfri) – både klient- og serverside.
- Spec: `docs/superpowers/specs/2026-08-27-paragraf56-medarbejder-design.md`

---

## Filstruktur

```
app/
  database/models.py      # MODIFY: tre nye kolonner på Employee (linje 83-85)
  database/session.py     # MODIFY: idempotent migration i _migrate() (linje 115-117)
  database/schemas.py     # MODIFY: EmployeeCreate/EmployeeUpdate/EmployeeResponse (linje 33-104)
  routers/employees.py    # MODIFY: _validate_paragraf_56(), create_employee, update_employee, _to_response (linje 36-238)
  templates/index.html    # MODIFY: modal-employee Aktiv/Fuldlønnet-række (linje 1391-1402)
  static/js/app.js        # MODIFY: onParagraf56Change(), openNewEmployeeModal, openEditEmployee, confirmEmployee
tests/
  test_paragraf_56.py     # CREATE: backend-tests for validering og persistering
CODEREF.md                 # MODIFY: dokumentér de tre nye Employee-felter
```

---

## Task 1: Backend – datamodel, migration, validering

**Files:**
- Modify: `app/database/models.py:83-85`
- Modify: `app/database/session.py:115-117`
- Modify: `app/database/schemas.py:33-104`
- Modify: `app/routers/employees.py:1-238`
- Create: `tests/test_paragraf_56.py`

**Interfaces:**
- Consumes: `Employee`-modellen (`app/database/models.py`), `EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse` (`app/database/schemas.py`), eksisterende `db`/`employee`-pytest-fixtures (`tests/conftest.py`)
- Produces: `Employee.paragraf_56: bool`, `Employee.paragraf_56_start_date: date | None`, `Employee.paragraf_56_end_date: date | None`; `_validate_paragraf_56(active: bool, start: date | None, end: date | None) -> tuple[date | None, date | None]` i `app/routers/employees.py` – bruges af `create_employee`/`update_employee`

- [ ] **Step 1: Skriv de fejlende backend-tests i `tests/test_paragraf_56.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date
import pytest
from fastapi import HTTPException

from database.models import AppUser, MasterAgreementType, MasterAgreementKind
from database.schemas import EmployeeCreate, EmployeeUpdate, WorkSchedule


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _seed_agreement(db):
    from decimal import Decimal
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.commit()


def _employee_body(**overrides):
    data = dict(
        employee_number="9301",
        first_name="Ny",
        last_name="Paragraf",
        agreement_kind="hourly_fixed",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    return EmployeeCreate(**data)


def test_employee_paragraf_56_defaults_to_false(db, employee):
    assert employee.paragraf_56 is False
    assert employee.paragraf_56_start_date is None
    assert employee.paragraf_56_end_date is None


def test_create_employee_with_paragraf_56_requires_start_date(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(
            _employee_body(paragraf_56=True, paragraf_56_end_date=date(2026, 6, 1)),
            current_user=_dummy_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_create_employee_with_paragraf_56_requires_end_date(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(
            _employee_body(paragraf_56=True, paragraf_56_start_date=date(2026, 1, 1)),
            current_user=_dummy_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_create_employee_with_paragraf_56_rejects_end_before_start(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(
            _employee_body(
                paragraf_56=True,
                paragraf_56_start_date=date(2026, 6, 1),
                paragraf_56_end_date=date(2026, 1, 1),
            ),
            current_user=_dummy_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_create_employee_with_valid_paragraf_56_dates_is_saved(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(
        _employee_body(
            paragraf_56=True,
            paragraf_56_start_date=date(2026, 1, 1),
            paragraf_56_end_date=date(2026, 6, 1),
        ),
        current_user=_dummy_user(), db=db,
    )
    assert resp.paragraf_56 is True
    assert resp.paragraf_56_start_date == date(2026, 1, 1)
    assert resp.paragraf_56_end_date == date(2026, 6, 1)


def test_create_employee_without_paragraf_56_ignores_stray_dates(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(
        _employee_body(paragraf_56=False, paragraf_56_start_date=date(2026, 1, 1)),
        current_user=_dummy_user(), db=db,
    )
    assert resp.paragraf_56 is False
    assert resp.paragraf_56_start_date is None
    assert resp.paragraf_56_end_date is None


def test_update_employee_can_set_paragraf_56(db, employee):
    from routers.employees import update_employee
    updated = update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 2, 1), paragraf_56_end_date=date(2026, 8, 1)),
        current_user=_dummy_user(), db=db,
    )
    assert updated.paragraf_56 is True
    assert updated.paragraf_56_start_date == date(2026, 2, 1)
    assert updated.paragraf_56_end_date == date(2026, 8, 1)


def test_update_employee_can_clear_paragraf_56_and_dates(db, employee):
    from routers.employees import update_employee
    update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 2, 1), paragraf_56_end_date=date(2026, 8, 1)),
        current_user=_dummy_user(), db=db,
    )
    cleared = update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=False),
        current_user=_dummy_user(), db=db,
    )
    assert cleared.paragraf_56 is False
    assert cleared.paragraf_56_start_date is None
    assert cleared.paragraf_56_end_date is None


def test_update_employee_without_paragraf_56_field_leaves_it_unchanged(db, employee):
    from routers.employees import update_employee
    update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 2, 1), paragraf_56_end_date=date(2026, 8, 1)),
        current_user=_dummy_user(), db=db,
    )
    updated = update_employee(
        employee.id,
        EmployeeUpdate(first_name="Nytnavn"),
        current_user=_dummy_user(), db=db,
    )
    assert updated.paragraf_56 is True
    assert updated.paragraf_56_start_date == date(2026, 2, 1)
    assert updated.paragraf_56_end_date == date(2026, 8, 1)
```

- [ ] **Step 2: Kør testene og bekræft de fejler (fordi felterne ikke findes endnu)**

Run: `cd app && python -m pytest ../tests/test_paragraf_56.py -v`
Expected: FAIL – `TypeError` eller `ValidationError` om ukendte felter (`paragraf_56` findes ikke på `Employee`/`EmployeeCreate`/`EmployeeUpdate` endnu)

- [ ] **Step 3: Tilføj de tre nye kolonner på `Employee` i `app/database/models.py`**

Find (linje 83-85):

```python
    cvr_number = Column(String(20), nullable=True)          # Tilknyttet CVR-nummer (None = standard)
    anciennitet_dismissed_at = Column(DateTime, nullable=True)  # Tidspunkt for afvist anciennitetsadvarsel
    terminsdato = Column(Date, nullable=True)  # Seneste terminsdato angivet ved oprettelse af en barsel-aktivitet
```

Erstat med:

```python
    cvr_number = Column(String(20), nullable=True)          # Tilknyttet CVR-nummer (None = standard)
    anciennitet_dismissed_at = Column(DateTime, nullable=True)  # Tidspunkt for afvist anciennitetsadvarsel
    terminsdato = Column(Date, nullable=True)  # Seneste terminsdato angivet ved oprettelse af en barsel-aktivitet
    paragraf_56 = Column(Boolean, default=False, nullable=False)
    paragraf_56_start_date = Column(Date, nullable=True)
    paragraf_56_end_date = Column(Date, nullable=True)
```

- [ ] **Step 4: Tilføj idempotent migration i `app/database/session.py`**

Find (linje 115-117):

```python
        if "dispatcher_group_id" not in emp_cols:
            conn.execute("ALTER TABLE employees ADD COLUMN dispatcher_group_id INTEGER")
            conn.commit()
```

Erstat med:

```python
        if "dispatcher_group_id" not in emp_cols:
            conn.execute("ALTER TABLE employees ADD COLUMN dispatcher_group_id INTEGER")
            conn.commit()
        if "paragraf_56" not in emp_cols:
            conn.execute("ALTER TABLE employees ADD COLUMN paragraf_56 BOOLEAN NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE employees ADD COLUMN paragraf_56_start_date DATE")
            conn.execute("ALTER TABLE employees ADD COLUMN paragraf_56_end_date DATE")
            conn.commit()
```

- [ ] **Step 5: Tilføj felterne til schemas i `app/database/schemas.py`**

Find (linje 50-52):

```python
    dispatcher_group_id: Optional[int] = None
    cvr_number: Optional[str] = None
    initials: Optional[str] = None


class EmployeeUpdate(BaseModel):
```

Erstat med:

```python
    dispatcher_group_id: Optional[int] = None
    cvr_number: Optional[str] = None
    initials: Optional[str] = None
    paragraf_56: bool = False
    paragraf_56_start_date: Optional[date] = None
    paragraf_56_end_date: Optional[date] = None


class EmployeeUpdate(BaseModel):
```

Find (linje 72-74):

```python
    dispatcher_group_id: Optional[int] = None
    cvr_number: Optional[str] = None
    initials: Optional[str] = None


class EmployeeResponse(BaseModel):
```

Erstat med:

```python
    dispatcher_group_id: Optional[int] = None
    cvr_number: Optional[str] = None
    initials: Optional[str] = None
    paragraf_56: Optional[bool] = None
    paragraf_56_start_date: Optional[date] = None
    paragraf_56_end_date: Optional[date] = None


class EmployeeResponse(BaseModel):
```

Find (linje 100-103):

```python
    anciennitet_dismissed_at: Optional[datetime] = None
    terminsdato: Optional[date] = None
    initials: Optional[str] = None

    model_config = {"from_attributes": True}
```

Erstat med:

```python
    anciennitet_dismissed_at: Optional[datetime] = None
    terminsdato: Optional[date] = None
    initials: Optional[str] = None
    paragraf_56: bool
    paragraf_56_start_date: Optional[date] = None
    paragraf_56_end_date: Optional[date] = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 6: Tilføj `_validate_paragraf_56()` og kobl den ind i `create_employee`/`update_employee`/`_to_response` i `app/routers/employees.py`**

Find (linje 27-34):

```python
def _months_employed(hire_date: date, today: date = None) -> int:
    if today is None:
        today = date.today()
    months = (today.year - hire_date.year) * 12 + (today.month - hire_date.month)
    if today.day < hire_date.day:
        months -= 1
    return max(0, months)
```

Erstat med:

```python
def _months_employed(hire_date: date, today: date = None) -> int:
    if today is None:
        today = date.today()
    months = (today.year - hire_date.year) * 12 + (today.month - hire_date.month)
    if today.day < hire_date.day:
        months -= 1
    return max(0, months)


def _validate_paragraf_56(active: bool, start: Optional[date], end: Optional[date]) -> tuple:
    if not active:
        return None, None
    if not start or not end:
        raise HTTPException(400, "Start- og slutdato for §56 skal udfyldes")
    if end < start:
        raise HTTPException(400, "§56 slutdato skal være efter startdato")
    return start, end
```

Find (linje 41-67, `_to_response`):

```python
    return EmployeeResponse(
        id=emp.id,
        employee_number=emp.employee_number,
        tachograph_card_number=emp.tachograph_card_number,
        first_name=emp.first_name,
        last_name=emp.last_name,
        name=emp.name,
        address=emp.address,
        postal_code=emp.postal_code,
        email=emp.email,
        phone=emp.phone,
        mobile=emp.mobile,
        agreement_kind=emp.agreement_kind,
        agreement_type=emp.agreement_type,
        hourly_rate=rate,
        fuldloennet=emp.fuldloennet,
        active=emp.active,
        hire_date=emp.hire_date,
        termination_date=emp.termination_date,
        work_schedule=WorkSchedule(**emp.work_schedule),
        months_employed=_months_employed(emp.hire_date),
        dispatcher_group=DispatcherGroupResponse.model_validate(emp.dispatcher_group) if emp.dispatcher_group else None,
        cvr_number=emp.cvr_number,
        anciennitet_dismissed_at=emp.anciennitet_dismissed_at,
        terminsdato=emp.terminsdato,
        initials=emp.initials,
    )
```

Erstat med:

```python
    return EmployeeResponse(
        id=emp.id,
        employee_number=emp.employee_number,
        tachograph_card_number=emp.tachograph_card_number,
        first_name=emp.first_name,
        last_name=emp.last_name,
        name=emp.name,
        address=emp.address,
        postal_code=emp.postal_code,
        email=emp.email,
        phone=emp.phone,
        mobile=emp.mobile,
        agreement_kind=emp.agreement_kind,
        agreement_type=emp.agreement_type,
        hourly_rate=rate,
        fuldloennet=emp.fuldloennet,
        active=emp.active,
        hire_date=emp.hire_date,
        termination_date=emp.termination_date,
        work_schedule=WorkSchedule(**emp.work_schedule),
        months_employed=_months_employed(emp.hire_date),
        dispatcher_group=DispatcherGroupResponse.model_validate(emp.dispatcher_group) if emp.dispatcher_group else None,
        cvr_number=emp.cvr_number,
        anciennitet_dismissed_at=emp.anciennitet_dismissed_at,
        terminsdato=emp.terminsdato,
        initials=emp.initials,
        paragraf_56=emp.paragraf_56,
        paragraf_56_start_date=emp.paragraf_56_start_date,
        paragraf_56_end_date=emp.paragraf_56_end_date,
    )
```

Find (`create_employee`, linje 137-144):

```python
    if _agreement_type_required(db, body.agreement_kind):
        if not body.agreement_type or body.agreement_type not in load_agreement_types_from_db(db):
            raise HTTPException(400, f"Ukendt overenskomsttype: {body.agreement_type}")
    else:
        body.agreement_type = ""

    data = body.model_dump(exclude={"dispatcher_group_id"})
    data["work_schedule"] = body.work_schedule.model_dump()
```

Erstat med:

```python
    if _agreement_type_required(db, body.agreement_kind):
        if not body.agreement_type or body.agreement_type not in load_agreement_types_from_db(db):
            raise HTTPException(400, f"Ukendt overenskomsttype: {body.agreement_type}")
    else:
        body.agreement_type = ""
    body.paragraf_56_start_date, body.paragraf_56_end_date = _validate_paragraf_56(
        body.paragraf_56, body.paragraf_56_start_date, body.paragraf_56_end_date
    )

    data = body.model_dump(exclude={"dispatcher_group_id"})
    data["work_schedule"] = body.work_schedule.model_dump()
```

Find (`update_employee`, linje 226-232):

```python
    old_agreement_type = emp.agreement_type
    for field_name, value in body.model_dump(exclude_none=True, exclude={"dispatcher_group_id"}).items():
        if field_name == "work_schedule":
            value = body.work_schedule.model_dump()
        setattr(emp, field_name, value)
    if "dispatcher_group_id" in body.model_fields_set:
        emp.dispatcher_group = _resolve_dispatcher_group(db, body.dispatcher_group_id)
```

Erstat med:

```python
    old_agreement_type = emp.agreement_type
    _paragraf56_excludes = {"dispatcher_group_id", "paragraf_56", "paragraf_56_start_date", "paragraf_56_end_date"}
    for field_name, value in body.model_dump(exclude_none=True, exclude=_paragraf56_excludes).items():
        if field_name == "work_schedule":
            value = body.work_schedule.model_dump()
        setattr(emp, field_name, value)
    if "dispatcher_group_id" in body.model_fields_set:
        emp.dispatcher_group = _resolve_dispatcher_group(db, body.dispatcher_group_id)
    if "paragraf_56" in body.model_fields_set:
        start, end = _validate_paragraf_56(
            bool(body.paragraf_56), body.paragraf_56_start_date, body.paragraf_56_end_date
        )
        emp.paragraf_56 = bool(body.paragraf_56)
        emp.paragraf_56_start_date = start
        emp.paragraf_56_end_date = end
```

- [ ] **Step 7: Kør testene og bekræft de består**

Run: `cd app && python -m pytest ../tests/test_paragraf_56.py -v`
Expected: PASS – alle 9 tests grønne

- [ ] **Step 8: Kør hele test-suiten for at udelukke regression**

Run: `cd app && python -m pytest ../tests -q`
Expected: PASS – alle tests grønne (208 eksisterende + 9 nye = 217)

- [ ] **Step 9: Commit**

```bash
git add app/database/models.py app/database/session.py app/database/schemas.py app/routers/employees.py tests/test_paragraf_56.py
git commit -m "feat: §56-felt på medarbejderen (backend)"
```

---

## Task 2: Frontend – checkbox og dato-felter i medarbejder-modalen

**Files:**
- Modify: `app/templates/index.html:1391-1402`
- Modify: `app/static/js/app.js` (ved siden af `onAgreementKindChange()`, samt `openNewEmployeeModal()`, `openEditEmployee()`, `confirmEmployee()`)
- Modify: `CODEREF.md`

**Interfaces:**
- Consumes: `EmployeeResponse.paragraf_56/paragraf_56_start_date/paragraf_56_end_date` (Task 1), `buildDatePicker(id, isoValue)`/`readDatePicker(id)` (eksisterende, `app.js`)
- Produces: `onParagraf56Change() -> void` – ny global funktion i `app.js`

- [ ] **Step 1: Udvid Aktiv/Fuldlønnet-rækken og tilføj dato-rækken i `app/templates/index.html`**

Find (linje 1391-1402):

```html
      <div class="form-row">
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-active" checked> Aktiv
          </label>
        </div>
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-fuldloennet" checked> Fuldlønnet
          </label>
        </div>
      </div>
```

Erstat med:

```html
      <div class="form-row" style="grid-template-columns:1fr 1fr 1fr">
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-active" checked> Aktiv
          </label>
        </div>
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-fuldloennet" checked> Fuldlønnet
          </label>
        </div>
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

- [ ] **Step 2: Tilføj `onParagraf56Change()` i `app/static/js/app.js`, lige før `onAgreementKindChange()`**

Find:

```js
function onAgreementKindChange() {
```

Erstat med:

```js
function onParagraf56Change() {
  const checked = document.getElementById("emp-paragraf56").checked;
  document.getElementById("emp-paragraf56-dates").style.display = checked ? "" : "none";
}

function onAgreementKindChange() {
```

- [ ] **Step 3: Nulstil §56-feltet i `openNewEmployeeModal()`**

Find:

```js
  document.getElementById("emp-active").checked = true;
  document.getElementById("emp-fuldloennet").checked = true;
  buildScheduleTable(null);
  await _loadEmpCvrDropdown(null);
  document.getElementById("emp-active-supplement").value = "";
  openModal("modal-employee");
}

async function openEditEmployee(id) {
```

Erstat med:

```js
  document.getElementById("emp-active").checked = true;
  document.getElementById("emp-fuldloennet").checked = true;
  document.getElementById("emp-paragraf56").checked = false;
  buildDatePicker("emp-paragraf56-start", "");
  buildDatePicker("emp-paragraf56-end", "");
  onParagraf56Change();
  buildScheduleTable(null);
  await _loadEmpCvrDropdown(null);
  document.getElementById("emp-active-supplement").value = "";
  openModal("modal-employee");
}

async function openEditEmployee(id) {
```

- [ ] **Step 4: Udfyld §56-feltet i `openEditEmployee(id)`**

Find:

```js
  document.getElementById("emp-active").checked = e.active;
  document.getElementById("emp-fuldloennet").checked = e.fuldloennet;
  buildScheduleTable(e.work_schedule);
```

Erstat med:

```js
  document.getElementById("emp-active").checked = e.active;
  document.getElementById("emp-fuldloennet").checked = e.fuldloennet;
  document.getElementById("emp-paragraf56").checked = e.paragraf_56;
  buildDatePicker("emp-paragraf56-start", e.paragraf_56_start_date || "");
  buildDatePicker("emp-paragraf56-end", e.paragraf_56_end_date || "");
  onParagraf56Change();
  buildScheduleTable(e.work_schedule);
```

- [ ] **Step 5: Send og valider §56-feltet i `confirmEmployee()`**

Find:

```js
    fuldloennet: document.getElementById("emp-fuldloennet").checked,
    active: document.getElementById("emp-active").checked,
    hire_date: readDatePicker("emp-hire"),
    termination_date: readDatePicker("emp-termination") || "9999-12-31",
    work_schedule: readScheduleTable(),
  };
  if (!body.employee_number || !body.first_name || !body.last_name || !body.hire_date) {
    toast("Udfyld lønnummer, navn og ansættelsesdato", "error");
    return;
  }
```

Erstat med:

```js
    fuldloennet: document.getElementById("emp-fuldloennet").checked,
    active: document.getElementById("emp-active").checked,
    hire_date: readDatePicker("emp-hire"),
    termination_date: readDatePicker("emp-termination") || "9999-12-31",
    work_schedule: readScheduleTable(),
    paragraf_56: document.getElementById("emp-paragraf56").checked,
    paragraf_56_start_date: document.getElementById("emp-paragraf56").checked
      ? readDatePicker("emp-paragraf56-start") : null,
    paragraf_56_end_date: document.getElementById("emp-paragraf56").checked
      ? readDatePicker("emp-paragraf56-end") : null,
  };
  if (!body.employee_number || !body.first_name || !body.last_name || !body.hire_date) {
    toast("Udfyld lønnummer, navn og ansættelsesdato", "error");
    return;
  }
  if (body.paragraf_56 && (!body.paragraf_56_start_date || !body.paragraf_56_end_date)) {
    toast("Udfyld start- og slutdato for §56", "error");
    return;
  }
  if (body.paragraf_56 && body.paragraf_56_end_date < body.paragraf_56_start_date) {
    toast("§56 slutdato skal være efter startdato", "error");
    return;
  }
```

- [ ] **Step 6: Opdater `CODEREF.md`**

Find afsnittet om `Employee`-tabellen (feltoversigten under overskriften `### Employee (tabel: employees)`) og tilføj en ny række i tabellen:

```
| paragraf_56 | Boolean | Krydses af i medarbejder-modalen; kræver paragraf_56_start_date/paragraf_56_end_date udfyldt (400 ellers). Ingen kobling til lønberegning eller den eksisterende "§56 syg"-fraværstype endnu |
| paragraf_56_start_date / paragraf_56_end_date | Date nullable | Se paragraf_56 – nulstilles til NULL server-side når paragraf_56 sættes til false |
```

- [ ] **Step 7: Manuel browser-verifikation**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet med en bruger der har `manage_employees`.

1. Åbn "+ Opret medarbejder" → bekræft at §56-afkrydsningsfeltet vises ved siden af Aktiv/Fuldlønnet, og at ingen dato-felter er synlige.
2. Kryds §56 af → bekræft at der straks vises en ny række med "§56 startdato *" og "§56 slutdato *" (datovælgere, samme udseende som Ansættelsesdato).
3. Forsøg at oprette medarbejderen med §56 afkrydset men uden udfyldte datoer → bekræft fejlbesked "Udfyld start- og slutdato for §56", og at der IKKE sendes noget til serveren (ingen ny medarbejder oprettet).
4. Udfyld en slutdato der ligger FØR startdatoen → bekræft fejlbesked "§56 slutdato skal være efter startdato".
5. Udfyld gyldige datoer (fx 01-01-2026 til 01-06-2026) og udfyld resten af de påkrævede felter → opret medarbejderen → bekræft succes-toast.
6. Klik "Rediger" på den nyoprettede medarbejder → bekræft at §56 er afkrydset, og at de to datoer er forudfyldt korrekt.
7. Fjern fluebenet i §56 → bekræft at dato-rækken skjules igen → gem → åbn medarbejderen igen → bekræft at §56 nu er afkrydset FRA, og at datoerne er væk (ikke bare skjulte – tjek fx via `GET /api/employees/{id}` i en ny fane, eller åbn "Rediger" igen og bekræft de to felter er tomme).
8. Åbn en eksisterende medarbejder UDEN §56 → bekræft at checkboxen er tom og dato-rækken skjult, som forventet.

- [ ] **Step 8: Commit**

```bash
git add app/templates/index.html app/static/js/app.js CODEREF.md
git commit -m "feat: §56-felt i medarbejder-modalen (frontend)"
```

---

## Self-Review

**Spec coverage:**
- ✅ Tre nye kolonner på `Employee` + idempotent migration – Task 1, Step 3-4
- ✅ Schemas udvidet (Create/Update/Response) – Task 1, Step 5
- ✅ Backend-validering: påkrævede datoer, slutdato ≥ startdato, nulstilling ved `paragraf_56=false`, `exclude_none`-fælden undgået (samme mønster som `dispatcher_group_id`) – Task 1, Step 6
- ✅ Checkbox + betinget daterække i modalen, placeret ved Aktiv/Fuldlønnet – Task 2, Step 1
- ✅ Vis/skjul-logik, nulstilling ved opret, udfyldning ved rediger – Task 2, Step 2-4
- ✅ Klientside-validering (begge datoer + rækkefølge) – Task 2, Step 5
- ✅ CODEREF.md opdateret – Task 2, Step 6
- ✅ Ingen kobling til lønberegning/CSV/eksisterende §56 syg-fraværstype – ingen af de filer røres i planen
- ✅ Ingen ændring af Brugervejledningen – ikke en del af planen

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, testene indeholder konkrete assertions, verifikationstrinnet har konkrete handlinger og forventede resultater.

**Type-konsistens:** `_validate_paragraf_56(active: bool, start: Optional[date], end: Optional[date]) -> tuple` defineres i Task 1 Step 6 og bruges med samme signatur i både `create_employee` og `update_employee`. `onParagraf56Change() -> void` defineres i Task 2 Step 2 og kaldes konsistent fra HTML (`onchange`), `openNewEmployeeModal()` og `openEditEmployee()`. Feltnavnene `paragraf_56`/`paragraf_56_start_date`/`paragraf_56_end_date` er identiske på tværs af model, schema, router, HTML-id'er (med `emp-`-præfiks) og JS – ingen navnekollision med eksisterende felter.
