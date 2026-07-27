import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, require_permission
from calculators.rates_loader import (
    load_agreement_types_from_db,
    seniority_variant_exists_from_db,
)
from database.session import get_db
from database.models import AppUser, DispatcherGroup, Employee
from database.schemas import (
    AnciennitetsAlert,
    DispatcherGroupResponse,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
    WorkSchedule,
)

router = APIRouter(prefix="/api/employees", tags=["employees"])


def _months_employed(hire_date: date, today: date = None) -> int:
    if today is None:
        today = date.today()
    months = (today.year - hire_date.year) * 12 + (today.month - hire_date.month)
    if today.day < hire_date.day:
        months -= 1
    return max(0, months)


def _to_response(emp: Employee, db) -> EmployeeResponse:
    try:
        rate = float(load_agreement_types_from_db(db).get(emp.agreement_type, 0)) or None
    except Exception:
        rate = None
    return EmployeeResponse(
        id=emp.id,
        employee_number=emp.employee_number,
        tachograph_card_number=emp.tachograph_card_number,
        first_name=emp.first_name,
        last_name=emp.last_name,
        name=emp.name,
        address=emp.address,
        postal_code=emp.postal_code,
        email=emp.email,
        phone=emp.phone,
        mobile=emp.mobile,
        agreement_kind=emp.agreement_kind,
        agreement_type=emp.agreement_type,
        hourly_rate=rate,
        fuldloennet=emp.fuldloennet,
        active=emp.active,
        hire_date=emp.hire_date,
        termination_date=emp.termination_date,
        work_schedule=WorkSchedule(**emp.work_schedule),
        months_employed=_months_employed(emp.hire_date),
        dispatcher_groups=[DispatcherGroupResponse.model_validate(g) for g in emp.dispatcher_groups],
        cvr_number=emp.cvr_number,
        anciennitet_dismissed_at=emp.anciennitet_dismissed_at,
    )


@router.get("", response_model=list[EmployeeResponse])
def list_employees(active_only: bool = True,
                   current_user: AppUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    q = db.query(Employee)
    if active_only:
        q = q.filter(Employee.active == True)
    return [_to_response(e, db) for e in q.order_by(Employee.last_name, Employee.first_name).all()]


@router.get("/agreement-types")
def agreement_types(current_user: AppUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Overenskomsttyper og timesatser fra stamdata-tabellen."""
    try:
        types = load_agreement_types_from_db(db)
    except Exception as e:
        logging.error(f"Overenskomsttyper kunne ikke indlæses: {e}")
        raise HTTPException(500, "Overenskomsttyper kunne ikke indlæses – kontakt administrator")
    return [{"name": k, "hourly_rate": float(v)} for k, v in types.items()]


@router.get("/dispatcher-groups", response_model=list[DispatcherGroupResponse])
def dispatcher_groups(current_user: AppUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Liste over disponentgrupper – bruges til at udfylde medarbejder-modalens afkrydsningsliste."""
    return db.query(DispatcherGroup).order_by(DispatcherGroup.name).all()


def _resolve_dispatcher_groups(db: Session, ids: list[int]) -> list[DispatcherGroup]:
    if not ids:
        return []
    groups = db.query(DispatcherGroup).filter(DispatcherGroup.id.in_(ids)).all()
    found_ids = {g.id for g in groups}
    missing = set(ids) - found_ids
    if missing:
        raise HTTPException(400, f"Ukendt disponentgruppe-id: {', '.join(str(i) for i in sorted(missing))}")
    return groups


@router.post("", response_model=EmployeeResponse, status_code=201)
def create_employee(body: EmployeeCreate,
                    current_user: AppUser = Depends(require_permission("manage_employees")),
                    db: Session = Depends(get_db)):
    if db.query(Employee).filter(Employee.employee_number == body.employee_number).first():
        raise HTTPException(400, "Lønnummer eksisterer allerede")
    if body.tachograph_card_number:
        if db.query(Employee).filter(Employee.tachograph_card_number == body.tachograph_card_number).first():
            raise HTTPException(400, "Førerkortnummer eksisterer allerede")
    if body.agreement_type not in load_agreement_types_from_db(db):
        raise HTTPException(400, f"Ukendt overenskomsttype: {body.agreement_type}")

    data = body.model_dump(exclude={"dispatcher_group_ids"})
    data["work_schedule"] = body.work_schedule.model_dump()
    emp = Employee(**data)
    emp.dispatcher_groups = _resolve_dispatcher_groups(db, body.dispatcher_group_ids)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _to_response(emp, db)


@router.get("/anciennitet-alerts", response_model=list[AnciennitetsAlert])
def anciennitet_alerts(current_user: AppUser = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """
    Medarbejdere der har opnået 9 måneders anciennitet, men hvor
    overenskomsttypen har en 9-mdr-variant, de endnu ikke er flyttet til.
    Springer medarbejdere over, hvor advarslen er afvist server-side.
    """
    alerts = []
    employees = db.query(Employee).filter(Employee.active == True).all()
    for emp in employees:
        months = _months_employed(emp.hire_date)
        if months < 9:
            continue
        if emp.anciennitet_dismissed_at is not None:
            continue
        variant = seniority_variant_exists_from_db(db, emp.agreement_type)
        if variant:
            alerts.append(AnciennitetsAlert(
                employee_id=emp.id,
                employee_name=emp.name,
                employee_number=emp.employee_number,
                hire_date=emp.hire_date,
                months_employed=months,
                suggested_agreement_type=variant,
            ))
    return alerts


@router.post("/{employee_id}/dismiss-anciennitet", status_code=204)
def dismiss_anciennitet(employee_id: int,
                        current_user: AppUser = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Marker anciennitetsadvarsel som afvist for denne medarbejder."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    emp.anciennitet_dismissed_at = datetime.utcnow()
    db.commit()


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(employee_id: int,
                 current_user: AppUser = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    return _to_response(emp, db)


@router.patch("/{employee_id}", response_model=EmployeeResponse)
def update_employee(employee_id: int, body: EmployeeUpdate,
                    current_user: AppUser = Depends(require_permission("manage_employees")),
                    db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    if body.agreement_type and body.agreement_type not in load_agreement_types_from_db(db):
        raise HTTPException(400, f"Ukendt overenskomsttype: {body.agreement_type}")
    old_agreement_type = emp.agreement_type
    for field_name, value in body.model_dump(exclude_none=True, exclude={"dispatcher_group_ids"}).items():
        if field_name == "work_schedule":
            value = body.work_schedule.model_dump()
        setattr(emp, field_name, value)
    if body.dispatcher_group_ids is not None:
        emp.dispatcher_groups = _resolve_dispatcher_groups(db, body.dispatcher_group_ids)
    # Nulstil afvist anciennitetsadvarsel hvis overenskomsttype er ændret
    if body.agreement_type and body.agreement_type != old_agreement_type:
        emp.anciennitet_dismissed_at = None
    db.commit()
    db.refresh(emp)
    return _to_response(emp, db)
