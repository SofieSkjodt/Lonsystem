# Global til/fra-kontakt for auto-godkendelse – Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giv en admin (eller en bruger med en ny dedikeret permission) mulighed for at slå
BEGGE eksisterende auto-godkendelsesmekanismer (statistisk baseline-godkendelse ved
DDD-import/bulk-knap, og permission-baseret godkendelse ved manuel oprettelse) fra
globalt via én knap i en ny "Auto-godkendelse"-fane under Stamdata.

**Architecture:** Ny singleton-tabel `SystemSettings` (id altid 1) holder ét boolean-flag
`auto_approval_enabled`. En delt hjælpefunktion `is_auto_approval_enabled(db)` (i
`calculators/baseline_updater.py`, fail-open til `True` hvis recorden mangler) læses fra
de tre eksisterende beslutningspunkter (`should_auto_approve`, `update_baseline_from_activity`,
`create_manual_activity`) plus et nyt guard i bulk-endpointet. Et nyt `manage_auto_approval`-
permission gater et nyt GET/POST-endpointpar der læser/skriver flaget.

**Tech Stack:** FastAPI + SQLAlchemy (Python-backend), vanilla JS + Jinja2-templates
(frontend), pytest (test), SQLite.

## Global Constraints

- Begge eksisterende auto-godkendelsesmekanismer styres af ÉN global kontakt (bekræftet af bruger).
- Fraværstypers (ferie, sygdom, osv.) automatiske godkendelse ved manuel oprettelse
  påvirkes IKKE af kontakten – det er uændret adfærd uanset kontaktens tilstand.
- Ny permission `manage_auto_approval`, label "Slå auto-godkendelse til/fra". Default:
  KUN `admin` (implicit som systemrolle + eksplicit i admins permissions-liste, jf.
  eksisterende `manage_baselines`-mønster). Ikke `lonbogholder`, ikke `disponent`.
- Når kontakten er fra: bulk-knappen "Autogodkend aktiviteter" i aktivitetsoversigten
  skjules helt (`display:none`), ikke gråtonet.
- Baseline-læring (`EmployeeBaseline`-opdatering) stoppes HELT når kontakten er fra –
  også ved manuel godkendelse, ikke kun ved selve auto-godkendelses-beslutningen.
- Ny fane "Auto-godkendelse" tilføjes under den eksisterende Stamdata-visning (ikke som
  nyt sidebar-punkt, ikke under Brugerstyring).
- UI-kontrollen er en KNAP (ikke en toggle-switch), matcher eksisterende `btn-success`/
  `btn-danger`-mønster brugt andre steder i appen.
- Manglende `SystemSettings`-record (ikke-migreret/frisk test-DB) tolkes altid som
  "slået til" (`True`) – matcher default-værdien og undgår at bryde alle eksisterende
  tests i `test_auto_approval.py`/`test_baseline_updater.py`, som ikke seeder recorden.
- Spec: `docs/superpowers/specs/2026-08-27-global-auto-godkendelse-kontakt-design.md`

---

## Task 1: SystemSettings-model + is_auto_approval_enabled()-hjælpefunktion

**Files:**
- Modify: `app/database/models.py:396-401`
- Modify: `app/calculators/baseline_updater.py:1-10`
- Modify: `tests/conftest.py` (tilføj hjælpefunktion i slutningen)
- Create: `tests/test_system_settings.py`

**Interfaces:**
- Produces: `SystemSettings` model (`app/database/models.py`) med felter
  `id`, `auto_approval_enabled` (bool), `updated_by` (str|None), `updated_at` (datetime|None).
- Produces: `is_auto_approval_enabled(db: Session) -> bool` i `app/calculators/baseline_updater.py`.
- Produces: `set_auto_approval_enabled(db, enabled: bool) -> SystemSettings` testhjælper i `tests/conftest.py`.

- [ ] **Step 1: Skriv de fejlende tests**

Opret `tests/test_system_settings.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from database.models import SystemSettings
from calculators.baseline_updater import is_auto_approval_enabled
from conftest import set_auto_approval_enabled


def test_system_settings_model_exists():
    assert hasattr(SystemSettings, 'auto_approval_enabled')
    assert hasattr(SystemSettings, 'updated_by')
    assert hasattr(SystemSettings, 'updated_at')


def test_is_auto_approval_enabled_defaults_true_without_row(db):
    assert db.query(SystemSettings).count() == 0
    assert is_auto_approval_enabled(db) is True


def test_is_auto_approval_enabled_reflects_row_value(db):
    set_auto_approval_enabled(db, False)
    assert is_auto_approval_enabled(db) is False
    set_auto_approval_enabled(db, True)
    assert is_auto_approval_enabled(db) is True
```

Tilføj testhjælperen i `tests/conftest.py`, efter den eksisterende `make_activity`-funktion (sidst i filen):

```python
def set_auto_approval_enabled(db, enabled: bool):
    """Testhjælper: opret/opdater singleton SystemSettings-recorden direkte."""
    from database.models import SystemSettings
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if settings is None:
        settings = SystemSettings(id=1, auto_approval_enabled=enabled)
        db.add(settings)
    else:
        settings.auto_approval_enabled = enabled
    db.commit()
    return settings
```

- [ ] **Step 2: Kør testen for at bekræfte den fejler**

