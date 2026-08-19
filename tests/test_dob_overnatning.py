from datetime import datetime

import pytest
from pydantic import ValidationError

from database.schemas import ActivityCreate


def test_activity_create_allows_equal_start_end_for_dob_overnatning():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    activity = ActivityCreate(
        employee_id=1,
        activity_type="dob_overnatning",
        start_time=midnight,
        end_time=midnight,
    )
    assert activity.activity_type == "dob_overnatning"


def test_activity_create_still_allows_equal_start_end_for_overnatning():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    activity = ActivityCreate(
        employee_id=1,
        activity_type="overnatning",
        start_time=midnight,
        end_time=midnight,
    )
    assert activity.activity_type == "overnatning"


def test_activity_create_rejects_equal_start_end_for_normal():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    with pytest.raises(ValidationError):
        ActivityCreate(
            employee_id=1,
            activity_type="normal",
            start_time=midnight,
            end_time=midnight,
        )
