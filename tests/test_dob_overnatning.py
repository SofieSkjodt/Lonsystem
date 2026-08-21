from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from database.models import ActivityStatus, MasterAgreementType, MasterOvertimeRate, MasterSupplementRate
from database.schemas import ActivityCreate, ActivityUpdate
from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY


def test_activity_create_allows_equal_start_end_for_dob_overnatning():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    activity = ActivityCreate(
        employee_id=1,
        activity_type="dob_overnatning",
        start_time=midnight,
        end_time=midnight,
    )
    assert activity.activity_type == "dob_overnatning"


def test_activity_create_still_allows_equal_start_end_for_overnatning():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    activity = ActivityCreate(
        employee_id=1,
        activity_type="overnatning",
        start_time=midnight,
        end_time=midnight,
    )
    assert activity.activity_type == "overnatning"


def test_activity_create_rejects_equal_start_end_for_normal():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    with pytest.raises(ValidationError):
        ActivityCreate(
            employee_id=1,
            activity_type="normal",
            start_time=midnight,
            end_time=midnight,
        )


def test_activity_update_allows_equal_start_end_when_toggling_to_dob_overnatning():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    update = ActivityUpdate(
        activity_type="dob_overnatning",
        start_time=midnight,
        end_time=midnight,
    )
    assert update.activity_type == "dob_overnatning"


def test_activity_update_allows_equal_start_end_when_toggling_to_overnatning():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    update = ActivityUpdate(
        activity_type="overnatning",
        start_time=midnight,
        end_time=midnight,
    )
    assert update.activity_type == "overnatning"


def test_activity_update_still_rejects_equal_start_end_without_activity_type():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    with pytest.raises(ValidationError):
        ActivityUpdate(
            start_time=midnight,
            end_time=midnight,
        )


def test_load_dob_overnight_rate_from_db_returns_seeded_rate(db):
    from decimal import Decimal
    from database.models import MasterSupplementRate
    from calculators.rates_loader import load_dob_overnight_rate_from_db
    db.add(MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True))
    db.commit()
    assert load_dob_overnight_rate_from_db(db) == Decimal("597.00")


def test_load_dob_overnight_rate_from_db_returns_zero_when_missing(db):
    from decimal import Decimal
    from calculators.rates_loader import load_dob_overnight_rate_from_db
    assert load_dob_overnight_rate_from_db(db) == Decimal("0")


def _setup_rates(db, employee, hourly=Decimal("150.00")):
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=hourly))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.add(MasterSupplementRate(label="Overnatning", rate=Decimal("95.00")))
    db.add(MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True))
    db.commit()


def test_calculate_employee_dob_overnight_excluded_from_kode14_count(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 17), date(2026, 8, 23), db)

    assert calc["overnight_count"] == 0
    assert calc["dob_overnight_count"] == 1
    assert calc["dob_overnight_rate"] == pytest.approx(597.00)
    assert calc["dob_overnight_kr"] == pytest.approx(597.00)


def test_calculate_employee_regular_overnight_still_counts_as_kode14(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 17), date(2026, 8, 23), db)

    assert calc["overnight_count"] == 1
    assert calc["overnight_kr"] == pytest.approx(95.00)
    assert calc["dob_overnight_count"] == 0
    assert calc["dob_overnight_kr"] == 0.0


def test_calculate_employee_dob_overnight_not_counted_as_work_hours(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 20), date(2026, 8, 20), db)

    assert calc["normal_hours"] == 0.0
    day = next(d for d in calc["days"] if d["date"] == "2026-08-20")
    assert day["overnight"] == 1
    assert day["absence_type"] is None


