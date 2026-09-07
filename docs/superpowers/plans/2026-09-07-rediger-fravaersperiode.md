# Rediger fraværsperiode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gør det muligt at redigere fra/til-dato for en hel fraværsperiode (fx en uges ferie) i én handling, mens de underliggende dage stadig er individuelle `Activity`-rækker, præcis som i dag.

**Architecture:** Et nyt `absence_group_id` (UUID-streng) på `Activity` kobler de dage der blev oprettet sammen i én periode. To nye backend-endpoints (`GET`/`PATCH /api/activities/absence-group/{group_id}`) læser gruppen og anvender en dato-diff (fjern dage der falder udenfor den nye periode, tilføj dage der kommer til, lad uændrede dage være). Frontend tilføjer en "Fraværsperiode"-sektion i den eksisterende aktivitets-modal, når den åbnede aktivitet har et gruppe-id.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite) backend, vanilla JS frontend, pytest til backend-tests (kaldes direkte mod router-funktionerne, ikke via HTTP).

## Global Constraints

- Kun perioderne oprettet EFTER denne ændring får et gruppe-id — ingen tilbagevirkende migrering af historiske fraværsperioder (jf. spec).
- Fjernede dage slettes PERMANENT, uanset status (pending/approved/deactivated) — MEN hele kaldet afvises (ingen delvis anvendelse), hvis en fjernet dags lønperiode allerede er `closed`.
- Ingen ny rettighed/permission — samme åbne adgang (`get_current_user`) som resten af `/api/activities`, undtagen den eksisterende vagtplan-adgangskontrol (`_has_vagtplan_edit_access`) som skal håndhæves når periodens aktiviteter har `source == vagtplan`.
- Gælder kun typerne i `_RANGE_TYPES` (`app.js`): `ferie`, `feriefri`, `barsel`, `sygdom`, `paragraf_56_syg`, `graviditetsbetinget_sygdom`, `skole_kursus`, `afspadsering`.
- Spec: `docs/superpowers/specs/2026-09-07-rediger-fravaersperiode-design.md`.

---

### Task 1: Datamodel — `absence_group_id`

**Files:**
- Modify: `app/database/models.py` (klassen `Activity`, omkring linje 131-201)
- Modify: `app/database/session.py` (`_migrate()`, omkring linje 166-169)
- Test: `tests/test_absence_group_model.py`

**Interfaces:**
- Produces: `Activity.absence_group_id: str | None` — læses/sættes af alle senere tasks.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_absence_group_model.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

from database.models import Activity, ActivityStatus


def test_activity_can_be_created_and_queried_with_absence_group_id(db, employee):
    from conftest import make_activity
    a1 = make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                       activity_type="ferie", status=ActivityStatus.approved)
    a1.absence_group_id = "grp-1"
    a2 = make_activity(db, employee, datetime(2026, 1, 6, 6, 0), datetime(2026, 1, 6, 14, 0),
                       activity_type="ferie", status=ActivityStatus.approved)
    a2.absence_group_id = "grp-1"
    db.commit()

    rows = db.query(Activity).filter(Activity.absence_group_id == "grp-1").order_by(Activity.start_time).all()
    assert [r.id for r in rows] == [a1.id, a2.id]


def test_activity_absence_group_id_defaults_to_none(db, employee):
    from conftest import make_activity
    a = make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0))
    assert a.absence_group_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_absence_group_model.py -v`
Expected: FAIL — `AttributeError: 'Activity' object has no attribute 'absence_group_id'` (eller SQLAlchemy `InvalidRequestError`, da kolonnen ikke findes på modellen endnu).

- [ ] **Step 3: Tilføj kolonnen til modellen**

I `app/database/models.py`, find `Activity`-klassen. Den nuværende sidste kolonne før relationships er:

```python
    baseline_duration_minutes = Column(Numeric(10, 4), nullable=True)
    baseline_start_hour = Column(Numeric(8, 4), nullable=True)

    employee = relationship("Employee", back_populates="activities")
```

Erstat med (ny kolonne indsat før relationships):

```python
    baseline_duration_minutes = Column(Numeric(10, 4), nullable=True)
    baseline_start_hour = Column(Numeric(8, 4), nullable=True)
    # Sættes KUN når en flerdags-fraværsperiode oprettes (samme værdi på alle
    # dagenes Activity-rækker) – bruges til at redigere periodens fra/til-dato
    # samlet. Null for enkeltdags-aktiviteter og for perioder oprettet før
    # denne kolonne fandtes (ingen tilbagevirkende migrering).
    absence_group_id = Column(String(36), nullable=True)

    employee = relationship("Employee", back_populates="activities")
```

Tilføj derefter et index i `__table_args__` (find den eksisterende tuple, der slutter med `ix_activities_period_status`-indekset):

```python
        Index("ix_activities_period_status", "pay_period_id", "status"),
    )
