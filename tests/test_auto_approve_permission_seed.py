import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from sqlalchemy.orm import sessionmaker


def test_all_permissions_includes_auto_approve_manual_activities():
    from auth import ALL_PERMISSIONS
    assert "auto_approve_manual_activities" in ALL_PERMISSIONS
    assert ALL_PERMISSIONS["auto_approve_manual_activities"] == "Auto-godkend ved oprettelse"


def test_seed_roles_grants_permission_to_lonbogholder_not_disponent(db, monkeypatch):
    import database.session as session_module
    from database.models import Role

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    assert db.query(Role).count() == 0

    session_module._seed_roles()

    lonbogholder = db.query(Role).filter(Role.name == "lonbogholder").first()
    assert "auto_approve_manual_activities" in lonbogholder.permissions

    disponent = db.query(Role).filter(Role.name == "disponent").first()
    assert "auto_approve_manual_activities" not in disponent.permissions


def test_ensure_auto_approve_permission_adds_to_lonbogholder_and_is_idempotent(db, monkeypatch):
    import database.session as session_module
    from database.models import Role

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False, permissions=["payroll"]))
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()

    session_module._ensure_auto_approve_permission()

    lonbogholder = db.query(Role).filter(Role.name == "lonbogholder").first()
    db.refresh(lonbogholder)
    assert "auto_approve_manual_activities" in lonbogholder.permissions

    disponent = db.query(Role).filter(Role.name == "disponent").first()
    db.refresh(disponent)
    assert "auto_approve_manual_activities" not in disponent.permissions

    # Idempotent — kør igen, ingen dubletter
    session_module._ensure_auto_approve_permission()
    db.refresh(lonbogholder)
    assert lonbogholder.permissions.count("auto_approve_manual_activities") == 1
