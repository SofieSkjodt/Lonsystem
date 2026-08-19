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


def test_load_dob_overnight_rate_from_db_returns_seeded_rate(db):
    from decimal import Decimal
    from database.models import MasterSupplementRate
    from calculators.rates_loader import load_dob_overnight_rate_from_db
    db.add(MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True))
    db.commit()
    assert load_dob_overnight_rate_from_db(db) == Decimal("597.00")


def test_load_dob_overnight_rate_from_db_returns_zero_when_missing(db):
    from decimal import Decimal
    from calculators.rates_loader import load_dob_overnight_rate_from_db
    assert load_dob_overnight_rate_from_db(db) == Decimal("0")
