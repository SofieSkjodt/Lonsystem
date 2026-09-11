from datetime import date as date_type, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import log_action, require_permission
from calculators.dagsplan_helpers import effective_vehicle_for_employee
from database.models import (
    Activity, ActivityStatus, AppUser, DailyPlanAssignment, DailyPlanExtraAssignment, Employee,
    MasterAbsenceType, VagtplanComment, Vehicle, VehicleAbsence,
)
from database.schemas import (
    DagsplanEmployeeRow, DagsplanExtraRow, DagsplanResponse, DagsplanVehicleRow,
    DailyPlanAssignmentUpsert, DailyPlanExtraAssignmentUpsert, VehicleAbsenceCreate, VehicleAbsenceResponse,
)
from database.session import get_db

router = APIRouter(prefix="/api/dagsplan", tags=["dagsplan"])
vehicle_absence_router = APIRouter(prefix="/api/vehicle-absences", tags=["vehicle-absences"])


def _absent_vehicle_ids(db: Session, d: date_type) -> set[int]:
    rows = db.query(VehicleAbsence.vehicle_id).filter(
        VehicleAbsence.date_from <= d,
        or_(VehicleAbsence.date_to.is_(None), VehicleAbsence.date_to >= d),
    ).all()
    return {r[0] for r in rows}


def _mismatch_vehicle_number(db: Session, employee_id: int, d: date_type, assigned_vehicle_number: str) -> Optional[str]:
    day_start = datetime.combine(d, time.min)
    day_end = day_start + timedelta(days=1)
    acts = db.query(Activity).filter(
        Activity.employee_id == employee_id,
        Activity.activity_type == "normal",
        Activity.start_time >= day_start,
        Activity.start_time < day_end,
    ).all()
    for a in acts:
        if a.vehicle_number and a.vehicle_number != assigned_vehicle_number:
            return a.vehicle_number
    return None


def _build_vehicle_rows(db: Session, d: date_type) -> list[DagsplanVehicleRow]:
    """Effektiv chauffør-tildeling pr. vogn: gemt tildeling vinder, ellers
    'Fast bil'-fallback - samme regel som effective_vehicle_for_employee(),
    blot indekseret pr. vogn i stedet for pr. medarbejder (én forespørgsel
    i stedet for én pr. medarbejder)."""
    absent_ids = _absent_vehicle_ids(db, d)
    assignments = {
        a.vehicle_id: a for a in
        db.query(DailyPlanAssignment).filter(DailyPlanAssignment.date == d).all()
    }
    fast_bil_by_vehicle = {
        e.fast_bil_vehicle_id: e for e in
        db.query(Employee).filter(Employee.fast_bil == True, Employee.fast_bil_vehicle_id.isnot(None)).all()
    }
    rows = []
    for v in db.query(Vehicle).filter(Vehicle.vognpark == True).order_by(Vehicle.vehicle_number).all():
        a = assignments.get(v.id)
        default_emp = fast_bil_by_vehicle.get(v.id) if a is None else None
        employee = a.employee if (a and a.employee) else default_emp
        mismatch = (
            _mismatch_vehicle_number(db, employee.id, d, v.vehicle_number)
            if employee else None
        )
        rows.append(DagsplanVehicleRow(
            vehicle_id=v.id,
            vehicle_number=v.vehicle_number,
            description=v.description,
            dispatcher_group_id=v.dispatcher_group_id,
            employee_id=employee.id if employee else None,
            employee_name=employee.name if employee else None,
            task=a.task if a else None,
            informed=a.informed if a else False,
            absent=v.id in absent_ids,
            mismatch_vehicle_number=mismatch,
        ))
    return rows


def _build_extra_rows(db: Session, d: date_type) -> list[DagsplanExtraRow]:
    """De 10 faste EKSTRA-pladser (1-10) - i modsætning til vogne findes der
    intet 'Fast bil'-fallback for dem, kun en evt. gemt tildeling."""
    assignments = {
        a.slot: a for a in
        db.query(DailyPlanExtraAssignment).filter(DailyPlanExtraAssignment.date == d).all()
    }
    rows = []
    for slot in range(1, 11):
        a = assignments.get(slot)
        employee = a.employee if (a and a.employee) else None
        rows.append(DagsplanExtraRow(
            slot=slot,
            employee_id=employee.id if employee else None,
            employee_name=employee.name if employee else None,
            task=a.task if a else None,
            informed=a.informed if a else False,
        ))
    return rows


