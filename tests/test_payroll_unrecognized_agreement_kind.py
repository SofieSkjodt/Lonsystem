from datetime import datetime, date

from database.models import Employee, ActivitySource, ActivityStatus
from routers.payroll_router import _calculate_employee
from conftest import make_activity


def test_unrecognized_agreement_kind_gets_flat_hours_no_overtime(db):
    emp = Employee(
        employee_number="9201",
        first_name="Ny",
        last_name="Aftaletype",
        agreement_kind="fremtidig_type",  # findes ikke i AgreementKind
        agreement_type="",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    # Vagt der ville udløse aftentillæg for en normal medarbejder (18-22)
    make_activity(
        db, emp,
        datetime(2026, 8, 24, 14, 0), datetime(2026, 8, 24, 22, 0),
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )

    result = _calculate_employee(emp, date(2026, 8, 24), date(2026, 8, 24), db)

    assert result["normal_hours"] == 8.0
    assert result["ot_before_hours"] == 0.0
    assert result["ot_13_hours"] == 0.0
    assert result["ot_extra_hours"] == 0.0
    assert result["sh_kode8_hours"] == 0.0
    assert result["sh_kode9_hours"] == 0.0
