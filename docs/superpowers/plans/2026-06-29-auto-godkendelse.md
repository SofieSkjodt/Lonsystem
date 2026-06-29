# Auto-godkendelse af aktiviteter – Implementationsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Systemet skal automatisk godkende chaufførers normale tachograf-aktiviteter baseret på per-medarbejder statistiske baselines, og markere outliers til manuel behandling.

**Architecture:** En ny `EmployeeBaseline`-tabel gemmer rullende Welford-statistik (mean + M2 til std) per medarbejder per ugedag (0=mandag..6=søndag). Kun `normal`-type aktiviteter fra tachografen indgår i baselinen og auto-godkendes. Nye aktiviteter vurderes mod baselinen ved import; godkendte aktiviteter opdaterer baselines inkrementelt. En seedings-endpoint genberegner baselines fra eksisterende godkendte aktiviteter, så historisk data kan bootstrappes.

**Tech Stack:** Python/FastAPI, SQLAlchemy, SQLite, pytest, math.sqrt (stdlib – ingen nye deps)

## Global Constraints

- Python 3.11+, FastAPI, SQLAlchemy, SQLite (WAL)
- Ingen nye pip-afhængigheder – brug kun stdlib og allerede installerede pakker
- Brand-farver: `--primary: #317423`, `--accent: #78b21a`, `--light-tint: #d4edcc`
- Kørende server kræver genstart ved `.py`-ændringer (`cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`)
- Tests køres fra projektets rod: `cd app && python -m pytest ../tests/ -v`
- `MIN_SAMPLES = 5` – minimum godkendte aktiviteter per (medarbejder, ugedag) for at aktivere auto-godkendelse
- `DURATION_STD_MULTIPLIER = 2.5` – antal std.afvigelser der tillades
- `DURATION_TOLERANCE_FALLBACK = 0.30` – 30% tolerance hvis std er 0 eller n<2
- `START_HOUR_TOLERANCE_HOURS = 1.5` – ±1,5 time tolerance på starttidspunkt

---

## Filstruktur

```
app/
  database/
    models.py                    # MODIFY: tilføj EmployeeBaseline + 2 felter på Activity
    schemas.py                   # MODIFY: tilføj auto_approved + auto_approval_flags i ActivityResponse
  calculators/
    auto_approval.py             # CREATE: should_auto_approve() + _duration_minutes_for_baseline()
    baseline_updater.py          # CREATE: update_baseline_from_activity() + rebuild_baselines_for_employee()
  routers/
    activities.py                # MODIFY: approve-endpoint kalder update_baseline; ny bulk-auto-approve endpoint
    import_ddd.py                # MODIFY: _import_activity() kalder should_auto_approve efter oprettelse
    auto_approval_router.py      # CREATE: POST /api/auto-approval/rebuild-baselines (admin)
  main.py                        # MODIFY: inkluder auto_approval_router
  templates/index.html           # MODIFY: auto-godkendt badge + flags i aktivitetsdetalje + "Auto-godkend egnede"-knap
  static/js/app.js               # MODIFY: renderCellActivity badge-styling + openActivityDetail flags-sektion
tests/
  conftest.py                    # CREATE: pytest fixtures (in-memory SQLite DB, test-employee, test-activities)
  test_auto_approval.py          # CREATE: tests for should_auto_approve()
  test_baseline_updater.py       # CREATE: tests for update_baseline_from_activity() + rebuild
```

---

## Task 1: DB-model – EmployeeBaseline + nye Activity-felter

**Files:**
- Modify: `app/database/models.py`
- Create: `tests/conftest.py`
- Create: `tests/test_auto_approval.py` (første stub der importerer modellen)

**Interfaces:**
- Produces: `EmployeeBaseline`-klasse med felterne beskrevet nedenfor, tilgængeligt for import i alle efterfølgende tasks
- Produces: `Activity.auto_approved: Column(Boolean)`, `Activity.auto_approval_flags: Column(JSON)`

- [ ] **Step 1: Tilføj `EmployeeBaseline` til `models.py`**

Åbn `app/database/models.py` og tilføj følgende klasse i slutningen af filen (efter `Holiday`-klassen):

```python
class EmployeeBaseline(Base):
    __tablename__ = "employee_baselines"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    weekday = Column(Integer, nullable=False)          # 0=mandag … 6=søndag
    sample_count = Column(Integer, default=0, nullable=False)
    duration_mean_minutes = Column(Numeric(10, 4), default=0, nullable=False)
    duration_m2_minutes = Column(Numeric(14, 6), default=0, nullable=False)  # Welford M2
    start_hour_mean = Column(Numeric(8, 4), default=0, nullable=False)       # float timer, fx 7.5 = 07:30
    start_hour_m2 = Column(Numeric(12, 6), default=0, nullable=False)        # Welford M2
    salt_count = Column(Integer, default=0, nullable=False)                  # antal aktiviteter med salt
    last_updated = Column(DateTime, nullable=True)

    employee = relationship("Employee", back_populates="baselines")
```

- [ ] **Step 2: Tilføj relationship på `Employee`**

I `Employee`-klassen i `models.py`, tilføj efter `activities = relationship(...)`:

```python
    baselines = relationship("EmployeeBaseline", back_populates="employee")
```

- [ ] **Step 3: Tilføj nye felter på `Activity`**

I `Activity`-klassen, tilføj efter `created_at`-kolonnen (linje ~149):