```

Erstat med:

```python
        Index("ix_activities_period_status", "pay_period_id", "status"),
        Index("ix_activities_absence_group", "absence_group_id"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_absence_group_model.py -v`
Expected: PASS (testene bruger `Base.metadata.create_all()` i `conftest.py`s `db`-fixture, som automatisk opretter den nye kolonne på den friske in-memory-DB — ingen migrering nødvendig for testene).

- [ ] **Step 5: Tilføj den idempotente migrering (for eksisterende produktions-databaser)**

I `app/database/session.py`, find blokken i `_migrate()`:

```python
        if "hidden_from_vagtplan" not in act_cols2:
            conn.execute("ALTER TABLE activities ADD COLUMN hidden_from_vagtplan BOOLEAN NOT NULL DEFAULT 0")
            conn.commit()
        existing_indexes = {row[1] for row in conn.execute("PRAGMA index_list(activities)")}
```

Erstat med:

```python
        if "hidden_from_vagtplan" not in act_cols2:
            conn.execute("ALTER TABLE activities ADD COLUMN hidden_from_vagtplan BOOLEAN NOT NULL DEFAULT 0")
            conn.commit()
        if "absence_group_id" not in act_cols2:
            conn.execute("ALTER TABLE activities ADD COLUMN absence_group_id VARCHAR(36)")
            conn.commit()
        existing_indexes = {row[1] for row in conn.execute("PRAGMA index_list(activities)")}
```

Find derefter blokken (lidt længere nede i samme funktion):

```python
        if "ix_activities_period_status" not in existing_indexes:
            conn.execute(
                "CREATE INDEX ix_activities_period_status ON activities(pay_period_id, status)"
            )
            conn.commit()
```

Erstat med:

```python
        if "ix_activities_period_status" not in existing_indexes:
            conn.execute(
                "CREATE INDEX ix_activities_period_status ON activities(pay_period_id, status)"
            )
            conn.commit()
        if "ix_activities_absence_group" not in existing_indexes:
            conn.execute(
                "CREATE INDEX ix_activities_absence_group ON activities(absence_group_id)"
            )
            conn.commit()
```

**Manuel verifikation af migreringen** (ikke automatiseret, jf. resten af `_migrate()`s eksisterende kolonner, som heller ikke har tests): stop den kørende server, ryd `app/__pycache__`, genstart (`uvicorn main:app --reload`) mod en eksisterende `lonsystem.db`, og bekræft at opstarten ikke fejler og at `PRAGMA table_info(activities)` (fx via DB Browser for SQLite) nu indeholder `absence_group_id`.

- [ ] **Step 6: Run alle eksisterende tests for at sikre ingen regression**

Run: `pytest tests/ -q`
Expected: Alle tests der kørte før stadig passerer (ingen ændring i eksisterende adfærd).

- [ ] **Step 7: Commit**

```bash
git add app/database/models.py app/database/session.py tests/test_absence_group_model.py
git commit -m "feat: tilføj absence_group_id til Activity (grundlag for periode-redigering)"
```

---

### Task 2: Schemas

**Files:**
- Modify: `app/database/schemas.py` (`ActivityResponse`, `ActivityCreate`, samt nye klasser i bunden af filen)
- Test: `tests/test_absence_group_schemas.py`

**Interfaces:**
- Consumes: intet (ren schema-task).
- Produces: `ActivityCreate.absence_group_id: str | None`, `ActivityResponse.absence_group_id: str | None`, `AbsenceGroupDatesUpdate(new_start_date, new_end_date)`, `AbsenceGroupUpdateResponse(activities, skipped)` — bruges af Task 3, 5 og 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_absence_group_schemas.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest
from pydantic import ValidationError

from database.schemas import ActivityCreate, AbsenceGroupDatesUpdate


def test_activity_create_accepts_absence_group_id():
    body = ActivityCreate(
        employee_id=1,
        activity_type="ferie",
        start_time="2026-01-05T06:00:00",
        end_time="2026-01-05T14:00:00",
        absence_group_id="grp-abc-123",
    )
    assert body.absence_group_id == "grp-abc-123"


def test_activity_create_absence_group_id_defaults_to_none():
    body = ActivityCreate(
        employee_id=1,
        activity_type="normal",
        start_time="2026-01-05T06:00:00",
        end_time="2026-01-05T14:00:00",
    )
    assert body.absence_group_id is None


def test_absence_group_dates_update_rejects_end_before_start():
    with pytest.raises(ValidationError):
        AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 9), new_end_date=date(2026, 1, 5))


def test_absence_group_dates_update_accepts_valid_range():
    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 9))
    assert body.new_start_date == date(2026, 1, 5)
    assert body.new_end_date == date(2026, 1, 9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_absence_group_schemas.py -v`
Expected: FAIL — `TypeError`/`ValidationError: absence_group_id ... unexpected keyword argument` og `ImportError: cannot import name 'AbsenceGroupDatesUpdate'`.

- [ ] **Step 3: Tilføj felterne til `ActivityResponse` og `ActivityCreate`**

I `app/database/schemas.py`, find slutningen af `ActivityResponse`:

```python
    is_likely_incomplete: bool = False
    hidden_from_vagtplan: bool = False


class ActivityCreate(BaseModel):
```

Erstat med:

```python
    is_likely_incomplete: bool = False
    hidden_from_vagtplan: bool = False
    absence_group_id: Optional[str] = None


class ActivityCreate(BaseModel):
```

Find derefter i `ActivityCreate`:

```python
    pause_intervals: list = Field(default_factory=list)
    source: Optional[str] = None
```

Erstat med:

```python
    pause_intervals: list = Field(default_factory=list)
    source: Optional[str] = None
    absence_group_id: Optional[str] = Field(default=None, max_length=36)
```

- [ ] **Step 4: Tilføj de to nye schema-klasser**

I bunden af `app/database/schemas.py` (efter `ActivitySplit`, før evt. efterfølgende klasser som `AnciennitetsAlert`), indsæt:

```python
class AbsenceGroupDatesUpdate(BaseModel):
    new_start_date: date
    new_end_date: date

    @model_validator(mode="after")
    def end_after_start(self):
        if self.new_end_date < self.new_start_date:
            raise ValueError("Til dato skal være på eller efter fra dato")
        return self


class AbsenceGroupUpdateResponse(BaseModel):
    activities: list[ActivityResponse]
    skipped: list[str] = []
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_absence_group_schemas.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/database/schemas.py tests/test_absence_group_schemas.py
git commit -m "feat: tilføj absence_group_id-felt og periode-dato schemas"
```

---

### Task 3: `create_manual_activity` gemmer og returnerer `absence_group_id`

**Files:**
- Modify: `app/routers/activities.py` (`_to_response()` omkring linje 234-277, `create_manual_activity()` omkring linje 418-495)
- Test: `tests/test_absence_group_create.py`

**Interfaces:**
- Consumes: `ActivityCreate.absence_group_id`, `ActivityResponse.absence_group_id` (Task 2).
- Produces: `_to_response(a)` inkluderer nu `absence_group_id` — forventes af Task 5/6's tests, der læser aktiviteter via `_to_response`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_absence_group_create.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

from database.models import AppUser
from database.schemas import ActivityCreate


def _user(initials="LB1"):
    return AppUser(name="Test", initials=initials, role="lonbogholder", password_hash="x")


def test_create_manual_activity_persists_absence_group_id(db, employee):
    from routers.activities import create_manual_activity

    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="ferie",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),
        absence_group_id="grp-xyz",
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.absence_group_id == "grp-xyz"