def _conflicting_assignment_label(
    db: Session, d: date_type, employee_id: int,
    exclude_vehicle_id: Optional[int] = None, exclude_slot: Optional[int] = None,
) -> Optional[str]:
    """Menneskelæsbar betegnelse ('vogn X' / 'EKSTRA Y'), hvis medarbejderen
    allerede har en anden effektiv tildeling (vogn ELLER EKSTRA-plads) samme
    dag - bruges til at advare, uanset hvor den anden tildeling stammer fra."""
    for r in _build_vehicle_rows(db, d):
        if r.employee_id == employee_id and r.vehicle_id != exclude_vehicle_id:
            return f"vogn {r.vehicle_number}"
    for r in _build_extra_rows(db, d):
        if r.employee_id == employee_id and r.slot != exclude_slot:
            return f"EKSTRA-plads {r.slot}"
    return None


def _absence_warning_message(db: Session, employee: Employee, d: date_type) -> Optional[str]:
    day_start = datetime.combine(d, time.min)
    day_end = day_start + timedelta(days=1)
    absence = db.query(Activity).filter(
        Activity.employee_id == employee.id,
        Activity.activity_type != "normal",
        Activity.status != ActivityStatus.deactivated,
        Activity.start_time < day_end,
        Activity.end_time > day_start,
    ).first()
    if not absence:
        return None
    label_row = db.query(MasterAbsenceType).filter(
        MasterAbsenceType.normalized_key == absence.activity_type
    ).first()
    label = label_row.label if label_row else absence.activity_type
    return f"{employee.name} har registreret {label}. Vil du tilføje til bilen?"


@router.get("", response_model=DagsplanResponse)
def get_dagsplan(
    date: date_type,
    dispatcher_group_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    current_user: AppUser = Depends(require_permission("dagsplan_view")),
    db: Session = Depends(get_db),
):
    all_rows = _build_vehicle_rows(db, date)
    extra_rows = _build_extra_rows(db, date)
    assigned_employee_ids = {r.employee_id for r in all_rows if r.employee_id} | \
        {r.employee_id for r in extra_rows if r.employee_id}

    visible_rows = all_rows
    if dispatcher_group_id:
        visible_rows = [r for r in visible_rows if r.dispatcher_group_id == dispatcher_group_id]
    if employee_id:
        visible_rows = [r for r in visible_rows if r.employee_id == employee_id]

    day_start = datetime.combine(date, time.min)
    day_end = day_start + timedelta(days=1)
    absence_acts = db.query(Activity).filter(
        Activity.activity_type != "normal",
        Activity.status != ActivityStatus.deactivated,
        Activity.start_time < day_end,
        Activity.end_time > day_start,
    ).all()
    absence_by_employee = {}
    for a in absence_acts:
        absence_by_employee.setdefault(a.employee_id, a)
    comment_by_employee = {
        c.employee_id: c for c in db.query(VagtplanComment).filter(VagtplanComment.date == date).all()
    }

    # Kun medarbejdere i disponentgrupper der vises i Aktivitetsoversigten -
    # samme filter som _active_employees() i payroll_router.py og
    # _empHasVisibleGroup() i app.js. Medarbejdere uden disponentgruppe
    # udelades også, i tråd med de to andre steder.
    all_active = (
        db.query(Employee).filter(Employee.active == True)
        .order_by(Employee.first_name, Employee.last_name).all()
    )
    visible_employees = [
        e for e in all_active if e.dispatcher_group and e.dispatcher_group.visible_in_activity_overview
    ]

    employee_rows = []
    for emp in visible_employees:
        comment = comment_by_employee.get(emp.id)
        absence = absence_by_employee.get(emp.id)
        assigned = emp.id in assigned_employee_ids
        if comment:
            status, absence_text = "comment_only", comment.text
        elif absence:
            status, absence_text = "absent", absence.activity_type
        elif assigned:
            status, absence_text = "assigned", None
        else:
            status, absence_text = "none", None
        employee_rows.append(DagsplanEmployeeRow(
            employee_id=emp.id, employee_name=emp.name, status=status, absence_text=absence_text,
        ))

    return DagsplanResponse(date=date, vehicles=visible_rows, employees=employee_rows, extra_rows=extra_rows)


