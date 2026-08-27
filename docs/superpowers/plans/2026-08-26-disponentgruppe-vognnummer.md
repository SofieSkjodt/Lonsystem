# Disponentgruppe → ét vognnummer på fraværsregistrering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En medarbejder kan fremover kun tilhøre én disponentgruppe (i stedet for flere i dag). Hver disponentgruppe kan tilknyttes ét vognnummer via Stamdata. Ved registrering af enhver fraværstype foreslås dette vognnummer automatisk (redigerbart), og en fejl der forhindrede vognnummer i overhovedet at blive gemt på flerdags-fravær rettes.

**Architecture:** `Employee.dispatcher_groups` (mange-til-mange) erstattes af `Employee.dispatcher_group_id` (nullable FK, ét-til-mange). `DispatcherGroup` får `vehicle_id` (nullable FK til `Vehicle`). En idempotent migration reducerer eksisterende data til én gruppe pr. medarbejder (alfabetisk først ved konflikt) og dropper junction-tabellen. API og frontend omdøbes fra liste- til skalar-form. Vognnummer-autoudfyldning er en ren frontend-bekvemmelighed (prefill, redigerbar) – ingen backend-håndhævelse.

**Tech Stack:** Python/FastAPI/SQLAlchemy/SQLite (backend), vanilla JavaScript (frontend, intet build-trin, intet JS-testframework). `node` er ikke installeret i miljøet – JS-verifikation sker manuelt i browseren.

## Global Constraints

- Ingen nye afhængigheder
- Python 3.11+ (kan bruge `str | None` uden `Optional`-import i nye modelfelter)
- Tests køres fra `app/`: `cd app && python -m pytest ../tests/ -v`
- Server kræver genstart ved `.py`-ændringer; `.js`/`.html`-ændringer kræver kun browser-reload
- Rå SQL-migrationer i `session.py` (ALTER TABLE/DROP TABLE via `sqlite3`) har i denne kodebase **ingen** automatiseret testdækning (samme mønster som eksisterende `_migrate_dispatcher_groups()`) – verificeres manuelt mod den rigtige dev-database
- Spec: `docs/superpowers/specs/2026-08-26-disponentgruppe-vognnummer-design.md`

---

## Filstruktur

```
app/
  database/
    models.py                 # MODIFY: Employee, DispatcherGroup, fjern EmployeeDispatcherGroup
    session.py                 # MODIFY: ny _migrate_dispatcher_group_to_single(), kaldt fra init_db()
    schemas.py                  # MODIFY: DispatcherGroupResponse, EmployeeCreate/Update/Response
  routers/
    employees.py                # MODIFY: enkelt-gruppe CRUD
    stamdata.py                  # MODIFY: vehicle_id på disponentgruppe-CRUD
    payroll_router.py            # MODIFY: _active_employees() singular-tjek
    absence_overview_router.py   # MODIFY: employee_options()/export_per_employee() singular-tjek
  templates/index.html           # MODIFY: medarbejder-modal select, stamdata-modal vognnummer-felt+tabel
  static/js/app.js                # MODIFY: single-select, søgbar vogn-dropdown, autoudfyldning, POST-fix
tests/
  test_dispatcher_group_single.py   # CREATE: model-, API- og consumer-tests for 1:1-relationen
  test_dispatcher_group_visibility.py # MODIFY: udvid med vehicle_id-tests
  test_dob_overnatning.py            # MODIFY: ret brugen af .dispatcher_groups.append(...)
  test_payroll_settlement.py         # MODIFY: samme rettelse
  test_springertillaeg.py            # MODIFY: samme rettelse
```

---

## Task 1: Datamodel + migration

**Files:**
- Modify: `app/database/models.py:89-95` (Employee), `:174-193` (DispatcherGroup + EmployeeDispatcherGroup), `:227-233` (Vehicle-nærhed, ingen ændring i selve Vehicle)
- Modify: `app/database/session.py:61` (init_db-kald), efter linje 551 (ny funktion)
- Modify: `tests/test_dob_overnatning.py:163`
- Modify: `tests/test_payroll_settlement.py:329`
- Modify: `tests/test_springertillaeg.py:122`
- Create: `tests/test_dispatcher_group_single.py`

**Interfaces:**
- Produces: `Employee.dispatcher_group_id: int|None`, `Employee.dispatcher_group: DispatcherGroup|None`, `DispatcherGroup.vehicle_id: int|None`, `DispatcherGroup.vehicle: Vehicle|None`, `DispatcherGroup.vehicle_number: str|None` (property)

- [ ] **Step 1: Skriv de failing tests**

Opret `tests/test_dispatcher_group_single.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database.models import DispatcherGroup, Employee, Vehicle


def test_employee_dispatcher_group_defaults_to_none(db, employee):
    assert employee.dispatcher_group_id is None
    assert employee.dispatcher_group is None


def test_employee_can_be_assigned_a_single_dispatcher_group(db, employee):
    group = DispatcherGroup(name="Testgruppe")
    db.add(group)
    db.commit()
    db.refresh(group)

    employee.dispatcher_group = group
    db.commit()
    db.refresh(employee)

    assert employee.dispatcher_group_id == group.id
    assert employee.dispatcher_group.name == "Testgruppe"


def test_employee_no_longer_has_a_many_to_many_dispatcher_groups_relationship():
    assert not hasattr(Employee, "dispatcher_groups")


def test_dispatcher_group_vehicle_number_is_none_without_vehicle(db):
    group = DispatcherGroup(name="Uden vogn")
    db.add(group)
    db.commit()
    db.refresh(group)
    assert group.vehicle_number is None


def test_dispatcher_group_vehicle_number_reads_linked_vehicle(db):
    vehicle = Vehicle(registration_number="AB12345", vehicle_number="99")
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    group = DispatcherGroup(name="Med vogn", vehicle_id=vehicle.id)
    db.add(group)
    db.commit()
    db.refresh(group)

    assert group.vehicle_number == "99"
```

- [ ] **Step 2: Kør tests og bekræft FAIL**

```bash
cd app && python -m pytest ../tests/test_dispatcher_group_single.py -v
```

Forventet: alle 5 tests `FAILED` (`AttributeError: 'Employee' object has no attribute 'dispatcher_group_id'` / `TypeError` på `vehicle_id=` osv., da felterne endnu ikke findes).

- [ ] **Step 3: Ret `Employee`-relationen i `app/database/models.py`**

Find (linje 91-95):

```python
    dispatcher_groups = relationship(
        "DispatcherGroup",
        secondary="employee_dispatcher_groups",
        back_populates="employees"
    )
```

Erstat med:

```python
    dispatcher_group_id = Column(Integer, ForeignKey("dispatcher_groups.id"), nullable=True)
    dispatcher_group = relationship("DispatcherGroup", back_populates="employees")
```

- [ ] **Step 4: Ret `DispatcherGroup`-klassen og fjern `EmployeeDispatcherGroup`**

Find (linje 174-193):

```python
class DispatcherGroup(Base):
    __tablename__ = "dispatcher_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    visible_in_activity_overview = Column(Boolean, nullable=False, default=True)

    employees = relationship(
        "Employee",
        secondary="employee_dispatcher_groups",
        back_populates="dispatcher_groups"
    )


class EmployeeDispatcherGroup(Base):
    __tablename__ = "employee_dispatcher_groups"

    employee_id = Column(Integer, ForeignKey("employees.id"), primary_key=True)
    dispatcher_group_id = Column(Integer, ForeignKey("dispatcher_groups.id"), primary_key=True)
```

Erstat med:

```python
class DispatcherGroup(Base):
    __tablename__ = "dispatcher_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    visible_in_activity_overview = Column(Boolean, nullable=False, default=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)

    employees = relationship("Employee", back_populates="dispatcher_group")
    vehicle = relationship("Vehicle")

    @property
    def vehicle_number(self) -> str | None:
        return self.vehicle.vehicle_number if self.vehicle else None
```

- [ ] **Step 5: Kør de nye tests og bekræft PASS**

```bash
cd app && python -m pytest ../tests/test_dispatcher_group_single.py -v
```

Forventet: alle 5 tests `PASSED`.

- [ ] **Step 6: Ret de 3 eksisterende tests der bruger den gamle mange-til-mange-API**

I `tests/test_dob_overnatning.py`, find (linje 163):

```python
    employee.dispatcher_groups.append(DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True))
```

Erstat med:

```python
    employee.dispatcher_group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)
```

I `tests/test_payroll_settlement.py`, find (linje 319-330):

