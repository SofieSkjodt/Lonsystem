# §56-advarsel som rollestyret permission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brugere med en ny rollestyret tilladelse ("§56-advarsel") får en pop-up når en medarbejders §56-slutdato er inden for 30 dage, og en separat pop-up når §56 automatisk er blevet deaktiveret pga. en overskredet slutdato. Afvisning er pr. bruger.

**Architecture:** Ny tabel `Paragraf56AlertDismissal` (employee_id + user_id + alert_type, unikt) holder pr.-bruger-afvisninger. Et sweep (`_sweep_expired_paragraf_56`) sætter `paragraf_56=false` for udløbne aftaler – kørt fra `list_employees()` (rammes af enhver bruger) så det ikke afhænger af permissionen, og datoerne bevares bevidst for at kunne indgå i "udløbet"-beskeden. Et nyt endpoint (`GET /paragraf56-alerts`) returnerer `{upcoming, expired}` filtreret på den aktuelle brugers afvisninger. Permissionen følger nøjagtig samme arkitektur som det eksisterende anciennitetsvarsel (dynamisk rollestyring, togglbar under Brugere → Roller uden ekstra frontend-arbejde).

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (backend, testet med pytest), vanilla JS/HTML (frontend, verificeret manuelt i browseren).

## Global Constraints

- Sweepet (dataens korrekthed) må ALDRIG afhænge af `paragraf_56_alert`-permissionen – det skal køre for enhver bruger, uanset rolle.
- Afvisning er pr. bruger – aldrig global på medarbejderen.
- Auto-deaktivering nulstiller IKKE `paragraf_56_start_date`/`paragraf_56_end_date` (i modsætning til en manuel afkrydsning-fra i modalen, som fortsat nulstiller dem).
- Ingen ny manuel DB-migration nødvendig for selve tabellen – `Base.metadata.create_all()` opretter nye tabeller automatisk ved opstart.
- Spec: `docs/superpowers/specs/2026-08-27-paragraf56-advarsel-design.md`

---

## Filstruktur

```
app/
  database/models.py      # MODIFY: ny Paragraf56AlertDismissal-klasse (efter Employee, linje ~99)
  database/schemas.py     # MODIFY: Paragraf56Alert/Paragraf56AlertsResponse/Paragraf56AlertDismiss (efter AnciennitetsAlert)
  database/session.py     # MODIFY: _ensure_paragraf_56_alert_permission() + kald fra init_db()
  auth.py                 # MODIFY: ny nøgle i ALL_PERMISSIONS
  routers/employees.py    # MODIFY: sweep, nye endpoints, update_employee-udvidelse
  templates/index.html    # MODIFY: ny modal-paragraf56-alert
  static/js/app.js        # MODIFY: PERMISSION_LABELS, checkParagraf56Alerts(), dismissParagraf56Alert(), loadApp()-hook
tests/
  test_paragraf_56_alert.py  # CREATE: backend-tests
```

---

## Task 1: Backend – datamodel, permission, sweep og endpoints

**Files:**
- Modify: `app/database/models.py`
- Modify: `app/database/schemas.py`
- Modify: `app/database/session.py`
- Modify: `app/auth.py`
- Modify: `app/routers/employees.py`
- Create: `tests/test_paragraf_56_alert.py`

**Interfaces:**
- Consumes: `Employee.paragraf_56/paragraf_56_start_date/paragraf_56_end_date` (allerede findes), `db`/`employee`-pytest-fixtures
- Produces: `Paragraf56AlertDismissal`-model, `_sweep_expired_paragraf_56(db) -> None`, `_paragraf56_alert(emp) -> Paragraf56Alert`, endpoints `GET /api/employees/paragraf56-alerts` og `POST /api/employees/{id}/dismiss-paragraf56-alert` i `app/routers/employees.py`

- [ ] **Step 1: Skriv de fejlende backend-tests i `tests/test_paragraf_56_alert.py`**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException

from database.models import AppUser, MasterAgreementType, MasterAgreementKind, Paragraf56AlertDismissal
from database.schemas import EmployeeUpdate, Paragraf56AlertDismiss


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _make_user(db, initials="USR1"):
    user = AppUser(name="Bruger", initials=initials, role="lonbogholder", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_agreement(db):
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.commit()


def test_sweep_deactivates_expired_paragraf_56(db, employee):
    from routers.employees import _sweep_expired_paragraf_56
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date(2026, 1, 1)
    employee.paragraf_56_end_date = date.today() - timedelta(days=1)
    db.commit()

    _sweep_expired_paragraf_56(db)
    db.refresh(employee)

    assert employee.paragraf_56 is False
    assert employee.paragraf_56_end_date == date.today() - timedelta(days=1)


def test_sweep_leaves_future_end_date_untouched(db, employee):
    from routers.employees import _sweep_expired_paragraf_56
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date.today()
    employee.paragraf_56_end_date = date.today() + timedelta(days=10)
    db.commit()

    _sweep_expired_paragraf_56(db)
    db.refresh(employee)

    assert employee.paragraf_56 is True


def test_list_employees_triggers_sweep(db, employee):
    from routers.employees import list_employees
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date(2026, 1, 1)
    employee.paragraf_56_end_date = date.today() - timedelta(days=1)
    db.commit()

    list_employees(active_only=False, current_user=_dummy_user(), db=db)
    db.refresh(employee)

    assert employee.paragraf_56 is False


def test_paragraf56_alerts_categorizes_upcoming(db, employee):
    from routers.employees import paragraf56_alerts
    user = _make_user(db)
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date.today()
    employee.paragraf_56_end_date = date.today() + timedelta(days=10)
    db.commit()

    result = paragraf56_alerts(current_user=user, db=db)

    assert len(result.upcoming) == 1
    assert result.upcoming[0].employee_id == employee.id
    assert len(result.expired) == 0


def test_paragraf56_alerts_categorizes_expired(db, employee):
    from routers.employees import paragraf56_alerts
    user = _make_user(db)
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date(2026, 1, 1)
    employee.paragraf_56_end_date = date.today() - timedelta(days=1)
    db.commit()

    result = paragraf56_alerts(current_user=user, db=db)

    assert len(result.expired) == 1
    assert result.expired[0].employee_id == employee.id
    assert len(result.upcoming) == 0


def test_paragraf56_alerts_ignores_employee_without_paragraf_56(db, employee):
    from routers.employees import paragraf56_alerts
    user = _make_user(db)

    result = paragraf56_alerts(current_user=user, db=db)

    assert result.upcoming == []
    assert result.expired == []


def test_paragraf56_alerts_excludes_outside_30_day_window(db, employee):
    from routers.employees import paragraf56_alerts
    user = _make_user(db)
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date.today()
    employee.paragraf_56_end_date = date.today() + timedelta(days=45)
    db.commit()

    result = paragraf56_alerts(current_user=user, db=db)

    assert result.upcoming == []


def test_dismiss_paragraf56_alert_is_per_user(db, employee):
    from routers.employees import paragraf56_alerts, dismiss_paragraf56_alert
    user_a = _make_user(db, "USRA")
    user_b = _make_user(db, "USRB")
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date.today()
    employee.paragraf_56_end_date = date.today() + timedelta(days=10)
    db.commit()

    dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="upcoming"), current_user=user_a, db=db)

    result_a = paragraf56_alerts(current_user=user_a, db=db)
    result_b = paragraf56_alerts(current_user=user_b, db=db)

    assert result_a.upcoming == []
    assert len(result_b.upcoming) == 1


def test_dismiss_paragraf56_alert_is_idempotent(db, employee):
    from routers.employees import dismiss_paragraf56_alert
    user = _make_user(db)

    dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="expired"), current_user=user, db=db)
    dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="expired"), current_user=user, db=db)

    count = db.query(Paragraf56AlertDismissal).filter(
        Paragraf56AlertDismissal.employee_id == employee.id,
        Paragraf56AlertDismissal.user_id == user.id,
    ).count()
    assert count == 1