```python
    auto_approved = Column(Boolean, default=False, nullable=False, server_default="0")
    auto_approval_flags = Column(JSON, nullable=False, default=list)
```

- [ ] **Step 4: Opret `tests/conftest.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date

from database.models import Base, Employee, Activity, ActivitySource, ActivityStatus, AgreementKind
from calculators.pay_period import get_or_create_period_for_date


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def employee(db):
    emp = Employee(
        employee_number="1001",
        first_name="Test",
        last_name="Chauffør",
        agreement_kind=AgreementKind.hourly_fixed,
        agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def make_activity(db, employee, start: datetime, end: datetime,
                  activity_type="normal", source=ActivitySource.tachograph,
                  salt_supplement=False, status=ActivityStatus.pending):
    period = get_or_create_period_for_date(start.date(), db)
    act = Activity(
        employee_id=employee.id,
        pay_period_id=period.id,
        source=source,
        activity_type=activity_type,
        start_time=start,
        end_time=end,
        salt_supplement=salt_supplement,
        status=status,
        pause_intervals=[],
        segments=[],
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act
```

- [ ] **Step 5: Opret `tests/test_auto_approval.py` med en smoke-test**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database.models import EmployeeBaseline


def test_employee_baseline_model_exists():
    assert hasattr(EmployeeBaseline, 'employee_id')
    assert hasattr(EmployeeBaseline, 'sample_count')
    assert hasattr(EmployeeBaseline, 'duration_mean_minutes')
    assert hasattr(EmployeeBaseline, 'duration_m2_minutes')
    assert hasattr(EmployeeBaseline, 'start_hour_mean')
    assert hasattr(EmployeeBaseline, 'start_hour_m2')
    assert hasattr(EmployeeBaseline, 'salt_count')
```

- [ ] **Step 6: Kør test og bekræft PASS**

```
cd app && python -m pytest ../tests/test_auto_approval.py::test_employee_baseline_model_exists -v
```

Forventet: `PASSED`

- [ ] **Step 7: Commit**

```
git add app/database/models.py tests/conftest.py tests/test_auto_approval.py
git commit -m "feat: add EmployeeBaseline model and auto_approved/auto_approval_flags on Activity"
```

---

## Task 2: Baseline Updater

**Files:**
- Create: `app/calculators/baseline_updater.py`
- Create: `tests/test_baseline_updater.py`

**Interfaces:**
- Consumes: `EmployeeBaseline` fra `database.models`, `Activity` fra `database.models`
- Produces:
  - `update_baseline_from_activity(activity: Activity, db: Session) -> None`  
    Opdaterer (eller opretter) `EmployeeBaseline` for aktivitetens medarbejder+ugedag via Welford's inkrementelle algoritme. Kaldes kun for godkendte `normal`-type tachograf-aktiviteter.
  - `rebuild_baselines_for_employee(employee_id: int, db: Session) -> int`  
    Sletter alle `EmployeeBaseline`-rækker for medarbejderen og genberegner fra alle godkendte `normal` tachograf-aktiviteter. Returnerer antallet af behandlede aktiviteter.

- [ ] **Step 1: Skriv de failing tests**

Opret `tests/test_baseline_updater.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from datetime import datetime
from database.models import ActivitySource, ActivityStatus, EmployeeBaseline
from calculators.baseline_updater import update_baseline_from_activity, rebuild_baselines_for_employee
from conftest import make_activity


def test_update_creates_baseline_row(db, employee):
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 1, 7, 0),   # mandag
        end=datetime(2026, 6, 1, 15, 0),    # 8 timer
        status=ActivityStatus.approved,
    )
    update_baseline_from_activity(act, db)

    baseline = db.query(EmployeeBaseline).filter_by(
        employee_id=employee.id, weekday=0
    ).first()
    assert baseline is not None
    assert baseline.sample_count == 1
    assert float(baseline.duration_mean_minutes) == pytest.approx(480.0)
    assert float(baseline.start_hour_mean) == pytest.approx(7.0)


def test_update_increments_sample_count(db, employee):
    for day in [1, 8, 15, 22]:
        act = make_activity(
            db, employee,
            start=datetime(2026, 6, day, 7, 30),
            end=datetime(2026, 6, day, 15, 30),
            status=ActivityStatus.approved,
        )
        update_baseline_from_activity(act, db)

    baseline = db.query(EmployeeBaseline).filter_by(
        employee_id=employee.id, weekday=0
    ).first()
    assert baseline.sample_count == 4


def test_update_mean_converges(db, employee):
    durations_minutes = [480, 510, 450, 490, 500]
    for i, dur in enumerate(durations_minutes):
        start = datetime(2026, 6, 1 + i * 7, 7, 0)
        from datetime import timedelta
        act = make_activity(
            db, employee,
            start=start,
            end=start + timedelta(minutes=dur),
            status=ActivityStatus.approved,
        )
        update_baseline_from_activity(act, db)

    baseline = db.query(EmployeeBaseline).filter_by(
        employee_id=employee.id, weekday=0
    ).first()
    expected_mean = sum(durations_minutes) / len(durations_minutes)
    assert float(baseline.duration_mean_minutes) == pytest.approx(expected_mean, abs=0.01)