Run: `python -m pytest tests/test_system_settings.py -v`
Expected: FAIL – `ImportError: cannot import name 'SystemSettings'` (modellen findes ikke endnu)

- [ ] **Step 3: Tilføj SystemSettings-modellen**

I `app/database/models.py`, find (linje 396-401):

```python
    last_updated = Column(DateTime, nullable=True)

    employee = relationship("Employee", back_populates="baselines")


class EmployeeSupplement(Base):
```

Erstat med:

```python
    last_updated = Column(DateTime, nullable=True)

    employee = relationship("Employee", back_populates="baselines")


class SystemSettings(Base):
    """Singleton-tabel (id altid 1) til globale systemindstillinger."""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    auto_approval_enabled = Column(Boolean, default=True, nullable=False, server_default="1")
    updated_by = Column(String, nullable=True)   # initialer på seneste bruger der ændrede
    updated_at = Column(DateTime, nullable=True)


class EmployeeSupplement(Base):
```

- [ ] **Step 4: Tilføj is_auto_approval_enabled()-hjælpefunktionen**

I `app/calculators/baseline_updater.py`, find (linje 1-10):

```python
from datetime import datetime

from sqlalchemy.orm import Session

from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline


_SAME_THRESHOLD_MINUTES = 0.5   # < 30 sekunder forskel = uændret
_SAME_THRESHOLD_HOURS  = 1 / 60  # < 1 minut forskel i starttid = uændret
```

Erstat med:

```python
from datetime import datetime

from sqlalchemy.orm import Session

from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline, SystemSettings


_SAME_THRESHOLD_MINUTES = 0.5   # < 30 sekunder forskel = uændret
_SAME_THRESHOLD_HOURS  = 1 / 60  # < 1 minut forskel i starttid = uændret


def is_auto_approval_enabled(db: Session) -> bool:
    """Global til/fra-kontakt for auto-godkendelse (Stamdata → Auto-godkendelse).
    Manglende record (endnu ikke migreret/seedet DB) tolkes som slået til (default)."""
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    return settings.auto_approval_enabled if settings is not None else True
```

- [ ] **Step 5: Kør testen for at bekræfte den nu passerer**

Run: `python -m pytest tests/test_system_settings.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Kør hele test-suiten for at sikre ingen regressioner**

Run: `python -m pytest tests/ -q`
Expected: Alle tests passerer (ingen regressioner fra den nye kolonne/import)

- [ ] **Step 7: Commit**

```bash
git add app/database/models.py app/calculators/baseline_updater.py tests/conftest.py tests/test_system_settings.py
git commit -m "feat: tilføj SystemSettings-model og is_auto_approval_enabled()-hjælper"
```

---

## Task 2: manage_auto_approval-permission + seeding/migration

**Files:**
- Modify: `app/auth.py:25-33`
- Modify: `app/database/session.py:44-64` (init_db + _seed_roles)
- Modify: `app/database/session.py` (tilføj to nye `_ensure_*`-funktioner)
- Modify: `tests/test_system_settings.py` (tilføj flere tests)

**Interfaces:**
- Consumes: `SystemSettings` model fra Task 1.
- Produces: `"manage_auto_approval"` i `ALL_PERMISSIONS` (`app/auth.py`).
- Produces: `_ensure_manage_auto_approval_permission()` og `_ensure_system_settings()`
  i `app/database/session.py`, begge kaldt fra `init_db()`.

- [ ] **Step 1: Skriv de fejlende tests**

Tilføj til `tests/test_system_settings.py` (efter de eksisterende tests):

```python
from sqlalchemy.orm import sessionmaker


def test_all_permissions_includes_manage_auto_approval():
    from auth import ALL_PERMISSIONS
    assert "manage_auto_approval" in ALL_PERMISSIONS
    assert ALL_PERMISSIONS["manage_auto_approval"] == "Slå auto-godkendelse til/fra"


def test_seed_roles_grants_manage_auto_approval_to_admin_only(db, monkeypatch):
    import database.session as session_module
    from database.models import Role

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    assert db.query(Role).count() == 0

    session_module._seed_roles()

    admin = db.query(Role).filter(Role.name == "admin").first()
    assert "manage_auto_approval" in admin.permissions

    lonbogholder = db.query(Role).filter(Role.name == "lonbogholder").first()
    assert "manage_auto_approval" not in lonbogholder.permissions

    disponent = db.query(Role).filter(Role.name == "disponent").first()
    assert "manage_auto_approval" not in disponent.permissions


def test_ensure_manage_auto_approval_permission_is_idempotent(db, monkeypatch):
    import database.session as session_module
    from database.models import Role

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.commit()

    session_module._ensure_manage_auto_approval_permission()
    admin = db.query(Role).filter(Role.name == "admin").first()
    db.refresh(admin)
    assert "manage_auto_approval" in admin.permissions

    session_module._ensure_manage_auto_approval_permission()
    db.refresh(admin)
    assert admin.permissions.count("manage_auto_approval") == 1


def test_ensure_system_settings_creates_default_row_and_is_idempotent(db, monkeypatch):
    import database.session as session_module
    from database.models import SystemSettings

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    assert db.query(SystemSettings).count() == 0

    session_module._ensure_system_settings()
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    assert settings is not None
    assert settings.auto_approval_enabled is True

    session_module._ensure_system_settings()
    assert db.query(SystemSettings).count() == 1
