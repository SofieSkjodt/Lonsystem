from database.models import DispatcherGroup


def test_new_dispatcher_group_defaults_to_visible(db):
    group = DispatcherGroup(name="Testgruppe")
    db.add(group)
    db.commit()
    db.refresh(group)
    assert group.visible_in_activity_overview is True
