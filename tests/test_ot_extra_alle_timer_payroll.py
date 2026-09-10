from datetime import datetime, date

from database.models import Employee, ActivitySource, ActivityStatus, Holiday
from routers.payroll_router import _calculate_employee
from conftest import make_activity

# 2026-09-13 er en søndag, 2026-09-12 en lørdag, 2026-09-11 en fredag (hverdag)
_SUNDAY = date(2026, 9, 13)
_SATURDAY = date(2026, 9, 12)
_WEEKDAY = date(2026, 9, 11)
_1MAJ = date(2026, 5, 1)          # fredag
_GRUNDLOVSDAG = date(2026, 6, 5)  # fredag

_SCHEDULE = {
    "even": [8, 8, 8, 8, 8, 0, 8],
    "odd":  [8, 8, 8, 8, 8, 0, 8],
}


def _make_employee(db, ot_extra_alle_timer: bool, employee_number: str = "9601"):
    emp = Employee(
        employee_number=employee_number,
        first_name="Test",
        last_name="Saeraftale",
        agreement_kind="hourly_fixed",
        agreement_type="",
        fuldloennet=True,
        ot_extra_alle_timer=ot_extra_alle_timer,
        hire_date=date(2020, 1, 1),
        work_schedule=_SCHEDULE,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def test_weekday_16_hour_shift_gives_full_normal_and_full_ot_extra(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    make_activity(
        db, emp,
        datetime(2026, 9, 11, 6, 0), datetime(2026, 9, 11, 22, 0),  # 16 timer
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _WEEKDAY, _WEEKDAY, db)
    assert result["normal_hours"] == 16.0
    assert result["ot_extra_hours"] == 16.0
    assert result["ot_13_hours"] == 0.0
    assert result["ot_before_hours"] == 0.0


def test_saturday_shift_gives_full_normal_and_full_ot_extra(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    make_activity(
        db, emp,
        datetime(2026, 9, 12, 6, 0), datetime(2026, 9, 12, 14, 0),  # 8 timer
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _SATURDAY, _SATURDAY, db)
    assert result["normal_hours"] == 8.0
    assert result["ot_extra_hours"] == 8.0
    assert result["ot_13_hours"] == 0.0


def test_sunday_still_gives_kode1_and_kode9_never_kode8(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    make_activity(
        db, emp,
        datetime(2026, 9, 13, 6, 0), datetime(2026, 9, 13, 14, 0),  # 8 timer
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _SUNDAY, _SUNDAY, db)
    assert result["normal_hours"] == 8.0
    assert result["sh_kode9_hours"] == 8.0
    assert result["sh_kode8_hours"] == 0.0


def test_1maj_kode9_covers_whole_day_never_kode8(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    db.add(Holiday(date=_1MAJ, name="1. maj", half_day_from="12:00"))
    db.commit()
    make_activity(
        db, emp,
        datetime(2026, 5, 1, 8, 0), datetime(2026, 5, 1, 16, 0),  # 4t før/4t efter kl. 12
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _1MAJ, _1MAJ, db)
    assert result["normal_hours"] == 8.0
    assert result["sh_kode9_hours"] == 8.0  # ikke kun de 4 eftermiddagstimer
    assert result["sh_kode8_hours"] == 0.0  # aldrig kode 8, heller ikke for 1. maj


def test_grundlovsdag_kode9_covers_whole_day(db):
    emp = _make_employee(db, ot_extra_alle_timer=True)
    db.add(Holiday(date=_GRUNDLOVSDAG, name="Grundlovsdag", half_day_from="12:00"))
    db.commit()
    make_activity(
        db, emp,
        datetime(2026, 6, 5, 8, 0), datetime(2026, 6, 5, 16, 0),
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _GRUNDLOVSDAG, _GRUNDLOVSDAG, db)
    assert result["normal_hours"] == 8.0
    assert result["sh_kode9_hours"] == 8.0
    assert result["sh_kode8_hours"] == 0.0


def test_kode4_63_guarantee_unaffected_by_flag(db):
    """Kode 4/63 (SH-garanti) skal give samme resultat med og uden flaget."""
    emp_on = _make_employee(db, ot_extra_alle_timer=True, employee_number="9602")
    emp_off = _make_employee(db, ot_extra_alle_timer=False, employee_number="9603")
    result_on = _calculate_employee(emp_on, _SUNDAY, _SUNDAY, db)
    result_off = _calculate_employee(emp_off, _SUNDAY, _SUNDAY, db)
    assert result_on["sh_fuldloennet_hours"] == result_off["sh_fuldloennet_hours"]
    assert result_on["sh_timeloennet_hours"] == result_off["sh_timeloennet_hours"]


def test_flag_off_is_unaffected_regression(db):
    emp = _make_employee(db, ot_extra_alle_timer=False)
    make_activity(
        db, emp,
        datetime(2026, 9, 11, 6, 0), datetime(2026, 9, 11, 22, 0),  # 16 timer
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )
    result = _calculate_employee(emp, _WEEKDAY, _WEEKDAY, db)
    # normal_hours er (uændret, som hele tiden) alle arbejdede timer (additiv
    # model, jf. calculate_overtime()) - det er IKKE dette der adskiller
    # særaftalen. Forskellen er ot_13/ot_extra-fordelingen: en almindelig
    # medarbejder med 8t loft (fredag) får her kode 8 (3t, loftet for
    # "1-3 timer") + kode 9 (5t, resten) - IKKE kode 9 for alle 16 timer og
    # ALDRIG kode 8, som en medarbejder med flaget ville få.
    assert result["normal_hours"] == 16.0
    assert result["ot_13_hours"] == 3.0
    assert result["ot_extra_hours"] == 5.0
