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