```

- [ ] **Step 2: Kør testene for at bekræfte de fejler**

Run: `python -m pytest tests/test_system_settings.py -v`
Expected: De 4 nye tests FAIL (`KeyError`/`AttributeError` – permission og funktioner findes ikke endnu)

- [ ] **Step 3: Tilføj permissionen til ALL_PERMISSIONS**

I `app/auth.py`, find:

```python
    "auto_approve_manual_activities": "Auto-godkend ved oprettelse",
    "view_calendar":       "Se aktivitetskalender",
```

Erstat med:

```python
    "auto_approve_manual_activities": "Auto-godkend ved oprettelse",
    "manage_auto_approval": "Slå auto-godkendelse til/fra",
    "view_calendar":       "Se aktivitetskalender",
```

- [ ] **Step 4: Tilføj permissionen til admins default-liste i _seed_roles()**

I `app/database/session.py`, find:

```python
                Role(name="admin", display_name="Administrator", is_system=True,
                     permissions=["payroll", "import_ddd", "user_management", "reopen_period", "manage_baselines", "approve_activities", "view_calendar"]),
```

Erstat med:

```python
                Role(name="admin", display_name="Administrator", is_system=True,
                     permissions=["payroll", "import_ddd", "user_management", "reopen_period", "manage_baselines", "manage_auto_approval", "approve_activities", "view_calendar"]),
```

- [ ] **Step 5: Tilføj de to nye idempotente migrationsfunktioner**

I `app/database/session.py`, find `_ensure_manage_baselines_permission()` (slutter lige før `_ensure_auto_approve_permission()`):

```python
def _ensure_auto_approve_permission():
    """Tilføjer auto_approve_manual_activities til lonbogholder-rollen (idempotent)."""
