import logging
from datetime import date

import pytest
from fastapi import HTTPException


def test_send_timeseddel_logs_full_error_and_returns_generic_message(db, employee, monkeypatch, caplog):
    from routers.timeseddel_router import send_timeseddel
    from calculators.pay_period import get_or_create_period_for_date
    import utils.email_sender as email_sender

    employee.email = "chauffoer@example.com"
    db.commit()

    period = get_or_create_period_for_date(date(2026, 1, 5), db)

    def _boom(**kwargs):
        raise RuntimeError("535 5.7.3 Authentication unsuccessful")

    monkeypatch.setattr(email_sender, "send_timeseddel", _boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as exc_info:
            send_timeseddel(
                employee_id=employee.id,
                period_start=period.start_date.isoformat(),
                db=db,
                current_user=None,
            )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Mailen kunne ikke sendes – kontakt administrator"
    assert "Authentication unsuccessful" not in exc_info.value.detail
    assert "Authentication unsuccessful" in caplog.text
    assert employee.name in caplog.text


def test_send_all_timesedler_logs_full_error_and_returns_generic_failed_entry(db, employee, monkeypatch, caplog):
    from routers.timeseddel_router import send_all_timesedler, SendAllRequest
    from calculators.pay_period import get_or_create_period_for_date
    from conftest import make_activity
    from database.models import ActivityStatus
    from datetime import datetime
    import utils.email_sender as email_sender

    employee.email = "chauffoer@example.com"
    db.commit()

    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    make_activity(
        db, employee,
        datetime.combine(period.start_date, datetime.min.time()).replace(hour=8),
        datetime.combine(period.start_date, datetime.min.time()).replace(hour=16),
        status=ActivityStatus.approved,
    )

    def _boom(**kwargs):
        raise RuntimeError("535 5.7.3 Authentication unsuccessful")

    monkeypatch.setattr(email_sender, "send_timeseddel", _boom)

    with caplog.at_level(logging.ERROR):
        result = send_all_timesedler(
            SendAllRequest(from_date=period.start_date, to_date=period.end_date, employee_id=employee.id),
            db=db,
            current_user=None,
        )

    assert result["failed"] == [{"name": employee.name, "error": "Kunne ikke sendes"}]
    assert "Authentication unsuccessful" in caplog.text
    assert employee.name in caplog.text
