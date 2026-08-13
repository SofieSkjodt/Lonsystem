from datetime import date
from decimal import Decimal

import pytest

from database.models import EmployeeSupplement
from database.schemas import EmployeeSupplementCreate


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
