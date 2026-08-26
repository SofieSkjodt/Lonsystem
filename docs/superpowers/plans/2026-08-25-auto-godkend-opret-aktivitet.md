# Auto-godkendelse ved oprettelse af aktivitet – Implementationsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Når en bruger med den nye permission `auto_approve_manual_activities` opretter en aktivitet via `POST /api/activities`, skal aktiviteten automatisk godkendes med det samme (uanset type), og hvis den er under 4 timer og kommentarfeltet er tomt, skal kommentaren automatisk sættes til brugerens initialer.

**Architecture:** En ny dynamisk permission (`auto_approve_manual_activities`) styrer adfærden, i stedet for et hardcodet rollenavne-check. `lonbogholder` får den som default (kode + idempotent DB-migration); `admin` har den automatisk fordi rollen er en systemrolle; `disponent` får den ikke som default, men kan tildeles den senere via den eksisterende rolle-editor. `create_manual_activity()` i `app/routers/activities.py` tjekker permissionen og genbruger den eksisterende 4-timers-beregning (`_duration_minutes()` + `_day_reaches_4h_with_approved()`) til kommentar-fallback.

**Tech Stack:** Python/FastAPI, SQLAlchemy, SQLite, pytest. Ingen nye afhængigheder.

## Global Constraints

- Python 3.11+, FastAPI, SQLAlchemy, SQLite (WAL)
- Ingen nye pip-afhængigheder
- Tests køres fra projektets rod: `cd app && python -m pytest ../tests/ -v`
- Kørende server kræver genstart ved `.py`-ændringer (`cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`)
- Ny permission: `auto_approve_manual_activities` (label: "Auto-godkend ved oprettelse")
- `admin` er systemrolle (`is_system=True`) og har derfor automatisk alle permissions – tilføjes IKKE til dens permissions-liste
- `lonbogholder` får permissionen som default (ny rolle-seed + idempotent migration for eksisterende DB)
- `disponent` får IKKE permissionen som default
- Spec: `docs/superpowers/specs/2026-08-25-auto-godkend-opret-aktivitet-design.md`

---

## Filstruktur

```
app/
  auth.py                       # MODIFY: tilføj auto_approve_manual_activities til ALL_PERMISSIONS
  database/
    session.py                  # MODIFY: _seed_roles() + ny _ensure_auto_approve_permission() + init_db()
  routers/
    activities.py                # MODIFY: create_manual_activity() – permission-gated auto-approve + kommentar-fallback
  static/js/app.js               # MODIFY: PERMISSION_LABELS
tests/
  test_auto_approve_permission_seed.py       # CREATE: permission-definition + seed + migration
  test_activity_auto_approve_on_create.py    # CREATE: create_manual_activity()-adfærd
CODEREF.md                       # MODIFY: ny sektion om funktionen
```

---

## Task 1: Permission-definition, default-seed og migration

**Files:**
- Modify: `app/auth.py`
- Modify: `app/database/session.py`
- Modify: `app/static/js/app.js`
- Create: `tests/test_auto_approve_permission_seed.py`

**Interfaces:**
- Consumes: `Role`-model fra `database.models`, eksisterende `SessionLocal`-mønster fra `database/session.py`
- Produces: permission-nøglen `"auto_approve_manual_activities"` tilgængelig i `auth.ALL_PERMISSIONS`, seedet som default på `lonbogholder`, og migreret ind på eksisterende `lonbogholder`-rolle via `_ensure_auto_approve_permission()`

- [ ] **Step 1: Skriv de failing tests**

