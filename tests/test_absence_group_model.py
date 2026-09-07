import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

from database.models import Activity, ActivityStatus


def test_activity_can_be_created_and_queried_with_absence_group_id(db, employee):
    from conftest import make_activity
    a1 = make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                       activity_type="ferie", status=ActivityStatus.approved)
    a1.absence_group_id = "grp-1"
    a2 = make_activity(db, employee, datetime(2026, 1, 6, 6, 0), datetime(2026, 1, 6, 14, 0),
                       activity_type="ferie", status=ActivityStatus.approved)
    a2.absence_group_id = "grp-1"
    db.commit()

    rows = db.query(Activity).filter(Activity.absence_group_id == "grp-1").order_by(Activity.start_time).all()
    assert [r.id for r in rows] == [a1.id, a2.id]


def test_activity_absence_group_id_defaults_to_none(db, employee):
    from conftest import make_activity
    a = make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0))
    assert a.absence_group_id is None
