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
