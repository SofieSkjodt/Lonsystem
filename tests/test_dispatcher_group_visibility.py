from database.models import DispatcherGroup
from database.schemas import DispatcherGroupResponse


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