```

Indsæt to nye funktioner LIGE FØR denne linje (dvs. umiddelbart efter `_ensure_manage_baselines_permission()` slutter):

```python
def _ensure_manage_auto_approval_permission():
    """Tilføjer manage_auto_approval til admin-rollen (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "admin").first()
        if role:
            perms = list(role.permissions or [])
            if "manage_auto_approval" not in perms:
                perms.append("manage_auto_approval")
                role.permissions = perms
                db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af manage_auto_approval-tilladelse: {e}")
    finally:
        db.close()


def _ensure_system_settings():
    """Opretter singleton-recorden for systemindstillinger hvis den mangler (idempotent)."""
    from database.models import SystemSettings
    db = SessionLocal()
    try:
        if db.query(SystemSettings).filter(SystemSettings.id == 1).first() is None:
            db.add(SystemSettings(id=1, auto_approval_enabled=True))
            db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved oprettelse af systemindstillinger: {e}")
    finally:
        db.close()


def _ensure_auto_approve_permission():
    """Tilføjer auto_approve_manual_activities til lonbogholder-rollen (idempotent)."""
```

- [ ] **Step 6: Wire funktionerne ind i init_db()**

I `app/database/session.py`, find:

```python
    _ensure_manage_baselines_permission()
    _ensure_activity_permissions()
    _ensure_auto_approve_permission()
    _ensure_vagtplan_permissions()
```

Erstat med:

```python
    _ensure_manage_baselines_permission()
    _ensure_activity_permissions()
    _ensure_auto_approve_permission()
    _ensure_manage_auto_approval_permission()
    _ensure_system_settings()
    _ensure_vagtplan_permissions()
```

- [ ] **Step 7: Kør testene for at bekræfte de passerer**

Run: `python -m pytest tests/test_system_settings.py -v`
Expected: PASS (7 passed)

- [ ] **Step 8: Kør hele test-suiten**

Run: `python -m pytest tests/ -q`
Expected: Alle tests passerer

- [ ] **Step 9: Commit**

```bash
git add app/auth.py app/database/session.py tests/test_system_settings.py
git commit -m "feat: tilføj manage_auto_approval-permission og seeding af systemindstillinger"
```

---

## Task 3: Gate baseline-læring (update_baseline_from_activity)

**Files:**
- Modify: `app/calculators/baseline_updater.py:12-27`
- Modify: `tests/conftest.py` (allerede tilføjet i Task 1 – ingen ændring her)
- Modify: `tests/test_baseline_updater.py`

**Interfaces:**
- Consumes: `is_auto_approval_enabled(db)` fra Task 1 (samme fil).
- Consumes: `set_auto_approval_enabled(db, enabled)` testhjælper fra Task 1 (`tests/conftest.py`).

- [ ] **Step 1: Skriv den fejlende test**

I `tests/test_baseline_updater.py`, find importlinjen:

```python
from conftest import make_activity
```

Erstat med:

```python
from conftest import make_activity, set_auto_approval_enabled
```

Tilføj til sidst i filen:

```python
def test_update_skipped_when_globally_disabled(db, employee):
    set_auto_approval_enabled(db, False)
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 1, 7, 0),
        end=datetime(2026, 6, 1, 15, 0),
        status=ActivityStatus.approved,
    )
    update_baseline_from_activity(act, db)

    count = db.query(EmployeeBaseline).filter_by(employee_id=employee.id).count()
    assert count == 0
```

- [ ] **Step 2: Kør testen for at bekræfte den fejler**

Run: `python -m pytest tests/test_baseline_updater.py::test_update_skipped_when_globally_disabled -v`
Expected: FAIL – der oprettes en baseline-række, selvom kontakten er slået fra

- [ ] **Step 3: Tilføj guard i update_baseline_from_activity()**

I `app/calculators/baseline_updater.py`, find:

```python
    if activity.activity_type != "normal":
        return
    if activity.source != ActivitySource.tachograph:
        return
    if activity.status != ActivityStatus.approved:
        return

    weekday = activity.start_time.weekday()
```

Erstat med:

```python
    if activity.activity_type != "normal":
        return
    if activity.source != ActivitySource.tachograph:
        return
    if activity.status != ActivityStatus.approved:
        return
    if not is_auto_approval_enabled(db):
        return

    weekday = activity.start_time.weekday()
```

- [ ] **Step 4: Kør testene for at bekræfte de passerer**

Run: `python -m pytest tests/test_baseline_updater.py -v`
Expected: PASS (8 passed – de 7 eksisterende + den nye)

- [ ] **Step 5: Commit**

```bash
git add app/calculators/baseline_updater.py tests/test_baseline_updater.py
git commit -m "feat: stop baseline-læring når auto-godkendelse er slået fra globalt"
```

---

## Task 4: Gate den statistiske beslutning (should_auto_approve)

**Files:**
- Modify: `app/calculators/auto_approval.py:1-11`
- Modify: `app/calculators/auto_approval.py:20-24`
- Modify: `tests/test_auto_approval.py`

**Interfaces:**
- Consumes: `is_auto_approval_enabled(db)` fra `app/calculators/baseline_updater.py` (Task 1).
- Consumes: `set_auto_approval_enabled(db, enabled)` testhjælper fra `tests/conftest.py` (Task 1).

- [ ] **Step 1: Skriv den fejlende test**

I `tests/test_auto_approval.py`, find importlinjen:

```python
from conftest import make_activity
```

Erstat med:

```python
from conftest import make_activity, set_auto_approval_enabled
```

Tilføj til sidst i filen:

```python
def test_auto_approve_disabled_globally_even_with_matching_baseline(db, employee):
    _seed_baseline(db, employee, n=6)
    set_auto_approval_enabled(db, False)
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 8, 7, 0),   # matcher baseline perfekt
        end=datetime(2026, 6, 8, 15, 0),
    )
    ok, flags = should_auto_approve(act, db)
    assert ok is False
    assert any("slået fra" in f.lower() for f in flags)
```

- [ ] **Step 2: Kør testen for at bekræfte den fejler**

Run: `python -m pytest tests/test_auto_approval.py::test_auto_approve_disabled_globally_even_with_matching_baseline -v`
Expected: FAIL – `ok is True` (baseline matcher stadig, kontakten ignoreres)

- [ ] **Step 3: Tilføj guard i should_auto_approve()**

I `app/calculators/auto_approval.py`, find:

```python
from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline
from calculators.baseline_updater import _effective_duration_minutes
```

Erstat med:

```python
from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline
from calculators.baseline_updater import _effective_duration_minutes, is_auto_approval_enabled
```

Find derefter:

```python
    if activity.activity_type != "normal":
        return False, ["Kun normale tachograf-aktiviteter auto-godkendes"]
    if activity.source != ActivitySource.tachograph:
        return False, ["Kun tachograf-aktiviteter auto-godkendes"]

    weekday = activity.start_time.weekday()
```

Erstat med:

```python
    if activity.activity_type != "normal":
        return False, ["Kun normale tachograf-aktiviteter auto-godkendes"]
    if activity.source != ActivitySource.tachograph:
        return False, ["Kun tachograf-aktiviteter auto-godkendes"]
    if not is_auto_approval_enabled(db):
        return False, ["Automatisk godkendelse er slået fra i systemindstillinger"]

    weekday = activity.start_time.weekday()
```

- [ ] **Step 4: Kør testene for at bekræfte de passerer**

Run: `python -m pytest tests/test_auto_approval.py -v`
Expected: PASS (8 passed – de 7 eksisterende + den nye)

- [ ] **Step 5: Commit**

```bash
git add app/calculators/auto_approval.py tests/test_auto_approval.py
git commit -m "feat: respekter global kontakt i should_auto_approve()"
```

---

## Task 5: Gate manuel oprettelse og bulk-endpoint (activities.py)

**Files:**
- Modify: `app/routers/activities.py:14`
- Modify: `app/routers/activities.py:459`
- Modify: `app/routers/activities.py:641-647` (bulk_auto_approve)
- Modify: `tests/test_activity_auto_approve_on_create.py`
- Create: `tests/test_activities_bulk_auto_approve.py`

**Interfaces:**
- Consumes: `is_auto_approval_enabled(db)` fra `app/calculators/baseline_updater.py` (Task 1).
- Consumes: `set_auto_approval_enabled(db, enabled)` testhjælper fra `tests/conftest.py` (Task 1).

- [ ] **Step 1: Skriv de fejlende tests**

Tilføj til `tests/test_activity_auto_approve_on_create.py` (sidst i filen):

```python
def test_permission_holder_normal_activity_stays_pending_when_globally_disabled(db, employee):
    from routers.activities import create_manual_activity
    from conftest import set_auto_approval_enabled

    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    set_auto_approval_enabled(db, False)
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),  # 8 timer
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.pending
    assert resp.approved_by is None
    assert resp.comment is None


def test_disponent_absence_type_still_approved_when_globally_disabled(db, employee):
    from routers.activities import create_manual_activity
    from conftest import set_auto_approval_enabled

    _grant(db, "disponent", [])
    set_auto_approval_enabled(db, False)
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="ferie",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),
    )
    resp = create_manual_activity(body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert resp.status == ActivityStatus.approved  # fraværstyper uændret, jf. spec
```

Opret `tests/test_activities_bulk_auto_approve.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
import pytest
from fastapi import HTTPException

from database.models import AppUser, ActivityStatus
from conftest import make_activity, set_auto_approval_enabled


def _user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_bulk_auto_approve_raises_when_globally_disabled(db, employee):
    from routers.activities import bulk_auto_approve

    set_auto_approval_enabled(db, False)
    make_activity(
        db, employee,
        start=datetime(2026, 6, 8, 7, 0),
        end=datetime(2026, 6, 8, 15, 0),
        status=ActivityStatus.pending,
    )
    with pytest.raises(HTTPException) as exc:
        bulk_auto_approve(period_start="2026-06-08", current_user=_user(), db=db)
    assert exc.value.status_code == 400


def test_bulk_auto_approve_works_when_enabled(db, employee):
    from routers.activities import bulk_auto_approve
    from calculators.baseline_updater import update_baseline_from_activity

    # Byg baseline: 6 godkendte mandage kl. 7-15 (8 timer)
    base_monday = datetime(2026, 1, 5, 7, 0)
    for i in range(6):
        start = base_monday + timedelta(weeks=i)
        act = make_activity(
            db, employee, start=start, end=start + timedelta(hours=8),
            status=ActivityStatus.approved,
        )
        update_baseline_from_activity(act, db)

    # Ny pending mandag-aktivitet der matcher mønsteret perfekt
    pending_start = datetime(2026, 6, 8, 7, 0)
    make_activity(
        db, employee, start=pending_start, end=pending_start + timedelta(hours=8),
        status=ActivityStatus.pending,
    )

    result = bulk_auto_approve(period_start="2026-06-08", current_user=_user(), db=db)
    assert result["approved"] == 1
    assert result["flagged"] == 0
```

- [ ] **Step 2: Kør testene for at bekræfte de fejler**

Run: `python -m pytest tests/test_activity_auto_approve_on_create.py tests/test_activities_bulk_auto_approve.py -v`
Expected: De 3 nye tests FAIL (`test_bulk_auto_approve_works_when_enabled` passerer muligvis allerede – det er OK, den er der for regressionsdækning af eksisterende adfærd)

- [ ] **Step 3: Gate create_manual_activity()**

I `app/routers/activities.py`, find (linje 14):

```python
from calculators.baseline_updater import update_baseline_from_activity
```

Erstat med:

```python
from calculators.baseline_updater import update_baseline_from_activity, is_auto_approval_enabled
```

Find derefter (linje 459):

```python
    can_auto_approve = user_has_permission(db, current_user, "auto_approve_manual_activities")
```

Erstat med:

```python
    can_auto_approve = (
        user_has_permission(db, current_user, "auto_approve_manual_activities")
        and is_auto_approval_enabled(db)
    )
```

- [ ] **Step 4: Gate bulk_auto_approve()**

I `app/routers/activities.py`, find:

```python
    """Auto-godkend alle egnede pending-aktiviteter i en lønperiode."""
    from datetime import date as _date
    from datetime import datetime as _dt
    from calculators.auto_approval import should_auto_approve

    start_date = _date.fromisoformat(period_start) if period_start else _date.today()
```

Erstat med:

```python
    """Auto-godkend alle egnede pending-aktiviteter i en lønperiode."""
    from datetime import date as _date
    from datetime import datetime as _dt
    from calculators.auto_approval import should_auto_approve

    if not is_auto_approval_enabled(db):
        raise HTTPException(400, "Automatisk godkendelse er slået fra i systemindstillinger")

    start_date = _date.fromisoformat(period_start) if period_start else _date.today()
```

- [ ] **Step 5: Kør testene for at bekræfte de passerer**

Run: `python -m pytest tests/test_activity_auto_approve_on_create.py tests/test_activities_bulk_auto_approve.py -v`
Expected: PASS (11 passed – 9 eksisterende + 2 nye i første fil, 2 nye i anden fil)

- [ ] **Step 6: Kør hele test-suiten**

Run: `python -m pytest tests/ -q`
Expected: Alle tests passerer

- [ ] **Step 7: Commit**

```bash
git add app/routers/activities.py tests/test_activity_auto_approve_on_create.py tests/test_activities_bulk_auto_approve.py
git commit -m "feat: respekter global kontakt ved manuel oprettelse og bulk-godkendelse"
```

---

## Task 6: GET/POST /api/auto-approval/settings-endpoints

**Files:**
- Modify: `app/routers/auto_approval_router.py`
- Create: `tests/test_auto_approval_settings_router.py`

**Interfaces:**
- Consumes: `is_auto_approval_enabled(db)` fra `app/calculators/baseline_updater.py` (Task 1).
- Consumes: `SystemSettings` model fra `app/database/models.py` (Task 1).
- Consumes: `manage_auto_approval`-permission fra Task 2.
- Produces: `GET /api/auto-approval/settings` → `{"enabled": bool}`.
- Produces: `POST /api/auto-approval/settings` (body `{"enabled": bool}`, kræver
  `manage_auto_approval`) → `{"enabled": bool}`.

- [ ] **Step 1: Skriv de fejlende tests**

Opret `tests/test_auto_approval_settings_router.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from database.models import AppUser, SystemSettings


def _user(role="admin", initials="ADM"):
    return AppUser(name="Test", initials=initials, role=role, password_hash="x")


def test_get_settings_defaults_to_enabled_without_row(db):
    from routers.auto_approval_router import get_auto_approval_settings
    result = get_auto_approval_settings(current_user=_user(), db=db)
    assert result == {"enabled": True}


def test_post_settings_creates_row_and_updates_it(db):
    from routers.auto_approval_router import set_auto_approval_settings, AutoApprovalSettingsBody

    result = set_auto_approval_settings(AutoApprovalSettingsBody(enabled=False), current_user=_user(), db=db)
    assert result == {"enabled": False}

    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    assert settings.auto_approval_enabled is False
    assert settings.updated_by == "ADM"
    assert settings.updated_at is not None


def test_get_settings_reflects_change_after_post(db):
    from routers.auto_approval_router import (
        set_auto_approval_settings, get_auto_approval_settings, AutoApprovalSettingsBody,
    )
    set_auto_approval_settings(AutoApprovalSettingsBody(enabled=False), current_user=_user(), db=db)
    result = get_auto_approval_settings(current_user=_user(), db=db)
    assert result == {"enabled": False}


def test_post_settings_toggles_existing_row_back_to_true(db):
    from routers.auto_approval_router import set_auto_approval_settings, AutoApprovalSettingsBody

    set_auto_approval_settings(AutoApprovalSettingsBody(enabled=False), current_user=_user(), db=db)
    result = set_auto_approval_settings(AutoApprovalSettingsBody(enabled=True), current_user=_user(), db=db)
    assert result == {"enabled": True}
    assert db.query(SystemSettings).count() == 1
```

- [ ] **Step 2: Kør testene for at bekræfte de fejler**

Run: `python -m pytest tests/test_auto_approval_settings_router.py -v`
Expected: FAIL – `ImportError: cannot import name 'get_auto_approval_settings'`

- [ ] **Step 3: Tilføj endpoints i auto_approval_router.py**

I `app/routers/auto_approval_router.py`, find hele importblokken og router-opsætningen (linje 1-13):

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from auth import require_permission
from database.models import AppUser, Employee
from database.session import get_db
from calculators.baseline_updater import rebuild_baselines_for_employee

router = APIRouter(prefix="/api/auto-approval", tags=["auto-approval"])

_admin_access = require_permission("manage_baselines")
```

Erstat med:

```python
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from auth import get_current_user, log_action, require_permission
from database.models import AppUser, Employee, SystemSettings
from database.session import get_db
from calculators.baseline_updater import rebuild_baselines_for_employee, is_auto_approval_enabled

router = APIRouter(prefix="/api/auto-approval", tags=["auto-approval"])

_admin_access = require_permission("manage_baselines")
_toggle_access = require_permission("manage_auto_approval")


class AutoApprovalSettingsBody(BaseModel):
    enabled: bool
```

Tilføj derefter de to nye endpoints til sidst i filen (efter `baseline_summary`-funktionen):

```python
@router.get("/settings")
def get_auto_approval_settings(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Nuværende tilstand af den globale auto-godkendelses-kontakt. Åben for alle
    godkendte brugere, så frontend kan skjule 'Autogodkend aktiviteter'-knappen."""
    return {"enabled": is_auto_approval_enabled(db)}


