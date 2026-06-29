from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_permission
from database.session import get_db
from database.models import AppUser, Employee, Activity, ActivitySource, ActivityStatus, Vehicle
from calculators.pay_period import get_or_create_period_for_date
from parsers.ddd_parser import scan_ddd_folder, parse_ddd_file, ParsedActivity

router = APIRouter(prefix="/api", tags=["import"])

DDD_INPUT_DIR = Path(__file__).resolve().parent.parent / "ddd_input"

_ddd_access = require_permission("import_ddd")


@router.get("/browse-ddd-folder")
def browse_ddd_folder(initial: str = "",
                      current_user: AppUser = Depends(_ddd_access)):
    """Åbner native mappevælger til valg af DDD-mappe."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", True)
    start = initial if initial else str(Path.home() / "Downloads")
    chosen = filedialog.askdirectory(initialdir=start, title="Vælg mappe med .ddd-filer")
    root.destroy()
    return {"path": str(Path(chosen)) if chosen else None}


@router.get("/browse-ddd-files")
def browse_ddd_files(initial: str = "",
                     current_user: AppUser = Depends(_ddd_access)):
    """Åbner native filvælger til valg af en eller flere .ddd-filer."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", True)
    start = initial if initial else str(Path.home() / "Downloads")
    chosen = filedialog.askopenfilenames(
        initialdir=start,
        title="Vælg .ddd-filer",
        filetypes=[("DDD-filer", "*.ddd"), ("Alle filer", "*.*")],
    )
    root.destroy()
    return {"paths": list(chosen)}


class ImportFromRequest(BaseModel):
    source_folder: Optional[str] = None
    source_files: Optional[List[str]] = None


@router.post("/import-ddd-from")
def import_ddd_from(body: ImportFromRequest,
                    current_user: AppUser = Depends(_ddd_access),
                    db: Session = Depends(get_db)):
    """
    Importer .ddd-filer fra en valgt mappe eller en liste af enkeltfiler.
    Springer allerede importerede aktiviteter over.
    """
    imported = 0
    updated = 0
    skipped = 0
    errors = []
    files_processed = 0

    if body.source_folder:
        folder = Path(body.source_folder).resolve()
        if not folder.exists():
            raise HTTPException(400, "Mappen findes ikke")
        results = scan_ddd_folder(folder)
    elif body.source_files:
        MAX_DDD_BYTES = 10 * 1024 * 1024  # 10 MB – reelle .ddd-filer er ~100-300 KB
        results = []
        for fp in body.source_files:
            p = Path(fp).resolve()
            if not p.exists():
                errors.append(f"{p.name}: fil ikke fundet")
                continue
            if p.suffix.lower() != ".ddd":
                errors.append(f"{p.name}: kun .ddd-filer er tilladt")
                continue
            if p.stat().st_size > MAX_DDD_BYTES:
                errors.append(f"{p.name}: filen er for stor (max 10 MB)")
                continue
            try:
                acts = parse_ddd_file(p)
                results.append((p, acts))
            except Exception as e:
                import logging; logging.error(f"Fejl ved parsing af {p}: {e}")
                errors.append(f"{p.name}: fejl ved import")
    else:
        raise HTTPException(400, "Angiv enten source_folder eller source_files")

    for file_path, activities in results:
        files_processed += 1
        for act in activities:
            try:
                result = _import_activity(act, db)
                if result == "new":
                    imported += 1
                elif result == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"{file_path.name}: {e}")

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "files_processed": files_processed,
    }


@router.post("/import-ddd")
def import_ddd_folder(current_user: AppUser = Depends(_ddd_access),
                      db: Session = Depends(get_db)):
    """
    Scan ddd_input/ folder and import all .ddd files.
    Skips activities that are already imported (same employee + start_time).
    """
    if not DDD_INPUT_DIR.exists():
        raise HTTPException(status_code=404, detail="ddd_input mappe ikke fundet")

    results = scan_ddd_folder(DDD_INPUT_DIR)
    imported = 0
    updated = 0
    skipped = 0
    errors = []

    for file_path, activities in results:
        for act in activities:
            try:
                result = _import_activity(act, db)
                if result == "new":
                    imported += 1
                elif result == "updated":
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"{file_path.name}: {e}")

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "files_processed": len(results),
    }


def _import_activity(act: ParsedActivity, db: Session) -> str:
    """Import a single parsed activity. Returns 'new', 'updated' or 'skipped'."""
    employee = (
        db.query(Employee)
        .filter(Employee.tachograph_card_number == act.tachograph_card_number)
        .first()
    )
    if not employee:
        return "skipped"  # Unknown card number – employee must be created first

    # Check for existing activity
    existing = (
        db.query(Activity)
        .filter(
            Activity.employee_id == employee.id,
            Activity.start_time == act.start_time,
            Activity.source == ActivitySource.tachograph,
        )
        .first()
    )
    if existing:
        # Opdater km-data hvis parseren fandt værdier og aktiviteten mangler dem
        changed = False
        if act.km_start is not None and existing.km_start is None:
            existing.km_start = act.km_start
            changed = True
        if act.km_end is not None and existing.km_end is None:
            existing.km_end = act.km_end
            changed = True
        if changed:
            db.commit()
            return "updated"
        return "skipped"

    pay_period = get_or_create_period_for_date(act.start_time.date(), db)

    vehicle_number = None
    if act.vehicle_registration:
        v = db.query(Vehicle).filter(Vehicle.registration_number == act.vehicle_registration).first()
        if v:
            vehicle_number = v.vehicle_number

    activity = Activity(
        employee_id=employee.id,
        pay_period_id=pay_period.id,
        source=ActivitySource.tachograph,
        start_time=act.start_time,
        end_time=act.end_time,
        availability_time_pct=act.availability_time_pct,
        rest_pause_pct=act.rest_pause_pct,
        other_work_pct=act.other_work_pct,
        driving_pct=act.driving_pct,
        vehicle_registration=act.vehicle_registration,
        vehicle_number=vehicle_number,
        km_start=act.km_start,
        km_end=act.km_end,
        pause_intervals=[
            [s.isoformat(), e.isoformat()] for s, e in (act.pause_intervals or [])
        ],
        segments=[
            [s.isoformat(), e.isoformat(), name] for s, e, name in (act.segments or [])
        ],
        status=ActivityStatus.pending,
    )
    db.add(activity)
    db.commit()
    return "new"
