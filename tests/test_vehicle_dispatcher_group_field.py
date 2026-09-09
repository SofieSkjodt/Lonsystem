import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from fastapi import HTTPException

from database.models import AppUser, DispatcherGroup
from database.schemas import VehicleCreate, VehicleUpdate


def _admin():
    return AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")


def test_create_vehicle_with_description_and_dispatcher_group(db):
    from routers.vehicles import create_vehicle
    group = DispatcherGroup(name="2 - Kran")
    db.add(group)
    db.commit()
    body = VehicleCreate(registration_number="BN47449", vehicle_number="52",
                          description="Kranvogn", dispatcher_group_id=group.id)
    resp = create_vehicle(body, current_user=_admin(), db=db)
    assert resp.description == "Kranvogn"
    assert resp.dispatcher_group_id == group.id
    assert resp.dispatcher_group_name == "2 - Kran"


def test_create_vehicle_unknown_dispatcher_group_rejected(db):
    from routers.vehicles import create_vehicle
    body = VehicleCreate(registration_number="BN47449", vehicle_number="52",
                          dispatcher_group_id=999)
    with pytest.raises(HTTPException) as exc:
        create_vehicle(body, current_user=_admin(), db=db)
    assert exc.value.status_code == 400


def test_update_vehicle_description(db):
    from routers.vehicles import create_vehicle, update_vehicle
    created = create_vehicle(VehicleCreate(registration_number="BN47449", vehicle_number="52"),
                              current_user=_admin(), db=db)
    updated = update_vehicle(created.id, VehicleUpdate(description="Ny beskrivelse"),
                              current_user=_admin(), db=db)
    assert updated.description == "Ny beskrivelse"


def test_vehicle_response_includes_fast_bil_employee_name(db, employee):
    from routers.vehicles import create_vehicle, list_vehicles
    created = create_vehicle(VehicleCreate(registration_number="BN47449", vehicle_number="52"),
                              current_user=_admin(), db=db)
    listed = list_vehicles(current_user=_admin(), db=db)
    assert listed[0].fast_bil_employee_name is None

    employee.fast_bil = True
    employee.fast_bil_vehicle_id = created.id
    db.commit()
    listed_after = list_vehicles(current_user=_admin(), db=db)
    assert listed_after[0].fast_bil_employee_name == employee.name
