import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from datetime import datetime
from database.models import ActivitySource, ActivityStatus, EmployeeBaseline
from calculators.baseline_updater import update_baseline_from_activity, rebuild_baselines_for_employee
from conftest import make_activity, set_auto_approval_enabled


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


def test_skip_unapproved_activity(db, employee):
    act = make_activity(
        db, employee,
        start=datetime(2026, 6, 1, 7, 0),
        end=datetime(2026, 6, 1, 15, 0),
        status=ActivityStatus.pending,
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
    from datetime import timedelta, date
    base = datetime(2026, 6, 2, 8, 0)  # første tirsdag
    for i in range(6):
        start = base + timedelta(weeks=i)
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
