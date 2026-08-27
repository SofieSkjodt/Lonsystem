import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

from database.models import ActivitySource, ActivityStatus, AppUser, Role
from database.schemas import ActivityCreate


def _user(role="lonbogholder", initials="LB1"):
    return AppUser(name="Test", initials=initials, role=role, password_hash="x")


def _grant(db, role_name, permissions, is_system=False):
    db.add(Role(name=role_name, display_name=role_name, is_system=is_system, permissions=permissions))
    db.commit()


def test_permission_holder_long_activity_is_approved(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),  # 8 timer
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.approved_by == "LB1"
    assert resp.comment is None


def test_permission_holder_short_activity_without_comment_gets_initials(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.comment == "LB1"


def test_permission_holder_short_activity_with_own_comment_is_preserved(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer
        comment="Kørt ærinde for kontoret",
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.comment == "Kørt ærinde for kontoret"


def test_permission_holder_short_activity_reaching_4h_with_other_approved_skips_fallback(db, employee):
    from routers.activities import create_manual_activity
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import Activity

    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    period = get_or_create_period_for_date(datetime(2026, 1, 5).date(), db)
    db.add(Activity(
        employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.manual,
        activity_type="normal", start_time=datetime(2026, 1, 5, 6, 0), end_time=datetime(2026, 1, 5, 8, 0),
        status=ActivityStatus.approved, pause_intervals=[], segments=[],
    ))
    db.commit()

    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 8, 0),
        end_time=datetime(2026, 1, 5, 10, 0),  # yderligere 2 timer = 4 timer samlet denne dag
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.comment is None


def test_no_permission_normal_activity_stays_pending(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "disponent", [])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer
    )
    resp = create_manual_activity(body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert resp.status == ActivityStatus.pending
    assert resp.approved_by is None
    assert resp.comment is None


def test_no_permission_absence_type_still_approved_without_comment_fallback(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "disponent", [])
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="ferie",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer, under 4h
    )
    resp = create_manual_activity(body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert resp.status == ActivityStatus.approved  # uændret eksisterende adfærd for fraværstyper
    assert resp.comment is None  # men INGEN kommentar-fallback uden permission


def test_system_role_admin_auto_approves_without_explicit_permission(db, employee):
    from routers.activities import create_manual_activity
    _grant(db, "admin", [], is_system=True)
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),  # 2 timer
    )
    resp = create_manual_activity(body, current_user=_user(role="admin", initials="ADM"), db=db)
    assert resp.status == ActivityStatus.approved
    assert resp.comment == "ADM"


def test_permission_holder_normal_activity_stays_pending_when_globally_disabled(db, employee):
    from routers.activities import create_manual_activity
    from conftest import set_auto_approval_enabled

    _grant(db, "lonbogholder", ["auto_approve_manual_activities"])
    set_auto_approval_enabled(db, False)
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),  # 8 timer
    )
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.status == ActivityStatus.pending
    assert resp.approved_by is None
    assert resp.comment is None


def test_disponent_absence_type_still_approved_when_globally_disabled(db, employee):
    from routers.activities import create_manual_activity
    from conftest import set_auto_approval_enabled

    _grant(db, "disponent", [])
    set_auto_approval_enabled(db, False)
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="ferie",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 8, 0),
    )
    resp = create_manual_activity(body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert resp.status == ActivityStatus.approved  # fraværstyper uændret, jf. spec