def test_create_manual_activity_without_group_id_returns_none(db, employee):
    from routers.activities import create_manual_activity

    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.absence_group_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_absence_group_create.py -v`
Expected: FAIL — `assert None == 'grp-xyz'` (feltet gemmes/mappes endnu ikke).

- [ ] **Step 3: Map feltet i `_to_response`**

I `app/routers/activities.py`, find slutningen af `_to_response()`:

```python
        is_likely_incomplete=bool(a.is_likely_incomplete),
        hidden_from_vagtplan=bool(a.hidden_from_vagtplan),
    )
```

Erstat med:

```python
        is_likely_incomplete=bool(a.is_likely_incomplete),
        hidden_from_vagtplan=bool(a.hidden_from_vagtplan),
        absence_group_id=a.absence_group_id,
    )
```

- [ ] **Step 4: Gem feltet ved oprettelse**

I samme fil, find `Activity(...)`-konstruktøren i `create_manual_activity()`:

```python
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
```

Erstat med:

```python
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
        absence_group_id=body.absence_group_id,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_absence_group_create.py -v`
Expected: PASS

- [ ] **Step 6: Run alle eksisterende tests**

Run: `pytest tests/ -q`
Expected: Alle passerer (ingen ændring i eksisterende felter/adfærd).

- [ ] **Step 7: Commit**

```bash
git add app/routers/activities.py tests/test_absence_group_create.py
git commit -m "feat: gem og returnér absence_group_id ved oprettelse af aktivitet"
```

---

### Task 4: Hjælpefunktioner — hverdags-datoer og timetal pr. dag

**Files:**
- Modify: `app/routers/activities.py` (nye modul-funktioner, indsæt lige efter `_EIGHT_WEEKS = 56` omkring linje 415, FØR `create_manual_activity`)
- Test: `tests/test_absence_group_helpers.py`

**Interfaces:**
- Consumes: `Employee.work_schedule` (Task-uafhængigt, allerede eksisterende felt), `calculators.pay_period.is_even_week`.
- Produces: `_weekday_dates(start: date, end: date) -> list[date]`, `_range_day_defaults(activity_type: str, d: date, employee: Employee) -> float | None` — bruges direkte af Task 6.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_absence_group_helpers.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

from database.models import Employee, AgreementKind


def _emp(schedule):
    return Employee(
        employee_number="9999", first_name="Test", last_name="Medarbejder",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1), work_schedule=schedule,
    )


def test_weekday_dates_excludes_weekend():
    from routers.activities import _weekday_dates
    dates = _weekday_dates(date(2026, 1, 5), date(2026, 1, 11))  # man 5/1 - søn 11/1
    assert dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                     date(2026, 1, 8), date(2026, 1, 9)]


def test_weekday_dates_single_day():
    from routers.activities import _weekday_dates
    assert _weekday_dates(date(2026, 1, 7), date(2026, 1, 7)) == [date(2026, 1, 7)]


def test_range_day_defaults_uses_scheduled_hours_for_ferie():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]})
    assert _range_day_defaults("ferie", date(2026, 1, 5), emp) == 8  # mandag uge 2 (lige)


def test_range_day_defaults_falls_back_to_7_4_when_no_schedule():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [0, 0, 0, 0, 0, 0, 0], "odd": [0, 0, 0, 0, 0, 0, 0]})
    assert _range_day_defaults("ferie", date(2026, 1, 5), emp) == 7.4


def test_range_day_defaults_feriefri_always_7_4_ignoring_schedule():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]})
    assert _range_day_defaults("feriefri", date(2026, 1, 5), emp) == 7.4


def test_range_day_defaults_afspadsering_uses_scheduled_hours():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [8, 8, 0, 8, 8, 0, 0], "odd": [8, 8, 0, 8, 8, 0, 0]})
    assert _range_day_defaults("afspadsering", date(2026, 1, 5), emp) == 8  # mandag = 8


def test_range_day_defaults_afspadsering_skips_zero_scheduled_day():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [8, 8, 0, 8, 8, 0, 0], "odd": [8, 8, 0, 8, 8, 0, 0]})
    assert _range_day_defaults("afspadsering", date(2026, 1, 7), emp) is None  # onsdag = 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_absence_group_helpers.py -v`
Expected: FAIL — `ImportError: cannot import name '_weekday_dates'`.

- [ ] **Step 3: Tilføj `time` til imports og implementér hjælpefunktionerne**

I `app/routers/activities.py`, find import-linjen øverst:

```python
from datetime import date, datetime, timedelta
```

Erstat med:

```python
from datetime import date, datetime, time, timedelta
```

Find derefter:

```python
from calculators.pay_period import get_billing_period, get_or_create_period_for_date
```

Erstat med:

```python
from calculators.pay_period import get_billing_period, get_or_create_period_for_date, is_even_week
```

Find:

```python
_EIGHT_WEEKS = 56  # dage
```

Erstat med:

```python
_EIGHT_WEEKS = 56  # dage


def _weekday_dates(start: date, end: date) -> list[date]:
    """Alle hverdage (mandag-fredag) i [start, end] – mirror af getWeekdayDates() i app.js."""
    dates = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    return dates


def _range_day_defaults(activity_type: str, d: date, employee: Employee) -> Optional[float]:
    """Timetal for én dag i en fraværsperiode, eller None hvis dagen skal
    springes over (afspadsering uden skemalagte timer denne ugedag). Mirror af
    confirmManualActivity()'s isRange-gren i app.js – hold de to i sync ved
    ændringer af den ene."""
    schedule = employee.work_schedule or {}
    week_key = "even" if is_even_week(d) else "odd"
    week = schedule.get(week_key) or []
    idx = d.weekday()
    scheduled = week[idx] if idx < len(week) else 0

    if activity_type == "afspadsering":
        return scheduled if scheduled > 0 else None
    if activity_type == "feriefri":
        return 7.4
    return scheduled if scheduled > 0 else 7.4
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_absence_group_helpers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/activities.py tests/test_absence_group_helpers.py
git commit -m "feat: hjælpefunktioner til hverdage og timetal for fraværsperioder"
```

---

### Task 5: `GET /api/activities/absence-group/{group_id}`

**Files:**
- Modify: `app/routers/activities.py` (ny route, indsæt lige efter `create_manual_activity()`, FØR `get_activity()` omkring linje 498)
- Test: `tests/test_absence_group_get.py`

