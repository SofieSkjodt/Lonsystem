from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import log_action, require_permission
from database.models import AppUser, Employee, EmployeeSupplement
from database.schemas import EmployeeSupplementCreate, EmployeeSupplementResponse
from database.session import get_db

router = APIRouter(prefix="/api/employee-supplements", tags=["employee-supplements"])

_supplements_access = require_permission("manage_employee_supplements")

_OPEN_ENDED = date(9999, 12, 31)


def get_active_supplement_for_period(
    db: Session, employee_id: int, period_start: date, period_end: date
) -> Optional[EmployeeSupplement]:
    """Finder tillægget hvis gyldighedsperiode overlapper [period_start, period_end].
    Overlapper flere rækker (nyt tillæg oprettet midt i perioden), vinder den
    med nyeste start_date, for hele perioden."""
    return (
        db.query(EmployeeSupplement)
        .filter(
            EmployeeSupplement.employee_id == employee_id,
            EmployeeSupplement.end_date >= period_start,
            EmployeeSupplement.start_date <= period_end,
        )
        .order_by(EmployeeSupplement.start_date.desc())
        .first()
    )


def _create_supplement(db: Session, employee_id: int, start_date: date, value: Decimal) -> EmployeeSupplement:
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
    db.commit()
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
    q = db.query(EmployeeSupplement)
    if employee_id is not None:
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
    log_action(db, current_user, "Oprettede medarbejdertillæg", "employee_supplement", row.id,
               f"{row.value} kr/t fra {row.start_date.isoformat()}")
    db.commit()
    return _to_response(row)
