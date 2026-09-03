import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from database.models import AppUser


def _seed_user(db, name="Administrator", initials="admin", role="admin"):
    user = AppUser(name=name, initials=initials, role=role, password_hash="x", active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_admin_can_change_own_password_when_stored_initials_differ_in_case(db):
    """Reproducerer bug: adminbrugeren er seedet med initialer 'admin' (små bogstaver),
    men frontenden sender altid initialer i store bogstaver. update_user's duplikat-tjek
    matchede tidligere brugerens EGEN række via case-insensitive ilike, så alle
    opdateringer (inkl. adgangskode) blev afvist med 'Initialer er allerede i brug'."""
    from routers.users import update_user, UserUpdate

    admin = _seed_user(db)
    old_hash = admin.password_hash

    result = update_user(
        admin.id,
        UserUpdate(name="Administrator", initials="ADMIN", email="", role="admin", password="nytkodeord"),
        current_user=admin,
        db=db,
    )

    assert result["initials"] == "ADMIN"
    db.refresh(admin)
    assert admin.password_hash != old_hash


def test_update_user_still_rejects_duplicate_initials_from_another_user(db):
    from routers.users import update_user, UserUpdate
    from fastapi import HTTPException

    admin = _seed_user(db, name="Administrator", initials="ADMIN", role="admin")
    other = _seed_user(db, name="Anden Bruger", initials="OTH", role="lonbogholder")

    try:
        update_user(
            other.id,
            UserUpdate(initials="ADMIN"),
            current_user=admin,
            db=db,
        )
        assert False, "Skulle have kastet HTTPException"
    except HTTPException as e:
        assert e.status_code == 400
