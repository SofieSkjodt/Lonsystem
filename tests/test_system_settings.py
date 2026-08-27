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
