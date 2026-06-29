import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from database.models import EmployeeBaseline


def test_employee_baseline_model_exists():
    assert hasattr(EmployeeBaseline, 'employee_id')
    assert hasattr(EmployeeBaseline, 'sample_count')
    assert hasattr(EmployeeBaseline, 'duration_mean_minutes')
    assert hasattr(EmployeeBaseline, 'duration_m2_minutes')
    assert hasattr(EmployeeBaseline, 'start_hour_mean')
    assert hasattr(EmployeeBaseline, 'start_hour_m2')
    assert hasattr(EmployeeBaseline, 'salt_count')


from datetime import datetime, timedelta
from database.models import ActivitySource, ActivityStatus, EmployeeBaseline
from calculators.auto_approval import should_auto_approve
from calculators.baseline_updater import update_baseline_from_activity
from conftest import make_activity


def _seed_baseline(db, employee, n=6, start_hour=7.0, duration_minutes=480):
    """Hjælper: opret n godkendte mandag-aktiviteter med fast varighed."""
    base_monday = datetime(2026, 1, 5, int(start_hour), int((start_hour % 1) * 60))
    for i in range(n):
        start = base_monday + timedelta(weeks=i)
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