@router.post("/settings")
def set_auto_approval_settings(
    body: AutoApprovalSettingsBody,
    current_user: AppUser = Depends(_toggle_access),
    db: Session = Depends(get_db),
):
    """Slår den globale auto-godkendelses-proces til/fra."""
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if settings is None:
        settings = SystemSettings(id=1, auto_approval_enabled=body.enabled)
        db.add(settings)
    else:
        settings.auto_approval_enabled = body.enabled
    settings.updated_by = current_user.initials
    settings.updated_at = datetime.utcnow()
    log_action(db, current_user, "toggle_auto_approval",
               details=f"auto_approval_enabled={body.enabled}")
    db.commit()
    return {"enabled": settings.auto_approval_enabled}
```

- [ ] **Step 4: Kør testene for at bekræfte de passerer**

Run: `python -m pytest tests/test_auto_approval_settings_router.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Kør hele test-suiten**

Run: `python -m pytest tests/ -q`
Expected: Alle tests passerer

- [ ] **Step 6: Commit**

```bash
git add app/routers/auto_approval_router.py tests/test_auto_approval_settings_router.py
git commit -m "feat: tilføj GET/POST /api/auto-approval/settings-endpoints"
```

---

## Task 7: Frontend – fane, knap og skjul af bulk-knap