**Interfaces:**
- Consumes: `_to_response` (Task 3).
- Produces: `get_absence_group(group_id, current_user, db) -> list[ActivityResponse]` — bruges direkte af Task 6's test (til at bekræfte gruppens tilstand efter en PATCH) og af frontend (Task 8/9).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_absence_group_get.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

import pytest
from fastapi import HTTPException

from database.models import AppUser, ActivityStatus


def _user(initials="LB1"):
    return AppUser(name="Test", initials=initials, role="lonbogholder", password_hash="x")


def test_get_absence_group_returns_all_days_sorted(db, employee):
    from conftest import make_activity
    from routers.activities import get_absence_group

    a1 = make_activity(db, employee, datetime(2026, 1, 6, 6, 0), datetime(2026, 1, 6, 14, 0),
                       activity_type="ferie", status=ActivityStatus.approved)
    a1.absence_group_id = "grp-1"
    a2 = make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                       activity_type="ferie", status=ActivityStatus.approved)
    a2.absence_group_id = "grp-1"
    db.commit()

    result = get_absence_group("grp-1", current_user=_user(), db=db)
    assert [r.id for r in result] == [a2.id, a1.id]  # sorteret efter start_time


def test_get_absence_group_404_when_empty(db, employee):
    from routers.activities import get_absence_group

    with pytest.raises(HTTPException) as exc_info:
        get_absence_group("does-not-exist", current_user=_user(), db=db)
    assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_absence_group_get.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_absence_group'`.

- [ ] **Step 3: Implementér endpointet**

I `app/routers/activities.py`, find slutningen af `create_manual_activity()`:

```python
    log_action(db, current_user, "create_activity", "activity", activity.id,
               f"Manuelt oprettet for {emp.name}")
    db.commit()
    db.refresh(activity)
    return _to_response(activity)


@router.get("/{activity_id}", response_model=ActivityResponse)
def get_activity(activity_id: int,
```

Erstat med:

```python
    log_action(db, current_user, "create_activity", "activity", activity.id,
               f"Manuelt oprettet for {emp.name}")
    db.commit()
    db.refresh(activity)
    return _to_response(activity)


@router.get("/absence-group/{group_id}", response_model=list[ActivityResponse])
def get_absence_group(group_id: str,
                      current_user: AppUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    activities = (
        db.query(Activity)
        .options(selectinload(Activity.employee), selectinload(Activity.split_children))
        .filter(Activity.absence_group_id == group_id)
        .order_by(Activity.start_time)
        .all()
    )
    if not activities:
        raise HTTPException(404, "Fraværsperiode ikke fundet")
    return [_to_response(a) for a in activities]


@router.get("/{activity_id}", response_model=ActivityResponse)
def get_activity(activity_id: int,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_absence_group_get.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/activities.py tests/test_absence_group_get.py
git commit -m "feat: GET-endpoint til at hente en fraværsperiodes aktiviteter"
```

---

### Task 6: `PATCH /api/activities/absence-group/{group_id}` — periode-redigering

**Files:**
- Modify: `app/routers/activities.py` (ny route, indsæt lige efter `get_absence_group()` fra Task 5)
- Modify: `app/routers/activities.py` (import-linjen for `database.schemas`)
- Test: `tests/test_absence_group_patch.py`

**Interfaces:**
- Consumes: `_weekday_dates`, `_range_day_defaults` (Task 4), `get_absence_group` (Task 5, genbruges ikke direkte men samme query-mønster), `AbsenceGroupDatesUpdate`/`AbsenceGroupUpdateResponse` (Task 2), `_has_vagtplan_edit_access` (eksisterende, linje ~76).
- Produces: `update_absence_group_dates(group_id, body, current_user, db) -> AbsenceGroupUpdateResponse` — bruges af frontend (Task 9).

- [ ] **Step 1: Write the failing tests (grundlæggende scenarier)**

```python
# tests/test_absence_group_patch.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime, date

import pytest
from fastapi import HTTPException

from database.models import Activity, AppUser, ActivityStatus, ActivitySource, PayPeriodStatus, Role
from database.schemas import AbsenceGroupDatesUpdate


def _user(role="lonbogholder", initials="LB1"):
    return AppUser(name="Test", initials=initials, role=role, password_hash="x")


def _grant(db, role_name, permissions, is_system=False):
    db.add(Role(name=role_name, display_name=role_name, is_system=is_system, permissions=permissions))
    db.commit()


def _make_group(db, employee, dates, activity_type="ferie", status=ActivityStatus.approved,
                group_id="grp-1", source=ActivitySource.manual):
    from conftest import make_activity
    acts = []
    for d in dates:
        a = make_activity(db, employee,
                          datetime.combine(d, datetime.min.time().replace(hour=6)),
                          datetime.combine(d, datetime.min.time().replace(hour=14)),
                          activity_type=activity_type, source=source, status=status)
        a.absence_group_id = group_id
        acts.append(a)
    db.commit()
    return acts


def test_shrinking_range_deletes_pending_days_outside_new_range(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)]
    _make_group(db, employee, dates, status=ActivityStatus.pending)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 7))
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    assert db.query(Activity).filter(Activity.absence_group_id == "grp-1").count() == 3


def test_growing_range_creates_new_days_with_scheduled_hours(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)]
    _make_group(db, employee, dates)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 13))
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                               date(2026, 1, 8), date(2026, 1, 9),
                               date(2026, 1, 12), date(2026, 1, 13)]
    new_day = next(a for a in result.activities if a.start_time.date() == date(2026, 1, 12))
    assert new_day.start_time.strftime("%H:%M") == "06:00"
    assert new_day.end_time.strftime("%H:%M") == "14:00"  # 8 timer skemalagt (mandag)
    assert new_day.status == ActivityStatus.approved
    assert result.skipped == []


def test_unchanged_days_are_not_touched(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6)]
    acts = _make_group(db, employee, dates)
    original_id = acts[0].id
    original_approved_at = acts[0].approved_at

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 7))
    update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    kept = db.query(Activity).filter(Activity.id == original_id).first()
    assert kept is not None
    assert kept.approved_at == original_approved_at
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_absence_group_patch.py -v`
Expected: FAIL — `ImportError: cannot import name 'update_absence_group_dates'`.

- [ ] **Step 3: Implementér endpointet (grundlæggende diff-logik)**

I `app/routers/activities.py`, find import-linjen for schemas:

