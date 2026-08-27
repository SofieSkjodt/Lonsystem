import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from database.models import SystemSettings
from calculators.baseline_updater import is_auto_approval_enabled
from conftest import set_auto_approval_enabled


def test_system_settings_model_exists():
    assert hasattr(SystemSettings, 'auto_approval_enabled')
    assert hasattr(SystemSettings, 'updated_by')
    assert hasattr(SystemSettings, 'updated_at')


def test_is_auto_approval_enabled_defaults_true_without_row(db):
    assert db.query(SystemSettings).count() == 0
    assert is_auto_approval_enabled(db) is True


def test_is_auto_approval_enabled_reflects_row_value(db):
    set_auto_approval_enabled(db, False)
    assert is_auto_approval_enabled(db) is False
    set_auto_approval_enabled(db, True)
    assert is_auto_approval_enabled(db) is True


from sqlalchemy.orm import sessionmaker


def test_all_permissions_includes_manage_auto_approval():
    from auth import ALL_PERMISSIONS
    assert "manage_auto_approval" in ALL_PERMISSIONS
    assert ALL_PERMISSIONS["manage_auto_approval"] == "Slå auto-godkendelse til/fra"


def test_seed_roles_grants_manage_auto_approval_to_admin_only(db, monkeypatch):
    import database.session as session_module
    from database.models import Role

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    assert db.query(Role).count() == 0

    session_module._seed_roles()

    admin = db.query(Role).filter(Role.name == "admin").first()
    assert "manage_auto_approval" in admin.permissions

    lonbogholder = db.query(Role).filter(Role.name == "lonbogholder").first()
    assert "manage_auto_approval" not in lonbogholder.permissions

    disponent = db.query(Role).filter(Role.name == "disponent").first()
    assert "manage_auto_approval" not in disponent.permissions


def test_ensure_manage_auto_approval_permission_is_idempotent(db, monkeypatch):
    import database.session as session_module
    from database.models import Role

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.commit()

    session_module._ensure_manage_auto_approval_permission()
    admin = db.query(Role).filter(Role.name == "admin").first()
    db.refresh(admin)
    assert "manage_auto_approval" in admin.permissions

    session_module._ensure_manage_auto_approval_permission()
    db.refresh(admin)
    assert admin.permissions.count("manage_auto_approval") == 1


def test_ensure_system_settings_creates_default_row_and_is_idempotent(db, monkeypatch):
    import database.session as session_module
    from database.models import SystemSettings

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    assert db.query(SystemSettings).count() == 0

    session_module._ensure_system_settings()
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    assert settings is not None
    assert settings.auto_approval_enabled is True

    session_module._ensure_system_settings()
    assert db.query(SystemSettings).count() == 1
