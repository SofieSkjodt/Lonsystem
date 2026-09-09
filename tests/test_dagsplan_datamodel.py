import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from database.models import DailyPlanAssignment, DispatcherGroup, Employee, Vehicle, VehicleAbsence


def _vehicle(db, number="52", reg="BN47449"):
    v = Vehicle(registration_number=reg, vehicle_number=number)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_vehicle_has_description_and_dispatcher_group(db):
    group = DispatcherGroup(name="2 - Kran")
    db.add(group)
    db.commit()
    v = Vehicle(registration_number="BN47449", vehicle_number="52",
                description="Kranvogn", dispatcher_group_id=group.id)
    db.add(v)
    db.commit()
    db.refresh(v)
    assert v.description == "Kranvogn"
    assert v.dispatcher_group.name == "2 - Kran"
    assert v.dispatcher_group_name == "2 - Kran"


def test_dispatcher_group_vehicle_link_still_works_independently(db):
    """Det gamle DispatcherGroup.vehicle_id (standardvogn) må ikke kollidere
    med det nye Vehicle.dispatcher_group_id (mange vogne -> én gruppe)."""
    v1 = _vehicle(db, "52", "BN47449")
    v2 = _vehicle(db, "60", "AB12345")
    group = DispatcherGroup(name="2 - Kran", vehicle_id=v1.id)
    db.add(group)
    db.commit()
    v2.dispatcher_group_id = group.id
    db.commit()
    db.refresh(group)
    db.refresh(v2)
    assert group.vehicle.vehicle_number == "52"
    assert v2.dispatcher_group.name == "2 - Kran"


def test_employee_fast_bil_fields(db, employee):
    v = _vehicle(db)
    employee.fast_bil = True
    employee.fast_bil_vehicle_id = v.id
    db.commit()
    db.refresh(employee)
    assert employee.fast_bil_vehicle.vehicle_number == "52"


def test_vehicle_fast_bil_employee_name_property(db, employee):
    v = _vehicle(db)
    assert v.fast_bil_employee_name is None  # ingen har den som Fast bil endnu

    employee.fast_bil = True
    employee.fast_bil_vehicle_id = v.id
    db.commit()
    db.refresh(v)
    assert v.fast_bil_employee_name == employee.name


def test_vehicle_fast_bil_employee_name_lists_multiple_if_present(db, employee):
    """Ikke forventet i praksis, men intet forhindrer det i dag - vis begge i stedet for at skjule det."""
    from database.models import AgreementKind, Employee as EmployeeModel
    v = _vehicle(db)
    employee.fast_bil = True
    employee.fast_bil_vehicle_id = v.id
    other = EmployeeModel(
        employee_number="9500", first_name="Anden", last_name="Fastbil",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
        hire_date=employee.hire_date, work_schedule=employee.work_schedule,
        fast_bil=True, fast_bil_vehicle_id=v.id,
    )
    db.add(other)
    db.commit()
    db.refresh(v)
    assert employee.name in v.fast_bil_employee_name
    assert other.name in v.fast_bil_employee_name


def test_daily_plan_assignment_unique_per_date_and_vehicle(db, employee):
    v = _vehicle(db)
    db.add(DailyPlanAssignment(date=date(2026, 9, 9), vehicle_id=v.id,
                                employee_id=employee.id, task="Asfalt", informed=True))
    db.commit()
    db.add(DailyPlanAssignment(date=date(2026, 9, 9), vehicle_id=v.id, employee_id=employee.id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_vehicle_absence_vehicle_number_property(db):
    v = _vehicle(db)
    absence = VehicleAbsence(vehicle_id=v.id, date_from=date(2026, 9, 9),
                              comment="Til syn")
    db.add(absence)
    db.commit()
    db.refresh(absence)
    assert absence.date_to is None
    assert absence.vehicle_number == "52"