def _dummy_user():
    from database.models import AppUser
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_export_csv_post_splits_overnight_into_kode14_and_kode43(db, employee, tmp_path):
    from datetime import timedelta
    from database.models import MasterPayType, ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_router import export_csv_post, ExportCsvRequest
    from conftest import make_activity

    employee.cvr_number = "13246505"
    _setup_rates(db, employee)
    dob_supp = db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "DOB_overnatning").first()
    db.add(MasterPayType(
        code_key="OVERNATNING", label="Overnatning", danloen_code="14",
        include_in_csv=True, sort_order=6, csv_quantity_type="count", csv_rate_source="overnight",
    ))
    db.add(MasterPayType(
        code_key="dob_overnatning", label="DOB_overnatning", danloen_code="43",
        is_user_created=True, include_in_csv=True, sort_order=17,
        csv_quantity_type="count", csv_rate_source=f"supplement:{dob_supp.id}",
    ))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 8, 20), db)
    # Begge dage afledes af den faktiske periode (ikke hardcodede datoer) for at
    # garantere at de falder inden for samme lønperiode, uanset periodens grænser.
    midnight_a = datetime.combine(period.start_date, datetime.min.time())
    midnight_b = midnight_a + timedelta(days=1)
    make_activity(db, employee, midnight_a, midnight_a, activity_type="overnatning",
                  status=ActivityStatus.approved)
    make_activity(db, employee, midnight_b, midnight_b, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    body = ExportCsvRequest(period_start=period.start_date.isoformat(), output_folder=str(tmp_path))
    export_csv_post(body, current_user=_dummy_user(), db=db)

    csv_files = list(tmp_path.glob("danloen_*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text(encoding="utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    codes = {l.split(";")[2] for l in lines}
    assert "14" in codes, f"Forventede kode 14 (Overnatning) i linjerne: {lines}"
    assert "43" in codes, f"Forventede kode 43 (DOB_overnatning) i linjerne: {lines}"
    code14_line = next(l for l in lines if l.split(";")[2] == "14")
    code43_line = next(l for l in lines if l.split(";")[2] == "43")
    assert code14_line.split(";")[3] == "100"  # 1 stk * 100 (fmt() ganger med 100)
    assert code43_line.split(";")[3] == "100"
    assert code43_line.split(";")[4] == "59700"  # 597,00 kr * 100


def test_update_activity_toggles_overnatning_to_dob_overnatning(db, employee):
    from database.schemas import ActivityUpdate
    from routers.activities import update_activity
    from conftest import make_activity

    midnight = datetime(2026, 8, 20, 0, 0, 0)
    act = make_activity(db, employee, midnight, midnight, activity_type="overnatning",
                         status=ActivityStatus.pending)

    body = ActivityUpdate(activity_type="dob_overnatning", start_time=midnight, end_time=midnight)
    updated = update_activity(act.id, body, current_user=_dummy_user(), db=db)

    assert updated.activity_type == "dob_overnatning"


def test_absence_types_excludes_dob_overnatning_from_type_picker(db, employee):
    from database.models import MasterPayType
    from routers.activities import get_absence_types

    db.add(MasterPayType(
        code_key="dob_overnatning", label="DOB_overnatning", danloen_code="43",
        is_user_created=True, sort_order=17, csv_quantity_type="count",
        csv_rate_source="supplement:1",
    ))
    db.add(MasterPayType(
        code_key="andet_tillæg", label="Andet tillæg", danloen_code="99",
        is_user_created=True, sort_order=18, csv_quantity_type="hours",
        csv_rate_source="hourly",
    ))
    db.commit()

    result = get_absence_types(current_user=_dummy_user(), db=db)

    values = [r["value"] for r in result]
    assert "dob_overnatning" not in values
    assert "andet_tillæg" in values


def test_proevekoersel_workbook_includes_dob_overnight_row(db, employee):
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_router import _build_proevekoersel_workbook
    from conftest import make_activity

    _setup_rates(db, employee)
    period = get_or_create_period_for_date(date(2026, 8, 20), db)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    wb = _build_proevekoersel_workbook([employee], period, db)
    ws = wb.active
    labels = [row[3] for row in ws.iter_rows(values_only=True) if row[3]]
    assert "DOB Overnatning (kr.)" in labels
