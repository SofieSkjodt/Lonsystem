import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database.models import Vehicle


def test_vehicle_vognpark_defaults_to_false(db):
    v = Vehicle(registration_number="BN47449", vehicle_number="52")
    db.add(v)
    db.commit()
    db.refresh(v)
    assert v.vognpark is False