Opret `tests/test_auto_approve_permission_seed.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from sqlalchemy.orm import sessionmaker


def test_all_permissions_includes_auto_approve_manual_activities():
    from auth import ALL_PERMISSIONS
    assert "auto_approve_manual_activities" in ALL_PERMISSIONS
    assert ALL_PERMISSIONS["auto_approve_manual_activities"] == "Auto-godkend ved oprettelse"


def test_seed_roles_grants_permission_to_lonbogholder_not_disponent(db, monkeypatch):
    import database.session as session_module
    from database.models import Role

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    assert db.query(Role).count() == 0

    session_module._seed_roles()

    lonbogholder = db.query(Role).filter(Role.name == "lonbogholder").first()
    assert "auto_approve_manual_activities" in lonbogholder.permissions

    disponent = db.query(Role).filter(Role.name == "disponent").first()
    assert "auto_approve_manual_activities" not in disponent.permissions


def test_ensure_auto_approve_permission_adds_to_lonbogholder_and_is_idempotent(db, monkeypatch):
    import database.session as session_module
    from database.models import Role

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False, permissions=["payroll"]))
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()

    session_module._ensure_auto_approve_permission()

    lonbogholder = db.query(Role).filter(Role.name == "lonbogholder").first()
    db.refresh(lonbogholder)
    assert "auto_approve_manual_activities" in lonbogholder.permissions

    disponent = db.query(Role).filter(Role.name == "disponent").first()
    db.refresh(disponent)
    assert "auto_approve_manual_activities" not in disponent.permissions

    # Idempotent — kør igen, ingen dubletter
    session_module._ensure_auto_approve_permission()
    db.refresh(lonbogholder)
    assert lonbogholder.permissions.count("auto_approve_manual_activities") == 1
```

- [ ] **Step 2: Kør tests og bekræft FAIL**

```bash
cd app && python -m pytest ../tests/test_auto_approve_permission_seed.py -v
```

Forventet: `test_all_permissions_includes_auto_approve_manual_activities` FAILER med `KeyError`/`assert False` (nøglen findes ikke). De to andre FAILER med `AttributeError: module 'database.session' has no attribute '_ensure_auto_approve_permission'` eller assertion-fejl (permissionen mangler i seed-listen).

- [ ] **Step 3: Tilføj permission til `ALL_PERMISSIONS` i `app/auth.py`**

Find linjen `"approve_activities":  "Godkend aktiviteter",` (linje 23) og tilføj umiddelbart efter:

```python
    "approve_activities":  "Godkend aktiviteter",
    "auto_approve_manual_activities": "Auto-godkend ved oprettelse",
```

- [ ] **Step 4: Tilføj label til `PERMISSION_LABELS` i `app/static/js/app.js`**

Find linjen `  approve_activities:  "Godkend aktiviteter",` (linje 52) i `PERMISSION_LABELS`-objektet og tilføj umiddelbart efter:

```js
  approve_activities:  "Godkend aktiviteter",
  auto_approve_manual_activities: "Auto-godkend ved oprettelse",
```

- [ ] **Step 5: Tilføj permissionen til `lonbogholder`s default-liste i `_seed_roles()` (`app/database/session.py`)**

Find (omkring linje 190-191):

```python
                Role(name="lonbogholder", display_name="Lønbogholder", is_system=False,
                     permissions=["payroll", "absence_overview", "import_ddd", "anciennitet_alert", "approve_activities", "view_calendar"]),
```

Skift til:

```python
                Role(name="lonbogholder", display_name="Lønbogholder", is_system=False,
                     permissions=["payroll", "absence_overview", "import_ddd", "anciennitet_alert", "approve_activities", "view_calendar", "auto_approve_manual_activities"]),
```

`admin`- og `disponent`-linjerne ændres ikke.

- [ ] **Step 6: Tilføj `_ensure_auto_approve_permission()` i `app/database/session.py`**

Find funktionen `_ensure_manage_baselines_permission()` (omkring linje 553-569) og tilføj en ny funktion umiddelbart efter den, med samme struktur men målrettet `lonbogholder`:

```python
def _ensure_auto_approve_permission():
    """Tilføjer auto_approve_manual_activities til lonbogholder-rollen (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "lonbogholder").first()
        if role:
            perms = list(role.permissions or [])
            if "auto_approve_manual_activities" not in perms:
                perms.append("auto_approve_manual_activities")
                role.permissions = perms
                db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af auto_approve_manual_activities-tilladelse: {e}")
    finally:
        db.close()
```