```python
def _assign_visible_dispatcher_group(db, employee):
    """_active_employees() (payroll_router.py:669) udelukker medarbejdere uden
    mindst én disponentgruppe med visible_in_activity_overview=True — den delte
    'employee'-fixture i conftest.py har ingen grupper, så enhver test der
    rammer preview/export skal selv tildele én."""
    from database.models import DispatcherGroup
    group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)
    db.add(group)
    db.commit()
    db.refresh(group)
    employee.dispatcher_groups.append(group)
    db.commit()
```

Erstat med:

```python
def _assign_visible_dispatcher_group(db, employee):
    """_active_employees() (payroll_router.py) udelukker medarbejdere uden en
    disponentgruppe med visible_in_activity_overview=True — den delte
    'employee'-fixture i conftest.py har ingen gruppe, så enhver test der
    rammer preview/export skal selv tildele én."""
    from database.models import DispatcherGroup
    group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)
    db.add(group)
    db.commit()
    db.refresh(group)
    employee.dispatcher_group = group
    db.commit()
```

I `tests/test_springertillaeg.py`, find (linje 116-123):

```python
def _give_visible_dispatcher_group(db, employee):
    """_active_employees() udelukker medarbejdere uden en synlig disponentgruppe
    (jf. payroll_router.py) — testens employee-fixture har ingen, så CSV-export
    ville ellers stille og roligt give 0 medarbejdere."""
    from database.models import DispatcherGroup
    group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)
    employee.dispatcher_groups.append(group)
    db.commit()
```

Erstat med:

```python
def _give_visible_dispatcher_group(db, employee):
    """_active_employees() udelukker medarbejdere uden en synlig disponentgruppe
    (jf. payroll_router.py) — testens employee-fixture har ingen, så CSV-export
    ville ellers stille og roligt give 0 medarbejdere."""
    from database.models import DispatcherGroup
    group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)
    employee.dispatcher_group = group
    db.commit()
```

- [ ] **Step 7: Kør fuld test-suite og bekræft ingen regressioner**

```bash
cd app && python -m pytest ../tests/ -v
```

Forventet: alle tests `PASSED` (de 3 rettede filer + de nye 5 tests + alt andet upåvirket).

- [ ] **Step 8: Tilføj migrationsfunktionen i `app/database/session.py`**

Find slutningen af `_migrate_dispatcher_groups()` (linje 545-551):

```python
            conn.execute("ALTER TABLE employees DROP COLUMN dispatcher_group")
            conn.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved migrering af disponentgrupper: {e}")
    finally:
        db.close()
```

Tilføj umiddelbart efter (før `def _ensure_manage_baselines_permission():`):

```python


def _migrate_dispatcher_group_to_single():
    """
    Reducerer disponentgruppe fra mange-til-mange til én gruppe pr. medarbejder.
    Har en medarbejder i dag flere grupper, beholdes den alfabetisk først
    sorterede (efter gruppenavn). Idempotent – dropper employee_dispatcher_groups
    efter migrering; kører derfor kun data-trinnet én gang (tabellen er væk bagefter).
    """
    import sqlite3 as _sqlite3

    try:
        with _sqlite3.connect(str(DB_PATH)) as conn:
            emp_cols = {row[1] for row in conn.execute("PRAGMA table_info(employees)")}
            if "dispatcher_group_id" not in emp_cols:
                conn.execute("ALTER TABLE employees ADD COLUMN dispatcher_group_id INTEGER")
                conn.commit()
            dg_cols = {row[1] for row in conn.execute("PRAGMA table_info(dispatcher_groups)")}
            if "vehicle_id" not in dg_cols:
                conn.execute("ALTER TABLE dispatcher_groups ADD COLUMN vehicle_id INTEGER")
                conn.commit()

            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "employee_dispatcher_groups" not in tables:
                return

            rows = conn.execute(
                "SELECT edg.employee_id, dg.id "
                "FROM employee_dispatcher_groups edg "
                "JOIN dispatcher_groups dg ON dg.id = edg.dispatcher_group_id "
                "ORDER BY edg.employee_id, dg.name"
            ).fetchall()
            primary_by_employee = {}
            for emp_id, group_id in rows:
                primary_by_employee.setdefault(emp_id, group_id)
            for emp_id, group_id in primary_by_employee.items():
                conn.execute(
                    "UPDATE employees SET dispatcher_group_id = ? "
                    "WHERE id = ? AND dispatcher_group_id IS NULL",
                    (group_id, emp_id),
                )
            conn.commit()
            conn.execute("DROP TABLE employee_dispatcher_groups")
            conn.commit()
    except Exception as e:
        logging.error(f"Fejl ved migrering af disponentgruppe til én-til-én: {e}")
```

- [ ] **Step 9: Kald migrationen fra `init_db()`**

Find (linje 61):

```python
    _migrate_dispatcher_groups()
```

Erstat med:

```python
    _migrate_dispatcher_groups()
    _migrate_dispatcher_group_to_single()
```

- [ ] **Step 10: Manuel verifikation af migrationen mod den rigtige dev-database**

Denne migration rører en rå SQL-tabel (`employee_dispatcher_groups`) og har – ligesom den eksisterende `_migrate_dispatcher_groups()` den bygger videre på – ingen automatiseret testdækning i dette projekt. Verificér i stedet direkte, før serveren genstartes:

```bash
cd app && python -c "
import sys; sys.path.insert(0, '.')
from database.session import SessionLocal
from database.models import Employee
db = SessionLocal()
before = {
    e.employee_number: [g.name for g in e.dispatcher_groups]
    for e in db.query(Employee).filter(Employee.employee_number.in_(['34517', '34518'])).all()
}
print('Før migrering (34517=Andreas Lentz, 34518=Nick Vinge):', before)
db.close()
"
```

