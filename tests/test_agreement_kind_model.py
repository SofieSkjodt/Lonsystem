from datetime import date

from database.models import MasterAgreementKind, Employee, AgreementKind


def test_master_agreement_kind_row_has_expected_fields(db):
    row = MasterAgreementKind(
        key="hourly_fixed",
        label="Timelønnet, fast arbejdstid",
        is_active=True,
        is_user_created=False,
        requires_agreement_type=True,
        sort_order=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.id is not None
    assert row.key == "hourly_fixed"
    assert row.is_user_created is False
    assert row.requires_agreement_type is True


def test_employee_agreement_kind_accepts_new_custom_string(db):
    """agreement_kind skal kunne gemme en helt ny, brugeroprettet nøgle –
    ikke kun de to gamle enum-værdier."""
    emp = Employee(
        employee_number="9001",
        first_name="Ny",
        last_name="Type",
        agreement_kind="mit_nye_aftale_flag",
        agreement_type="",
        hire_date=date(2026, 1, 1),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    assert emp.agreement_kind == "mit_nye_aftale_flag"


def test_employee_agreement_kind_still_accepts_system_enum_values(db):
    """De to eksisterende værdier skal fortsat kunne gemmes uændret."""
    emp = Employee(
        employee_number="9002",
        first_name="Gammel",
        last_name="Type",
        agreement_kind=AgreementKind.hourly_flexible,
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    assert emp.agreement_kind == "hourly_flexible"
