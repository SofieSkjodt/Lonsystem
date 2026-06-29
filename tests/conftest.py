import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date

from database.models import Base, Employee, Activity, ActivitySource, ActivityStatus, AgreementKind
from calculators.pay_period import get_or_create_period_for_date


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def employee(db):
    emp = Employee(
        employee_number="1001",
        first_name="Test",
        last_name="Chauffør",
        agreement_kind=AgreementKind.hourly_fixed,
        agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def make_activity(db, employee, start: datetime, end: datetime,
                  activity_type="normal", source=ActivitySource.tachograph,
                  salt_supplement=False, status=ActivityStatus.pending):
    period = get_or_create_period_for_date(start.date(), db)
    act = Activity(
        employee_id=employee.id,
        pay_period_id=period.id,
        source=source,
        activity_type=activity_type,
        start_time=start,
        end_time=end,
        salt_supplement=salt_supplement,
        status=status,
        pause_intervals=[],
        segments=[],
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act
