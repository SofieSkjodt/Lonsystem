from datetime import date as date_type
from typing import Optional

from sqlalchemy.orm import Session

from database.models import DailyPlanAssignment, Employee, Vehicle


def effective_vehicle_for_employee(db: Session, employee_id: int, d: date_type) -> Optional[Vehicle]:
    """Vognen chaufføren reelt er tildelt i Dagsplanen den givne dag.

    En gemt Dagsplan-tildeling for dagen vinder altid (også hvis den
    eksplicit har employee_id sat til netop denne medarbejder uden vogn er
    umuligt - vognen er nøglen). Findes ingen gemt tildeling, falder vi
    tilbage til medarbejderens "Fast bil", hvis den er sat.
    """
    assignment = (
        db.query(DailyPlanAssignment)
        .filter(DailyPlanAssignment.date == d, DailyPlanAssignment.employee_id == employee_id)
        .first()
    )
    if assignment:
        return assignment.vehicle
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if emp and emp.fast_bil and emp.fast_bil_vehicle_id:
        return emp.fast_bil_vehicle
    return None