def test_dismiss_paragraf56_alert_rejects_unknown_alert_type(db, employee):
    from routers.employees import dismiss_paragraf56_alert
    user = _make_user(db)

    with pytest.raises(HTTPException) as exc:
        dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="whatever"), current_user=user, db=db)
    assert exc.value.status_code == 400


def test_update_employee_clears_dismissals_when_end_date_changes(db, employee):
    from routers.employees import update_employee, dismiss_paragraf56_alert
    _seed_agreement(db)
    user = _make_user(db)
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date(2026, 1, 1)
    employee.paragraf_56_end_date = date(2026, 6, 1)
    db.commit()

    dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="upcoming"), current_user=user, db=db)
    assert db.query(Paragraf56AlertDismissal).filter(Paragraf56AlertDismissal.employee_id == employee.id).count() == 1

    update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 1, 1), paragraf_56_end_date=date(2026, 8, 1)),
        current_user=_dummy_user(), db=db,
    )

    assert db.query(Paragraf56AlertDismissal).filter(Paragraf56AlertDismissal.employee_id == employee.id).count() == 0
```

- [ ] **Step 2: Kør testene og bekræft de fejler**

Run: `cd app && python -m pytest ../tests/test_paragraf_56_alert.py -v`
Expected: FAIL – `Paragraf56AlertDismissal`, `Paragraf56AlertDismiss`, `_sweep_expired_paragraf_56` m.fl. findes ikke endnu

- [ ] **Step 3: Tilføj `Paragraf56AlertDismissal`-modellen i `app/database/models.py`**

Find:

```python
    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class PayPeriod(Base):
```

Erstat med:

```python
    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Paragraf56AlertDismissal(Base):
    __tablename__ = "paragraf_56_alert_dismissals"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False)
    alert_type = Column(String(20), nullable=False)  # "upcoming" | "expired"
    dismissed_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("employee_id", "user_id", "alert_type", name="uq_paragraf56_dismissal"),
    )


