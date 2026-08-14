from datetime import date, datetime
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


def test_load_springer_rate_from_db_returns_seeded_rate(db):
    from decimal import Decimal
    from database.models import MasterSupplementRate
    from calculators.rates_loader import load_springer_rate_from_db
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("25.50")))
    db.commit()
    assert load_springer_rate_from_db(db) == Decimal("25.50")


def test_load_springer_rate_from_db_returns_zero_when_missing(db):
    from decimal import Decimal
    from calculators.rates_loader import load_springer_rate_from_db
    assert load_springer_rate_from_db(db) == Decimal("0")


def test_resolve_rate_springer_reads_calc_dict():
    from routers.payroll_router import _resolve_rate
    calc = {"springer_rate": 25.5, "hourly_rate": 150.0}
    assert _resolve_rate("springer", calc) == 25.5


def test_resolve_rate_springer_defaults_to_zero_when_missing():
    from routers.payroll_router import _resolve_rate
    calc = {"hourly_rate": 150.0}
    assert _resolve_rate("springer", calc) == 0


def _setup_rates(db, employee, hourly=Decimal("150.00")):
    from database.models import MasterAgreementType, MasterOvertimeRate
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=hourly))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()


def test_calculate_employee_springer_disabled_by_default(db, employee):
    from routers.payroll_router import _calculate_employee
    _setup_rates(db, employee)
    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 14), db)
    assert calc["springer_enabled"] is False


def test_calculate_employee_springer_enabled_when_flag_set(db, employee):
    from database.models import EmployeeSpringerFlag, MasterSupplementRate
    from routers.payroll_router import _calculate_employee
    _setup_rates(db, employee)
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("20.00")))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=True))
    db.commit()

    calc = _calculate_employee(employee, period.start_date, period.end_date, db)
    assert calc["springer_enabled"] is True
    assert calc["springer_rate"] == pytest.approx(20.00)


def test_calculate_employee_springer_flag_does_not_carry_to_next_period(db, employee):
    from database.models import EmployeeSpringerFlag
    from routers.payroll_router import _calculate_employee
    _setup_rates(db, employee)
    period1 = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period1.id, enabled=True))
    db.commit()

    period2 = get_or_create_period_for_date(date(2026, 1, 15), db)
    calc = _calculate_employee(employee, period2.start_date, period2.end_date, db)
    assert calc["springer_enabled"] is False


def test_springer_row_uses_normal_hours_when_enabled():
    from routers.payroll_router import _springer_row
    calc = {"normal_hours": 74.0, "springer_enabled": True, "springer_rate": 20.0}
    assert _springer_row(calc) == ("SPRINGERTILLAEG", 74.0, 20.0)


def test_springer_row_zero_when_disabled():
    from routers.payroll_router import _springer_row
    calc = {"normal_hours": 74.0, "springer_enabled": False, "springer_rate": 20.0}
    assert _springer_row(calc) == ("SPRINGERTILLAEG", 0, 20.0)


def test_export_csv_post_includes_springer_line_when_enabled(db, employee, tmp_path):
    from database.models import EmployeeSpringerFlag, MasterSupplementRate, MasterPayType, ActivityStatus
    from calculators.pay_rates import DANLOEN_CODE_SPRINGERTILLAEG
    from routers.payroll_router import export_csv_post, ExportCsvRequest
    from conftest import make_activity

    employee.cvr_number = "13246505"
    _setup_rates(db, employee)
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("20.00")))
    db.add(MasterPayType(
        code_key="SPRINGERTILLAEG", label="Springertillæg", danloen_code=DANLOEN_CODE_SPRINGERTILLAEG,
        include_in_csv=True, sort_order=16, csv_quantity_type="hours", csv_rate_source="springer",
        csv_include_rate=True, csv_include_total=False,
    ))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=True))
    db.commit()
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    body = ExportCsvRequest(period_start="2026-01-01", output_folder=str(tmp_path))
    export_csv_post(body, current_user=_dummy_user(), db=db)

    csv_files = list(tmp_path.glob("danloen_*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text(encoding="utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    # Medarbejderen har kun én aktivitet (8 arbejdstimer, ingen overtid/salt/fravær) – med
    # flueben sat giver det præcis 2 linjer (NORMAL + SPRINGERTILLAEG), begge med kvantitet 800
    # (8 timer * 100, jf. fmt()). NORMAL og SPRINGERTILLAEG deler samme placeholder Danløn-kode
    # ("1"), så linjerne kan ikke skelnes på kolonne C – antallet af linjer er det robuste tjek.
    assert len(lines) == 2
    assert all(line.split(";")[3] == "800" for line in lines)


def test_export_csv_post_omits_springer_line_when_disabled(db, employee, tmp_path):
    from database.models import MasterSupplementRate, MasterPayType, ActivityStatus
    from calculators.pay_rates import DANLOEN_CODE_SPRINGERTILLAEG
    from routers.payroll_router import export_csv_post, ExportCsvRequest
    from conftest import make_activity

    employee.cvr_number = "13246505"
    _setup_rates(db, employee)
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("20.00")))
    db.add(MasterPayType(
        code_key="SPRINGERTILLAEG", label="Springertillæg", danloen_code=DANLOEN_CODE_SPRINGERTILLAEG,
        include_in_csv=True, sort_order=16, csv_quantity_type="hours", csv_rate_source="springer",
        csv_include_rate=True, csv_include_total=False,
    ))
    # Ingen EmployeeSpringerFlag-række oprettet — fluebenet er IKKE sat
    db.commit()
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    body = ExportCsvRequest(period_start="2026-01-01", output_folder=str(tmp_path))
    export_csv_post(body, current_user=_dummy_user(), db=db)

    csv_files = list(tmp_path.glob("danloen_*.csv"))
    content = csv_files[0].read_text(encoding="utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    assert len(lines) == 1  # kun NORMAL – ingen SPRINGERTILLAEG-linje uden flueben