def test_skip_non_normal_activity(db, employee):
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 1, 7, 0),
        end=datetime(2026, 6, 1, 15, 0),
        activity_type="ferie",
        status=ActivityStatus.approved,
    )
    update_baseline_from_activity(act, db)

    count = db.query(EmployeeBaseline).filter_by(employee_id=employee.id).count()
    assert count == 0


def test_skip_manual_activity(db, employee):
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 1, 7, 0),
        end=datetime(2026, 6, 1, 15, 0),
        source=ActivitySource.manual,
        status=ActivityStatus.approved,
    )
    update_baseline_from_activity(act, db)

    count = db.query(EmployeeBaseline).filter_by(employee_id=employee.id).count()
    assert count == 0


def test_rebuild_baselines(db, employee):
    from datetime import timedelta
    for i in range(6):
        start = datetime(2026, 6, 2 + i * 7, 8, 0)  # tirsdage
        act = make_activity(
            db, employee,
            start=start,
            end=start + timedelta(hours=8),
            status=ActivityStatus.approved,
        )

    count = rebuild_baselines_for_employee(employee.id, db)
    assert count == 6

    baseline = db.query(EmployeeBaseline).filter_by(
        employee_id=employee.id, weekday=1  # tirsdag
    ).first()
    assert baseline is not None
    assert baseline.sample_count == 6
```

- [ ] **Step 2: Kør tests og bekræft FAIL**

```
cd app && python -m pytest ../tests/test_baseline_updater.py -v
```

Forventet: `ModuleNotFoundError: No module named 'calculators.baseline_updater'`

- [ ] **Step 3: Implementer `app/calculators/baseline_updater.py`**

```python
from datetime import datetime
from math import sqrt

from sqlalchemy.orm import Session

from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline


def update_baseline_from_activity(activity: Activity, db: Session) -> None:
    """Opdaterer EmployeeBaseline for aktivitetens medarbejder+ugedag via Welford's algoritme.
    Ignorerer aktiviteter der ikke er normale tachograf-aktiviteter."""
    if activity.activity_type != "normal":
        return
    if activity.source != ActivitySource.tachograph:
        return

    weekday = activity.start_time.weekday()
    duration = _effective_duration_minutes(activity)
    start_hour = activity.start_time.hour + activity.start_time.minute / 60.0

    baseline = db.query(EmployeeBaseline).filter_by(
        employee_id=activity.employee_id,
        weekday=weekday,
    ).first()

    if baseline is None:
        baseline = EmployeeBaseline(
            employee_id=activity.employee_id,
            weekday=weekday,
            sample_count=0,
            duration_mean_minutes=0.0,
            duration_m2_minutes=0.0,
            start_hour_mean=0.0,
            start_hour_m2=0.0,
            salt_count=0,
        )
        db.add(baseline)

    n = baseline.sample_count + 1
    baseline.sample_count = n

    # Welford's online algoritme for varighed
    dur_mean = float(baseline.duration_mean_minutes)
    dur_m2 = float(baseline.duration_m2_minutes)
    delta = duration - dur_mean
    dur_mean += delta / n
    delta2 = duration - dur_mean
    dur_m2 += delta * delta2
    baseline.duration_mean_minutes = dur_mean
    baseline.duration_m2_minutes = dur_m2

    # Welford's online algoritme for starttid
    sh_mean = float(baseline.start_hour_mean)
    sh_m2 = float(baseline.start_hour_m2)
    delta = start_hour - sh_mean
    sh_mean += delta / n
    delta2 = start_hour - sh_mean
    sh_m2 += delta * delta2
    baseline.start_hour_mean = sh_mean
    baseline.start_hour_m2 = sh_m2

    if activity.salt_supplement:
        baseline.salt_count = (baseline.salt_count or 0) + 1

    baseline.last_updated = datetime.utcnow()
    db.commit()


def rebuild_baselines_for_employee(employee_id: int, db: Session) -> int:
    """Slet og genberegn alle baselines for én medarbejder fra godkendte normale aktiviteter.
    Returnerer antal behandlede aktiviteter."""
    db.query(EmployeeBaseline).filter_by(employee_id=employee_id).delete()
    db.commit()

    activities = (
        db.query(Activity)
        .filter(
            Activity.employee_id == employee_id,
            Activity.activity_type == "normal",
            Activity.source == ActivitySource.tachograph,
            Activity.status == ActivityStatus.approved,
        )
        .order_by(Activity.start_time)
        .all()
    )

    for act in activities:
        update_baseline_from_activity(act, db)

    return len(activities)


def _effective_duration_minutes(activity: Activity) -> float:
    """Netto varighed i minutter efter pausefradrag."""
    total = (activity.end_time - activity.start_time).total_seconds() / 60.0
    for p in (activity.pause_intervals or []):
        try:
            from datetime import datetime as _dt
            ps = _dt.fromisoformat(p[0])
            pe = _dt.fromisoformat(p[1])
            actual_start = max(activity.start_time, ps)
            actual_end = min(activity.end_time, pe)
            if actual_end > actual_start:
                total -= (actual_end - actual_start).total_seconds() / 60.0
        except (ValueError, IndexError):
            pass
    return max(0.0, total)