- [ ] **Step 7: Kald den nye migration fra `init_db()`**

Find kaldet `_ensure_activity_permissions()` i `init_db()` (omkring linje 53) og tilføj kaldet til den nye funktion umiddelbart efter:

```python
    _ensure_activity_permissions()
    _ensure_auto_approve_permission()
```

- [ ] **Step 8: Kør tests og bekræft PASS**

```bash
cd app && python -m pytest ../tests/test_auto_approve_permission_seed.py -v
```

Forventet: alle 3 tests `PASSED`.

- [ ] **Step 9: Commit**

```bash
git add app/auth.py app/static/js/app.js app/database/session.py tests/test_auto_approve_permission_seed.py
git commit -m "feat: tilføj auto_approve_manual_activities-permission (seed + migration)"
```

---

## Task 2: Auto-godkendelse og kommentar-fallback i `create_manual_activity()`

**Files:**
- Modify: `app/routers/activities.py:456-485`
- Create: `tests/test_activity_auto_approve_on_create.py`

**Interfaces:**
- Consumes: `user_has_permission(db, current_user, perm) -> bool` (allerede importeret i `activities.py:13`), `_duration_minutes(a) -> int` (`activities.py:132`), `_day_reaches_4h_with_approved(a, dur) -> bool` (`activities.py:209`), `FOUR_HOURS` (`activities.py:128`)
- Produces: opdateret adfærd i `create_manual_activity(body: ActivityCreate, current_user: AppUser, db: Session) -> ActivityResponse` – ingen ændring i signatur

- [ ] **Step 1: Skriv de failing tests**

Opret `tests/test_activity_auto_approve_on_create.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

from database.models import ActivitySource, ActivityStatus, AppUser, Role
from database.schemas import ActivityCreate


def _user(role="lonbogholder", initials="LB1"):
    return AppUser(name="Test", initials=initials, role=role, password_hash="x")


def _grant(db, role_name, permissions, is_system=False):
    db.add(Role(name=role_name, display_name=role_name, is_system=is_system, permissions=permissions))
    db.commit()


def test_permission_holder_long_activity_is_approved(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),  # 8 timer
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.approved_by == "LB1"
    assert resp.comment is None


def test_permission_holder_short_activity_without_comment_gets_initials(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.comment == "LB1"


def test_permission_holder_short_activity_with_own_comment_is_preserved(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer
        comment="Kørt ærinde for kontoret",
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.comment == "Kørt ærinde for kontoret"


def test_permission_holder_short_activity_reaching_4h_with_other_approved_skips_fallback(db, employee):
    from routers.activities import create_manual_activity
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import Activity

    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    period = get_or_create_period_for_date(datetime(2026, 1, 5).date(), db)
    db.add(Activity(
        employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.manual,
        activity_type="normal", start_time=datetime(2026, 1, 5, 6, 0), end_time=datetime(2026, 1, 5, 8, 0),
        status=ActivityStatus.approved, pause_intervals=[], segments=[],
    ))
    db.commit()

    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 8, 0),
        end_time=datetime(2026, 1, 5, 10, 0),  # yderligere 2 timer = 4 timer samlet denne dag
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.comment is None


def test_no_permission_normal_activity_stays_pending(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "disponent", [])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer
    )
    resp = create_manual_activity(body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert resp.status == ActivityStatus.pending
    assert resp.approved_by is None
    assert resp.comment is None


def test_no_permission_absence_type_still_approved_without_comment_fallback(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "disponent", [])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="ferie",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer, under 4h
    )
    resp = create_manual_activity(body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert resp.status == ActivityStatus.approved  # uændret eksisterende adfærd for fraværstyper
    assert resp.comment is None  # men INGEN kommentar-fallback uden permission


def test_system_role_admin_auto_approves_without_explicit_permission(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "admin", [], is_system=True)
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer
    )
    resp = create_manual_activity(body, current_user=_user(role="admin", initials="ADM"), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.comment == "ADM"
```

