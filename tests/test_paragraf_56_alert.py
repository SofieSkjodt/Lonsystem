import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException

from database.models import AppUser, MasterAgreementType, MasterAgreementKind, Paragraf56AlertDismissal
from database.schemas import EmployeeUpdate, Paragraf56AlertDismiss


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _make_user(db, initials="USR1"):
    user = AppUser(name="Bruger", initials=initials, role="lonbogholder", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_agreement(db):
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.commit()


def test_sweep_deactivates_expired_paragraf_56(db, employee):
    from routers.employees import _sweep_expired_paragraf_56
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date(2026, 1, 1)
    employee.paragraf_56_end_date = date.today() - timedelta(days=1)
    db.commit()

    _sweep_expired_paragraf_56(db)
    db.refresh(employee)

    assert employee.paragraf_56 is False
    assert employee.paragraf_56_end_date == date.today() - timedelta(days=1)


def test_sweep_leaves_future_end_date_untouched(db, employee):
    from routers.employees import _sweep_expired_paragraf_56
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date.today()
    employee.paragraf_56_end_date = date.today() + timedelta(days=10)
    db.commit()

    _sweep_expired_paragraf_56(db)
    db.refresh(employee)

    assert employee.paragraf_56 is True


def test_list_employees_triggers_sweep(db, employee):
    from routers.employees import list_employees
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date(2026, 1, 1)
    employee.paragraf_56_end_date = date.today() - timedelta(days=1)
    db.commit()

    list_employees(active_only=False, current_user=_dummy_user(), db=db)
    db.refresh(employee)

    assert employee.paragraf_56 is False


def test_paragraf56_alerts_categorizes_upcoming(db, employee):
    from routers.employees import paragraf56_alerts
    user = _make_user(db)
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date.today()
    employee.paragraf_56_end_date = date.today() + timedelta(days=10)
    db.commit()

    result = paragraf56_alerts(current_user=user, db=db)

    assert len(result.upcoming) == 1
    assert result.upcoming[0].employee_id == employee.id
    assert len(result.expired) == 0


def test_paragraf56_alerts_categorizes_expired(db, employee):
    from routers.employees import paragraf56_alerts
    user = _make_user(db)
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date(2026, 1, 1)
    employee.paragraf_56_end_date = date.today() - timedelta(days=1)
    db.commit()

    result = paragraf56_alerts(current_user=user, db=db)

    assert len(result.expired) == 1
    assert result.expired[0].employee_id == employee.id
    assert len(result.upcoming) == 0


def test_paragraf56_alerts_ignores_employee_without_paragraf_56(db, employee):
    from routers.employees import paragraf56_alerts
    user = _make_user(db)

    result = paragraf56_alerts(current_user=user, db=db)

    assert result.upcoming == []
    assert result.expired == []


def test_paragraf56_alerts_excludes_outside_30_day_window(db, employee):
    from routers.employees import paragraf56_alerts
    user = _make_user(db)
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date.today()
    employee.paragraf_56_end_date = date.today() + timedelta(days=45)
    db.commit()

    result = paragraf56_alerts(current_user=user, db=db)

    assert result.upcoming == []


def test_dismiss_paragraf56_alert_is_per_user(db, employee):
    from routers.employees import paragraf56_alerts, dismiss_paragraf56_alert
    user_a = _make_user(db, "USRA")
    user_b = _make_user(db, "USRB")
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date.today()
    employee.paragraf_56_end_date = date.today() + timedelta(days=10)
    db.commit()

    dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="upcoming"), current_user=user_a, db=db)

    result_a = paragraf56_alerts(current_user=user_a, db=db)
    result_b = paragraf56_alerts(current_user=user_b, db=db)

    assert result_a.upcoming == []
    assert len(result_b.upcoming) == 1


def test_dismiss_paragraf56_alert_is_idempotent(db, employee):
    from routers.employees import dismiss_paragraf56_alert
    user = _make_user(db)

    dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="expired"), current_user=user, db=db)
    dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="expired"), current_user=user, db=db)

    count = db.query(Paragraf56AlertDismissal).filter(
        Paragraf56AlertDismissal.employee_id == employee.id,
        Paragraf56AlertDismissal.user_id == user.id,
    ).count()
    assert count == 1


def test_dismiss_paragraf56_alert_rejects_unknown_alert_type(db, employee):
    from routers.employees import dismiss_paragraf56_alert
    user = _make_user(db)

    with pytest.raises(HTTPException) as exc:
        dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="whatever"), current_user=user, db=db)
    assert exc.value.status_code == 400


def test_update_employee_clears_dismissals_when_end_date_changes(db, employee):
    from routers.employees import update_employee, dismiss_paragraf56_alert
    _seed_agreement(db)
    user = _make_user(db)
    employee.paragraf_56 = True
    employee.paragraf_56_start_date = date(2026, 1, 1)
    employee.paragraf_56_end_date = date(2026, 6, 1)
    db.commit()

    dismiss_paragraf56_alert(employee.id, Paragraf56AlertDismiss(alert_type="upcoming"), current_user=user, db=db)
    assert db.query(Paragraf56AlertDismissal).filter(Paragraf56AlertDismissal.employee_id == employee.id).count() == 1

    update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 1, 1), paragraf_56_end_date=date(2026, 8, 1)),
        current_user=_dummy_user(), db=db,
    )

    assert db.query(Paragraf56AlertDismissal).filter(Paragraf56AlertDismissal.employee_id == employee.id).count() == 0
