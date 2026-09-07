import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

from database.models import Employee, AgreementKind


def _emp(schedule):
    return Employee(
        employee_number="9999", first_name="Test", last_name="Medarbejder",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1), work_schedule=schedule,
    )


def test_weekday_dates_excludes_weekend():
    from routers.activities import _weekday_dates
    dates = _weekday_dates(date(2026, 1, 5), date(2026, 1, 11))  # man 5/1 - søn 11/1
    assert dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                     date(2026, 1, 8), date(2026, 1, 9)]


def test_weekday_dates_single_day():
    from routers.activities import _weekday_dates
    assert _weekday_dates(date(2026, 1, 7), date(2026, 1, 7)) == [date(2026, 1, 7)]


def test_range_day_defaults_uses_scheduled_hours_for_ferie():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]})
    assert _range_day_defaults("ferie", date(2026, 1, 5), emp) == 8  # mandag uge 2 (lige)


def test_range_day_defaults_falls_back_to_7_4_when_no_schedule():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [0, 0, 0, 0, 0, 0, 0], "odd": [0, 0, 0, 0, 0, 0, 0]})
    assert _range_day_defaults("ferie", date(2026, 1, 5), emp) == 7.4


def test_range_day_defaults_feriefri_always_7_4_ignoring_schedule():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]})
    assert _range_day_defaults("feriefri", date(2026, 1, 5), emp) == 7.4


def test_range_day_defaults_afspadsering_uses_scheduled_hours():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [8, 8, 0, 8, 8, 0, 0], "odd": [8, 8, 0, 8, 8, 0, 0]})
    assert _range_day_defaults("afspadsering", date(2026, 1, 5), emp) == 8  # mandag = 8


def test_range_day_defaults_afspadsering_skips_zero_scheduled_day():
    from routers.activities import _range_day_defaults
    emp = _emp({"even": [8, 8, 0, 8, 8, 0, 0], "odd": [8, 8, 0, 8, 8, 0, 0]})
    assert _range_day_defaults("afspadsering", date(2026, 1, 7), emp) is None  # onsdag = 0