```

- [ ] **Step 4: Kør tests og bekræft PASS**

```
cd app && python -m pytest ../tests/test_baseline_updater.py -v
```

Forventet: alle 7 tests `PASSED`

- [ ] **Step 5: Commit**

```
git add app/calculators/baseline_updater.py tests/test_baseline_updater.py
git commit -m "feat: add baseline updater with Welford's incremental algorithm"
```

---

## Task 3: Auto-godkendelseslogik

**Files:**
- Create: `app/calculators/auto_approval.py`
- Modify: `tests/test_auto_approval.py` (udvid med funktionelle tests)

**Interfaces:**
- Consumes: `EmployeeBaseline` fra `database.models`, `_effective_duration_minutes` fra `baseline_updater`
- Produces:
  - `should_auto_approve(activity: Activity, db: Session) -> tuple[bool, list[str]]`  
    Returnerer `(True, [])` hvis aktiviteten kan auto-godkendes, eller `(False, ["årsag1", ...])` ved afvigelse.

Konstanter (defineres øverst i filen):
- `MIN_SAMPLES = 5`
- `DURATION_STD_MULTIPLIER = 2.5`
- `DURATION_TOLERANCE_FALLBACK = 0.30` (30% af mean)
- `START_HOUR_TOLERANCE_HOURS = 1.5`

- [ ] **Step 1: Tilføj failing tests til `tests/test_auto_approval.py`**

Tilføj følgende tests i slutningen af filen (behold den eksisterende smoke-test øverst):

```python
from datetime import datetime, timedelta
from database.models import ActivitySource, ActivityStatus, EmployeeBaseline
from calculators.auto_approval import should_auto_approve
from calculators.baseline_updater import update_baseline_from_activity
from conftest import make_activity


def _seed_baseline(db, employee, n=6, start_hour=7.0, duration_minutes=480):
    """Hjælper: opret n godkendte mandag-aktiviteter med fast varighed."""
    for i in range(n):
        start = datetime(2026, 1, 5 + i * 7, int(start_hour), int((start_hour % 1) * 60))
        act = make_activity(
            db, employee,
            start=start,
            end=start + timedelta(minutes=duration_minutes),
            status=ActivityStatus.approved,
        )
        update_baseline_from_activity(act, db)


def test_auto_approve_normal_within_tolerance(db, employee):
    _seed_baseline(db, employee, n=6)
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 8, 7, 15),   # mandag, 15 min fra typisk
        end=datetime(2026, 6, 8, 15, 15),    # 8 timer = typisk
    )
    ok, flags = should_auto_approve(act, db)
    assert ok is True
    assert flags == []


def test_auto_approve_flags_too_long(db, employee):
    _seed_baseline(db, employee, n=6, duration_minutes=480)  # typisk 8t
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 8, 7, 0),
        end=datetime(2026, 6, 8, 20, 0),    # 13 timer = langt over 8t
    )
    ok, flags = should_auto_approve(act, db)
    assert ok is False
    assert any("varighed" in f.lower() or "Varighed" in f for f in flags)


def test_auto_approve_flags_too_early(db, employee):
    _seed_baseline(db, employee, n=6, start_hour=8.0)  # typisk start kl. 8
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 8, 4, 0),   # kl. 4 – 4 timer tidligt
        end=datetime(2026, 6, 8, 12, 0),
    )
    ok, flags = should_auto_approve(act, db)
    assert ok is False
    assert any("starttid" in f.lower() or "Starttid" in f for f in flags)


def test_auto_approve_not_enough_data(db, employee):
    _seed_baseline(db, employee, n=4)  # under MIN_SAMPLES=5
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 8, 7, 0),
        end=datetime(2026, 6, 8, 15, 0),
    )
    ok, flags = should_auto_approve(act, db)
    assert ok is False
    assert any("data" in f.lower() for f in flags)


def test_auto_approve_skips_absence_types(db, employee):
    _seed_baseline(db, employee, n=6)
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 8, 7, 0),
        end=datetime(2026, 6, 8, 15, 0),
        activity_type="ferie",
    )
    ok, flags = should_auto_approve(act, db)
    assert ok is False


def test_auto_approve_skips_manual_source(db, employee):
    _seed_baseline(db, employee, n=6)
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 8, 7, 0),
        end=datetime(2026, 6, 8, 15, 0),
        source=ActivitySource.manual,
    )
    ok, flags = should_auto_approve(act, db)
    assert ok is False


def test_auto_approve_no_baseline_for_weekday(db, employee):
    _seed_baseline(db, employee, n=6)  # seeder kun mandage (weekday=0)
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 9, 7, 0),  # tirsdag
        end=datetime(2026, 6, 9, 15, 0),
    )
    ok, flags = should_auto_approve(act, db)
    assert ok is False
    assert any("data" in f.lower() for f in flags)
```

- [ ] **Step 2: Kør tests og bekræft FAIL**

```
cd app && python -m pytest ../tests/test_auto_approval.py -v -k "not test_employee_baseline_model_exists"
```

Forventet: `ImportError: cannot import name 'should_auto_approve'`

- [ ] **Step 3: Implementer `app/calculators/auto_approval.py`**

```python
from math import sqrt

from sqlalchemy.orm import Session

from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline
from calculators.baseline_updater import _effective_duration_minutes

MIN_SAMPLES = 5
DURATION_STD_MULTIPLIER = 2.5
DURATION_TOLERANCE_FALLBACK = 0.30
START_HOUR_TOLERANCE_HOURS = 1.5