- [ ] **Step 2: Kør tests og bekræft FAIL**

```bash
cd app && python -m pytest ../tests/test_activity_auto_approve_on_create.py -v
```

Forventet: `test_permission_holder_long_activity_is_approved` FAILER (status er `pending`, ikke `approved`, da normal arbejdstid i dag altid starter som `pending`). `test_permission_holder_short_activity_without_comment_gets_initials` FAILER af samme grund. De øvrige tests, der forventer nuværende adfærd (pending for uden-permission, approved for fravær), bør allerede PASSE – bekræft at kun de to første fejler.

- [ ] **Step 3: Implementer ændringen i `create_manual_activity()` (`app/routers/activities.py:456-485`)**

Find blokken:

```python
    period = get_billing_period(body.start_time.date(), db)
    is_absence = activity_type != "normal"
    activity = Activity(
        employee_id=body.employee_id,
        pay_period_id=period.id,
        source=activity_source,
        created_by=current_user.initials,
        activity_type=activity_type,
        start_time=body.start_time,
        end_time=body.end_time,
        loading_minutes=body.loading_minutes,
        unloading_minutes=body.unloading_minutes,
        comment=body.comment,
        vehicle_number=body.vehicle_number,
        km_start=body.km_start,
        km_end=body.km_end,
        salt_supplement=body.salt_supplement,
        pause_intervals=body.pause_intervals,
        status=ActivityStatus.approved if is_absence else ActivityStatus.pending,
        approved_by=current_user.initials if is_absence else None,
        approved_at=datetime.utcnow() if is_absence else None,
    )
    db.add(activity)
    db.flush()
    log_action(db, current_user, "create_activity", "activity", activity.id,
               f"Manuelt oprettet for {emp.name}")
    db.commit()
    db.refresh(activity)
    return _to_response(activity)
```

Erstat med:

```python
    period = get_billing_period(body.start_time.date(), db)
    is_absence = activity_type != "normal"
    can_auto_approve = user_has_permission(db, current_user, "auto_approve_manual_activities")
    activity = Activity(
        employee_id=body.employee_id,
        pay_period_id=period.id,
        source=activity_source,
        created_by=current_user.initials,
        activity_type=activity_type,
        start_time=body.start_time,
        end_time=body.end_time,
        loading_minutes=body.loading_minutes,
        unloading_minutes=body.unloading_minutes,
        comment=body.comment,
        vehicle_number=body.vehicle_number,
        km_start=body.km_start,
        km_end=body.km_end,
        salt_supplement=body.salt_supplement,
        pause_intervals=body.pause_intervals,
        status=ActivityStatus.pending,
    )
    db.add(activity)
    db.flush()

    if is_absence or can_auto_approve:
        activity.status = ActivityStatus.approved
        activity.approved_by = current_user.initials
        activity.approved_at = datetime.utcnow()

        if can_auto_approve and not activity.comment:
            dur = _duration_minutes(activity)
            if dur < FOUR_HOURS and not _day_reaches_4h_with_approved(activity, dur):
                activity.comment = current_user.initials

    log_action(db, current_user, "create_activity", "activity", activity.id,
               f"Manuelt oprettet for {emp.name}")
    db.commit()
    db.refresh(activity)
    return _to_response(activity)
```

- [ ] **Step 4: Kør tests og bekræft PASS**

```bash
cd app && python -m pytest ../tests/test_activity_auto_approve_on_create.py -v
```

Forventet: alle 7 tests `PASSED`.

- [ ] **Step 5: Kør de eksisterende Vagtplan-tests for at bekræfte ingen regression**

```bash
cd app && python -m pytest ../tests/test_vagtplan.py -v
```

