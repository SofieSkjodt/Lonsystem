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


from database.models import Vehicle


def _make_vehicle(db, reg="AB12345", num="99"):
    v = Vehicle(registration_number=reg, vehicle_number=num)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_create_dispatcher_group_with_vehicle(db):
    vehicle = _make_vehicle(db)
    result = create_dispatcher_group(
        DispatcherGroupBody(name="Med vogn", vehicle_id=vehicle.id),
        current_user=_dummy_user(), db=db,
    )
    assert result["vehicle_id"] == vehicle.id
    assert result["vehicle_number"] == "99"


def test_create_dispatcher_group_rejects_unknown_vehicle(db):
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        create_dispatcher_group(
            DispatcherGroupBody(name="Ukendt vogn", vehicle_id=999999),
            current_user=_dummy_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_update_dispatcher_group_can_set_and_clear_vehicle(db):
    vehicle = _make_vehicle(db)
    created = create_dispatcher_group(DispatcherGroupBody(name="Skal have vogn"), current_user=_dummy_user(), db=db)
    assert created["vehicle_id"] is None

    updated = update_dispatcher_group(
        created["id"], DispatcherGroupBody(vehicle_id=vehicle.id), current_user=_dummy_user(), db=db,
    )
    assert updated["vehicle_id"] == vehicle.id

    cleared = update_dispatcher_group(
        created["id"], DispatcherGroupBody(vehicle_id=None), current_user=_dummy_user(), db=db,
    )
    assert cleared["vehicle_id"] is None


def test_update_dispatcher_group_without_vehicle_field_leaves_it_unchanged(db):
    vehicle = _make_vehicle(db)
    created = create_dispatcher_group(
        DispatcherGroupBody(name="Uændret vogn", vehicle_id=vehicle.id), current_user=_dummy_user(), db=db,
    )
    updated = update_dispatcher_group(
        created["id"], DispatcherGroupBody(description="Ny beskrivelse"), current_user=_dummy_user(), db=db,
    )
    assert updated["vehicle_id"] == vehicle.id
