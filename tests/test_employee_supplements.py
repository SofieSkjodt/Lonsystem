from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from database.models import EmployeeSupplement
from database.schemas import EmployeeSupplementCreate
from routers.employee_supplements import get_active_supplement_for_period, _create_supplement


def test_supplement_defaults_to_open_ended_with_hardcoded_name_and_type(db, employee):
    row = EmployeeSupplement(employee_id=employee.id, value=Decimal("10.00"), start_date=date(2026, 1, 1))
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.end_date == date(9999, 12, 31)
    assert row.name == "Ikke overenskomstmæssigt tillæg"
    assert row.type == "Timebaseret"


def test_schema_rejects_non_positive_value():
    with pytest.raises(Exception):
        EmployeeSupplementCreate(employee_id=1, start_date=date(2026, 1, 1), value=0)


def test_schema_accepts_positive_value():
    body = EmployeeSupplementCreate(employee_id=1, start_date=date(2026, 1, 1), value=12.5)
    assert body.value == 12.5


def test_no_overlap_returns_none(db, employee):
    result = get_active_supplement_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert result is None


def test_single_overlap_found(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("15.00"))
    result = get_active_supplement_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert result is not None
    assert result.value == Decimal("15.00")


def test_newest_wins_when_created_mid_period(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2026, 1, 15), Decimal("20.00"))
    result = get_active_supplement_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert result.value == Decimal("20.00")


def test_historical_period_still_finds_old_supplement_after_new_one_added(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2026, 2, 1), Decimal("20.00"))
    result = get_active_supplement_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert result.value == Decimal("10.00")


def test_create_closes_previous_open_row(db, employee):
    first = _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2026, 2, 1), Decimal("20.00"))
    db.refresh(first)
    assert first.end_date == date(2026, 1, 31)


def test_create_rejects_non_positive_value(db, employee):
    with pytest.raises(HTTPException):
        _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("0"))


def test_create_rejects_start_date_not_after_open_row(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 15), Decimal("10.00"))
    with pytest.raises(HTTPException):
        _create_supplement(db, employee.id, date(2026, 1, 10), Decimal("20.00"))


def test_create_rejects_unknown_employee(db):
    with pytest.raises(HTTPException):
        _create_supplement(db, 999999, date(2026, 1, 1), Decimal("10.00"))
