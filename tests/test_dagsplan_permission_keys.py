import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from auth import ALL_PERMISSIONS


def test_dagsplan_permissions_registered():
    assert "dagsplan_view" in ALL_PERMISSIONS
    assert "dagsplan_edit" in ALL_PERMISSIONS
