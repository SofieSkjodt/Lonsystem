from datetime import datetime, date

from database.models import Employee, ActivitySource, ActivityStatus
from routers.payroll_router import _calculate_employee
from conftest import make_activity

# 2026-08-30 er en søndag (bekræftet ift. lønperioden 24/8-6/9-2026)
_SUNDAY = date(2026, 8, 30)
_SATURDAY = date(2026, 8, 29)

_SCHEDULE_WITH_SUNDAY_HOURS = {
    "even": [8, 8, 8, 8, 8, 0, 8],
    "odd":  [8, 8, 8, 8, 8, 0, 8],
}


def _make_employee(db, afloeser: bool, fuldloennet: bool = True, employee_number: str = "9501"):
    emp = Employee(
        employee_number=employee_number,
        first_name="Test",
        last_name="Afloeser",
        agreement_kind="hourly_fixed",
        agreement_type="",
        fuldloennet=fuldloennet,
        afloeser=afloeser,
        hire_date=date(2020, 1, 1),
        work_schedule=_SCHEDULE_WITH_SUNDAY_HOURS,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def test_employee_afloeser_defaults_to_false(db, employee):
    assert employee.afloeser is False


def test_afloeser_gets_no_sh_pay_on_sunday_without_any_activity(db):
    emp = _make_employee(db, afloeser=True)
    result = _calculate_employee(emp, _SUNDAY, _SUNDAY, db)
    assert result["sh_fuldloennet_hours"] == 0.0
    assert result["sh_timeloennet_hours"] == 0.0


def test_afloeser_gets_no_sh_pay_on_sunday_with_only_absence_activity(db):
    emp = _make_employee(db, afloeser=True)
    make_activity(
        db, emp,
        datetime(2026, 8, 30, 6, 0), datetime(2026, 8, 30, 13, 24),
        activity_type="ferie", source=ActivitySource.manual,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _SUNDAY, _SUNDAY, db)
    assert result["sh_fuldloennet_hours"] == 0.0


def test_afloeser_still_gets_sh_pay_on_sunday_with_normal_activity(db):
    emp = _make_employee(db, afloeser=True, fuldloennet=True)
    make_activity(
        db, emp,
        datetime(2026, 8, 30, 6, 0), datetime(2026, 8, 30, 14, 0),
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _SUNDAY, _SUNDAY, db)
    assert result["sh_fuldloennet_hours"] == 8.0
    assert result["sh_timeloennet_hours"] == 0.0


def test_afloeser_timeloennet_gets_no_sh_pay_on_sunday_without_activity(db):
    emp = _make_employee(db, afloeser=True, fuldloennet=False)
    result = _calculate_employee(emp, _SUNDAY, _SUNDAY, db)
    assert result["sh_timeloennet_hours"] == 0.0
    assert result["sh_fuldloennet_hours"] == 0.0


def test_non_afloeser_still_gets_sh_pay_on_sunday_without_activity(db):
    emp = _make_employee(db, afloeser=False)
    result = _calculate_employee(emp, _SUNDAY, _SUNDAY, db)
    assert result["sh_fuldloennet_hours"] == 8.0


def test_afloeser_saturday_unaffected(db):
    emp = _make_employee(db, afloeser=True)
    result = _calculate_employee(emp, _SATURDAY, _SATURDAY, db)
    assert result["sh_fuldloennet_hours"] == 0.0
    assert result["sh_timeloennet_hours"] == 0.0
