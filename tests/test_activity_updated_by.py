import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

from database.models import Activity, ActivitySource, ActivityStatus, AppUser
from database.schemas import ActivityUpdate
from calculators.pay_period import get_or_create_period_for_date


def _user(initials="LB1"):
    return AppUser(name="Test", initials=initials, role="lonbogholder", password_hash="x")


def _activity(db, employee, start=None, end=None):
    start = start or datetime(2026, 1, 5, 6, 0)
    end = end or datetime(2026, 1, 5, 14, 0)
    period = get_or_create_period_for_date(start.date(), db)
    a = Activity(
        employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.manual,
        activity_type="normal", start_time=start, end_time=end,
        status=ActivityStatus.pending, pause_intervals=[], segments=[],
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_updated_by_is_none_before_any_edit(db, employee):
    a = _activity(db, employee)
    assert a.updated_by is None


def test_update_activity_sets_updated_by_to_editor_initials(db, employee):
    from routers.activities import update_activity
    a = _activity(db, employee)
    resp = update_activity(a.id, ActivityUpdate(comment="Rettet kommentar"),
                            current_user=_user("LB1"), db=db)
    assert resp.updated_by == "LB1"


def test_update_activity_overwrites_updated_by_with_latest_editor(db, employee):
    from routers.activities import update_activity
    a = _activity(db, employee)
    update_activity(a.id, ActivityUpdate(comment="Første rettelse"),
                     current_user=_user("LB1"), db=db)
    resp = update_activity(a.id, ActivityUpdate(comment="Anden rettelse"),
                            current_user=_user("DSP"), db=db)
    assert resp.updated_by == "DSP"
