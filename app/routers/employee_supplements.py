from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from auth import log_action, require_permission
from calculators.rates_loader import get_active_supplement_for_period
from database.models import AppUser, Employee, EmployeeSupplement
from database.schemas import EmployeeSupplementCreate, EmployeeSupplementResponse
from database.session import get_db

router = APIRouter(prefix="/api/employee-supplements", tags=["employee-supplements"])

_supplements_access = require_permission("manage_employee_supplements")

_OPEN_ENDED = date(9999, 12, 31)


def _create_supplement(db: Session, employee_id: int, start_date: date, value: Decimal) -> EmployeeSupplement:
    value = value.quantize(Decimal("0.01"))
    if value <= 0:
        raise HTTPException(400, "Værdien skal være et positivt beløb")
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    open_row = (
        db.query(EmployeeSupplement)
        .filter(EmployeeSupplement.employee_id == employee_id, EmployeeSupplement.end_date == _OPEN_ENDED)
        .first()
    )
    if open_row and start_date <= open_row.start_date:
        raise HTTPException(400, f"Startdato skal være efter {open_row.start_date.isoformat()}")
    if open_row:
        open_row.end_date = start_date - timedelta(days=1)
    new_row = EmployeeSupplement(employee_id=employee_id, start_date=start_date, value=value)
    db.add(new_row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Der skete en samtidig ændring for denne medarbejder — prøv igen")
    db.refresh(new_row)
    return new_row


def _to_response(row: EmployeeSupplement) -> EmployeeSupplementResponse:
    today = date.today()
    return EmployeeSupplementResponse(
        id=row.id,
        employee_id=row.employee_id,
        employee_number=row.employee.employee_number,
        employee_name=row.employee.name,
        name=row.name,
        type=row.type,
        value=float(row.value),
        start_date=row.start_date,
        end_date=row.end_date,
        is_active=row.start_date <= today <= row.end_date,
    )


@router.get("", response_model=list[EmployeeSupplementResponse])
def list_supplements(
    employee_id: Optional[int] = None,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    q = db.query(EmployeeSupplement).options(joinedload(EmployeeSupplement.employee))
    if employee_id is not None:
        if not db.query(Employee).filter(Employee.id == employee_id).first():
            raise HTTPException(404, "Medarbejder ikke fundet")
        q = q.filter(EmployeeSupplement.employee_id == employee_id)
    if date_from is not None:
        q = q.filter(EmployeeSupplement.end_date >= date_from)
    if date_to is not None:
        q = q.filter(EmployeeSupplement.start_date <= date_to)
    rows = q.order_by(EmployeeSupplement.start_date.desc()).all()
    return [_to_response(r) for r in rows]


@router.get("/active/{employee_id}", response_model=Optional[EmployeeSupplementResponse])
def get_active_supplement(
    employee_id: int,
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    if not db.query(Employee).filter(Employee.id == employee_id).first():
        raise HTTPException(404, "Medarbejder ikke fundet")
    today = date.today()
    row = get_active_supplement_for_period(db, employee_id, today, today)
    return _to_response(row) if row else None


@router.post("", response_model=EmployeeSupplementResponse, status_code=201)
def create_supplement(
    body: EmployeeSupplementCreate,
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    row = _create_supplement(db, body.employee_id, body.start_date, Decimal(str(body.value)))
    log_action(db, current_user, "employee_supplement_create", "employee_supplement", row.id,
               f"{row.value} kr/t fra {row.start_date.isoformat()}")
    db.commit()
    return _to_response(row)


@router.post("/{supplement_id}/end", response_model=EmployeeSupplementResponse)
def end_supplement(
    supplement_id: int,
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    row = db.query(EmployeeSupplement).filter(EmployeeSupplement.id == supplement_id).first()
    if not row:
        raise HTTPException(404, "Tillæg ikke fundet")
    today = date.today()
    if row.end_date != _OPEN_ENDED or not (row.start_date <= today <= row.end_date):
        raise HTTPException(400, "Kun det aktuelt aktive tillæg kan afsluttes")
    from calculators.pay_period import get_or_create_period_for_date
    current_period = get_or_create_period_for_date(today, db)
    row.end_date = current_period.end_date
    db.commit()
    log_action(db, current_user, "employee_supplement_end", "employee_supplement", row.id,
               f"Afsluttet, sidste gyldige dag {current_period.end_date.isoformat()}")
    db.commit()
    db.refresh(row)
    return _to_response(row)
