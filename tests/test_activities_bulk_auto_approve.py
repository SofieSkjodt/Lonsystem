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
