from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from auth import get_current_user, log_action, require_permission
from database.models import AppUser, Employee, SystemSettings
from database.session import get_db
from calculators.baseline_updater import rebuild_baselines_for_employee, is_auto_approval_enabled

router = APIRouter(prefix="/api/auto-approval", tags=["auto-approval"])

_admin_access = require_permission("manage_baselines")
_toggle_access = require_permission("manage_auto_approval")


class AutoApprovalSettingsBody(BaseModel):
    enabled: bool


@router.post("/rebuild-baselines")
def rebuild_baselines(
    employee_id: Optional[int] = None,
    current_user: AppUser = Depends(_admin_access),
    db: Session = Depends(get_db),
):
    """Genberegn baselines fra alle historiske godkendte aktiviteter.
    employee_id=None → alle aktive medarbejdere. Bruges til bootstrapping af historisk data."""
    if employee_id is not None:
        count = rebuild_baselines_for_employee(employee_id, db)
        return {"employees_processed": 1, "total_activities": count}

    employees = db.query(Employee).filter(Employee.active == True).all()
    total = 0
    for emp in employees:
        total += rebuild_baselines_for_employee(emp.id, db)

    return {"employees_processed": len(employees), "total_activities": total}


@router.get("/baseline-summary")
def baseline_summary(
    current_user: AppUser = Depends(_admin_access),
    db: Session = Depends(get_db),
):
    """Oversigt over baseline-status per medarbejder – bruges til at vurdere datakvalitet."""
    from database.models import EmployeeBaseline
    from sqlalchemy import func

    rows = (
        db.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            func.count(EmployeeBaseline.id).label("weekday_count"),
            func.sum(EmployeeBaseline.sample_count).label("total_samples"),
            func.min(EmployeeBaseline.sample_count).label("min_samples"),
        )
        .outerjoin(EmployeeBaseline, EmployeeBaseline.employee_id == Employee.id)
        .filter(Employee.active == True)
        .group_by(Employee.id)
        .all()
    )

    MIN_SAMPLES = 5
    return [
        {
            "employee_id": r.id,
            "name": f"{r.first_name} {r.last_name}",
            "weekday_count": r.weekday_count or 0,
            "total_samples": int(r.total_samples or 0),
            "min_samples_per_weekday": int(r.min_samples or 0),
            "auto_approval_ready": (r.min_samples or 0) >= MIN_SAMPLES and (r.weekday_count or 0) >= 5,
        }
        for r in rows
    ]


@router.get("/settings")
def get_auto_approval_settings(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Nuværende tilstand af den globale auto-godkendelses-kontakt. Åben for alle
    godkendte brugere, så frontend kan skjule 'Autogodkend aktiviteter'-knappen."""
    return {"enabled": is_auto_approval_enabled(db)}


@router.post("/settings")
def set_auto_approval_settings(
    body: AutoApprovalSettingsBody,
    current_user: AppUser = Depends(_toggle_access),
    db: Session = Depends(get_db),
):
    """Slår den globale auto-godkendelses-proces til/fra."""
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if settings is None:
        settings = SystemSettings(id=1, auto_approval_enabled=body.enabled)
        db.add(settings)
    else:
        settings.auto_approval_enabled = body.enabled
    settings.updated_by = current_user.initials
    settings.updated_at = datetime.utcnow()
    log_action(db, current_user, "toggle_auto_approval",
               details=f"auto_approval_enabled={body.enabled}")
    db.commit()
    return {"enabled": settings.auto_approval_enabled}
