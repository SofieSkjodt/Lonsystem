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


def test_ensure_toggle_springer_permission_adds_to_all_roles(db, monkeypatch):
    from database.models import Role
    from database.session import _ensure_toggle_springer_permission
    import database.session as session_module

    # _ensure_toggle_springer_permission bruger sin egen SessionLocal, ikke test-db'en –
    # patch den (auto-reverteres af monkeypatch efter testen) til test-enginens
    # sessionmaker så funktionen skriver til samme in-memory DB.
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=["payroll"]))
    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False, permissions=["payroll"]))
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()

    _ensure_toggle_springer_permission()

    for role in db.query(Role).all():
        db.refresh(role)
        assert "toggle_springer" in role.permissions

    # Idempotent — kald igen ændrer ikke noget/fejler ikke
    _ensure_toggle_springer_permission()
    for role in db.query(Role).all():
        db.refresh(role)
        assert role.permissions.count("toggle_springer") == 1


def test_ensure_springer_pay_type_seeds_rate_and_paytype(db, monkeypatch):
    from database.models import MasterSupplementRate, MasterPayType
    from database.session import _ensure_springer_pay_type
    import database.session as session_module
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    _ensure_springer_pay_type()

    rate_row = db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "Springertillæg").first()
    assert rate_row is not None
    assert rate_row.rate == 0

    pt_row = db.query(MasterPayType).filter(MasterPayType.code_key == "SPRINGERTILLAEG").first()
    assert pt_row is not None
    assert pt_row.csv_quantity_type == "hours"
    assert pt_row.csv_rate_source == "springer"
    assert pt_row.include_in_csv is True

    # Idempotent
    _ensure_springer_pay_type()
    assert db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "Springertillæg").count() == 1
    assert db.query(MasterPayType).filter(MasterPayType.code_key == "SPRINGERTILLAEG").count() == 1
