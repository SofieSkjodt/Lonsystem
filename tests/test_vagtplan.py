from database.schemas import EmployeeCreate, WorkSchedule
from datetime import date


def test_employee_response_includes_initials(db, employee):
    from routers.employees import _to_response
    employee.initials = "ABC"
    db.commit()
    resp = _to_response(employee, db)
    assert resp.initials == "ABC"


def test_employee_initials_defaults_to_none(db, employee):
    from routers.employees import _to_response
    resp = _to_response(employee, db)
    assert resp.initials is None


def test_create_employee_persists_initials(db):
    from routers.employees import create_employee
    from database.models import AppUser, MasterAgreementType
    from decimal import Decimal
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.commit()
    body = EmployeeCreate(
        employee_number="9999",
        first_name="Ny",
        last_name="Person",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        initials="NYP",
    )
    user = AppUser(name="Test", initials="TST", role="admin", password_hash="x")
    resp = create_employee(body, current_user=user, db=db)
    assert resp.initials == "NYP"
