from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from database.models import ActivityStatus, MasterAgreementType, MasterOvertimeRate, MasterSupplementRate
from database.schemas import ActivityCreate
from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY


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


def _setup_rates(db, employee, hourly=Decimal("150.00")):
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=hourly))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.add(MasterSupplementRate(label="Overnatning", rate=Decimal("95.00")))
    db.add(MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True))
    db.commit()


def test_calculate_employee_dob_overnight_excluded_from_kode14_count(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 17), date(2026, 8, 23), db)

    assert calc["overnight_count"] == 0
    assert calc["dob_overnight_count"] == 1
    assert calc["dob_overnight_rate"] == pytest.approx(597.00)
    assert calc["dob_overnight_kr"] == pytest.approx(597.00)


def test_calculate_employee_regular_overnight_still_counts_as_kode14(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 17), date(2026, 8, 23), db)

    assert calc["overnight_count"] == 1
    assert calc["overnight_kr"] == pytest.approx(95.00)
    assert calc["dob_overnight_count"] == 0
    assert calc["dob_overnight_kr"] == 0.0


def test_calculate_employee_dob_overnight_not_counted_as_work_hours(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 20), date(2026, 8, 20), db)

    assert calc["normal_hours"] == 0.0
    day = next(d for d in calc["days"] if d["date"] == "2026-08-20")
    assert day["overnight"] == 1
    assert day["absence_type"] is None