**Files:**
- Modify: `app/static/js/app.js` (PERMISSION_LABELS, state, loadApp, switchStamdataTab, loadStamdata, nye funktioner)
- Modify: `app/templates/index.html` (ny fane-knap + panel under Stamdata)

**Interfaces:**
- Consumes: `GET /api/auto-approval/settings`, `POST /api/auto-approval/settings` fra Task 6.
- Consumes: `data-perm-require`-mekanismen (`applyRoleVisibility()`) og `manage_auto_approval`-
  permissionen fra Task 2.

- [ ] **Step 1: Tilføj permission-label**

I `app/static/js/app.js`, find:

```javascript
  auto_approve_manual_activities: "Auto-godkend ved oprettelse",
  view_calendar:       "Se aktivitetskalender",
```

Erstat med:

```javascript
  auto_approve_manual_activities: "Auto-godkend ved oprettelse",
  manage_auto_approval: "Slå auto-godkendelse til/fra",
  view_calendar:       "Se aktivitetskalender",
```

- [ ] **Step 2: Tilføj state-felt**

I `app/static/js/app.js`, find:

```javascript
  dispatcherGroups: [],    // { id, name, description }
```

Erstat med:

```javascript
  dispatcherGroups: [],    // { id, name, description }
  autoApprovalEnabled: true, // global til/fra-kontakt, hentet ved app-bootstrap
```