def should_auto_approve(activity: Activity, db: Session) -> tuple[bool, list[str]]:
    """Vurder om en aktivitet kan auto-godkendes mod medarbejderens historiske baseline.

    Returnerer (True, []) hvis aktiviteten falder inden for normale grænser,
    eller (False, [årsag, ...]) med en eller flere flagbeskrivelser.
    """
    if activity.activity_type != "normal":
        return False, ["Kun normale tachograf-aktiviteter auto-godkendes"]
    if activity.source != ActivitySource.tachograph:
        return False, ["Kun tachograf-aktiviteter auto-godkendes"]

    weekday = activity.start_time.weekday()
    baseline = db.query(EmployeeBaseline).filter_by(
        employee_id=activity.employee_id,
        weekday=weekday,
    ).first()

    if baseline is None or baseline.sample_count < MIN_SAMPLES:
        count = baseline.sample_count if baseline else 0
        return False, [f"Ikke nok data ({count}/{MIN_SAMPLES} registreringer for denne ugedag)"]

    flags = []
    n = baseline.sample_count

    # --- Varighed ---
    duration = _effective_duration_minutes(activity)
    dur_mean = float(baseline.duration_mean_minutes)
    dur_std = sqrt(float(baseline.duration_m2_minutes) / n) if n > 1 else 0.0
    dur_tolerance = max(dur_std * DURATION_STD_MULTIPLIER, dur_mean * DURATION_TOLERANCE_FALLBACK)

    if abs(duration - dur_mean) > dur_tolerance:
        direction = "for lang" if duration > dur_mean else "for kort"
        flags.append(
            f"Varighed afviger: {duration:.0f}min vs. typisk {dur_mean:.0f}±{dur_std:.0f}min ({direction})"
        )

    # --- Starttid ---
    start_hour = activity.start_time.hour + activity.start_time.minute / 60.0
    sh_mean = float(baseline.start_hour_mean)
    sh_std = sqrt(float(baseline.start_hour_m2) / n) if n > 1 else 0.0
    sh_tolerance = max(sh_std * DURATION_STD_MULTIPLIER, START_HOUR_TOLERANCE_HOURS)

    if abs(start_hour - sh_mean) > sh_tolerance:
        mean_h = int(sh_mean)
        mean_m = int((sh_mean % 1) * 60)
        act_h = activity.start_time.hour
        act_m = activity.start_time.minute
        flags.append(
            f"Starttid afviger: {act_h:02d}:{act_m:02d} vs. typisk {mean_h:02d}:{mean_m:02d} (±{sh_std:.1f}t)"
        )

    return len(flags) == 0, flags
```

- [ ] **Step 4: Kør tests og bekræft PASS**

```
cd app && python -m pytest ../tests/test_auto_approval.py -v
```

Forventet: alle tests `PASSED`

- [ ] **Step 5: Commit**

```
git add app/calculators/auto_approval.py tests/test_auto_approval.py
git commit -m "feat: add auto-approval calculator with baseline comparison"
```

---

## Task 4: Schemas – ActivityResponse nye felter

**Files:**
- Modify: `app/database/schemas.py`

**Interfaces:**
- Consumes: `Activity.auto_approved`, `Activity.auto_approval_flags`
- Produces: `ActivityResponse.auto_approved: bool`, `ActivityResponse.auto_approval_flags: list[str]`

- [ ] **Step 1: Åbn `app/database/schemas.py` og find `ActivityResponse`**

Find feltet `salt_supplement: bool` i `ActivityResponse`-klassen. Tilføj disse to felter umiddelbart efter:

```python
    auto_approved: bool = False
    auto_approval_flags: list[str] = []
```

- [ ] **Step 2: Opdater `_to_response()` i `app/routers/activities.py`**

I funktionen `_to_response(a: Activity)`, tilføj de to nye felter i `ActivityResponse(...)`-kaldet. Find `salt_supplement=bool(a.salt_supplement),` og tilføj efter:

```python
        auto_approved=bool(a.auto_approved),
        auto_approval_flags=a.auto_approval_flags or [],
```

- [ ] **Step 3: Genstart serveren og test manuelt**

```
cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Kald `GET /api/activities` og bekræft at `auto_approved` og `auto_approval_flags` er med i svaret.

- [ ] **Step 4: Commit**

```
git add app/database/schemas.py app/routers/activities.py
git commit -m "feat: add auto_approved and auto_approval_flags to ActivityResponse"
```

---

## Task 5: Integration i import_ddd + activities approve-endpoint

**Files:**
- Modify: `app/routers/import_ddd.py`
- Modify: `app/routers/activities.py`

**Interfaces:**
- Consumes: `should_auto_approve()` fra `calculators.auto_approval`, `update_baseline_from_activity()` fra `calculators.baseline_updater`
- Produces:
  - DDD-import: nye aktiviteter auto-godkendes hvis baselines er tilstrækkelige
  - approve-endpoint: opdaterer baseline ved manuel godkendelse
  - Nyt endpoint: `POST /api/activities/auto-approve-pending` – auto-godkender alle egnede pending-aktiviteter i en periode

- [ ] **Step 1: Tilføj auto-godkendelse i `_import_activity()` i `import_ddd.py`**

Åbn `app/routers/import_ddd.py`. Find funktionen `_import_activity()`. Find stedet hvor en ny aktivitet commit'es til DB (efter `db.commit()` ved ny aktivitet). Læs den præcise placering i filen.

Tilføj disse imports øverst i filen (efter de eksisterende imports):

```python
from datetime import datetime as _dt_now
from calculators.auto_approval import should_auto_approve
from calculators.baseline_updater import update_baseline_from_activity
```

