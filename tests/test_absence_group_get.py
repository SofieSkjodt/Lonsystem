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