```python
from database.schemas import (
    ActivityApprove,
    ActivityCreate,
    ActivityDeactivate,
    ActivityResponse,
    ActivitySplit,
    ActivityUpdate,
    VagtplanHideBody,
)
```

Erstat med:

```python
from database.schemas import (
    AbsenceGroupDatesUpdate,
    AbsenceGroupUpdateResponse,
    ActivityApprove,
    ActivityCreate,
    ActivityDeactivate,
    ActivityResponse,
    ActivitySplit,
    ActivityUpdate,
    VagtplanHideBody,
)
```

Find derefter slutningen af `get_absence_group()` (fra Task 5):

```python
    if not activities:
        raise HTTPException(404, "Fraværsperiode ikke fundet")
    return [_to_response(a) for a in activities]


@router.get("/{activity_id}", response_model=ActivityResponse)
def get_activity(activity_id: int,
```

Erstat med:

```python
    if not activities:
        raise HTTPException(404, "Fraværsperiode ikke fundet")
    return [_to_response(a) for a in activities]


@router.patch("/absence-group/{group_id}", response_model=AbsenceGroupUpdateResponse)
def update_absence_group_dates(group_id: str, body: AbsenceGroupDatesUpdate,
                               current_user: AppUser = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    activities = (
        db.query(Activity)
        .filter(Activity.absence_group_id == group_id)
        .order_by(Activity.start_time)
        .all()
    )
    if not activities:
        raise HTTPException(404, "Fraværsperiode ikke fundet")

    template = activities[0]
    employee = db.query(Employee).filter(Employee.id == template.employee_id).first()
    activity_type = template.activity_type

    if template.source == ActivitySource.vagtplan and not _has_vagtplan_edit_access(db, current_user, employee):
        raise HTTPException(403, "Ingen redigeringsret til Vagtplan for denne medarbejder")

    new_dates = set(_weekday_dates(body.new_start_date, body.new_end_date))
    if not new_dates:
        raise HTTPException(400, "Ingen hverdage i den valgte periode")

    existing_by_date = {a.start_time.date(): a for a in activities}
    existing_dates = set(existing_by_date)

    to_remove_dates = existing_dates - new_dates
    to_add_dates = sorted(new_dates - existing_dates)

    # Trin 1: validér ALLE fjernelser FØR nogen ændring foretages (alt-eller-intet)
    for d in to_remove_dates:
        act = existing_by_date[d]
        if act.pay_period.status == PayPeriodStatus.closed:
            raise HTTPException(
                400,
                f"Kan ikke fjerne {d.strftime('%d-%m-%Y')} – lønperioden er allerede afsluttet",
            )
        if act.split_children:
            raise HTTPException(
                400,
                f"Kan ikke fjerne {d.strftime('%d-%m-%Y')} – aktiviteten er splittet, fortryd splittet først",
            )

    # Trin 2: fjern
    for d in to_remove_dates:
        act = existing_by_date[d]
        log_action(db, current_user, "delete_activity", "activity", act.id,
                  f"Slettet permanent for {act.employee.name} ({act.start_time.strftime('%d-%m-%Y')}, "
                  f"{act.activity_type}) – periode-redigering")
        db.delete(act)

    # Trin 3: tilføj
    skipped: list[str] = []
    for d in to_add_dates:
        hours = _range_day_defaults(activity_type, d, employee)
        if hours is None:
            skipped.append(d.isoformat())
            continue
        start_dt = datetime.combine(d, time(6, 0))
        end_dt = start_dt + timedelta(minutes=round(hours * 60))
        period = get_billing_period(d, db)
        db.add(Activity(
            employee_id=template.employee_id,
            pay_period_id=period.id,
            source=template.source,
            created_by=current_user.initials,
            activity_type=activity_type,
            start_time=start_dt,
            end_time=end_dt,
            vehicle_number=template.vehicle_number,
            pause_intervals=[],
            segments=[],
            status=ActivityStatus.approved,
            approved_by=current_user.initials,
            approved_at=datetime.utcnow(),
            absence_group_id=group_id,
        ))

    log_action(db, current_user, "update_absence_group_dates", "activity", template.id,
              f"{employee.name}: periode ændret til {body.new_start_date.strftime('%d-%m-%Y')}–"
              f"{body.new_end_date.strftime('%d-%m-%Y')} ({len(to_remove_dates)} fjernet, "
              f"{len(to_add_dates) - len(skipped)} tilføjet)")
    db.commit()

    result = (
        db.query(Activity)
        .options(selectinload(Activity.employee), selectinload(Activity.split_children))
        .filter(Activity.absence_group_id == group_id)
        .order_by(Activity.start_time)
        .all()
    )
    return AbsenceGroupUpdateResponse(
        activities=[_to_response(a) for a in result],
        skipped=skipped,
    )


@router.get("/{activity_id}", response_model=ActivityResponse)
def get_activity(activity_id: int,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_absence_group_patch.py -v`
Expected: PASS (alle tre tests fra Step 1)

- [ ] **Step 5: Write failing tests for guard rails (lukket periode, split, vagtplan-rettighed, sprungne dage)**

Tilføj til `tests/test_absence_group_patch.py`:

