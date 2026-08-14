from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from database.models import AppUser, EmployeeSpringerFlag
from calculators.pay_period import get_or_create_period_for_date


def _dummy_user():
    """Ugemt AppUser til at kalde route-funktioner direkte i tests uden en
    rigtig session — samme mønster som i tests/test_employee_supplements.py."""
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_unique_constraint_prevents_duplicate_employee_period_row(db, employee):
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=True))
    db.commit()
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=False))
    with pytest.raises(Exception):  # IntegrityError fra det unikke indeks
        db.commit()
    db.rollback()


def test_different_periods_can_both_have_a_row_for_same_employee(db, employee):
    period1 = get_or_create_period_for_date(date(2026, 1, 1), db)
    period2 = get_or_create_period_for_date(date(2026, 1, 15), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period1.id, enabled=True))
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period2.id, enabled=True))
    db.commit()  # skal IKKE kaste IntegrityError
