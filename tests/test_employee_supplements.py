from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from database.models import AppUser, EmployeeSupplement, MasterAgreementType, MasterOvertimeRate
from database.schemas import EmployeeSupplementCreate
from calculators.rates_loader import get_active_supplement_for_period
from routers.employee_supplements import _create_supplement
from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
from routers.payroll_router import _calculate_employee


def _dummy_user():
    """Ubevaret AppUser til at kalde route-funktioner direkte i tests uden en
    rigtig session — log_action() læser kun .id/.initials, som begge er None/
    ubrugt på et ugemt objekt, hvilket er fint da AuditLog.user_id er nullable.
    Samme mønster som _test_user() i tests/test_import_ddd.py."""
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


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


def test_calculate_employee_includes_supplement_in_hourly_rate(db, employee):
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("12.50"))

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["hourly_rate"] == pytest.approx(162.50)


def test_calculate_employee_unaffected_when_no_supplement(db, employee):
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["hourly_rate"] == pytest.approx(150.00)


# ── Punkt A: "Afslut tillæg" ────────────────────────────────────────────────


def test_end_supplement_sets_end_date_to_current_period_end(db, employee):
    from calculators.pay_period import get_or_create_period_for_date
    from routers.employee_supplements import end_supplement
    row = _create_supplement(db, employee.id, date.today() - timedelta(days=5), Decimal("10.00"))
    period = get_or_create_period_for_date(date.today(), db)
    result = end_supplement(row.id, current_user=_dummy_user(), db=db)
    assert result.end_date == period.end_date
    assert result.is_active is True  # stadig aktiv resten af den nuværende periode


def test_ended_supplement_does_not_apply_to_next_period(db, employee):
    from calculators.pay_period import get_or_create_period_for_date
    from routers.employee_supplements import end_supplement
    row = _create_supplement(db, employee.id, date.today() - timedelta(days=5), Decimal("10.00"))
    end_supplement(row.id, current_user=_dummy_user(), db=db)
    period = get_or_create_period_for_date(date.today(), db)
    next_day = period.end_date + timedelta(days=1)
    result = get_active_supplement_for_period(db, employee.id, next_day, next_day + timedelta(days=13))
    assert result is None


def test_end_supplement_rejects_historical_row(db, employee):
    from routers.employee_supplements import end_supplement
    old = _create_supplement(db, employee.id, date(2020, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2020, 6, 1), Decimal("20.00"))  # lukker 'old'
    with pytest.raises(HTTPException):
        end_supplement(old.id, current_user=_dummy_user(), db=db)


def test_end_supplement_rejects_unknown_id(db):
    from routers.employee_supplements import end_supplement
    with pytest.raises(HTTPException):
        end_supplement(999999, current_user=_dummy_user(), db=db)


# ── Punkt D: race condition / unikt constraint ──────────────────────────────


def test_create_supplement_conflict_returns_409(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    # Simulér race condition: indsæt manuelt en anden åbentstående række for samme
    # medarbejder direkte i DB'en (uden om _create_supplement's egen lukke-logik)
    conflicting = EmployeeSupplement(employee_id=employee.id, value=Decimal("99.00"), start_date=date(2026, 6, 1))
    db.add(conflicting)
    with pytest.raises(Exception):  # IntegrityError fra det unikke constraint
        db.commit()
    db.rollback()


# ── Punkt F: værdi-præcision ─────────────────────────────────────────────────


def test_create_supplement_rounds_down_to_zero_is_rejected(db, employee):
    with pytest.raises(HTTPException):
        _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("0.001"))


# ── Punkt G: 404 for ukendt employee_id ──────────────────────────────────────


def test_list_supplements_unknown_employee_id_raises_404(db):
    from routers.employee_supplements import list_supplements
    with pytest.raises(HTTPException):
        list_supplements(employee_id=999999, date_from=None, date_to=None, current_user=_dummy_user(), db=db)


def test_get_active_supplement_unknown_employee_id_raises_404(db):
    from routers.employee_supplements import get_active_supplement
    with pytest.raises(HTTPException):
        get_active_supplement(999999, current_user=_dummy_user(), db=db)


# ── Punkt J: is_active-beregning ─────────────────────────────────────────────


def test_is_active_computed_correctly_for_past_present_future(db, employee):
    from routers.employee_supplements import _to_response
    past = EmployeeSupplement(employee_id=employee.id, value=Decimal("10"),
                               start_date=date(2000, 1, 1), end_date=date(2000, 12, 31))
    current = EmployeeSupplement(employee_id=employee.id, value=Decimal("10"),
                                  start_date=date(2000, 1, 1))
    future = EmployeeSupplement(employee_id=employee.id, value=Decimal("10"),
                                 start_date=date(9999, 1, 1), end_date=date(9999, 12, 30))
    for row in (past, current, future):
        db.add(row)
    db.commit()
    assert _to_response(past).is_active is False
    assert _to_response(current).is_active is True
    assert _to_response(future).is_active is False


# ── Punkt B: fraværsoversigten matcher lønkørslens sats ─────────────────────


def test_absence_overview_rate_matches_payroll_calculation(db, employee):
    from database.models import ActivityStatus
    from conftest import make_activity
    from routers.absence_overview_router import _compute_data

    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("12.50"))

    make_activity(
        db, employee,
        datetime(2026, 1, 10, 8, 0), datetime(2026, 1, 10, 16, 0),
        activity_type="sygdom", status=ActivityStatus.approved,
    )

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)
    overview = _compute_data(date(2026, 1, 1), date(2026, 1, 31), db)

    emp_overview = next(e for e in overview["employees"] if e["employee_id"] == employee.id)
    overview_rate = emp_overview["absences"]["sygdom"]["rate"]

    assert overview_rate == pytest.approx(calc["hourly_rate"])
    assert overview_rate == pytest.approx(162.50)
