from datetime import datetime as _dt_now
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_permission, log_action
from calculators.auto_approval import should_auto_approve
from calculators.baseline_updater import update_baseline_from_activity
from database.session import get_db
from database.models import AppUser, Employee, Activity, ActivitySource, ActivityStatus, Vehicle
from calculators.pay_period import get_billing_period, get_or_create_period_for_date
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
    errors = []

    if body.source_folder:
        folder = Path(body.source_folder).resolve()
        if not folder.exists():
            raise HTTPException(400, "Mappen findes ikke")
        results, scan_errors = scan_ddd_folder(folder)
        errors.extend(scan_errors)
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
                errors.append(f"{p.name}: fejl ved import ({e})")
    else:
        raise HTTPException(400, "Angiv enten source_folder eller source_files")

    return _process_import_results(results, errors, current_user, db)


@router.post("/import-ddd")
def import_ddd_folder(current_user: AppUser = Depends(_ddd_access),
                      db: Session = Depends(get_db)):
    """
    Scan ddd_input/ folder and import all .ddd files.
    Skips activities that are already imported (same employee + start_time).
    """
    if not DDD_INPUT_DIR.exists():
        raise HTTPException(status_code=404, detail="ddd_input mappe ikke fundet")

    results, errors = scan_ddd_folder(DDD_INPUT_DIR)
    return _process_import_results(results, errors, current_user, db)


def _process_import_results(
    results: list, errors: list, current_user: AppUser, db: Session
) -> dict:
    """
    Importerer de fundne aktiviteter, sammentæller resultat pr. årsag og
    logger en hændelse i audit-loggen så alle skip-årsager kan læses bagefter.
    """
    imported = 0
    updated = 0
    skipped_unknown_card = 0
    skipped_duplicate = 0
    unknown_cards: set[str] = set()
    zero_activity_files: list[str] = []

    for file_path, activities in results:
        if not activities:
            zero_activity_files.append(file_path.name)
        for act in activities:
            try:
                result = _import_activity(act, db)
            except Exception as e:
                errors.append(f"{file_path.name}: {e}")
                continue
            if result == "new":
                imported += 1
            elif result == "updated":
                updated += 1
            elif result == "skipped_unknown_card":
                skipped_unknown_card += 1
                unknown_cards.add(act.tachograph_card_number)
            elif result == "skipped_duplicate":
                skipped_duplicate += 1

    skipped = skipped_unknown_card + skipped_duplicate

    summary_parts = [
        f"{len(results)} fil(er) behandlet",
        f"{imported} importeret",
        f"{updated} opdateret",
    ]
    if skipped_unknown_card:
        summary_parts.append(
            f"{skipped_unknown_card} sprunget over (ukendt førerkortnummer: "
            f"{', '.join(sorted(unknown_cards))})"
        )
    if skipped_duplicate:
        summary_parts.append(f"{skipped_duplicate} sprunget over (allerede importeret)")
    if zero_activity_files:
        summary_parts.append(
            f"{len(zero_activity_files)} fil(er) uden aktiviteter: "
            f"{', '.join(zero_activity_files)}"
        )
    if errors:
        summary_parts.append(f"{len(errors)} fejl: {'; '.join(errors)}")

    log_action(db, current_user, "ddd_import", "import", None, "; ".join(summary_parts))
    db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "skipped_unknown_card": skipped_unknown_card,
        "skipped_duplicate": skipped_duplicate,
        "unknown_cards": sorted(unknown_cards),
        "zero_activity_files": zero_activity_files,
        "errors": errors,
        "files_processed": len(results),
    }


def _import_activity(act: ParsedActivity, db: Session) -> str:
    """Import a single parsed activity. Returns 'new', 'updated', 'skipped_unknown_card' or 'skipped_duplicate'."""
    employee = (
        db.query(Employee)
        .filter(Employee.tachograph_card_number == act.tachograph_card_number)
        .first()
    )
    if not employee:
        return "skipped_unknown_card"  # Unknown card number – employee must be created first

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

        # En senere kortudlæsning kan dække en mere komplet dag (senere sluttidspunkt)
        # end den tidligere importerede – udvid i så fald i stedet for at springe over,
        # ellers går den ekstra tid tabt for altid.
        if act.end_time > existing.end_time:
            existing.end_time = act.end_time
            existing.availability_time_pct = act.availability_time_pct
            existing.rest_pause_pct = act.rest_pause_pct
            existing.other_work_pct = act.other_work_pct
            existing.driving_pct = act.driving_pct
            existing.pause_intervals = [
                [s.isoformat(), e.isoformat()] for s, e in (act.pause_intervals or [])
            ]
            existing.segments = [
                [s.isoformat(), e.isoformat(), name] for s, e, name in (act.segments or [])
            ]
            # Opdater ufuldstændig-flaget efter den nye, mere komplette fil –
            # rydder flaget hvis dagen nu er komplet, eller sætter det hvis
            # den nye fil stadig ser ufuldstændig ud.
            existing.is_likely_incomplete = act.is_likely_incomplete
            if act.vehicle_registration and not existing.vehicle_registration:
                existing.vehicle_registration = act.vehicle_registration
                if not existing.vehicle_number:
                    v = db.query(Vehicle).filter(Vehicle.registration_number == act.vehicle_registration).first()
                    if v:
                        existing.vehicle_number = v.vehicle_number
            if existing.status != ActivityStatus.pending:
                # Godkendt/deaktiveret aktivitet er nu blevet længere end det, der blev
                # taget stilling til – genåbnes til afventende, så tiden skal godkendes igen.
                existing.status = ActivityStatus.pending
                existing.approved_by = None
                existing.approved_at = None
                existing.deactivated_by = None
                existing.auto_approved = False
                existing.auto_approval_flags = []
            changed = True

        if changed:
            db.commit()
            return "updated"
        return "skipped_duplicate"

    pay_period = get_billing_period(act.start_time.date(), db)

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
        is_likely_incomplete=act.is_likely_incomplete,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    ok, flags = should_auto_approve(activity, db)
    if ok:
        activity.status = ActivityStatus.approved
        activity.auto_approved = True
        activity.auto_approval_flags = []
        activity.approved_by = "AUTO"
        activity.approved_at = _dt_now.utcnow()
        db.commit()
        update_baseline_from_activity(activity, db)
    else:
        activity.auto_approval_flags = flags
        db.commit()

    return "new"