Forventet: alle tests `PASSED`, inkl. `test_create_activity_without_vagtplan_source_is_unaffected` (som ikke seeder nogen `Role`, så `can_auto_approve` bliver `False` og aktiviteten forbliver `pending` som før).

- [ ] **Step 6: Commit**

```bash
git add app/routers/activities.py tests/test_activity_auto_approve_on_create.py
git commit -m "feat: auto-godkend aktiviteter ved oprettelse for brugere med auto_approve_manual_activities"
```

---

## Task 3: Fuld testkørsel og CODEREF-opdatering

**Files:**
- Modify: `CODEREF.md`

- [ ] **Step 1: Kør hele test-suiten**

```bash
cd app && python -m pytest ../tests/ -v
```

Forventet: alle tests `PASSED`, ingen regressioner i andre testfiler.

- [ ] **Step 2: Tilføj ny sektion i `CODEREF.md`**

Find den sidste sektion i filen (efter linje ~413, "Periodegrænser i aktivitetsoversigten...") og tilføj en ny sektion i samme stil for enden af filen:

```markdown
---

## Auto-godkendelse ved oprettelse af aktivitet (2026-08-25, activities.py + auth.py + session.py)
Ny permission `auto_approve_manual_activities` ("Auto-godkend ved oprettelse") – styrer om `create_manual_activity()` sætter `status=approved` direkte i stedet for `pending` for normal arbejdstid. `admin` har den automatisk (systemrolle), `lonbogholder` får den som default-seed + migration (`_ensure_auto_approve_permission()`, samme mønster som `_ensure_manage_baselines_permission()`), `disponent` får den ikke som default men kan tildeles den via rolle-editoren. Er aktiviteten under 4 timer (samme beregning som `is_under_4h`/godkendelses-endpointet: `_duration_minutes()` + `_day_reaches_4h_with_approved()`) og kommentarfeltet er tomt, sættes `comment = current_user.initials` automatisk – kun for brugere med permissionen, og kun hvis de ikke selv har skrevet en kommentar. Fraværstypers eksisterende ubetingede auto-godkendelse (alle roller) er uændret; kommentar-fallback'en udløses dog ikke for roller uden permissionen.
```

- [ ] **Step 3: Commit**

```bash
git add CODEREF.md
git commit -m "docs: dokumenter auto_approve_manual_activities i CODEREF"
```

---

## Self-Review

**Spec coverage:**
- ✅ Ny permission `auto_approve_manual_activities` i `ALL_PERMISSIONS` + `PERMISSION_LABELS`
- ✅ Default-seed på `lonbogholder`, ikke på `disponent`, ikke nødvendig for `admin` (systemrolle)
- ✅ Idempotent migration for eksisterende DB (`_ensure_auto_approve_permission()`, kaldt fra `init_db()`)
- ✅ `create_manual_activity()`: auto-godkend for alle typer når permission eller fraværstype
- ✅ Kommentar-fallback: kun ved permission, kun ved endelig status=approved i dette kald, kun under 4 timer (inkl. dags-samlet-check), kun hvis kommentarfelt tomt
- ✅ Disponent uændret (normal → pending, fravær → approved uden kommentar-fallback)
- ✅ Gælder for alle oprettelsesveje gennem samme endpoint (manual + vagtplan-source) – ingen særskilt kode nødvendig, da tjekket er permission-baseret, ikke source-baseret
- ✅ Tests for alle scenarier fra spec'ens "Test-dækning"-sektion

**Placeholder-scan:** Ingen TBD/TODO – alle steps har konkret kode og eksakte linjenumre/kommandoer.

**Type-konsistens:**
- `user_has_permission(db, current_user, perm) -> bool` bruges som allerede defineret i `auth.py` (allerede importeret i `activities.py`)
- `create_manual_activity(body: ActivityCreate, current_user: AppUser, db: Session) -> ActivityResponse` – signatur uændret, kun funktionslegeme ændret
- `_ensure_auto_approve_permission()` følger samme parameterløse mønster som `_ensure_manage_baselines_permission()`
