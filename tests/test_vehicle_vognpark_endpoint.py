import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database.models import AppUser
from database.schemas import VehicleCreate, VehicleUpdate


def _admin():
    return AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")


def test_create_vehicle_with_vognpark_true(db):
    from routers.vehicles import create_vehicle
    body = VehicleCreate(registration_number="BN47449", vehicle_number="52", vognpark=True)
    resp = create_vehicle(body, current_user=_admin(), db=db)
    assert resp.vognpark is True


def test_update_vehicle_toggles_vognpark(db):
    from routers.vehicles import create_vehicle, update_vehicle
    created = create_vehicle(VehicleCreate(registration_number="BN47449", vehicle_number="52"),
                              current_user=_admin(), db=db)
    assert created.vognpark is False  # default, jf. Task 1

    updated = update_vehicle(created.id, VehicleUpdate(vognpark=True),
                              current_user=_admin(), db=db)
    assert updated.vognpark is True

    updated_again = update_vehicle(created.id, VehicleUpdate(vognpark=False),
                                    current_user=_admin(), db=db)
    assert updated_again.vognpark is False
