import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from database.models import AppUser, SystemSettings


def _user(role="admin", initials="ADM"):
    return AppUser(name="Test", initials=initials, role=role, password_hash="x")


def test_get_settings_defaults_to_enabled_without_row(db):
    from routers.auto_approval_router import get_auto_approval_settings
    result = get_auto_approval_settings(current_user=_user(), db=db)
    assert result == {"enabled": True}


def test_post_settings_creates_row_and_updates_it(db):
    from routers.auto_approval_router import set_auto_approval_settings, AutoApprovalSettingsBody

    result = set_auto_approval_settings(AutoApprovalSettingsBody(enabled=False), current_user=_user(), db=db)
    assert result == {"enabled": False}

    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    assert settings.auto_approval_enabled is False
    assert settings.updated_by == "ADM"
    assert settings.updated_at is not None


def test_get_settings_reflects_change_after_post(db):
    from routers.auto_approval_router import (
        set_auto_approval_settings, get_auto_approval_settings, AutoApprovalSettingsBody,
    )
    set_auto_approval_settings(AutoApprovalSettingsBody(enabled=False), current_user=_user(), db=db)
    result = get_auto_approval_settings(current_user=_user(), db=db)
    assert result == {"enabled": False}


def test_post_settings_toggles_existing_row_back_to_true(db):
    from routers.auto_approval_router import set_auto_approval_settings, AutoApprovalSettingsBody

    set_auto_approval_settings(AutoApprovalSettingsBody(enabled=False), current_user=_user(), db=db)
    result = set_auto_approval_settings(AutoApprovalSettingsBody(enabled=True), current_user=_user(), db=db)
    assert result == {"enabled": True}
    assert db.query(SystemSettings).count() == 1