- [ ] **Step 3: Hent indstillingen ved app-bootstrap og skjul bulk-knappen**

I `app/static/js/app.js`, find `loadApp()`:

```javascript
async function loadApp() {
  try {
    [state.employees, state.vehicles, state.dispatcherGroups] = await Promise.all([
      GET("/api/employees"),
      GET("/api/vehicles"),
      GET("/api/employees/dispatcher-groups"),
    ]);
    fillDispatcherGroupFilter();
    fillEmployeeDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (e) { console.error(e); }

  await loadAbsenceTypes();
  await setView("activities");
  await checkAnciennitetsAlerts();
  await checkParagraf56Alerts();
}
```

Erstat med:

```javascript
async function loadApp() {
  try {
    [state.employees, state.vehicles, state.dispatcherGroups] = await Promise.all([
      GET("/api/employees"),
      GET("/api/vehicles"),
      GET("/api/employees/dispatcher-groups"),
    ]);
    fillDispatcherGroupFilter();
    fillEmployeeDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (e) { console.error(e); }

  try {
    const settings = await GET("/api/auto-approval/settings");
    state.autoApprovalEnabled = settings.enabled;
  } catch (e) { console.error(e); }
  applyAutoApprovalVisibility();

  await loadAbsenceTypes();
  await setView("activities");
  await checkAnciennitetsAlerts();
  await checkParagraf56Alerts();
}

function applyAutoApprovalVisibility() {
  const btn = document.getElementById("btn-auto-approve");
  if (btn) btn.style.display = state.autoApprovalEnabled ? "" : "none";
}
```

- [ ] **Step 4: Tilføj den nye fane til switchStamdataTab() og loadStamdata()**

I `app/static/js/app.js`, find:

```javascript
function switchStamdataTab(tab) {
  ["agreement", "overtime", "supplement", "paytype", "absence", "cvr", "holiday", "dispatcher", "agreementkind"].forEach(t => {
```

Erstat med:

```javascript
function switchStamdataTab(tab) {
  ["agreement", "overtime", "supplement", "paytype", "absence", "cvr", "holiday", "dispatcher", "agreementkind", "autoapproval"].forEach(t => {
```

Find derefter:

```javascript
async function loadStamdata() {
  switchStamdataTab("agreement");
  await Promise.all([
    loadStamdataAgreementTypes(),
    loadStamdataOvertimeRates(),
    loadStamdataSupplements(),
    loadStamdataPayTypes(),
    loadStamdataAbsenceTypes(),
    loadStamdataCvrNumbers(),
    loadStamdataHolidays(),
    loadStamdataDispatcherGroups(),
    loadStamdataAgreementKinds(),
  ]);
}
```

Erstat med:

```javascript
async function loadStamdata() {
  switchStamdataTab("agreement");
  await Promise.all([
    loadStamdataAgreementTypes(),
    loadStamdataOvertimeRates(),
    loadStamdataSupplements(),
    loadStamdataPayTypes(),
    loadStamdataAbsenceTypes(),
    loadStamdataCvrNumbers(),
    loadStamdataHolidays(),
    loadStamdataDispatcherGroups(),
    loadStamdataAgreementKinds(),
    loadStamdataAutoApproval(),
  ]);
}

async function loadStamdataAutoApproval() {
  const badge = document.getElementById("auto-approval-status-badge");
  const btn = document.getElementById("btn-toggle-auto-approval");
  if (!badge || !btn) return;
  try {
    const settings = await GET("/api/auto-approval/settings");
    state.autoApprovalEnabled = settings.enabled;
    renderAutoApprovalStatus();
  } catch (e) {
    badge.textContent = "Kunne ikke hente status";
  }
}

function renderAutoApprovalStatus() {
  const badge = document.getElementById("auto-approval-status-badge");
  const btn = document.getElementById("btn-toggle-auto-approval");
  if (!badge || !btn) return;
  if (state.autoApprovalEnabled) {
    badge.textContent = "Slået til";
    badge.className = "stat-chip approved";
    btn.textContent = "Slå fra";
    btn.className = "btn btn-danger";
  } else {
    badge.textContent = "Slået fra";
    badge.className = "stat-chip deact";
    btn.textContent = "Slå til";
    btn.className = "btn btn-success";
  }
}

async function toggleAutoApproval() {
  const newValue = !state.autoApprovalEnabled;
  try {
    const result = await POST("/api/auto-approval/settings", { enabled: newValue });
    state.autoApprovalEnabled = result.enabled;
    renderAutoApprovalStatus();
    applyAutoApprovalVisibility();
    toast(state.autoApprovalEnabled ? "Auto-godkendelse slået til" : "Auto-godkendelse slået fra");
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 5: Tilføj fane-knap og panel i index.html**

I `app/templates/index.html`, find fane-knap-blokken:

```html
        <button id="sd-tab-agreementkind" onclick="switchStamdataTab('agreementkind')"
                style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer">
          Aftale
        </button>
      </div>