I `_import_activity()`, efter `db.commit()` og `db.refresh(new_act)` ved oprettelse af ny aktivitet, tilføj:

```python
                ok, flags = should_auto_approve(new_act, db)
                if ok:
                    new_act.status = ActivityStatus.approved
                    new_act.auto_approved = True
                    new_act.auto_approval_flags = []
                    new_act.approved_by = "AUTO"
                    new_act.approved_at = _dt_now.utcnow()
                    db.commit()
                    update_baseline_from_activity(new_act, db)
                else:
                    new_act.auto_approval_flags = flags
                    db.commit()
```

- [ ] **Step 2: Tilføj baseline-opdatering i approve-endpoint i `activities.py`**

Åbn `app/routers/activities.py`. Find `@router.post("/{activity_id}/approve")`. Tilføj disse imports øverst:

```python
from calculators.baseline_updater import update_baseline_from_activity
```

Find stedet i approve-endpointet, hvor `a.status = ActivityStatus.approved` sættes og `db.commit()` kaldes. Umiddelbart efter `db.commit()` tilføj:

```python
    update_baseline_from_activity(a, db)
```

- [ ] **Step 3: Tilføj bulk auto-approve endpoint i `activities.py`**

Tilføj dette nye endpoint i `app/routers/activities.py` (tilføj efter approve-endpointet):

```python
@router.post("/auto-approve-pending")
def bulk_auto_approve(
    period_start: Optional[str] = None,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Auto-godkend alle egnede pending-aktiviteter i en lønperiode."""
    from datetime import date as _date
    from calculators.auto_approval import should_auto_approve
    from calculators.baseline_updater import update_baseline_from_activity
    from datetime import datetime as _dt

    start_date = _date.fromisoformat(period_start) if period_start else _date.today()
    period = get_or_create_period_for_date(start_date, db)

    pending = (
        db.query(Activity)
        .filter(
            Activity.pay_period_id == period.id,
            Activity.status == ActivityStatus.pending,
        )
        .all()
    )

    approved_count = 0
    flagged_count = 0

    for act in pending:
        ok, flags = should_auto_approve(act, db)
        if ok:
            act.status = ActivityStatus.approved
            act.auto_approved = True
            act.auto_approval_flags = []
            act.approved_by = "AUTO"
            act.approved_at = _dt.utcnow()
            db.commit()
            update_baseline_from_activity(act, db)
            approved_count += 1
        else:
            act.auto_approval_flags = flags
            db.commit()
            flagged_count += 1

    log_action(current_user, "auto_approve_bulk",
               details=f"periode={period.start_date}, godkendt={approved_count}, flagget={flagged_count}",
               db=db)

    return {"approved": approved_count, "flagged": flagged_count}
```

- [ ] **Step 4: Genstart serveren og test import**

```
cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Importer en .ddd-fil og bekræft via `GET /api/activities` at:
- Aktiviteter med tilstrækkelig baseline har `auto_approved: true` og `status: "approved"`
- Aktiviteter uden baseline har `auto_approval_flags: ["Ikke nok data..."]`

- [ ] **Step 5: Commit**

```
git add app/routers/import_ddd.py app/routers/activities.py
git commit -m "feat: auto-approve on DDD import, update baseline on manual approve, bulk auto-approve endpoint"
```

---

## Task 6: Seedings-endpoint (rebuild baselines fra historik)

**Files:**
- Create: `app/routers/auto_approval_router.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `rebuild_baselines_for_employee()` fra `calculators.baseline_updater`
- Produces: `POST /api/auto-approval/rebuild-baselines` – (re)bygger baselines for alle eller én medarbejder

- [ ] **Step 1: Opret `app/routers/auto_approval_router.py`**

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


@router.post("/rebuild-baselines")
def rebuild_baselines(
    employee_id: Optional[int] = None,
    current_user: AppUser = Depends(_admin_access),
    db: Session = Depends(get_db),
):
    """Genberegn baselines fra alle historiske godkendte aktiviteter.
    employee_id=None → alle aktive medarbejdere. Bruges til bootstrapping af historisk data."""
    if employee_id is not None:
        count = rebuild_baselines_for_employee(employee_id, db)
        return {"employees_processed": 1, "total_activities": count}

    employees = db.query(Employee).filter(Employee.active == True).all()
    total = 0
    for emp in employees:
        total += rebuild_baselines_for_employee(emp.id, db)

    return {"employees_processed": len(employees), "total_activities": total}


@router.get("/baseline-summary")
def baseline_summary(
    current_user: AppUser = Depends(_admin_access),
    db: Session = Depends(get_db),
):
    """Oversigt over baseline-status per medarbejder – bruges til at vurdere datakvalitet."""
    from database.models import EmployeeBaseline
    from sqlalchemy import func

    rows = (
        db.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            func.count(EmployeeBaseline.id).label("weekday_count"),
            func.sum(EmployeeBaseline.sample_count).label("total_samples"),
            func.min(EmployeeBaseline.sample_count).label("min_samples"),
        )
        .outerjoin(EmployeeBaseline, EmployeeBaseline.employee_id == Employee.id)
        .filter(Employee.active == True)
        .group_by(Employee.id)
        .all()
    )

    MIN_SAMPLES = 5
    return [
        {
            "employee_id": r.id,
            "name": f"{r.first_name} {r.last_name}",
            "weekday_count": r.weekday_count or 0,
            "total_samples": int(r.total_samples or 0),
            "min_samples_per_weekday": int(r.min_samples or 0),
            "auto_approval_ready": (r.min_samples or 0) >= MIN_SAMPLES and (r.weekday_count or 0) >= 5,
        }
        for r in rows
    ]