```python
def test_removing_day_in_closed_period_blocks_entire_call(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    acts = _make_group(db, employee, dates, status=ActivityStatus.pending)
    # Luk lønperioden for den dag der skulle fjernes
    acts[2].pay_period.status = PayPeriodStatus.closed
    db.commit()

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    with pytest.raises(HTTPException) as exc_info:
        update_absence_group_dates("grp-1", body, current_user=_user(), db=db)
    assert exc_info.value.status_code == 400

    # Intet må være ændret – alle tre dage skal stadig findes
    assert db.query(Activity).filter(Activity.absence_group_id == "grp-1").count() == 3


def test_removing_split_activity_blocks_entire_call(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6)]
    acts = _make_group(db, employee, dates, status=ActivityStatus.pending)
    # Simulér et split-barn på den dag der skulle fjernes
    child = Activity(
        employee_id=employee.id, pay_period_id=acts[1].pay_period_id, source=ActivitySource.manual,
        activity_type="ferie", start_time=acts[1].start_time, end_time=acts[1].end_time,
        status=ActivityStatus.pending, pause_intervals=[], segments=[],
        parent_activity_id=acts[1].id, split_part=1,
    )
    db.add(child)
    db.commit()

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 5))
    with pytest.raises(HTTPException) as exc_info:
        update_absence_group_dates("grp-1", body, current_user=_user(), db=db)
    assert exc_info.value.status_code == 400
    assert db.query(Activity).filter(Activity.absence_group_id == "grp-1").count() == 2


def test_afspadsering_skips_day_with_no_scheduled_hours(db):
    from routers.activities import update_absence_group_dates
    from database.models import Employee, AgreementKind
    emp = Employee(
        employee_number="9998", first_name="Test", last_name="Afspadserer",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 0, 8, 8, 0, 0], "odd": [8, 8, 0, 8, 8, 0, 0]},  # onsdag = 0
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    dates = [date(2026, 1, 5), date(2026, 1, 6)]  # man+tir
    _make_group(db, emp, dates, activity_type="afspadsering")

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 7))  # +onsdag
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    assert result.skipped == [date(2026, 1, 7).isoformat()]
    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert date(2026, 1, 7) not in remaining_dates


def test_vagtplan_source_without_permission_is_forbidden(db, employee):
    from routers.activities import update_absence_group_dates
    _grant(db, "disponent", [])
    _make_group(db, employee, [date(2026, 1, 5), date(2026, 1, 6)], source=ActivitySource.vagtplan)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    with pytest.raises(HTTPException) as exc_info:
        update_absence_group_dates("grp-1", body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert exc_info.value.status_code == 403


def test_vagtplan_source_with_permission_succeeds(db, employee):
    from routers.activities import update_absence_group_dates
    _grant(db, "disponent", ["vagtplan_edit_all"])
    _make_group(db, employee, [date(2026, 1, 5), date(2026, 1, 6)], source=ActivitySource.vagtplan)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    result = update_absence_group_dates("grp-1", body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert len(result.activities) == 2
```

- [ ] **Step 6: Run test to verify it fails or passes**

Run: `pytest tests/test_absence_group_patch.py -v`
Expected: `test_removing_day_in_closed_period_blocks_entire_call`, `test_removing_split_activity_blocks_entire_call`,
`test_afspadsering_skips_day_with_no_scheduled_hours` og de to vagtplan-tests skal alle PASS allerede, da
guard-logikken blev skrevet i Step 3 (den fulde implementering var ikke opdelt i delvise trin). Bekræft dette
ved at køre testene og se alle ni tests i filen bestå. Hvis en enkelt fejler, ret implementeringen fra Step 3
tilsvarende (fx en tastefejl i betingelsen) og kør igen.

- [ ] **Step 7: Run alle eksisterende tests for at sikre ingen regression**

Run: `pytest tests/ -q`
Expected: Alle tests passerer.

- [ ] **Step 8: Commit**

```bash
git add app/routers/activities.py tests/test_absence_group_patch.py
git commit -m "feat: PATCH-endpoint til at redigere en fraværsperiodes fra/til-dato"
```

---

### Task 7: Frontend — generér og send `absence_group_id` ved oprettelse

**Files:**
- Modify: `app/static/js/app.js` (`confirmManualActivity()`s `isRange`-gren, omkring linje 2308-2379)

**Interfaces:**
- Produces: hvert `POST /api/activities`-kald i `isRange`-grenen sender nu `absence_group_id`, som er den samme værdi for alle dage i samme oprettelse.

- [ ] **Step 1: Tilføj en robust UUID-hjælpefunktion**

`crypto.randomUUID()` kræver en "secure context" (HTTPS eller `localhost`) i nogle browsere – appen kører i dag
på almindelig `http://` over LAN (jf. `docs/superpowers/specs/2026-08-29-...`/SSO-status), så et direkte kald
ville kaste en exception og ødelægge HELE flerdags-oprettelsen, ikke kun grupperingen. Tilføj derfor en fallback.

I `app/static/js/app.js`, find:

```js
function getWeekdayDates(from, to) {
```

Indsæt lige FØR denne linje:

```js
function _genGroupId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for ikke-sikre kontekster (fx almindelig http:// på LAN, hvor
  // crypto.randomUUID() ikke er tilgængelig) – kun brugt til at gruppere
  // aktiviteter oprettet i samme kald, ikke som kryptografisk nøgle.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === "x" ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

function getWeekdayDates(from, to) {
```

- [ ] **Step 2: Generér gruppe-id før løkken og send det med hvert POST-kald**

Find (i `confirmManualActivity()`s `isRange`-gren):

```js
    const emp = state.employees.find(e => e.id === empId);
    let created = 0;
    const skippedNoHours = [];
    try {
      for (const iso of dates) {
```

Erstat med:

```js
    const emp = state.employees.find(e => e.id === empId);
    let created = 0;
    const skippedNoHours = [];
    const absenceGroupId = _genGroupId();
    try {
      for (const iso of dates) {
```

Find derefter:

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
        created++;
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
          absence_group_id: absenceGroupId,
          source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
        });
        created++;
```

- [ ] **Step 3: Manuel verifikation**

Da projektet ikke har et JS-testværktøj, verificeres denne ændring sammen med Task 9's browser-gennemgang
(se Task 9, Step 3-4) – ingen separat verifikationsstep her.

- [ ] **Step 4: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: send fælles gruppe-id ved oprettelse af en fraværsperiode"
```

---

### Task 8: Frontend — "Fraværsperiode"-sektion i aktivitets-modalen

**Files:**
- Modify: `app/static/js/app.js` (`openActivityDetail()`, omkring linje 777-985)
- Modify: `app/templates/index.html` (`style.css?v=N` – kun hvis Task 8/9 tilføjer ny CSS, se Step 4)

**Interfaces:**
- Consumes: `GET /api/activities/absence-group/{group_id}` (Task 5).
- Produces: DOM-elementerne `#edit-period-start`, `#edit-period-end`, og en knap der kalder `saveAbsencePeriodDates(groupId)` (implementeres i Task 9) — vises kun når den åbnede aktivitet har `absence_group_id`.

- [ ] **Step 1: Gør `openActivityDetail` async og hent gruppens datoer først**

I `app/static/js/app.js`, find:

