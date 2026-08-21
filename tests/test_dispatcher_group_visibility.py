from database.models import AppUser, DispatcherGroup
from database.schemas import DispatcherGroupResponse
from routers.stamdata import (
    DispatcherGroupBody,
    create_dispatcher_group,
    update_dispatcher_group,
    _dispatcher_group_row,
)


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_new_dispatcher_group_defaults_to_visible(db):
    group = DispatcherGroup(name="Testgruppe")
    db.add(group)
    db.commit()
    db.refresh(group)
    assert group.visible_in_activity_overview is True


def test_dispatcher_group_response_includes_visibility_field(db):
    group = DispatcherGroup(name="Testgruppe 2", visible_in_activity_overview=False)
    db.add(group)
    db.commit()
    db.refresh(group)

    response = DispatcherGroupResponse.model_validate(group)

    assert response.visible_in_activity_overview is False


def test_create_dispatcher_group_defaults_to_visible(db):
    body = DispatcherGroupBody(name="Ny gruppe")
    result = create_dispatcher_group(body, current_user=_dummy_user(), db=db)
    assert result["visible_in_activity_overview"] is True


def test_create_dispatcher_group_can_be_created_hidden(db):
    body = DispatcherGroupBody(name="Skjult gruppe", visible_in_activity_overview=False)
    result = create_dispatcher_group(body, current_user=_dummy_user(), db=db)
    assert result["visible_in_activity_overview"] is False


def test_update_dispatcher_group_can_toggle_visibility(db):
    created = create_dispatcher_group(
        DispatcherGroupBody(name="Skal skjules"), current_user=_dummy_user(), db=db
    )
    updated = update_dispatcher_group(
        created["id"],
        DispatcherGroupBody(visible_in_activity_overview=False),
        current_user=_dummy_user(),
        db=db,
    )
    assert updated["visible_in_activity_overview"] is False


def test_dispatcher_group_row_includes_visibility_key(db):
    created = create_dispatcher_group(
        DispatcherGroupBody(name="Rå række"), current_user=_dummy_user(), db=db
    )
    assert "visible_in_activity_overview" in created