class PayPeriod(Base):
```

- [ ] **Step 4: Tilføj de nye schemas i `app/database/schemas.py`**

Find:

```python
class AnciennitetsAlert(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    hire_date: date
    months_employed: int
    suggested_agreement_type: Optional[str] = None
```

Erstat med:

```python
class AnciennitetsAlert(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    hire_date: date
    months_employed: int
    suggested_agreement_type: Optional[str] = None


class Paragraf56Alert(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    paragraf_56_end_date: date


class Paragraf56AlertsResponse(BaseModel):
    upcoming: list[Paragraf56Alert]
    expired: list[Paragraf56Alert]


class Paragraf56AlertDismiss(BaseModel):
    alert_type: str
```

- [ ] **Step 5: Tilføj permissionen i `app/auth.py`**

Find:

```python
    "anciennitet_alert":   "Anciennitetsvarsel",
```

Erstat med:

```python
    "anciennitet_alert":   "Anciennitetsvarsel",
    "paragraf_56_alert":   "§56-advarsel",
```

- [ ] **Step 6: Tilføj `_ensure_paragraf_56_alert_permission()` i `app/database/session.py`**

Find:

```python
def _ensure_anciennitet_alert_permission():
    """Tilføjer anciennitet_alert til lonbogholder-rollen (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "lonbogholder").first()
        if role and not role.is_system:
            perms = list(role.permissions or [])
            if "anciennitet_alert" not in perms:
                perms.append("anciennitet_alert")
                role.permissions = perms
                db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af anciennitet_alert-tilladelse: {e}")
    finally:
        db.close()
```

Erstat med:

```python
def _ensure_anciennitet_alert_permission():
    """Tilføjer anciennitet_alert til lonbogholder-rollen (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "lonbogholder").first()
        if role and not role.is_system:
            perms = list(role.permissions or [])
            if "anciennitet_alert" not in perms:
                perms.append("anciennitet_alert")
                role.permissions = perms
                db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af anciennitet_alert-tilladelse: {e}")
    finally:
        db.close()


def _ensure_paragraf_56_alert_permission():
    """Tilføjer paragraf_56_alert til lonbogholder-rollen (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "lonbogholder").first()
        if role and not role.is_system:
            perms = list(role.permissions or [])
            if "paragraf_56_alert" not in perms:
                perms.append("paragraf_56_alert")
                role.permissions = perms
                db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af paragraf_56_alert-tilladelse: {e}")
    finally:
        db.close()
```

Find:

```python
    _ensure_sh_pay_types()    # SH-løntypekoder kode 4 og 63
    _ensure_anciennitet_alert_permission()
```

Erstat med:

```python
    _ensure_sh_pay_types()    # SH-løntypekoder kode 4 og 63
    _ensure_anciennitet_alert_permission()
    _ensure_paragraf_56_alert_permission()
```

- [ ] **Step 7: Udvid `app/routers/employees.py` – imports, sweep, endpoints, update_employee**

Find:

```python
from datetime import date, datetime
from typing import Optional
```

Erstat med:

```python
from datetime import date, datetime, timedelta
from typing import Optional
```

Find:

```python
from database.models import AppUser, DispatcherGroup, Employee, MasterAgreementKind
from database.schemas import (
    AnciennitetsAlert,
    DispatcherGroupResponse,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
    WorkSchedule,
)
```

Erstat med:

```python
from database.models import AppUser, DispatcherGroup, Employee, MasterAgreementKind, Paragraf56AlertDismissal
from database.schemas import (
    AnciennitetsAlert,
    DispatcherGroupResponse,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
    Paragraf56Alert,
    Paragraf56AlertDismiss,
    Paragraf56AlertsResponse,
    WorkSchedule,
)
```

Find:

```python
def _validate_paragraf_56(active: bool, start: Optional[date], end: Optional[date]) -> tuple:
    if not active:
        return None, None
    if not start or not end:
        raise HTTPException(400, "Start- og slutdato for §56 skal udfyldes")
    if end < start:
        raise HTTPException(400, "§56 slutdato skal være efter startdato")
    return start, end
```

Erstat med:

```python
def _validate_paragraf_56(active: bool, start: Optional[date], end: Optional[date]) -> tuple:
    if not active:
        return None, None
    if not start or not end:
        raise HTTPException(400, "Start- og slutdato for §56 skal udfyldes")
    if end < start:
        raise HTTPException(400, "§56 slutdato skal være efter startdato")
    return start, end


def _sweep_expired_paragraf_56(db: Session) -> None:
    """Deaktiverer automatisk §56 for medarbejdere hvor slutdatoen er overskredet.
    Kører uafhængigt af paragraf_56_alert-tilladelsen (se list_employees()), så
    deaktiveringen sker uanset hvilke roller der har advarslen slået til. Datoerne
    bevares bevidst (ikke nulstillet), så de kan indgå i "udløbet"-informationen."""
    today = date.today()
    expired = db.query(Employee).filter(
        Employee.paragraf_56 == True,
        Employee.paragraf_56_end_date.isnot(None),
        Employee.paragraf_56_end_date < today,
    ).all()
    for emp in expired:
        emp.paragraf_56 = False
    if expired:
        db.commit()


def _paragraf56_alert(emp: Employee) -> Paragraf56Alert:
    return Paragraf56Alert(
        employee_id=emp.id,
        employee_name=emp.name,
        employee_number=emp.employee_number,
        paragraf_56_end_date=emp.paragraf_56_end_date,
    )
```

Find:

```python
@router.get("", response_model=list[EmployeeResponse])
def list_employees(active_only: bool = True,
                   current_user: AppUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    q = db.query(Employee)
    if active_only:
        q = q.filter(Employee.active == True)
    return [_to_response(e, db) for e in q.order_by(Employee.last_name, Employee.first_name).all()]
```

Erstat med:

```python
@router.get("", response_model=list[EmployeeResponse])
def list_employees(active_only: bool = True,
                   current_user: AppUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    _sweep_expired_paragraf_56(db)
    q = db.query(Employee)
    if active_only:
        q = q.filter(Employee.active == True)
    return [_to_response(e, db) for e in q.order_by(Employee.last_name, Employee.first_name).all()]
```

Find:

```python
@router.post("/{employee_id}/dismiss-anciennitet", status_code=204)
def dismiss_anciennitet(employee_id: int,
                        current_user: AppUser = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Marker anciennitetsadvarsel som afvist for denne medarbejder."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    emp.anciennitet_dismissed_at = datetime.utcnow()
    db.commit()


@router.get("/{employee_id}", response_model=EmployeeResponse)
```

Erstat med:

```python
@router.post("/{employee_id}/dismiss-anciennitet", status_code=204)
def dismiss_anciennitet(employee_id: int,
                        current_user: AppUser = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Marker anciennitetsadvarsel som afvist for denne medarbejder."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    emp.anciennitet_dismissed_at = datetime.utcnow()
    db.commit()


@router.get("/paragraf56-alerts", response_model=Paragraf56AlertsResponse)
def paragraf56_alerts(current_user: AppUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """
    §56-advarsler for den aktuelle bruger: 'upcoming' (slutdato inden for 30 dage,
    §56 stadig aktiv) og 'expired' (§56 netop auto-deaktiveret pga. overskredet
    slutdato). Afvisning er pr. bruger (Paragraf56AlertDismissal), ikke global.
    """
    _sweep_expired_paragraf_56(db)
    today = date.today()
    window = today + timedelta(days=30)
    dismissed = {
        (d.employee_id, d.alert_type)
        for d in db.query(Paragraf56AlertDismissal).filter(
            Paragraf56AlertDismissal.user_id == current_user.id
        ).all()
    }
    upcoming = [
        _paragraf56_alert(e) for e in db.query(Employee).filter(
            Employee.paragraf_56 == True,
            Employee.paragraf_56_end_date.isnot(None),
            Employee.paragraf_56_end_date >= today,
            Employee.paragraf_56_end_date <= window,
        ).all()
        if (e.id, "upcoming") not in dismissed
    ]
    expired = [
        _paragraf56_alert(e) for e in db.query(Employee).filter(
            Employee.paragraf_56 == False,
            Employee.paragraf_56_end_date.isnot(None),
            Employee.paragraf_56_end_date < today,
        ).all()
        if (e.id, "expired") not in dismissed
    ]
    return Paragraf56AlertsResponse(upcoming=upcoming, expired=expired)


@router.post("/{employee_id}/dismiss-paragraf56-alert", status_code=204)
def dismiss_paragraf56_alert(employee_id: int, body: Paragraf56AlertDismiss,
                             current_user: AppUser = Depends(get_current_user),
                             db: Session = Depends(get_db)):
    """Marker en §56-advarsel som afvist for DEN AKTUELLE BRUGER (ikke globalt)."""
    if body.alert_type not in ("upcoming", "expired"):
        raise HTTPException(400, f"Ukendt alert_type: {body.alert_type}")
    existing = db.query(Paragraf56AlertDismissal).filter(
        Paragraf56AlertDismissal.employee_id == employee_id,
        Paragraf56AlertDismissal.user_id == current_user.id,
        Paragraf56AlertDismissal.alert_type == body.alert_type,
    ).first()
    if not existing:
        db.add(Paragraf56AlertDismissal(
            employee_id=employee_id, user_id=current_user.id, alert_type=body.alert_type
        ))
        db.commit()


@router.get("/{employee_id}", response_model=EmployeeResponse)
```

Find:

```python
    if "paragraf_56" in body.model_fields_set:
        start, end = _validate_paragraf_56(
            bool(body.paragraf_56), body.paragraf_56_start_date, body.paragraf_56_end_date
        )
        emp.paragraf_56 = bool(body.paragraf_56)
        emp.paragraf_56_start_date = start
        emp.paragraf_56_end_date = end
```

Erstat med:

```python
    if "paragraf_56" in body.model_fields_set:
        start, end = _validate_paragraf_56(
            bool(body.paragraf_56), body.paragraf_56_start_date, body.paragraf_56_end_date
        )
        if end != emp.paragraf_56_end_date:
            db.query(Paragraf56AlertDismissal).filter(
                Paragraf56AlertDismissal.employee_id == emp.id
            ).delete()
        emp.paragraf_56 = bool(body.paragraf_56)
        emp.paragraf_56_start_date = start
        emp.paragraf_56_end_date = end
```

- [ ] **Step 8: Kør de nye tests og bekræft de består**

Run: `cd app && python -m pytest ../tests/test_paragraf_56_alert.py -v`
Expected: PASS – alle 11 tests grønne

- [ ] **Step 9: Kør hele test-suiten for at udelukke regression**

Run: `cd app && python -m pytest ../tests -q`
Expected: PASS – alle tests grønne (217 eksisterende + 11 nye = 228)

- [ ] **Step 10: Commit**

```bash
git add app/database/models.py app/database/schemas.py app/database/session.py app/auth.py app/routers/employees.py tests/test_paragraf_56_alert.py
git commit -m "feat: §56-advarsel som rollestyret permission (backend)"
```

---

## Task 2: Frontend – popup, afvisning og permission-label

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`

**Interfaces:**
- Consumes: `Paragraf56AlertsResponse` (`{upcoming: Paragraf56Alert[], expired: Paragraf56Alert[]}`), `GET`/`POST`-hjælperne, `formatDateShort()`, `h()`, `setView()`, `openEditEmployee()` (alle eksisterende)
- Produces: `checkParagraf56Alerts() -> void`, `dismissParagraf56Alert(employeeId: int, alertType: string) -> void` – nye globale funktioner i `app.js`

- [ ] **Step 1: Tilføj `modal-paragraf56-alert` i `app/templates/index.html`, lige efter `modal-anciennitet`**

Find:

```html
<div id="modal-anciennitet" class="modal-overlay">
  <div class="modal" style="width:460px">
    <div class="modal-header">
      <h2>&#128197; Ny anciennitetsstatus</h2>
      <button class="modal-close" onclick="closeModal('modal-anciennitet')">&#215;</button>
    </div>
    <div class="modal-body" id="anciennitet-body"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-anciennitet')">Luk</button>
      <button class="btn btn-warning" id="btn-anciennitet-done">Ændring foretaget</button>
      <button class="btn btn-primary" id="btn-goto-employee">Gå til medarbejder</button>
    </div>
  </div>
</div>
```

Erstat med:

```html
<div id="modal-anciennitet" class="modal-overlay">
  <div class="modal" style="width:460px">
    <div class="modal-header">
      <h2>&#128197; Ny anciennitetsstatus</h2>
      <button class="modal-close" onclick="closeModal('modal-anciennitet')">&#215;</button>
    </div>
    <div class="modal-body" id="anciennitet-body"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-anciennitet')">Luk</button>
      <button class="btn btn-warning" id="btn-anciennitet-done">Ændring foretaget</button>
      <button class="btn btn-primary" id="btn-goto-employee">Gå til medarbejder</button>
    </div>
  </div>
</div>

<div id="modal-paragraf56-alert" class="modal-overlay">
  <div class="modal" style="width:460px">
    <div class="modal-header">
      <h2 id="paragraf56-alert-title">&#9888; §56-advarsel</h2>
      <button class="modal-close" onclick="closeModal('modal-paragraf56-alert')">&#215;</button>
    </div>
    <div class="modal-body" id="paragraf56-alert-body"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-paragraf56-alert')">Luk</button>
      <button class="btn btn-warning" id="btn-paragraf56-alert-done">Set – afvis</button>
      <button class="btn btn-primary" id="btn-goto-employee-paragraf56">Gå til medarbejder</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Tilføj permission-label i `app/static/js/app.js`**

Find:

```js
  anciennitet_alert:   "Anciennitetsvarsel",
```

Erstat med:

```js
  anciennitet_alert:   "Anciennitetsvarsel",
  paragraf_56_alert:   "§56-advarsel",
```

- [ ] **Step 3: Tilføj `checkParagraf56Alerts()` og `dismissParagraf56Alert()`, lige efter anciennitet-blokken**

Find:

```js
    document.getElementById("btn-goto-employee").onclick = async () => {
      closeModal("modal-anciennitet");
      setView("employees");
      await loadEmployees();
      openEditEmployee(a.employee_id);
    };
    document.getElementById("btn-anciennitet-done").onclick = () => dismissAnciennitetsAlert(a.employee_id);
    openModal("modal-anciennitet");
  } catch (e) {
    console.error("Anciennitet check fejlede:", e);
  }
}

// ── Vehicles ────────────────────────────────────────────────────────────────
```

Erstat med:

```js
    document.getElementById("btn-goto-employee").onclick = async () => {
      closeModal("modal-anciennitet");
      setView("employees");
      await loadEmployees();
      openEditEmployee(a.employee_id);
    };
    document.getElementById("btn-anciennitet-done").onclick = () => dismissAnciennitetsAlert(a.employee_id);
    openModal("modal-anciennitet");
  } catch (e) {
    console.error("Anciennitet check fejlede:", e);
  }
}

// ── §56-advarsel popup ──────────────────────────────────────────────────────
async function dismissParagraf56Alert(employeeId, alertType) {
  try {
    await POST(`/api/employees/${employeeId}/dismiss-paragraf56-alert`, { alert_type: alertType });
  } catch (e) {
    console.error("Kunne ikke gemme afvisning af §56-advarsel:", e);
  }
  closeModal("modal-paragraf56-alert");
}

async function checkParagraf56Alerts() {
  if (!state.currentUser?.permissions?.includes("paragraf_56_alert")) return;
  try {
    const { upcoming, expired } = await GET("/api/employees/paragraf56-alerts");
    const alertType = expired.length ? "expired" : "upcoming";
    const alerts = expired.length ? expired : upcoming;
    if (alerts.length === 0) return;
    const a = alerts[0];
    document.getElementById("paragraf56-alert-title").innerHTML = alertType === "expired"
      ? "&#9888; §56 automatisk deaktiveret"
      : "&#128197; §56 udløber snart";
    document.getElementById("paragraf56-alert-body").innerHTML = alertType === "expired"
      ? `
        <p style="font-size:14px;margin-bottom:8px">
          Medarbejder <strong>${h(a.employee_name)} (${h(a.employee_number)})</strong>s §56-aftale er automatisk
          deaktiveret, da slutdatoen (${formatDateShort(a.paragraf_56_end_date)}) er overskredet.
        </p>
        ${alerts.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${alerts.length - 1} flere medarbejdere.</p>` : ""}
      `
      : `
        <p style="font-size:14px;margin-bottom:8px">
          Medarbejder <strong>${h(a.employee_name)} (${h(a.employee_number)})</strong>s §56-aftale udløber
          ${formatDateShort(a.paragraf_56_end_date)}.
        </p>
        ${alerts.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${alerts.length - 1} flere medarbejdere.</p>` : ""}
      `;
    document.getElementById("btn-goto-employee-paragraf56").onclick = async () => {
      closeModal("modal-paragraf56-alert");
      setView("employees");
      await loadEmployees();
      openEditEmployee(a.employee_id);
    };
    document.getElementById("btn-paragraf56-alert-done").onclick = () => dismissParagraf56Alert(a.employee_id, alertType);
    openModal("modal-paragraf56-alert");
  } catch (e) {
    console.error("§56-advarsel check fejlede:", e);
  }
}

// ── Vehicles ────────────────────────────────────────────────────────────────
```

- [ ] **Step 4: Kald `checkParagraf56Alerts()` fra `loadApp()`**

Find:

```js
  await loadAbsenceTypes();
  await setView("activities");
  await checkAnciennitetsAlerts();
}
```

Erstat med:

```js
  await loadAbsenceTypes();
  await setView("activities");
  await checkAnciennitetsAlerts();
  await checkParagraf56Alerts();
}
```

- [ ] **Step 5: Manuel browser-verifikation**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet.

1. Log ind som admin → Brugere → Roller → bekræft at "§56-advarsel" nu findes som togglbar tilladelse (uden ekstra frontend-arbejde, jf. dynamisk rollestyring) – bekræft at `lonbogholder` allerede har den slået til som udgangspunkt.
2. Åbn en medarbejder uden §56 → sæt §56 til med slutdato om 10 dage (inden for 30-dages-vinduet) → gem.
3. Log ind som en bruger med rollen `lonbogholder` (fx testbrugeren "TESTER") → bekræft at §56-advarsels-popup'en vises automatisk ved indlæsning, med korrekt medarbejdernavn og slutdato.
4. Klik "Set – afvis" → bekræft popup'en lukker. Genindlæs siden → bekræft at popup'en IKKE vises igen for denne bruger.
5. Log ind som en ANDEN bruger med samme rolle/tilladelse (fx en anden testbruger, eller midlertidigt tildel `disponent`-rollen tilladelsen) → bekræft at popup'en STADIG vises for denne bruger (pr.-bruger-afvisning, ikke global).
6. Sæt medarbejderens §56-slutdato til i går (direkte i databasen, da UI'et ikke tillader fortidsdatoer i det påkrævede felt – eller brug en dato der lige akkurat er passeret) → genindlæs siden som en bruger med tilladelsen → bekræft: (a) medarbejderens §56-felt er nu automatisk slået fra ved opslag i medarbejderlisten, og (b) der vises i stedet en "§56 automatisk deaktiveret"-info-popup med den korrekte (bevarede) slutdato.
7. Afvis info-popup'en → genindlæs → bekræft ingen flere popups for denne medarbejder/bruger.
8. Log ind som en bruger UDEN tilladelsen (fx `disponent`, medmindre den blev tildelt i punkt 5 – brug i så fald en tredje rolle) → bekræft at ingen §56-popup vises, uanset om der er aktive advarsler.
9. Ret medarbejderens §56-slutdato til en ny fremtidig dato → bekræft (via databasen eller ved at gentage punkt 3-4) at en tidligere afvisning nu er nulstillet, og advarslen kan dukke op igen.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: §56-advarsel som rollestyret permission (frontend)"
```

---

## Self-Review

**Spec coverage:**
- ✅ Ny `Paragraf56AlertDismissal`-tabel, pr.-bruger-afvisning – Task 1, Step 3
- ✅ Sweep kører uafhængigt af permissionen, via `list_employees()` – Task 1, Step 7
- ✅ Datoer bevares ved auto-deaktivering – Task 1, Step 7 (`_sweep_expired_paragraf_56`)
- ✅ Ny permission, idempotent tildelt `lonbogholder` som udgangspunkt, admin altid – Task 1, Step 5-6
- ✅ `GET /paragraf56-alerts` (upcoming + expired, pr.-bruger-filtreret) og `POST /dismiss-paragraf56-alert` – Task 1, Step 7
- ✅ `update_employee` nulstiller afvisninger ved ændret slutdato – Task 1, Step 7
- ✅ To adskilte popup-tilstande (upcoming/expired), samme knap-mønster som anciennitet – Task 2, Step 1 og 3
- ✅ Permission-label synkroniseret mellem backend og frontend – Task 1 Step 5 + Task 2 Step 2
- ✅ Ingen ændring af §56 syg-fraværstype/aktivitetslogik eller Brugervejledningen – ingen af de filer røres

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, testene indeholder konkrete assertions, verifikationstrinnet har konkrete handlinger og forventede resultater.

**Type-konsistens:** `_sweep_expired_paragraf_56(db: Session) -> None`, `_paragraf56_alert(emp: Employee) -> Paragraf56Alert`, `paragraf56_alerts(...) -> Paragraf56AlertsResponse`, `dismiss_paragraf56_alert(employee_id: int, body: Paragraf56AlertDismiss, ...) -> None` defineres i Task 1 og bruges konsistent i testene (Step 1) og i frontend-kaldene (Task 2, Step 3: `GET("/api/employees/paragraf56-alerts")` destrukturerer `{upcoming, expired}` som matcher `Paragraf56AlertsResponse`s felter; `POST(".../dismiss-paragraf56-alert", {alert_type})` matcher `Paragraf56AlertDismiss.alert_type`). HTML-id'erne (`paragraf56-alert-title`, `paragraf56-alert-body`, `btn-paragraf56-alert-done`, `btn-goto-employee-paragraf56`) er bevidst forskellige fra anciennitet-modalens id'er for at undgå dubletter i DOM'et – bekræftet ved sammenligning af Task 2 Step 1 og Step 3.