Forventet: viser Andreas Lentz med `['5 - Miljø', '9 - BN']` og Nick Vinge med `['4 - Makulering', '5 - Miljø']` (bekræfter udgangspunktet er som forventet, FØR koden med den nye kolonne er i brug – kør denne linje på den nuværende `master`-kode, inden Step 3-4's modelændring er aktiv i en kørende proces).

Genstart derefter serveren (kører `init_db()` og dermed migrationen), og verificér resultatet:

```bash
cd app && python -c "
import sys; sys.path.insert(0, '.')
from database.session import SessionLocal
from database.models import Employee
import sqlite3
db = SessionLocal()
rows = db.query(Employee.employee_number, Employee.dispatcher_group_id).filter(
    Employee.employee_number.in_(['34517', '34518'])
).all()
print('Efter migrering:', rows)
for num, gid in rows:
    g = db.query(Employee).filter(Employee.employee_number == num).first().dispatcher_group
    print(num, '->', g.name if g else None)
db.close()
conn = sqlite3.connect('database/lonsystem.db')
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")]
print('employee_dispatcher_groups findes stadig:', 'employee_dispatcher_groups' in tables)
"
```

Forventet: Andreas Lentz (34517) → `dispatcher_group.name == '5 - Miljø'`. Nick Vinge (34518) → `'4 - Makulering'`. `employee_dispatcher_groups` findes IKKE længere.

Genstart serveren én gang til (kør migrationen igen) og bekræft samme resultat uden fejl i loggen (idempotens).

- [ ] **Step 11: Commit**

```bash
git add app/database/models.py app/database/session.py tests/test_dispatcher_group_single.py tests/test_dob_overnatning.py tests/test_payroll_settlement.py tests/test_springertillaeg.py
git commit -m "feat: disponentgruppe er nu 1:1 med medarbejder, vognnummer på gruppen"
```

---

## Task 2: Employee-API til enkelt disponentgruppe

**Files:**
- Modify: `app/database/schemas.py:22-28` (`DispatcherGroupResponse`), `:48` (`EmployeeCreate`), `:70` (`EmployeeUpdate`), `:96` (`EmployeeResponse`)
- Modify: `app/routers/employees.py:61` (`_to_response`), `:116-124` (`_resolve_dispatcher_groups`), `:144-147` (`create_employee`), `:228-233` (`update_employee`)
- Modify: `tests/test_dispatcher_group_single.py`

**Interfaces:**
- Consumes: `Employee.dispatcher_group_id`/`Employee.dispatcher_group` fra Task 1
- Produces: `EmployeeCreate.dispatcher_group_id: Optional[int]`, `EmployeeUpdate.dispatcher_group_id: Optional[int]`, `EmployeeResponse.dispatcher_group: Optional[DispatcherGroupResponse]`, `_resolve_dispatcher_group(db, group_id) -> Optional[DispatcherGroup]`

- [ ] **Step 1: Skriv de failing tests**

Tilføj til `tests/test_dispatcher_group_single.py`:

```python
from database.models import AppUser
from database.schemas import EmployeeCreate, EmployeeUpdate, WorkSchedule
from datetime import date
from fastapi import HTTPException
import pytest


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _employee_body(**overrides):
    data = dict(
        employee_number="9201",
        first_name="Ny",
        last_name="Person",
        agreement_kind="hourly_fixed",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    return EmployeeCreate(**data)


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


def test_create_employee_with_dispatcher_group(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    group = DispatcherGroup(name="Ny Gruppe")
    db.add(group)
    db.commit()
    db.refresh(group)

    resp = create_employee(_employee_body(dispatcher_group_id=group.id), current_user=_dummy_user(), db=db)
    assert resp.dispatcher_group.id == group.id
    assert resp.dispatcher_group.name == "Ny Gruppe"


def test_create_employee_without_dispatcher_group(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(_employee_body(), current_user=_dummy_user(), db=db)
    assert resp.dispatcher_group is None


def test_create_employee_rejects_unknown_dispatcher_group(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_employee_body(dispatcher_group_id=999999), current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400


def test_update_employee_can_set_and_clear_dispatcher_group(db, employee):
    from routers.employees import update_employee
    group = DispatcherGroup(name="Skiftegruppe")
    db.add(group)
    db.commit()
    db.refresh(group)

    updated = update_employee(employee.id, EmployeeUpdate(dispatcher_group_id=group.id), current_user=_dummy_user(), db=db)
    assert updated.dispatcher_group.id == group.id

    cleared = update_employee(employee.id, EmployeeUpdate(dispatcher_group_id=None), current_user=_dummy_user(), db=db)
    assert cleared.dispatcher_group is None


def test_update_employee_without_dispatcher_group_field_leaves_it_unchanged(db, employee):
    from routers.employees import update_employee
    group = DispatcherGroup(name="Uændret-gruppe")
    db.add(group)
    db.commit()
    db.refresh(group)
    employee.dispatcher_group = group
    db.commit()

    updated = update_employee(employee.id, EmployeeUpdate(first_name="Nytnavn"), current_user=_dummy_user(), db=db)
    assert updated.dispatcher_group.id == group.id
```

- [ ] **Step 2: Kør tests og bekræft FAIL**

```bash
cd app && python -m pytest ../tests/test_dispatcher_group_single.py -v -k "dispatcher_group_id or dispatcher_group_field or set_and_clear or unknown_dispatcher"
```

Forventet: FEJL – `EmployeeCreate`/`EmployeeUpdate` kender endnu ikke `dispatcher_group_id`-feltet (Pydantic validation error ved ukendt keyword, eller feltet accepteres men gemmes ingen steder), og `resp.dispatcher_group` findes ikke på `EmployeeResponse` endnu.

- [ ] **Step 3: Opdater `app/database/schemas.py`**

Find `DispatcherGroupResponse` (linje 22-28):

```python
class DispatcherGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    visible_in_activity_overview: bool = True

    model_config = {"from_attributes": True}
```

Erstat med:

```python
class DispatcherGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    visible_in_activity_overview: bool = True
    vehicle_id: Optional[int] = None
    vehicle_number: Optional[str] = None

    model_config = {"from_attributes": True}
```

Find i `EmployeeCreate` (linje 48):

```python
    dispatcher_group_ids: list[int] = Field(default_factory=list)
```

Erstat med:

```python
    dispatcher_group_id: Optional[int] = None
```

Find i `EmployeeUpdate` (linje 70):

```python
    dispatcher_group_ids: Optional[list[int]] = None
```

Erstat med:

```python
    dispatcher_group_id: Optional[int] = None
```

Find i `EmployeeResponse` (linje 96):

```python
    dispatcher_groups: list[DispatcherGroupResponse] = Field(default_factory=list)
```

Erstat med:

```python
    dispatcher_group: Optional[DispatcherGroupResponse] = None
```

- [ ] **Step 4: Opdater `app/routers/employees.py`**

Find `_to_response()` (linje 61):

```python
        dispatcher_groups=[DispatcherGroupResponse.model_validate(g) for g in emp.dispatcher_groups],
```

Erstat med:

```python
        dispatcher_group=DispatcherGroupResponse.model_validate(emp.dispatcher_group) if emp.dispatcher_group else None,
```

Find `_resolve_dispatcher_groups()` (linje 116-124):

```python
def _resolve_dispatcher_groups(db: Session, ids: list[int]) -> list[DispatcherGroup]:
    if not ids:
        return []
    groups = db.query(DispatcherGroup).filter(DispatcherGroup.id.in_(ids)).all()
    found_ids = {g.id for g in groups}
    missing = set(ids) - found_ids
    if missing:
        raise HTTPException(400, f"Ukendt disponentgruppe-id: {', '.join(str(i) for i in sorted(missing))}")
    return groups
```

Erstat med:

```python
def _resolve_dispatcher_group(db: Session, group_id: Optional[int]) -> Optional[DispatcherGroup]:
    if group_id is None:
        return None
    group = db.query(DispatcherGroup).filter(DispatcherGroup.id == group_id).first()
    if not group:
        raise HTTPException(400, f"Ukendt disponentgruppe-id: {group_id}")
    return group
```

`Optional` er ikke importeret i denne fil i dag. Find toppen af `app/routers/employees.py` (linje 1-2):

```python
import logging
from datetime import date, datetime
```

Erstat med:

```python
import logging
from datetime import date, datetime
from typing import Optional
```

Find i `create_employee()` (linje 144-147):

```python
    data = body.model_dump(exclude={"dispatcher_group_ids"})
    data["work_schedule"] = body.work_schedule.model_dump()
    emp = Employee(**data)
    emp.dispatcher_groups = _resolve_dispatcher_groups(db, body.dispatcher_group_ids)
```

Erstat med:

```python
    data = body.model_dump(exclude={"dispatcher_group_id"})
    data["work_schedule"] = body.work_schedule.model_dump()
    emp = Employee(**data)
    emp.dispatcher_group = _resolve_dispatcher_group(db, body.dispatcher_group_id)
```

Find i `update_employee()` (linje 228-233):

```python
    for field_name, value in body.model_dump(exclude_none=True, exclude={"dispatcher_group_ids"}).items():
        if field_name == "work_schedule":
            value = body.work_schedule.model_dump()
        setattr(emp, field_name, value)
    if body.dispatcher_group_ids is not None:
        emp.dispatcher_groups = _resolve_dispatcher_groups(db, body.dispatcher_group_ids)
```

Erstat med:

```python
    for field_name, value in body.model_dump(exclude_none=True, exclude={"dispatcher_group_id"}).items():
        if field_name == "work_schedule":
            value = body.work_schedule.model_dump()
        setattr(emp, field_name, value)
    if "dispatcher_group_id" in body.model_fields_set:
        emp.dispatcher_group = _resolve_dispatcher_group(db, body.dispatcher_group_id)
```

- [ ] **Step 5: Kør tests og bekræft PASS**

```bash
cd app && python -m pytest ../tests/test_dispatcher_group_single.py -v
```

Forventet: alle tests `PASSED` (både Task 1's og Task 2's).

- [ ] **Step 6: Kør fuld test-suite**

```bash
cd app && python -m pytest ../tests/ -v
```

Forventet: alle tests `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add app/database/schemas.py app/routers/employees.py tests/test_dispatcher_group_single.py
git commit -m "feat: employees-API bruger nu enkelt disponentgruppe-id i stedet for en liste"
```

---

## Task 3: Vognnummer på disponentgruppe (Stamdata-API)

**Files:**
- Modify: `app/routers/stamdata.py:13-18` (imports), `:636-639` (`DispatcherGroupBody`), `:642-649` (`_dispatcher_group_row`), `:661-687` (`create_dispatcher_group`), `:690-719` (`update_dispatcher_group`)
- Modify: `tests/test_dispatcher_group_visibility.py`

**Interfaces:**
- Consumes: `DispatcherGroup.vehicle_id`/`vehicle`/`vehicle_number` fra Task 1
- Produces: `DispatcherGroupBody.vehicle_id: Optional[int]`, `_dispatcher_group_row(r)` inkluderer `vehicle_id`/`vehicle_number`

- [ ] **Step 1: Skriv de failing tests**

Tilføj til `tests/test_dispatcher_group_visibility.py`:

```python
from database.models import Vehicle


def _make_vehicle(db, reg="AB12345", num="99"):
    v = Vehicle(registration_number=reg, vehicle_number=num)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_create_dispatcher_group_with_vehicle(db):
    vehicle = _make_vehicle(db)
    result = create_dispatcher_group(
        DispatcherGroupBody(name="Med vogn", vehicle_id=vehicle.id),
        current_user=_dummy_user(), db=db,
    )
    assert result["vehicle_id"] == vehicle.id
    assert result["vehicle_number"] == "99"


def test_create_dispatcher_group_rejects_unknown_vehicle(db):
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        create_dispatcher_group(
            DispatcherGroupBody(name="Ukendt vogn", vehicle_id=999999),
            current_user=_dummy_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_update_dispatcher_group_can_set_and_clear_vehicle(db):
    vehicle = _make_vehicle(db)
    created = create_dispatcher_group(DispatcherGroupBody(name="Skal have vogn"), current_user=_dummy_user(), db=db)
    assert created["vehicle_id"] is None

    updated = update_dispatcher_group(
        created["id"], DispatcherGroupBody(vehicle_id=vehicle.id), current_user=_dummy_user(), db=db,
    )
    assert updated["vehicle_id"] == vehicle.id

    cleared = update_dispatcher_group(
        created["id"], DispatcherGroupBody(vehicle_id=None), current_user=_dummy_user(), db=db,
    )
    assert cleared["vehicle_id"] is None


def test_update_dispatcher_group_without_vehicle_field_leaves_it_unchanged(db):
    vehicle = _make_vehicle(db)
    created = create_dispatcher_group(
        DispatcherGroupBody(name="Uændret vogn", vehicle_id=vehicle.id), current_user=_dummy_user(), db=db,
    )
    updated = update_dispatcher_group(
        created["id"], DispatcherGroupBody(description="Ny beskrivelse"), current_user=_dummy_user(), db=db,
    )
    assert updated["vehicle_id"] == vehicle.id
```

- [ ] **Step 2: Kør tests og bekræft FAIL**

```bash
cd app && python -m pytest ../tests/test_dispatcher_group_visibility.py -v -k vehicle
```

Forventet: FEJL – `DispatcherGroupBody` kender ikke `vehicle_id`, og `_dispatcher_group_row()` returnerer det ikke.

- [ ] **Step 3: Tilføj `Vehicle` til imports i `app/routers/stamdata.py`**

Find (linje 13-18):

```python
from database.models import (
    AppUser, Employee, DispatcherGroup,
    MasterAgreementType, MasterAgreementKind, MasterOvertimeRate,
    MasterSupplementRate, MasterPayType, MasterAbsenceType, MasterCvrNumber,
    Holiday,
)
```

Erstat med:

```python
from database.models import (
    AppUser, Employee, DispatcherGroup, Vehicle,
    MasterAgreementType, MasterAgreementKind, MasterOvertimeRate,
    MasterSupplementRate, MasterPayType, MasterAbsenceType, MasterCvrNumber,
    Holiday,
)
```

- [ ] **Step 4: Opdater `DispatcherGroupBody` og `_dispatcher_group_row()`**

Find (linje 636-649):

```python
class DispatcherGroupBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visible_in_activity_overview: Optional[bool] = None


def _dispatcher_group_row(r) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "employee_count": len(r.employees),
        "visible_in_activity_overview": r.visible_in_activity_overview,
    }
```

Erstat med:

```python
class DispatcherGroupBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visible_in_activity_overview: Optional[bool] = None
    vehicle_id: Optional[int] = None


def _dispatcher_group_row(r) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "employee_count": len(r.employees),
        "visible_in_activity_overview": r.visible_in_activity_overview,
        "vehicle_id": r.vehicle_id,
        "vehicle_number": r.vehicle.vehicle_number if r.vehicle else None,
    }
```

- [ ] **Step 5: Opdater `create_dispatcher_group()`**

Find (linje 661-687):

```python
@router.post("/dispatcher-groups", status_code=201)
def create_dispatcher_group(
    body: DispatcherGroupBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.name:
        raise HTTPException(400, "Navn er påkrævet")
    name = body.name.strip()
    if db.query(DispatcherGroup).filter(DispatcherGroup.name == name).first():
        raise HTTPException(400, "En disponentgruppe med dette navn eksisterer allerede")
    row = DispatcherGroup(
        name=name,
        description=(body.description or "").strip() or None,
        visible_in_activity_overview=(
            body.visible_in_activity_overview
            if body.visible_in_activity_overview is not None
            else True
        ),
    )
```

Erstat med:

```python
@router.post("/dispatcher-groups", status_code=201)
def create_dispatcher_group(
    body: DispatcherGroupBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.name:
        raise HTTPException(400, "Navn er påkrævet")
    name = body.name.strip()
    if db.query(DispatcherGroup).filter(DispatcherGroup.name == name).first():
        raise HTTPException(400, "En disponentgruppe med dette navn eksisterer allerede")
    if body.vehicle_id is not None and not db.query(Vehicle).filter(Vehicle.id == body.vehicle_id).first():
        raise HTTPException(400, "Ukendt køretøj")
    row = DispatcherGroup(
        name=name,
        description=(body.description or "").strip() or None,
        visible_in_activity_overview=(
            body.visible_in_activity_overview
            if body.visible_in_activity_overview is not None
            else True
        ),
        vehicle_id=body.vehicle_id,
    )
```

(Resten af funktionen – `db.add(row)` og nedefter – er uændret.)

- [ ] **Step 6: Opdater `update_dispatcher_group()`**

Find (linje 690-719), den sidste del af funktionen efter `visible_in_activity_overview`-blokken:

```python
    if body.visible_in_activity_overview is not None:
        row.visible_in_activity_overview = body.visible_in_activity_overview
    db.commit()
```

Erstat med:

```python
    if body.visible_in_activity_overview is not None:
        row.visible_in_activity_overview = body.visible_in_activity_overview
    if "vehicle_id" in body.model_fields_set:
        if body.vehicle_id is not None and not db.query(Vehicle).filter(Vehicle.id == body.vehicle_id).first():
            raise HTTPException(400, "Ukendt køretøj")
        row.vehicle_id = body.vehicle_id
    db.commit()
```

- [ ] **Step 7: Kør tests og bekræft PASS**

```bash
cd app && python -m pytest ../tests/test_dispatcher_group_visibility.py -v
```

Forventet: alle tests `PASSED` (eksisterende + de 4 nye).

- [ ] **Step 8: Kør fuld test-suite**

```bash
cd app && python -m pytest ../tests/ -v
```

Forventet: alle tests `PASSED`.

- [ ] **Step 9: Commit**

```bash
git add app/routers/stamdata.py tests/test_dispatcher_group_visibility.py
git commit -m "feat: disponentgrupper kan tilknyttes et vognnummer via Stamdata"
```

---

## Task 4: Opdater forbrugere af disponentgruppe (lønkørsel, fraværsoversigt)

**Files:**
- Modify: `app/routers/payroll_router.py:715`
- Modify: `app/routers/absence_overview_router.py:192-233`
- Modify: `tests/test_dispatcher_group_single.py`

**Interfaces:**
- Consumes: `Employee.dispatcher_group_id`/`Employee.dispatcher_group` fra Task 1

- [ ] **Step 1: Skriv de failing tests**

Tilføj til `tests/test_dispatcher_group_single.py`:

```python
def test_active_employees_excludes_employee_without_dispatcher_group(db, employee):
    from routers.payroll_router import _active_employees
    result = _active_employees(db)
    assert employee.id not in [e.id for e in result]


def test_active_employees_includes_employee_with_visible_group(db, employee):
    from routers.payroll_router import _active_employees
    group = DispatcherGroup(name="Synlig gruppe", visible_in_activity_overview=True)
    db.add(group)
    db.commit()
    employee.dispatcher_group = group
    db.commit()

    result = _active_employees(db)
    assert employee.id in [e.id for e in result]


def test_active_employees_excludes_employee_with_hidden_group(db, employee):
    from routers.payroll_router import _active_employees
    group = DispatcherGroup(name="Skjult gruppe", visible_in_activity_overview=False)
    db.add(group)
    db.commit()
    employee.dispatcher_group = group
    db.commit()

    result = _active_employees(db)
    assert employee.id not in [e.id for e in result]
```

- [ ] **Step 2: Kør tests og bekræft FAIL**

```bash
cd app && python -m pytest ../tests/test_dispatcher_group_single.py -v -k active_employees
```

Forventet: FEJL – `_active_employees()` bruger stadig `e.dispatcher_groups` (tom liste for alle, da relationen ikke findes mere) → `AttributeError`.

- [ ] **Step 3: Opdater `_active_employees()` i `app/routers/payroll_router.py`**

Find (linje 715):

```python
    return [e for e in employees if any(g.visible_in_activity_overview for g in e.dispatcher_groups)]
```

Erstat med:

```python
    return [e for e in employees if e.dispatcher_group and e.dispatcher_group.visible_in_activity_overview]
```

- [ ] **Step 4: Opdater `employee_options()` og `export_per_employee()` i `app/routers/absence_overview_router.py`**

Find (linje 192-199):

```python
    used_group_ids = {g.id for e in emps for g in e.dispatcher_groups}
    groups = db.query(DispatcherGroup).filter(DispatcherGroup.id.in_(used_group_ids)).order_by(DispatcherGroup.name).all()
    return {
        "employees": [
            {"id": e.id, "name": e.name, "dispatcher_group_ids": [g.id for g in e.dispatcher_groups]}
            for e in emps
        ],
        "dispatcher_groups": [{"id": g.id, "name": g.name} for g in groups],
    }
```

Erstat med:

```python
    used_group_ids = {e.dispatcher_group_id for e in emps if e.dispatcher_group_id}
    groups = db.query(DispatcherGroup).filter(DispatcherGroup.id.in_(used_group_ids)).order_by(DispatcherGroup.name).all()
    return {
        "employees": [
            {"id": e.id, "name": e.name, "dispatcher_group_id": e.dispatcher_group_id}
            for e in emps
        ],
        "dispatcher_groups": [{"id": g.id, "name": g.name} for g in groups],
    }
```

Find (linje 223-233):

```python
    elif dispatcher_group_id:
        group = db.query(DispatcherGroup).filter(DispatcherGroup.id == dispatcher_group_id).first()
        group_name = group.name if group else None
        # Medarbejderen vises under alle sine tilknyttede grupper
        group_emp_ids = {
            e.id for e in db.query(Employee).filter(
                Employee.active == True,
                Employee.dispatcher_groups.any(DispatcherGroup.id == dispatcher_group_id),
            ).all()
        }
        employees = [e for e in employees if e["employee_id"] in group_emp_ids]
```

Erstat med:

```python
    elif dispatcher_group_id:
        group = db.query(DispatcherGroup).filter(DispatcherGroup.id == dispatcher_group_id).first()
        group_name = group.name if group else None
        group_emp_ids = {
            e.id for e in db.query(Employee).filter(
                Employee.active == True,
                Employee.dispatcher_group_id == dispatcher_group_id,
            ).all()
        }
        employees = [e for e in employees if e["employee_id"] in group_emp_ids]
```

- [ ] **Step 5: Kør tests og bekræft PASS**

```bash
cd app && python -m pytest ../tests/test_dispatcher_group_single.py -v
```

Forventet: alle tests `PASSED`.

- [ ] **Step 6: Kør fuld test-suite**

```bash
cd app && python -m pytest ../tests/ -v
```

Forventet: alle tests `PASSED` – inkl. `test_payroll_settlement.py` og `test_springertillaeg.py`, som afhænger af `_active_employees()`.

- [ ] **Step 7: Commit**

```bash
git add app/routers/payroll_router.py app/routers/absence_overview_router.py tests/test_dispatcher_group_single.py
git commit -m "feat: lønkørsel og fraværsoversigt bruger nu medarbejderens enkelte disponentgruppe"
```

---

## Task 5: Frontend – medarbejder-modal med enkelt disponentgruppe

**Files:**
- Modify: `app/templates/index.html:1309-1312`
- Modify: `app/static/js/app.js:2394-2406` (render-funktion), `:2418`, `:2449` (kaldesteder), `:2482` (confirmEmployee), `:4941-4952` (`_empInGroup`/`_empHasVisibleGroup`), `:247`, `:317`, `:5052` (vagtplan-/aktivitetsfiltre)

**Interfaces:**
- Consumes: `EmployeeResponse.dispatcher_group` (singular, fra Task 2), `state.dispatcherGroups` (uændret liste af alle grupper, til dropdown-indhold)

- [ ] **Step 1: Opdater medarbejder-modalens HTML i `app/templates/index.html`**

Find (linje 1309-1312):

```html
      <div class="form-group">
        <label>Disponentgrupper</label>
        <div id="emp-dispatcher-groups" style="display:flex;flex-direction:column;gap:6px"></div>
      </div>
```

Erstat med:

```html
      <div class="form-group">
        <label>Disponentgruppe</label>
        <select id="emp-dispatcher-group"></select>
      </div>
```

- [ ] **Step 2: Erstat `_renderDispatcherGroupCheckboxes()` i `app/static/js/app.js`**

Find (linje 2394-2406):

```js
function _renderDispatcherGroupCheckboxes(selectedIds) {
  const container = document.getElementById("emp-dispatcher-groups");
  if (!state.dispatcherGroups.length) {
    container.innerHTML = `<p style="font-size:13px;color:var(--text-light);margin:0">Ingen disponentgrupper oprettet endnu</p>`;
    return;
  }
  container.innerHTML = state.dispatcherGroups.map(g => `
    <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:14px">
      <input type="checkbox" value="${g.id}" ${selectedIds.includes(g.id) ? "checked" : ""}
             style="width:15px;height:15px;accent-color:var(--primary);cursor:pointer">
      ${h(g.name)}
    </label>`).join("");
}
```

Erstat med:

```js
function fillDispatcherGroupSelect(selectedId = null) {
  const sel = document.getElementById("emp-dispatcher-group");
  sel.innerHTML = `<option value="">— Ingen —</option>` + state.dispatcherGroups
    .map(g => `<option value="${g.id}" ${g.id === selectedId ? "selected" : ""}>${h(g.name)}</option>`)
    .join("");
}
```

- [ ] **Step 3: Opdater de to kaldesteder**

Find (linje 2418):

```js
  _renderDispatcherGroupCheckboxes([]);
```

Erstat med:

```js
  fillDispatcherGroupSelect(null);
```

Find (linje 2449):

```js
  _renderDispatcherGroupCheckboxes((e.dispatcher_groups || []).map(g => g.id));
```

Erstat med:

```js
  fillDispatcherGroupSelect(e.dispatcher_group?.id ?? null);
```

- [ ] **Step 4: Opdater `confirmEmployee()`**

Find (linje 2482):

```js
    dispatcher_group_ids: [...document.querySelectorAll("#emp-dispatcher-groups input:checked")].map(cb => parseInt(cb.value)),
```

Erstat med:

```js
    dispatcher_group_id: document.getElementById("emp-dispatcher-group").value
      ? parseInt(document.getElementById("emp-dispatcher-group").value) : null,
```

- [ ] **Step 5: Opdater `_empInGroup()` og `_empHasVisibleGroup()`**

Find (linje 4941-4952):

```js
function _empInGroup(emp, groupId) {
  return (emp.dispatcher_groups || []).some(g => String(g.id) === String(groupId));
}

function _empHasVisibleGroup(emp) {
  const visibleIds = new Set(
    (state.dispatcherGroups || [])
      .filter(g => g.visible_in_activity_overview)
      .map(g => String(g.id))
  );
  return (emp.dispatcher_groups || []).some(g => visibleIds.has(String(g.id)));
}
```

Erstat med:

```js
function _empInGroup(emp, groupId) {
  return String(emp.dispatcher_group?.id) === String(groupId);
}

function _empHasVisibleGroup(emp) {
  return !!emp.dispatcher_group?.visible_in_activity_overview;
}
```

- [ ] **Step 6: Opdater de tre direkte gruppefilter-tjek**

Find (linje 247):

```js
  if (groupIds) visibleEmps = visibleEmps.filter(e => (e.dispatcher_groups || []).some(g => groupIds.includes(g.id)));
```

Erstat med:

```js
  if (groupIds) visibleEmps = visibleEmps.filter(e => e.dispatcher_group && groupIds.includes(e.dispatcher_group.id));
```

Find (linje 317):

```js
  if (groupIds) emps = emps.filter(e => (e.dispatcher_groups || []).some(g => groupIds.includes(g.id)));
```

Erstat med:

```js
  if (groupIds) emps = emps.filter(e => e.dispatcher_group && groupIds.includes(e.dispatcher_group.id));
```

Find (linje 5052):

```js
  if (groupIds) visible = visible.filter(e => (e.dispatcher_groups || []).some(g => groupIds.includes(g.id)));
```

Erstat med:

```js
  if (groupIds) visible = visible.filter(e => e.dispatcher_group && groupIds.includes(e.dispatcher_group.id));
```

(`groupIds` er stadig en liste af valgte gruppe-id'er fra vagtplanens gruppefilter – det er visnings-filteret der forbliver multi-select, ikke medarbejderens tilhørsforhold.)

- [ ] **Step 7: Manuel browser-verifikation**

Genstart serveren (Python-ændringer fra Task 1-4 kræver det under alle omstændigheder). Log ind, og i browserens konsol:

```js
// Åbn opret-medarbejder-modalen og bekræft ét dropdown i stedet for afkrydsningsfelter
openNewEmployeeModal();
JSON.stringify({
  hasSelect: !!document.getElementById("emp-dispatcher-group"),
  hasOldCheckboxes: !!document.getElementById("emp-dispatcher-groups"),
  optionCount: document.getElementById("emp-dispatcher-group").options.length,
});
```

Forventet: `hasSelect: true`, `hasOldCheckboxes: false`, `optionCount` = antal disponentgrupper + 1 ("— Ingen —").

Åbn en eksisterende medarbejder med en gruppe (fx via `openEditEmployee(<id>)` for en medarbejder du ved har en gruppe) og bekræft at dropdownet viser den rigtige gruppe forudvalgt. Luk modalen uden at gemme.

- [ ] **Step 8: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: medarbejder-modal bruger ét dropdown for disponentgruppe i stedet for afkrydsningsfelter"
```

---

## Task 6: Frontend – vognnummer på disponentgruppe i Stamdata (søgbar dropdown)

**Files:**
- Modify: `app/templates/index.html:618-632` (tabel), `:1889-1915` (modal)
- Modify: `app/static/js/app.js:4508-4568` (`loadStamdataDispatcherGroups`, `openStamdataDispatcherModal`, `confirmStamdataDispatcher`) + nye søge-dropdown-funktioner

**Interfaces:**
- Consumes: `state.vehicles` (allerede indlæst globalt ved opstart, `{id, registration_number, vehicle_number}`), `DispatcherGroupResponse.vehicle_id`/`vehicle_number` fra Task 3
- Produces: `_renderVehicleSearchResults(query)`, `_selectVehicleForDispatcherGroup(id, vehicleNumber)` – nye globale funktioner i `app.js`

- [ ] **Step 1: Tilføj "Vognnummer"-kolonne til tabellen i `app/templates/index.html`**

Find (linje 618-632):

```html
        <!-- Disponentgrupper -->
        <div id="sd-pane-dispatcher" style="display:none">
          <table style="width:100%;border-collapse:collapse;font-size:14px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
            <thead>
              <tr style="background:var(--primary);color:#fff">
                <th style="padding:10px 14px;text-align:left;font-weight:600">Navn</th>
                <th style="padding:10px 14px;text-align:left;font-weight:600">Beskrivelse</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Medarbejdere</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Vis i aktivitetsoversigt</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Handlinger</th>
              </tr>
            </thead>
            <tbody id="stamdata-dispatcher-tbody">
              <tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>
            </tbody>
```

Erstat med:

```html
        <!-- Disponentgrupper -->
        <div id="sd-pane-dispatcher" style="display:none">
          <table style="width:100%;border-collapse:collapse;font-size:14px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
            <thead>
              <tr style="background:var(--primary);color:#fff">
                <th style="padding:10px 14px;text-align:left;font-weight:600">Navn</th>
                <th style="padding:10px 14px;text-align:left;font-weight:600">Beskrivelse</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Medarbejdere</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Vognnummer</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Vis i aktivitetsoversigt</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Handlinger</th>
              </tr>
            </thead>
            <tbody id="stamdata-dispatcher-tbody">
              <tr><td colspan="6" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>
            </tbody>
```

- [ ] **Step 2: Tilføj søgefelt til modalen i `app/templates/index.html`**

Find (linje 1889-1915):

```html
<div id="modal-stamdata-dispatcher" class="modal-overlay">
  <div class="modal" style="width:480px">
    <div class="modal-header">
      <h2 id="stamdata-dispatcher-title">Disponentgruppe</h2>
      <button class="modal-close" onclick="closeModal('modal-stamdata-dispatcher')">&#215;</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="stamdata-dispatcher-id">
      <div class="form-group">
        <label>Navn</label>
        <input type="text" id="stamdata-dispatcher-name" placeholder="fx 11 - Nyt lager">
      </div>
      <div class="form-group">
        <label>Beskrivelse</label>
        <input type="text" id="stamdata-dispatcher-description" placeholder="Valgfri">
      </div>
      <div class="form-group" style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" id="stamdata-dispatcher-visible" style="width:16px;height:16px;cursor:pointer" checked>
        <label for="stamdata-dispatcher-visible" style="margin:0;cursor:pointer">Vis i aktivitetsoversigt</label>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-stamdata-dispatcher')">Annuller</button>
      <button class="btn btn-primary" onclick="confirmStamdataDispatcher()">Gem</button>
    </div>
  </div>
</div>
```

Erstat med:

```html
<div id="modal-stamdata-dispatcher" class="modal-overlay">
  <div class="modal" style="width:480px">
    <div class="modal-header">
      <h2 id="stamdata-dispatcher-title">Disponentgruppe</h2>
      <button class="modal-close" onclick="closeModal('modal-stamdata-dispatcher')">&#215;</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="stamdata-dispatcher-id">
      <div class="form-group">
        <label>Navn</label>
        <input type="text" id="stamdata-dispatcher-name" placeholder="fx 11 - Nyt lager">
      </div>
      <div class="form-group">
        <label>Beskrivelse</label>
        <input type="text" id="stamdata-dispatcher-description" placeholder="Valgfri">
      </div>
      <div class="form-group" style="position:relative">
        <label>Vognnummer</label>
        <input type="text" id="stamdata-dispatcher-vehicle-search" placeholder="Søg vognnummer eller reg.nr." autocomplete="off">
        <input type="hidden" id="stamdata-dispatcher-vehicle-id">
        <div id="stamdata-dispatcher-vehicle-dropdown"
             style="display:none;position:absolute;z-index:20;left:0;right:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);max-height:220px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,.12)"></div>
      </div>
      <div class="form-group" style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" id="stamdata-dispatcher-visible" style="width:16px;height:16px;cursor:pointer" checked>
        <label for="stamdata-dispatcher-visible" style="margin:0;cursor:pointer">Vis i aktivitetsoversigt</label>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-stamdata-dispatcher')">Annuller</button>
      <button class="btn btn-primary" onclick="confirmStamdataDispatcher()">Gem</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Tilføj søge-dropdown-funktionerne i `app/static/js/app.js`**

Find `openStamdataDispatcherModal()` (linje 4542-4549):

```js
function openStamdataDispatcherModal(id, name, description, visible) {
  document.getElementById("stamdata-dispatcher-id").value = id || "";
  document.getElementById("stamdata-dispatcher-name").value = name || "";
  document.getElementById("stamdata-dispatcher-description").value = description || "";
  document.getElementById("stamdata-dispatcher-visible").checked = id ? !!visible : true;
  document.getElementById("stamdata-dispatcher-title").textContent = id ? "Rediger disponentgruppe" : "Ny disponentgruppe";
  openModal("modal-stamdata-dispatcher");
}
```

Erstat med:

```js
function _renderVehicleSearchResults(query) {
  const dropdown = document.getElementById("stamdata-dispatcher-vehicle-dropdown");
  const q = query.trim().toUpperCase();
  const matches = !q ? state.vehicles : state.vehicles.filter(v =>
    v.vehicle_number.toUpperCase().includes(q) || v.registration_number.toUpperCase().includes(q)
  );
  const noneRow = `<div class="vehicle-search-item" data-id="" data-num=""
       style="padding:8px 10px;cursor:pointer;font-size:13px;color:var(--text-light)">— Intet køretøj —</div>`;
  const rows = matches.length
    ? matches.map(v => `
        <div class="vehicle-search-item" data-id="${v.id}" data-num="${h(v.vehicle_number)}"
             style="padding:8px 10px;cursor:pointer;font-size:13px">
          ${h(v.vehicle_number)} <span style="color:var(--text-light)">– ${h(v.registration_number)}</span>
        </div>`).join("")
    : `<div style="padding:8px 10px;color:var(--text-light);font-size:13px">Ingen køretøjer fundet</div>`;
  dropdown.innerHTML = noneRow + rows;
  dropdown.querySelectorAll(".vehicle-search-item[data-id]").forEach(el => {
    el.addEventListener("mouseover", () => el.style.background = "var(--bg)");
    el.addEventListener("mouseout",  () => el.style.background = "");
    el.addEventListener("click", () => _selectVehicleForDispatcherGroup(el.dataset.id, el.dataset.num));
  });
  dropdown.style.display = "block";
}

function _selectVehicleForDispatcherGroup(id, vehicleNumber) {
  document.getElementById("stamdata-dispatcher-vehicle-search").value = vehicleNumber || "";
  document.getElementById("stamdata-dispatcher-vehicle-id").value = id || "";
  document.getElementById("stamdata-dispatcher-vehicle-dropdown").style.display = "none";
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#stamdata-dispatcher-vehicle-search, #stamdata-dispatcher-vehicle-dropdown")) {
    const dropdown = document.getElementById("stamdata-dispatcher-vehicle-dropdown");
    if (dropdown) dropdown.style.display = "none";
  }
});

function openStamdataDispatcherModal(id, name, description, visible, vehicleId, vehicleNumber) {
  document.getElementById("stamdata-dispatcher-id").value = id || "";
  document.getElementById("stamdata-dispatcher-name").value = name || "";
  document.getElementById("stamdata-dispatcher-description").value = description || "";
  document.getElementById("stamdata-dispatcher-visible").checked = id ? !!visible : true;
  document.getElementById("stamdata-dispatcher-vehicle-search").value = vehicleNumber || "";
  document.getElementById("stamdata-dispatcher-vehicle-id").value = vehicleId || "";
  document.getElementById("stamdata-dispatcher-vehicle-dropdown").style.display = "none";
  document.getElementById("stamdata-dispatcher-title").textContent = id ? "Rediger disponentgruppe" : "Ny disponentgruppe";
  openModal("modal-stamdata-dispatcher");
}
```

Find i `loadStamdataDispatcherGroups()` (starten af filen, kør et engangs-setup af søgefeltets `oninput` – tilføj lige efter `openStamdataDispatcherModal`-funktionen, før `confirmStamdataDispatcher`):

```js
document.getElementById("stamdata-dispatcher-vehicle-search")?.addEventListener("input", function () {
  _renderVehicleSearchResults(this.value);
});
document.getElementById("stamdata-dispatcher-vehicle-search")?.addEventListener("focus", function () {
  _renderVehicleSearchResults(this.value);
});
```

- [ ] **Step 4: Opdater tabel-rendering og gem-funktion**

Find `loadStamdataDispatcherGroups()` (linje 4508-4533), find specifikt tabel-cellerne og "Rediger"-knappens `onclick`:

```js
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;color:var(--text-light)">${h(r.description || "")}</td>
        <td style="padding:10px 14px;text-align:center">${r.employee_count}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.visible_in_activity_overview, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataDispatcherModal(${r.id},${jq(r.name)},${jq(r.description || "")},${r.visible_in_activity_overview})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataDispatcher(${r.id},${jq(r.name)},${r.employee_count})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
```

Erstat med:

```js
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;color:var(--text-light)">${h(r.description || "")}</td>
        <td style="padding:10px 14px;text-align:center">${r.employee_count}</td>
        <td style="padding:10px 14px;text-align:center">${h(r.vehicle_number || "–")}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.visible_in_activity_overview, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataDispatcherModal(${r.id},${jq(r.name)},${jq(r.description || "")},${r.visible_in_activity_overview},${r.vehicle_id || "null"},${jq(r.vehicle_number || "")})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataDispatcher(${r.id},${jq(r.name)},${r.employee_count})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
```

Find `confirmStamdataDispatcher()` (linje 4551-4568):

```js
async function confirmStamdataDispatcher() {
  const id   = document.getElementById("stamdata-dispatcher-id").value;
  const name = document.getElementById("stamdata-dispatcher-name").value.trim();
  const description = document.getElementById("stamdata-dispatcher-description").value.trim();
  const visible = document.getElementById("stamdata-dispatcher-visible").checked;
  if (!name) { toast("Navn er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/dispatcher-groups/${id}`, { name, description, visible_in_activity_overview: visible });
      toast("Disponentgruppe opdateret");
    } else {
      await POST("/api/stamdata/dispatcher-groups", { name, description, visible_in_activity_overview: visible });
      toast("Disponentgruppe oprettet");
    }
    closeModal("modal-stamdata-dispatcher");
    await loadStamdataDispatcherGroups();
  } catch (e) { toast(e.message, "error"); }
}
```

Erstat med:

```js
async function confirmStamdataDispatcher() {
  const id   = document.getElementById("stamdata-dispatcher-id").value;
  const name = document.getElementById("stamdata-dispatcher-name").value.trim();
  const description = document.getElementById("stamdata-dispatcher-description").value.trim();
  const visible = document.getElementById("stamdata-dispatcher-visible").checked;
  const vehicleIdRaw = document.getElementById("stamdata-dispatcher-vehicle-id").value;
  const vehicle_id = vehicleIdRaw ? parseInt(vehicleIdRaw) : null;
  if (!name) { toast("Navn er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/dispatcher-groups/${id}`, { name, description, visible_in_activity_overview: visible, vehicle_id });
      toast("Disponentgruppe opdateret");
    } else {
      await POST("/api/stamdata/dispatcher-groups", { name, description, visible_in_activity_overview: visible, vehicle_id });
      toast("Disponentgruppe oprettet");
    }
    closeModal("modal-stamdata-dispatcher");
    await loadStamdataDispatcherGroups();
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 5: Manuel browser-verifikation**

I browserens konsol, efter at have åbnet Stamdata → Disponentgrupper:

```js
openStamdataDispatcherModal(null, "", "", true, null, "");
document.getElementById("stamdata-dispatcher-vehicle-search").value = state.vehicles[0]?.vehicle_number.slice(0, 1) || "";
_renderVehicleSearchResults(document.getElementById("stamdata-dispatcher-vehicle-search").value);
JSON.stringify({
  dropdownVisible: document.getElementById("stamdata-dispatcher-vehicle-dropdown").style.display === "block",
  itemCount: document.querySelectorAll(".vehicle-search-item").length,
});
```

Forventet: `dropdownVisible: true`, `itemCount` > 0 (mindst "— Intet køretøj —" + evt. matches). Klik (eller kald `_selectVehicleForDispatcherGroup(...)` direkte med et kendt køretøjs-id/nummer fra `state.vehicles`) og bekræft at søgefeltet udfyldes og `#stamdata-dispatcher-vehicle-id` sættes. Luk modalen uden at gemme.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: søgbart vognnummer-felt på disponentgrupper i Stamdata"
```

---

## Task 7: Frontend – vognnummer-autoudfyldning ved fravær + POST-rettelse

**Files:**
- Modify: `app/static/js/app.js:1619-1627` (`updateManualTypeVisibility`, tilføj kald), `:1924-1931` (`manual-employee`-onchange, tilføj kald), `:2135-2142` (flerdags-POST, manglende felt)

**Interfaces:**
- Consumes: `emp.dispatcher_group.vehicle_number` (fra Task 2's `EmployeeResponse`), `ABSENCE_TYPES` (eksisterende global Set)
- Produces: `applyDispatcherGroupVehicleDefault() -> void`

- [ ] **Step 1: Tilføj `applyDispatcherGroupVehicleDefault()` i `app/static/js/app.js`**

Find `applyBarselTerminsdatoDefault()` (linje 1629-1638):

```js
// Foreslår medarbejderens seneste registrerede terminsdato ved oprettelse af en ny barsel-aktivitet.
// force=true overskriver et allerede udfyldt felt (bruges ved skift af medarbejder).
function applyBarselTerminsdatoDefault(force = false) {
```

Tilføj lige før denne funktion:

```js
// Foreslår vognnummeret fra medarbejderens disponentgruppe ved fraværsregistrering.
// Overskriver ikke et allerede udfyldt felt.
function applyDispatcherGroupVehicleDefault() {
  const type = document.getElementById("manual-type").value;
  if (!ABSENCE_TYPES.has(type)) return;
  const regField = document.getElementById("manual-reg");
  if (regField.value.trim()) return;
  const empId = parseInt(document.getElementById("manual-employee").value);
  const emp = state.employees.find(e => e.id === empId);
  const vehicleNumber = emp?.dispatcher_group?.vehicle_number;
  if (vehicleNumber) {
    regField.value = vehicleNumber;
    regField.dispatchEvent(new Event("input"));
  }
}

```

- [ ] **Step 2: Kald funktionen fra `updateManualTypeVisibility()`**

Find (linje 1619-1627):

```js
  if (isFerie)        applyFerieDefaults();
  if (isSygdom)       applySygdomDefaults();
  if (isAfspadsering) applyAfspadseringDefaults();
  if (isFeriefri)     applyFeriefriDefaults();
  if (isBarsel) {
    applySygdomDefaults();
    applyBarselTerminsdatoDefault();
  }
}
```

Erstat med:

```js
  if (isFerie)        applyFerieDefaults();
  if (isSygdom)       applySygdomDefaults();
  if (isAfspadsering) applyAfspadseringDefaults();
  if (isFeriefri)     applyFeriefriDefaults();
  if (isBarsel) {
    applySygdomDefaults();
    applyBarselTerminsdatoDefault();
  }
  applyDispatcherGroupVehicleDefault();
}
```

- [ ] **Step 3: Kald funktionen fra `manual-employee`'s `onchange`-handler**

Find (linje 1924-1931):

```js
  document.getElementById("manual-employee").onchange = () => {
    const t = document.getElementById("manual-type").value;
    if (t === "ferie" || t === "selvbetalt_fridag") applyFerieDefaults();
    if (t === "sygdom" || t === "barn_1sygedag" || t === "paragraf_56_syg" || t === "skole_kursus" || t === "barsel") applySygdomDefaults();
    if (t === "afspadsering")                       applyAfspadseringDefaults();
    if (t === "feriefri")                           applyFeriefriDefaults();
    if (t === "barsel")                             applyBarselTerminsdatoDefault(true);
  };
```

Erstat med:

```js
  document.getElementById("manual-employee").onchange = () => {
    const t = document.getElementById("manual-type").value;
    if (t === "ferie" || t === "selvbetalt_fridag") applyFerieDefaults();
    if (t === "sygdom" || t === "barn_1sygedag" || t === "paragraf_56_syg" || t === "skole_kursus" || t === "barsel") applySygdomDefaults();
    if (t === "afspadsering")                       applyAfspadseringDefaults();
    if (t === "feriefri")                           applyFeriefriDefaults();
    if (t === "barsel")                             applyBarselTerminsdatoDefault(true);
    document.getElementById("manual-reg").value = "";
    document.getElementById("manual-reg-hint").textContent = "";
    applyDispatcherGroupVehicleDefault();
  };
```

(Feltet ryddes eksplicit ved medarbejderskift, før autoudfyldningen forsøges igen – ellers ville et vognnummer fra den tidligere valgte medarbejder blokere for at det nye foreslås, jf. "overskriv ikke hvis udfyldt"-reglen i `applyDispatcherGroupVehicleDefault()`.)

- [ ] **Step 4: Ret manglende `vehicle_number` i flerdags-fraværs-POST**

Find (linje 2135-2142):

```js
        await POST("/api/activities", {
          employee_id: empId,
          activity_type: actType,
          start_time:   iso + "T06:00:00",
          end_time:     iso + "T" + endH + ":" + endM + ":00",
          terminsdato:  terminsdato,
          source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
        });
```

Erstat med:

```js
        await POST("/api/activities", {
          employee_id: empId,
          activity_type: actType,
          start_time:   iso + "T06:00:00",
          end_time:     iso + "T" + endH + ":" + endM + ":00",
          terminsdato:  terminsdato,
          vehicle_number: foundVehicle?.vehicle_number || null,
          source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
        });
```

- [ ] **Step 5: Manuel browser-verifikation**

I browserens konsol, med en medarbejder der har en disponentgruppe med et vognnummer sat (opret evt. en test-tilknytning midlertidigt via Stamdata først):

```js
openManualActivityModal();
document.getElementById("manual-employee").value = "<id på en medarbejder med gruppe+vognnummer>";
document.getElementById("manual-employee").dispatchEvent(new Event("change"));
document.getElementById("manual-type").value = "ferie";
document.getElementById("manual-type").dispatchEvent(new Event("change"));
document.getElementById("manual-reg").value;
```

Forventet: feltet er udfyldt med gruppens vognnummer. Skift type til "Normal tid" og tilbage til "ferie" med feltet allerede udfyldt manuelt til noget andet → bekræft det IKKE overskrives. Ryd feltet og udfyld en periode ("Til dato") for en flerdags-ferie, opret aktiviteten, og bekræft via `fetch('/api/activities?...')` at `vehicle_number` er sat på hver oprettet aktivitet (regressionstest for den fundne fejl – husk at deaktivere/oprydde testaktiviteten bagefter, jf. tidligere sessions praksis for test i den rigtige database).

- [ ] **Step 6: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: vognnummer foreslås automatisk fra disponentgruppen ved fraværsregistrering"
```

---

## Task 8: Fuld testkørsel og CODEREF-opdatering

**Files:**
- Modify: `CODEREF.md`

- [ ] **Step 1: Kør hele test-suiten**

```bash
cd app && python -m pytest ../tests/ -v
```

Forventet: alle tests `PASSED`, ingen regressioner.

- [ ] **Step 2: Tilføj ny sektion i `CODEREF.md`**

Find den sidste sektion i filen og tilføj til sidst:

```markdown
---

## Disponentgruppe 1:1 + vognnummer-autoudfyldning ved fravær (2026-08-26)
`Employee.dispatcher_groups` (mange-til-mange) er erstattet af `Employee.dispatcher_group_id`/`dispatcher_group` (én gruppe, nullable). `EmployeeDispatcherGroup`-tabellen er fjernet (migreret af `_migrate_dispatcher_group_to_single()` i `session.py`, som ved konflikt beholder den alfabetisk først sorterede gruppe). `DispatcherGroup.vehicle_id`/`vehicle`/`vehicle_number` (property) peger på et køretøj i vognparken, vedligeholdt via Stamdata → Disponentgrupper (søgbart vognnummer-felt, brugerdefineret dropdown – ikke native `<datalist>`, af hensyn til konsistent substring-søgning på tværs af browsere). `app.js`s `applyDispatcherGroupVehicleDefault()` foreslår automatisk gruppens vognnummer i opret-aktivitet-modalens vognnummer-felt for enhver fraværstype (kun hvis feltet er tomt) – rent frontend-prefill, ingen backend-håndhævelse. Fejl rettet undervejs: flerdags-fraværsregistrering (`confirmManualActivity()`s range-gren) sendte tidligere slet ikke `vehicle_number` med i sit `POST /api/activities`-kald.
```

- [ ] **Step 3: Commit**

```bash
git add CODEREF.md
git commit -m "docs: dokumenter disponentgruppe-1:1 og vognnummer-autoudfyldning i CODEREF"
```

---

## Self-Review

**Spec coverage:**
- ✅ Datamodel: `Employee.dispatcher_group_id`/`dispatcher_group`, `DispatcherGroup.vehicle_id`/`vehicle`/`vehicle_number`, `EmployeeDispatcherGroup` fjernet
- ✅ Migration: idempotent, alfabetisk-først-konfliktløsning, dropper junction-tabel, manuel verifikation da rå SQL-migrationer ikke har automatiseret dækning i dette projekt (matcher eksisterende `_migrate_dispatcher_groups()`)
- ✅ API/schemas: `EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse`, `DispatcherGroupResponse`, `_resolve_dispatcher_group`, `model_fields_set`-baseret nulstilling
- ✅ Stamdata: `vehicle_id` på `DispatcherGroupBody`, valideret mod vognparken, kan sættes/fjernes
- ✅ Forbrugere: `payroll_router._active_employees()`, `absence_overview_router.employee_options()`/`export_per_employee()`
- ✅ Frontend medarbejder-modal: enkelt dropdown, `_empInGroup`/`_empHasVisibleGroup` og vagtplan-filtrene opdateret
- ✅ Frontend Stamdata: søgbar brugerdefineret vogn-dropdown (matcher eksplicit ønsket om "vis alle muligheder ved søgning", ikke native datalist), ny tabelkolonne
- ✅ Autoudfyldning: kun for fraværstyper, kun hvis tomt, ryddes ved medarbejderskift for at kunne genforeslås
- ✅ Rettelse af manglende `vehicle_number` i flerdags-POST
- ✅ De 3 eksisterende tests der ville knuse af modelændringen (`test_dob_overnatning.py`, `test_payroll_settlement.py`, `test_springertillaeg.py`) er rettet i Task 1, før noget andet bygger videre

**Placeholder-scan:** Ingen TBD/TODO – alle steps har konkret kode, eksakte linjenumre og kommandoer. De to steder der er markeret som "manuel verifikation" (migrationen i Task 1, browser-UI i Task 5-7) er det bevidst, jf. projektets eksisterende konventioner (ingen automatiseret dækning af rå SQL-migrationer; intet JS-testframework i projektet).

**Type-konsistens:**
- `Employee.dispatcher_group_id: int|None`, `.dispatcher_group: DispatcherGroup|None` bruges konsistent i Task 1, 2, 4, 5
- `DispatcherGroup.vehicle_id: int|None`, `.vehicle: Vehicle|None`, `.vehicle_number: str|None` bruges konsistent i Task 1, 3, 7
- `_resolve_dispatcher_group(db, group_id) -> Optional[DispatcherGroup]` (Task 2) matcher brugen i `create_employee`/`update_employee`
- `EmployeeResponse.dispatcher_group: Optional[DispatcherGroupResponse]` (Task 2) matcher `e.dispatcher_group?.id`/`.vehicle_number` i al frontend-kode (Task 5, 7)
- `DispatcherGroupBody.vehicle_id` (Task 3) matcher `confirmStamdataDispatcher()`s payload (Task 6)