```js
function openActivityDetail(id) {
  const modalEl = document.getElementById("modal-activity");
  const reopeningSameActivity = modalEl.classList.contains("open") && state.selectedActivityId === id;
  let preservedEdits = null;
  if (reopeningSameActivity) {
    preservedEdits = {
      start: readDatetimePicker("edit-start"),
      end: readDatetimePicker("edit-end"),
      vehicle: document.getElementById("edit-vehicle")?.value,
      kmStart: document.getElementById("edit-km-start")?.value,
      kmEnd: document.getElementById("edit-km-end")?.value,
      salt: document.getElementById("edit-salt")?.checked,
      dob: document.getElementById("edit-dob")?.checked,
    };
  }
  state.selectedActivityId = id;
  const a = _findLoadedActivity(id);
  if (!a) return;

  document.getElementById("modal-activity-title").textContent =
    `${a.employee_name} – ${formatDate(a.start_time)}`;
```

Erstat med:

```js
async function openActivityDetail(id) {
  const modalEl = document.getElementById("modal-activity");
  const reopeningSameActivity = modalEl.classList.contains("open") && state.selectedActivityId === id;
  let preservedEdits = null;
  if (reopeningSameActivity) {
    preservedEdits = {
      start: readDatetimePicker("edit-start"),
      end: readDatetimePicker("edit-end"),
      vehicle: document.getElementById("edit-vehicle")?.value,
      kmStart: document.getElementById("edit-km-start")?.value,
      kmEnd: document.getElementById("edit-km-end")?.value,
      salt: document.getElementById("edit-salt")?.checked,
      dob: document.getElementById("edit-dob")?.checked,
    };
  }
  state.selectedActivityId = id;
  const a = _findLoadedActivity(id);
  if (!a) return;

  let absencePeriod = null;
  if (a.absence_group_id) {
    try {
      const group = await GET(`/api/activities/absence-group/${a.absence_group_id}`);
      const groupDates = group.map(g => g.start_time.slice(0, 10)).sort();
      absencePeriod = {
        groupId: a.absence_group_id,
        start: groupDates[0],
        end: groupDates[groupDates.length - 1],
      };
    } catch (e) { /* gruppen kunne ikke hentes – periode-sektionen udelades, enkeltdags-redigering virker stadig */ }
  }

  document.getElementById("modal-activity-title").textContent =
    `${a.employee_name} – ${formatDate(a.start_time)}`;
```

- [ ] **Step 2: Indsæt periode-sektionen øverst i modal-body**

Find (starten af `innerHTML`-templaten):

```js
  document.getElementById("modal-activity-body").innerHTML = `
    <div class="detail-grid">
```

Erstat med:

```js
  document.getElementById("modal-activity-body").innerHTML = `
    ${absencePeriod ? `
    <div class="form-group" id="absence-period-section" style="margin-bottom:14px;padding:10px;background:var(--bg);border-radius:var(--radius)">
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light);margin-bottom:6px;display:block">Fraværsperiode</label>
      <div class="form-row" style="margin-bottom:8px">
        <div class="form-group" style="min-width:0">
          <label>Fra dato</label>
          <input type="date" id="edit-period-start" value="${absencePeriod.start}">
        </div>
        <div class="form-group" style="min-width:0">
          <label>Til dato</label>
          <input type="date" id="edit-period-end" value="${absencePeriod.end}">
        </div>
      </div>
      <button type="button" class="btn btn-secondary" onclick="saveAbsencePeriodDates('${absencePeriod.groupId}')" style="font-size:13px;padding:5px 14px">Gem periodedatoer</button>
    </div>` : ""}
    <div class="detail-grid">
```

- [ ] **Step 3: Manuel verifikation (uden backend-ændring endnu er `saveAbsencePeriodDates` ikke defineret)**