@router.patch("/assignment", response_model=DagsplanVehicleRow)
def upsert_assignment(
    body: DailyPlanAssignmentUpsert,
    current_user: AppUser = Depends(require_permission("dagsplan_edit")),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Vogn ikke fundet")
    employee = db.query(Employee).filter(Employee.id == body.employee_id).first() if body.employee_id is not None else None
    if body.employee_id is not None and not employee:
        raise HTTPException(404, "Medarbejder ikke fundet")

    assignment = db.query(DailyPlanAssignment).filter(
        DailyPlanAssignment.date == body.date,
        DailyPlanAssignment.vehicle_id == body.vehicle_id,
    ).first()
    previous_employee_id = assignment.employee_id if assignment else None
    employee_is_changing = body.employee_id is not None and body.employee_id != previous_employee_id

    if employee_is_changing and not body.force:
        # Tjekker mod den EFFEKTIVE tildeling (gemt tildeling ELLER "Fast
        # bil"-standard, eller en EKSTRA-plads) alle andre steder end den der
        # lige nu redigeres, så brugeren advares uanset hvordan medarbejderen
        # endte der. Kun ved en FAKTISK ændring af chauffør - ikke ved fx
        # blot at redigere "Opgave" for en allerede tildelt (og evt. allerede
        # bekræftet) medarbejder.
        conflict_label = _conflicting_assignment_label(db, body.date, body.employee_id, exclude_vehicle_id=body.vehicle_id)
        if conflict_label:
            raise HTTPException(
                409, f"Medarbejderen er allerede tildelt {conflict_label} denne dag. "
                     f"Vil du stadig tildele til denne vogn?"
            )

        warning = _absence_warning_message(db, employee, body.date)
        if warning:
            raise HTTPException(409, warning)
    if assignment is None:
        assignment = DailyPlanAssignment(date=body.date, vehicle_id=body.vehicle_id)
        db.add(assignment)
    assignment.employee_id = body.employee_id
    assignment.task = body.task
    assignment.informed = body.informed
    db.flush()
    log_action(db, current_user, "upsert_dagsplan_assignment", "daily_plan_assignment", assignment.id)
    db.commit()

    rows = _build_vehicle_rows(db, body.date)
    return next(r for r in rows if r.vehicle_id == body.vehicle_id)


@router.patch("/extra-assignment", response_model=DagsplanExtraRow)
def upsert_extra_assignment(
    body: DailyPlanExtraAssignmentUpsert,
    current_user: AppUser = Depends(require_permission("dagsplan_edit")),
    db: Session = Depends(get_db),
):
    employee = db.query(Employee).filter(Employee.id == body.employee_id).first() if body.employee_id is not None else None
    if body.employee_id is not None and not employee:
        raise HTTPException(404, "Medarbejder ikke fundet")

    assignment = db.query(DailyPlanExtraAssignment).filter(
        DailyPlanExtraAssignment.date == body.date,
        DailyPlanExtraAssignment.slot == body.slot,
    ).first()
    previous_employee_id = assignment.employee_id if assignment else None
    employee_is_changing = body.employee_id is not None and body.employee_id != previous_employee_id

    if employee_is_changing and not body.force:
        conflict_label = _conflicting_assignment_label(db, body.date, body.employee_id, exclude_slot=body.slot)
        if conflict_label:
            raise HTTPException(
                409, f"Medarbejderen er allerede tildelt {conflict_label} denne dag. "
                     f"Vil du stadig tildele hertil?"
            )

        warning = _absence_warning_message(db, employee, body.date)
        if warning:
            raise HTTPException(409, warning)

    if assignment is None:
        assignment = DailyPlanExtraAssignment(date=body.date, slot=body.slot)
        db.add(assignment)
    assignment.employee_id = body.employee_id
    assignment.task = body.task
    assignment.informed = body.informed
    db.flush()
    log_action(db, current_user, "upsert_dagsplan_extra_assignment", "daily_plan_extra_assignment", assignment.id)
    db.commit()

    rows = _build_extra_rows(db, body.date)
    return next(r for r in rows if r.slot == body.slot)


@vehicle_absence_router.get("", response_model=list[VehicleAbsenceResponse])
def list_vehicle_absences(
    date: date_type,
    current_user: AppUser = Depends(require_permission("dagsplan_view")),
    db: Session = Depends(get_db),
):
    return db.query(VehicleAbsence).filter(
        VehicleAbsence.date_from <= date,
        or_(VehicleAbsence.date_to.is_(None), VehicleAbsence.date_to >= date),
    ).order_by(VehicleAbsence.date_from).all()


@vehicle_absence_router.post("", response_model=VehicleAbsenceResponse, status_code=201)
def create_vehicle_absence(
    body: VehicleAbsenceCreate,
    current_user: AppUser = Depends(require_permission("dagsplan_edit")),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Vogn ikke fundet")
    if body.date_to is not None and body.date_to < body.date_from:
        raise HTTPException(400, "Til dato kan ikke ligge før fra dato")
    absence = VehicleAbsence(
        vehicle_id=body.vehicle_id, date_from=body.date_from, date_to=body.date_to,
        comment=body.comment, created_by=current_user.initials,
    )
    db.add(absence)
    db.flush()
    log_action(db, current_user, "create_vehicle_absence", "vehicle_absence", absence.id)
    db.commit()
    db.refresh(absence)
    return absence


@vehicle_absence_router.delete("/{absence_id}", status_code=204)
def delete_vehicle_absence(
    absence_id: int,
    current_user: AppUser = Depends(require_permission("dagsplan_edit")),
    db: Session = Depends(get_db),
):
    absence = db.query(VehicleAbsence).filter(VehicleAbsence.id == absence_id).first()
    if not absence:
        raise HTTPException(404, "Fravær ikke fundet")
    log_action(db, current_user, "delete_vehicle_absence", "vehicle_absence", absence.id)
    db.delete(absence)
    db.commit()