```

Erstat med:

```html
        <button id="sd-tab-agreementkind" onclick="switchStamdataTab('agreementkind')"
                style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer">
          Aftale
        </button>
        <button id="sd-tab-autoapproval" onclick="switchStamdataTab('autoapproval')"
                style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer"
                data-perm-require="manage_auto_approval">
          Auto-godkendelse
        </button>
      </div>
```

Find derefter disponentgruppe-panelet og dets afsluttende `</div>`:

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
          </table>
        </div>

      </div>
    </div>
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
          </table>
        </div>

        <!-- Auto-godkendelse -->
        <div id="sd-pane-autoapproval" style="display:none">
          <div style="background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:20px;max-width:600px">
            <div style="font-weight:600;font-size:14px;margin-bottom:6px">Automatisk godkendelse</div>
            <div style="font-size:13px;color:var(--text-light);margin-bottom:16px;max-width:480px">
              Styrer om aktiviteter kan blive godkendt automatisk – både ved DDD-import
              (baseret på medarbejderens historiske mønster) og ved manuel oprettelse for
              brugere med rettigheden "Auto-godkend ved oprettelse". Fraværstyper som ferie
              og sygdom påvirkes ikke og godkendes altid automatisk ved oprettelse som i dag.
            </div>
            <div style="display:flex;align-items:center;gap:12px">
              <span id="auto-approval-status-badge" class="stat-chip">Indlæser...</span>
              <button id="btn-toggle-auto-approval" class="btn btn-secondary" onclick="toggleAutoApproval()">...</button>
            </div>
          </div>
        </div>

      </div>
    </div>
```

- [ ] **Step 6: Manuel verifikation i browser**

Start dev-serveren og gennemgå følgende tjekliste manuelt (ingen JS-testramme i dette
projekt – backend-logikken er allerede TDD-dækket i Task 1-6):

1. Start serveren (brug `preview_start` med `name: "lonsystem"` eller kør
   `cd app && python -m uvicorn main:app --reload` fra repo-roden).
2. Log ind som admin. Gå til Stamdata → fanen "Auto-godkendelse" skal være synlig
   (kun for admin/manage_auto_approval).
3. Badge viser "Slået til" og knappen "Slå fra" (rød).
4. Gå til Aktiviteter-visningen – knappen "Autogodkend aktiviteter" er synlig i toolbaren.
5. Gå tilbage til Stamdata → Auto-godkendelse, klik "Slå fra". Badge skifter til
   "Slået fra", knap skifter til "Slå til" (grøn).
6. Gå til Aktiviteter-visningen igen – knappen "Autogodkend aktiviteter" er nu væk.
7. Genindlæs siden (F5) – tilstanden "Slået fra" og skjult bulk-knap skal bevares
   (bekræfter at GET /settings virker korrekt ved bootstrap).
8. Klik "Slå til" igen i Stamdata – bulk-knappen dukker op igen i Aktiviteter-visningen.
9. Log ind som en bruger uden `manage_auto_approval` (fx disponent) – fanen
   "Auto-godkendelse" er ikke synlig i Stamdata.

- [ ] **Step 7: Kør hele test-suiten en sidste gang**

Run: `python -m pytest tests/ -q`
Expected: Alle tests passerer

- [ ] **Step 8: Commit**

```bash
git add app/static/js/app.js app/templates/index.html
git commit -m "feat: UI til at slå global auto-godkendelse til/fra under Stamdata"
```

---

## Self-Review

**Spec coverage:**
- Datamodel (SystemSettings singleton) → Task 1 ✓
- Permission manage_auto_approval, kun admin default → Task 2 ✓
- should_auto_approve() respekterer kontakten → Task 4 ✓
- update_baseline_from_activity() respekterer kontakten (også ved manuel godkendelse) → Task 3 ✓
- create_manual_activity() respekterer kontakten (kun normal-gren, ikke fravær) → Task 5 ✓
- bulk_auto_approve() afviser med 400 når slået fra → Task 5 ✓
- GET/POST /api/auto-approval/settings → Task 6 ✓
- Frontend-fane under Stamdata, permission-gated → Task 7 ✓
- Bulk-knap skjules helt når slået fra → Task 7 ✓
- Fail-open (manglende record = slået til) → Task 1, testet eksplicit ✓

**Placeholder scan:** Ingen TBD/TODO. Alle kodeblokke er komplette og køreklare.

**Type-konsistens:** `is_auto_approval_enabled(db) -> bool` bruges identisk i Task 3, 4, 5
og 6. `SystemSettings.id/auto_approval_enabled/updated_by/updated_at` navngivning er
konsistent gennem alle tasks. `set_auto_approval_enabled(db, enabled)` testhjælperen
defineres én gang (Task 1, conftest.py) og genbruges uændret i Task 3, 4 og 5.