Denne task alene giver en "ReferenceError: saveAbsencePeriodDates is not defined" hvis man klikker knappen –
det er forventet og rettes i Task 9. Test i browseren kun at sektionen VISES korrekt med de rigtige datoer for
en aktivitet der har et `absence_group_id` (fx en periode oprettet efter Task 7's ændring), og at den IKKE
vises for aktiviteter uden gruppe-id (normal tid, enkeltdags-fravær, alle historiske fraværsperioder).

- [ ] **Step 4: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: vis fraværsperiode-sektion i aktivitets-modalen"
```

---

### Task 9: Frontend — gem periodedatoer + fuld browser-verifikation

**Files:**
- Modify: `app/static/js/app.js` (ny funktion `saveAbsencePeriodDates`, placér lige efter `openActivityDetail()`s afsluttende funktioner – find et passende sted omkring linje 985-1000, fx lige før `saveActivityTimes()`)

**Interfaces:**
- Consumes: `getWeekdayDates` (eksisterende, linje 2155), `GET`/`PATCH` (eksisterende API-helpers), `refreshActivities`/`loadVagtplan` (eksisterende).
- Produces: `saveAbsencePeriodDates(groupId)` — kaldt fra knappen tilføjet i Task 8.

- [ ] **Step 1: Implementér `saveAbsencePeriodDates`**

I `app/static/js/app.js`, find (lige efter `openActivityDetail`s afsluttende `}` – brug funktionen
`saveActivityTimes` som anker, da den ligger umiddelbart efter i filen):

```js
async function saveActivityTimes() {
```

Indsæt lige FØR denne linje:

```js
async function saveAbsencePeriodDates(groupId) {
  const newStart = document.getElementById("edit-period-start").value;
  const newEnd   = document.getElementById("edit-period-end").value;
  if (!newStart || !newEnd) { toast("Angiv fra- og til-dato", "error"); return; }
  if (newEnd < newStart) { toast("Til dato skal være på eller efter fra dato", "error"); return; }

  let group;
  try {
    group = await GET(`/api/activities/absence-group/${groupId}`);
  } catch (e) { toast(e.message, "error"); return; }

  const empId = group[0].employee_id;
  const existingDates = group.map(g => g.start_time.slice(0, 10));
  const newDates = getWeekdayDates(newStart, newEnd);
  const toRemove = existingDates.filter(d => !newDates.includes(d));
  const toAdd    = newDates.filter(d => !existingDates.includes(d));

  if (toRemove.length === 0 && toAdd.length === 0) { toast("Ingen ændringer i perioden", "warning"); return; }

  if (toAdd.length > 0) {
    const conflicts = toAdd.filter(iso =>
      state.activities.some(a =>
        a.employee_id === empId &&
        a.activity_type === "normal" &&
        a.start_time.slice(0, 10) === iso &&
        a.status !== "deactivated"
      )
    );
    if (conflicts.length > 0) {
      const dateList = conflicts.map(d => { const [y,m,day]=d.split("-"); return `${day}-${m}-${y}`; }).join(", ");
      if (!window.confirm(`Der er allerede registreret kørsel på følgende dag${conflicts.length>1?"e":""}:\n${dateList}\n\nVil du alligevel udvide fraværsperioden til at inkludere den/dem?`)) return;
    }
  }

  const fmt = d => { const [y,m,day]=d.split("-"); return `${day}-${m}-${y}`; };
  const parts = [
    toRemove.length > 0 ? `${toRemove.length} dag${toRemove.length>1?"e":""} slettes permanent: ${toRemove.map(fmt).join(", ")}` : null,
    toAdd.length > 0 ? `${toAdd.length} dag${toAdd.length>1?"e":""} oprettes: ${toAdd.map(fmt).join(", ")}` : null,
  ].filter(Boolean).join("\n");
  if (!window.confirm(`${parts}\n\nFortsæt?`)) return;

  try {
    const result = await PATCH(`/api/activities/absence-group/${groupId}`, {
      new_start_date: newStart,
      new_end_date: newEnd,
    });
    toast("Fraværsperiode opdateret", "success");
    if (result.skipped && result.skipped.length > 0) {
      toast(`${result.skipped.length} dag${result.skipped.length>1?"e":""} sprunget over – ingen garanterede timer: ${result.skipped.map(fmt).join(", ")}`, "warning");
    }
    closeAllModals();
    await refreshActivities();
    if (state.currentView === "vagtplan") await loadVagtplan();
  } catch (e) { toast(e.message, "error"); }
}

async function saveActivityTimes() {
```

- [ ] **Step 2: Commit koden**

```bash
git add app/static/js/app.js
git commit -m "feat: gem-funktion til periode-redigering af fraværsdatoer"
```

- [ ] **Step 3: Start dev-serveren og forbered testdata**

Kør (stopper evt. kørende instans af serveren først, jf. CODEREF: `.py`-ændringer kræver genstart – denne
task rører ikke `.py`-filer, men en frisk genstart sikrer et rent udgangspunkt):

```bash
cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Åbn appen i browseren (brug Browser-værktøjet, ikke en almindelig terminal-check), log ind, og gå til
Aktivitetsoversigten.

- [ ] **Step 4: Verificér hele flowet i browseren**

1. Opret en ny fraværsperiode: vælg en medarbejder, type "Ferie", "Fra"-dato en mandag, "Til dato" den
   efterfølgende fredag (5 hverdage). Bekræft (via `read_network_requests`) at hvert af de 5
   `POST /api/activities`-kald indeholder samme `absence_group_id`-værdi i request-body.
2. Åbn én af de oprettede dage (klik på badgen i gitteret). Bekræft at modalen nu viser en
   "Fraværsperiode"-sektion øverst med korrekt "Fra dato"/"Til dato" (matcher de 5 dage).
3. Forkort perioden (ret "Til dato" til onsdag i samme uge) og klik "Gem periodedatoer". Bekræft
   bekræftelses-dialogen nævner de rigtige 2 datoer der slettes, og at gitteret efter "Fortsæt" kun viser
   3 dage tilbage for perioden.
4. Åbn en af de resterende dage igen og forlæng perioden til at inkludere den efterfølgende mandag+tirsdag.
   Bekræft de 2 nye dage oprettes med korrekt klokkeslæt (06:00 + skemalagte timer) og status "Godkendt".
5. Åbn en enkeltdags-fraværsaktivitet (oprettet UDEN "Til dato" udfyldt, eller en aktivitet oprettet før
   denne ændring). Bekræft "Fraværsperiode"-sektionen IKKE vises, og at den eksisterende enkeltdags-redigering
   (Ret starttid/Ret sluttid) fortsat fungerer uændret.
6. Gentag punkt 1-3 fra Vagtplan-visningen (samme modal, `source: "vagtplan"`) og bekræft samme adfærd.
7. Tag et screenshot af "Fraværsperiode"-sektionen og af bekræftelses-dialogen til dokumentation.

- [ ] **Step 5: Ret evt. fundne fejl og gentag Step 4**

Hvis noget af ovenstående fejler (fx forkert dato-format, manglende felt, konsol-fejl via
`read_console_messages`), ret koden i den relevante task og gentag verifikationen, indtil alle 7 punkter
i Step 4 er bekræftet.

---

## Self-Review

**Spec coverage:**
- Datamodel (`absence_group_id`, ingen tilbagevirkende migrering) → Task 1. ✓
- Backend schemas → Task 2. ✓
- `create_manual_activity` gemmer feltet → Task 3. ✓
- Hjælpelogik (hverdage, timetal, afspadsering-skip) → Task 4. ✓
- `GET .../absence-group/{id}` → Task 5. ✓
- `PATCH .../absence-group/{id}` (diff, alt-eller-intet, lukket periode blokerer, split-guard, vagtplan-rettighed) → Task 6. ✓
- Frontend: gruppe-id ved oprettelse → Task 7. ✓
- Frontend: periode-sektion i modal → Task 8. ✓
- Frontend: gem + overlap-advarsel + browser-verifikation → Task 9. ✓
- "Ikke omfattet"-punkterne i specen (ingen migrering af gamle perioder, ingen ny permission, enkeltdags-redigering uændret) kræver ingen egen task – de er fravalg, ikke funktionalitet, og er dækket implicit ved at Task 6/8 kun aktiverer sig for aktiviteter med et `absence_group_id`.

**Placeholder-scan:** Ingen "TBD"/"TODO" fundet. Alle kodeblokke er komplette, ingen "tilsvarende Task N"-henvisninger uden kode.

**Type-konsistens:** `_weekday_dates`/`_range_day_defaults` (Task 4) bruges med identiske navne og signaturer i Task 6. `AbsenceGroupDatesUpdate`/`AbsenceGroupUpdateResponse` (Task 2) bruges med identiske feltnavne (`new_start_date`, `new_end_date`, `activities`, `skipped`) i Task 6, 8 og 9. `absence_group_id` staves ens overalt (backend-felt, frontend-JSON-nøgle, DOM-id'er `edit-period-start`/`edit-period-end` er interne og kun brugt internt i Task 8/9).