```

- [ ] **Step 2: Tilføj `manage_baselines` permission og inkluder router i `main.py`**

Åbn `app/main.py`. Find stedet hvor andre routers inkluderes (fx `app.include_router(activities.router)`). Tilføj:

```python
from routers.auto_approval_router import router as auto_approval_router
# ... (i app-setup-blokken):
app.include_router(auto_approval_router)
```

- [ ] **Step 3: Tilføj `manage_baselines` til admin-rollen i seeding**

Åbn `app/database/session.py`. Find stedet hvor admin-rollen seedtes med permissions. Tilføj `"manage_baselines"` til admin-rollens permission-liste:

Find linjen med admin-permissions og tilføj `"manage_baselines"` til listen. Eksempel (den præcise linje varierer – læs filen først):

```python
# Find permissions-listen for admin-rollen og tilføj:
"manage_baselines"
```

- [ ] **Step 4: Genstart server og test**

```
cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Kald `POST /api/auto-approval/rebuild-baselines` og bekræft at det returnerer `{"employees_processed": N, "total_activities": M}`.

Kald `GET /api/auto-approval/baseline-summary` og bekræft at svaret indeholder medarbejdere med `auto_approval_ready`.

- [ ] **Step 5: Commit**

```
git add app/routers/auto_approval_router.py app/main.py app/database/session.py
git commit -m "feat: add rebuild-baselines and baseline-summary endpoints (admin)"
```

---

## Task 7: UI – badge-styling, flags-visning og bulk-knap

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`
- Modify: `app/static/css/style.css`

**Interfaces:**
- Consumes: `ActivityResponse.auto_approved`, `ActivityResponse.auto_approval_flags`
- Produces:
  - Auto-godkendt aktivitet vises med grønt badge med "A"-ikon i grid (forskelligt fra manuelt godkendt "✓"-badge)
  - `auto_approval_flags` vises i aktivitetsdetalje-modal som et gult advarselsfelt hvis ikke-tom
  - "Auto-godkend egnede"-knap i toolbar → kalder `POST /api/activities/auto-approve-pending`

- [ ] **Step 1: Tilføj CSS til `style.css`**

Find `.activity-badge.approved`-reglen i `app/static/css/style.css`. Tilføj umiddelbart efter:

```css
.activity-badge.auto-approved {
    background: var(--accent);
    color: white;
    border: none;
}
.auto-approval-flags {
    background: #fff8e1;
    border: 1px solid #f9a825;
    border-radius: 6px;
    padding: 8px 12px;
    margin-bottom: 10px;
    font-size: 0.85rem;
    color: #5d4037;
}
.auto-approval-flags strong {
    display: block;
    margin-bottom: 4px;
    color: #e65100;
}
.auto-approval-flags ul {
    margin: 0;
    padding-left: 16px;
}
```

- [ ] **Step 2: Opdater `renderCellActivity()` i `app.js` (linje ~220)**

Find funktionen `renderCellActivity(a)`. Find stedet der sætter badge-klassen baseret på `a.status`. Tilføj en check for `auto_approved`:

Find linjen der bygger badge-klassen (søg efter `approved` i badge-rendering). Den vil se nogenlunde sådan ud:

```js
let cls = `activity-badge ${a.status}`;
```

Skift til:

```js
let cls = `activity-badge ${a.status}`;
if (a.status === 'approved' && a.auto_approved) cls += ' auto-approved';
```

Og find stedet der renderer status-ikoner/initialer i badge'et. Tilføj efter `approved`-casen:

```js
if (a.status === 'approved' && a.auto_approved) {
    statusIcon = '<span title="Auto-godkendt">A</span>';
} else if (a.status === 'approved') {
    statusIcon = `<span title="${h(a.approved_by || '')}">✓</span>`;
}
```

(Tilpas til den præcise badge-rendering-struktur du finder i filen)

- [ ] **Step 3: Tilføj flags-visning i `openActivityDetail()` i `app.js` (linje ~360)**

Find funktionen `openActivityDetail(id)`. Find stedet i modal-renderingen der bygger modal-activity-body HTML. Tilføj en sektion for flags efter status-informationen:

```js
const flagsHtml = (a.auto_approval_flags && a.auto_approval_flags.length > 0)
    ? `<div class="auto-approval-flags">
         <strong>Afvigelser registreret (ikke auto-godkendt):</strong>
         <ul>${a.auto_approval_flags.map(f => `<li>${h(f)}</li>`).join('')}</ul>
       </div>`
    : '';
```

Indsæt `flagsHtml` i modal-body'ens HTML, f.eks. øverst i detalje-sektionen.

- [ ] **Step 4: Tilføj "Auto-godkend egnede"-knap i toolbar i `index.html`**

Find toolbar-sektionen i `app/templates/index.html` (søg efter `filter-status` eller `filter-employee`). Tilføj en ny knap efter eksisterende handlingsknapper:

```html
<button class="btn btn-secondary" onclick="bulkAutoApprove()" title="Auto-godkend alle egnede ventende aktiviteter i denne periode">
    Auto-godkend egnede
</button>
```

- [ ] **Step 5: Tilføj `bulkAutoApprove()` i `app.js`**

Tilføj funktionen (f.eks. efter `quickReopen()`-funktionen):

```js
async function bulkAutoApprove() {
    const params = state.currentPeriodStart ? `?period_start=${state.currentPeriodStart}` : '';
    const res = await POST(`/api/activities/auto-approve-pending${params}`, {});
    if (res) {
        toast(`Auto-godkendt: ${res.approved} aktiviteter. Flagget til gennemgang: ${res.flagged}.`);
        await refreshActivities();
    }
}
```

- [ ] **Step 6: Genstart server, åbn browser og verificer**

```
cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- Naviger til aktivitetsvisningen
- Bekræft at auto-godkendte aktiviteter vises med grønt "A"-badge
- Bekræft at manuelt godkendte aktiviteter stadig viser "✓" med initialer
- Klik en aktivitet med `auto_approval_flags` og bekræft at advarselsfeltet vises
- Klik "Auto-godkend egnede" og bekræft toast-besked og opdatering af tabellen

- [ ] **Step 7: Commit**

```
git add app/templates/index.html app/static/js/app.js app/static/css/style.css
git commit -m "feat: UI for auto-approved badge, flags display, and bulk auto-approve button"
```

---

## Task 8: Kørsel af fuld test-suite og CODEREF-opdatering

**Files:**
- Modify: `CODEREF.md`

- [ ] **Step 1: Kør alle tests**

```
cd app && python -m pytest ../tests/ -v
```

Forventet: alle tests `PASSED`, ingen warnings om ukendte modeller.

- [ ] **Step 2: Opdater `CODEREF.md`**

Tilføj ny sektion i `CODEREF.md` under `## Filer`:

```
  calculators/
    auto_approval.py             # should_auto_approve(activity, db) → (bool, list[str])
    baseline_updater.py          # update_baseline_from_activity(), rebuild_baselines_for_employee()
  routers/
    auto_approval_router.py      # POST /api/auto-approval/rebuild-baselines, GET /baseline-summary (manage_baselines perm)
```

Og under `## DB-modeller`, tilføj:

```
### EmployeeBaseline (tabel: employee_baselines)
| Felt | Type | Bemærk |
|---|---|---|
| employee_id | Int FK | |
| weekday | Int | 0=mandag…6=søndag |
| sample_count | Int | Antal godkendte aktiviteter |
| duration_mean_minutes | Numeric | Welford mean |
| duration_m2_minutes | Numeric | Welford M2 (til std-beregning) |
| start_hour_mean | Numeric | Starttid som float-timer (7.5 = 07:30) |
| start_hour_m2 | Numeric | Welford M2 |
| salt_count | Int | Antal aktiviteter med salttillæg |
```

- [ ] **Step 3: Commit**

```
git add CODEREF.md
git commit -m "docs: update CODEREF with auto-approval architecture"
```

---

## Workflow efter implementering: sådan seeder du med 4 ugers data

1. Importer de 4 ugers .ddd-filer via UI (de vil forblive `pending` da der ikke er baselines endnu)
2. Gennemgå og godkend aktiviteterne manuelt (baseline akkumuleres automatisk for hver godkendt normal-aktivitet)
3. Alternativt: importer og brug eksisterende `POST /api/activities/auto-approve-pending` efter de første 5+ godkendte aktiviteter per medarbejder per ugedag
4. Kald `GET /api/auto-approval/baseline-summary` for at se hvilke medarbejdere der er klar til auto-godkendelse (`auto_approval_ready: true`)
5. Fra uge 5+ vil nye DDD-imports auto-godkende egnede aktiviteter ved import

**Forventet progressionsplan:**
- Uge 1-4: Manuelt workflow som i dag. Baseline bygges stille og roligt.
- Uge 5-8: Første medarbejdere med fast vagtplan er klar. ~50% auto-godkendelse forventes.
- Måned 3+: Størstedelen af normale aktiviteter auto-godkendes.
- År 1+: Baselines inkluderer årstidsvariationer og ferie-perioder.

---

## Self-Review

**Spec coverage:**
- ✅ EmployeeBaseline-tabel med Welford-statistik
- ✅ should_auto_approve() med duration + starttid-tjek
- ✅ update_baseline_from_activity() ved manuel godkendelse
- ✅ Auto-godkendelse ved DDD-import
- ✅ Bulk auto-approve endpoint
- ✅ Seedings-endpoint (rebuild-baselines) til historisk data
- ✅ UI: auto-badge, flags-display, bulk-knap
- ✅ MIN_SAMPLES guard (ingen auto-godkendelse under 5 samples)
- ✅ Kun normal tachograf-aktiviteter (ikke fravær, ikke manuelle)
- ✅ Tests for alle calculators

**Placeholder-scan:** Ingen TBD eller TODOs – alle steps har konkret kode.

**Type-konsistens:**
- `should_auto_approve(activity: Activity, db: Session) -> tuple[bool, list[str]]` brugt konsistent i Task 3, 5 og 6
- `update_baseline_from_activity(activity: Activity, db: Session) -> None` brugt konsistent i Task 2, 5 og 6
- `rebuild_baselines_for_employee(employee_id: int, db: Session) -> int` brugt konsistent i Task 2 og 6
- `_effective_duration_minutes(activity: Activity) -> float` defineret i Task 2, importeret i Task 3
