from datetime import datetime as _dt_now
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import require_permission, log_action
from calculators.auto_approval import should_auto_approve
from calculators.baseline_updater import update_baseline_from_activity
from database.session import get_db
from database.models import (
    AppUser, Employee, Activity, ActivitySource, ActivityStatus, PayPeriodStatus, Vehicle,
    DeclinedImport,
)
from calculators.pay_period import get_billing_period, get_or_create_period_for_date
from parsers.ddd_parser import scan_ddd_folder, parse_ddd_file, ParsedActivity
from routers.activities import _recalculate_pcts
from utils.safe_paths import is_under_allowed_root

router = APIRouter(prefix="/api", tags=["import"])

DDD_INPUT_DIR = Path(__file__).resolve().parent.parent / "ddd_input"

_ddd_access = require_permission("import_ddd")


class ImportFromRequest(BaseModel):
    source_folder: Optional[str] = None
    source_files: Optional[List[str]] = None
    allow_closed_period: bool = False


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
        if not is_under_allowed_root(folder):
            raise HTTPException(400, "Ugyldig mappe – skal ligge under din hjemmemappe")
        if not folder.exists():
            raise HTTPException(400, "Mappen findes ikke")
        results, scan_errors = scan_ddd_folder(folder)
        errors.extend(scan_errors)
    elif body.source_files:
        MAX_DDD_BYTES = 10 * 1024 * 1024  # 10 MB – reelle .ddd-filer er ~100-300 KB
        results = []
        for fp in body.source_files:
            p = Path(fp).resolve()
            if not is_under_allowed_root(p):
                errors.append(f"{p.name}: uden for tilladt mappe (skal ligge under din hjemmemappe)")
                continue
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

    return _process_import_results(results, errors, current_user, db, body.allow_closed_period)


@router.post("/import-ddd")
def import_ddd_folder(allow_closed_period: bool = False,
                      current_user: AppUser = Depends(_ddd_access),
                      db: Session = Depends(get_db)):
    """
    Scan ddd_input/ folder and import all .ddd files.
    Skips activities that are already imported (same employee + start_time).
    """
    if not DDD_INPUT_DIR.exists():
        raise HTTPException(status_code=404, detail="ddd_input mappe ikke fundet")

    results, errors = scan_ddd_folder(DDD_INPUT_DIR)
    return _process_import_results(results, errors, current_user, db, allow_closed_period)


class DeclinedCandidate(BaseModel):
    employee_id: int
    start_time: str
    end_time: str


class DeclineClosedPeriodRequest(BaseModel):
    items: List[DeclinedCandidate]


@router.post("/decline-closed-period-import")
def decline_closed_period_import(
    body: DeclineClosedPeriodRequest,
    current_user: AppUser = Depends(_ddd_access),
    db: Session = Depends(get_db),
):
    """
    Husker at brugeren har valgt IKKE at importere disse vagter (lukket
    lønperiode) – de springes automatisk over uden ny bekræftelse ved
    fremtidige genimporter af samme fil(er).
    """
    added = 0
    # DB-sessionen bruger autoflush=False, så et tidligere db.add() i denne
    # samme request ikke er synligt for et efterfølgende db.query() – uden
    # dette lokale sæt ville den samme vagt optrædende to gange i body.items
    # (fx fundet i to forskellige .ddd-filer) blive tilføjet to gange og
    # ramme det unikke index (employee_id, start_time) ved commit, hvilket
    # fejlede HELE afvisningen (bekræftet 2026-08-11).
    seen: set[tuple[int, _dt_now]] = set()
    for item in body.items:
        start = _dt_now.fromisoformat(item.start_time)
        key = (item.employee_id, start)
        if key in seen:
            continue
        seen.add(key)
        exists = (
            db.query(DeclinedImport)
            .filter(DeclinedImport.employee_id == item.employee_id, DeclinedImport.start_time == start)
            .first()
        )
        if exists:
            continue
        db.add(DeclinedImport(
            employee_id=item.employee_id,
            start_time=start,
            end_time=_dt_now.fromisoformat(item.end_time),
            declined_by=current_user.initials,
        ))
        added += 1
    log_action(db, current_user, "decline_closed_period_import", "import", None,
               f"{added} vagt(er) markeret til altid at springes over (lukket lønperiode)")
    db.commit()
    return {"declined": added}


def _process_import_results(
    results: list, errors: list, current_user: AppUser, db: Session,
    allow_closed_period: bool = False,
) -> dict:
    """
    Importerer de fundne aktiviteter, sammentæller resultat pr. årsag og
    logger en hændelse i audit-loggen så alle skip-årsager kan læses bagefter.
    """
    imported = 0
    updated = 0
    skipped_unknown_card = 0
    skipped_duplicate = 0
    skipped_declined = 0
    skipped_conflict = 0
    conflicts: list[dict] = []
    unknown_cards: set[str] = set()
    zero_activity_files: list[str] = []
    # Samme vagt findes ofte i flere .ddd-filer (nye kortudlæsninger dækker
    # gerne de samme dage som en tidligere) – dedupliker pr. (medarbejder,
    # starttid), så brugeren ikke ser/afviser den samme vagt flere gange i
    # bekræftelses-popup'en (bekræftet 2026-08-11: dubletter fik "Nej,
    # spring over" til at fejle med en unik-indeks-fejl i afvisnings-tabellen).
    closed_period_candidates_by_key: dict[tuple[int, str], dict] = {}

    # Alle aktiviteter i én fil deler samme førerkortnummer – cache opslaget
    # pr. unikt kortnummer i stedet for at forespørge databasen for hver
    # eneste aktivitet (kan være 100+ pr. fil).
    employee_cache: dict[str, Employee | None] = {}

    for file_path, activities in results:
        if not activities:
            zero_activity_files.append(file_path.name)
        for act in activities:
            card = act.tachograph_card_number
            if card not in employee_cache:
                employee_cache[card] = (
                    db.query(Employee)
                    .filter(Employee.tachograph_card_number == card)
                    .first()
                )
            try:
                result, detail = _import_activity(
                    act, db, employee_cache[card], allow_closed_period
                )
            except Exception as e:
                # Uventet fejl (ikke den kendte SAVEPOINT-håndterede
                # unik-indeks-konflikt i _import_activity) – rul hele
                # sessionen tilbage, så den ikke efterlades i en "pending
                # rollback"-tilstand hvor ALLE efterfølgende aktiviteter i
                # denne kørsel ville fejle med en kryptisk følgefejl
                # (bekræftet 2026-09-04 ved genimport for Finn Thor Eriksen –
                # manglende rollback her lod én fejl vælte resten af
                # importen). Det koster de allerede flushede (men endnu ikke
                # committede) ændringer tidligere i denne kørsel, men det er
                # trygt: ingenting er committet til databasen endnu.
                db.rollback()
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
            elif result == "skipped_declined":
                skipped_declined += 1
            elif result == "skipped_conflict":
                skipped_conflict += 1
                if detail:
                    conflicts.append(detail)
            elif result == "pending_closed_period":
                key = (detail["employee_id"], detail["start_time"])
                existing_candidate = closed_period_candidates_by_key.get(key)
                if existing_candidate is None or detail["end_time"] > existing_candidate["end_time"]:
                    closed_period_candidates_by_key[key] = detail

    closed_period_candidates = list(closed_period_candidates_by_key.values())
    skipped = skipped_unknown_card + skipped_duplicate + skipped_declined + skipped_conflict

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
    if skipped_declined:
        summary_parts.append(f"{skipped_declined} sprunget over (tidligere afvist – lukket periode)")
    if skipped_conflict:
        summary_parts.append(
            f"{skipped_conflict} kunne IKKE rettes (kolliderer med en anden, allerede gemt "
            f"aktivitet for samme medarbejder på samme starttidspunkt – formentlig en ældre "
            f"duplikat-aktivitet der bør ryddes op manuelt)"
        )
    if closed_period_candidates:
        summary_parts.append(
            f"{len(closed_period_candidates)} vagt(er) afventer bekræftelse (lukket lønperiode)"
        )
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
        "skipped_declined": skipped_declined,
        "skipped_conflict": skipped_conflict,
        "conflicts": conflicts,
        "unknown_cards": sorted(unknown_cards),
        "zero_activity_files": zero_activity_files,
        "errors": errors,
        "files_processed": len(results),
        "closed_period_candidates": closed_period_candidates,
    }


def _import_activity(
    act: ParsedActivity, db: Session, employee: Employee | None,
    allow_closed_period: bool = False,
) -> tuple[str, dict | None]:
    """Import a single parsed activity. Returns (status, detail) where status is
    'new', 'updated', 'skipped_unknown_card', 'skipped_duplicate',
    'skipped_declined', 'skipped_conflict' or 'pending_closed_period' (detail
    is only set for 'skipped_conflict' and 'pending_closed_period')."""
    if not employee:
        return "skipped_unknown_card", None  # Unknown card number – employee must be created first

    # Brugeren har tidligere eksplicit valgt IKKE at importere denne vagt
    # (typisk: afvist en lukket-periode-bekræftelse) – husk det, så den ikke
    # bliver foreslået/importeret igen ved en senere genimport af filen.
    declined = (
        db.query(DeclinedImport)
        .filter(DeclinedImport.employee_id == employee.id, DeclinedImport.start_time == act.start_time)
        .first()
    )
    if declined:
        return "skipped_declined", None

    # Check for existing activity. Match på tidsoverlap i stedet for eksakt
    # start_time-lighed: en rettelse i parseren (eller en senere, mere
    # komplet kortudlæsning) kan ændre det beregnede starttidspunkt for en
    # vagt, og skal stadig kunne opdatere den eksisterende række i stedet for
    # fejlagtigt at oprette en duplikat (bekræftet 2026-09-03: Mikkel Hørlin
    # 2/9 – en parser-rettelse flyttede vagtens beregnede start fra 07:02 til
    # 06:54).
    existing = (
        db.query(Activity)
        .filter(
            Activity.employee_id == employee.id,
            Activity.source == ActivitySource.tachograph,
            Activity.start_time < act.end_time,
            Activity.end_time > act.start_time,
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

        # Ret registreringsnummeret uafhængigt af tid/segment-ændringerne
        # nedenfor – en tidligere fejlbehæftet parser-version kunne gemme et
        # forkert registreringsnummer for en dag der ellers ikke ændrer sig
        # ved genimport, og genimporten skal stadig kunne korrigere det. Feltet
        # er metadata uden betydning for løn/godkendelse, så det rettes
        # uanset aktivitetens status.
        if act.vehicle_registration and act.vehicle_registration != existing.vehicle_registration:
            existing.vehicle_registration = act.vehicle_registration
            v = db.query(Vehicle).filter(Vehicle.registration_number == act.vehicle_registration).first()
            existing.vehicle_number = v.vehicle_number if v else None
            changed = True

        new_segments = [
            [s.isoformat(), e.isoformat(), name] for s, e, name in (act.segments or [])
        ]
        new_pause_intervals = [
            [s.isoformat(), e.isoformat()] for s, e in (act.pause_intervals or [])
        ]

        def _reopen_for_review():
            if existing.status != ActivityStatus.pending:
                existing.status = ActivityStatus.pending
                existing.approved_by = None
                existing.approved_at = None
                existing.deactivated_by = None
                existing.auto_approved = False
                existing.auto_approval_flags = []

        # En aktivitet der stadig er 'pending' og ikke en del af et split (er
        # hverken selv splittet op, eller en af de to dele et split skabte)
        # er endnu ikke taget stilling til – trygt at synkronisere den FULDT
        # ind fra den nyeste parsing, i begge retninger. Det dækker bl.a. en
        # rettelse i parseren der afslører en kortere, korrekt vagt end den
        # tidligere gemte (bekræftet 2026-09-04: en .ddd-fil kan indeholde to
        # modstridende dags-records for samme dato, og en parser-rettelse kan
        # derfor gøre både start senere og slut tidligere – se
        # ddd_parser._find_all_daily_records). Er aktiviteten derimod
        # godkendt, deaktiveret eller en del af et split, er den allerede
        # taget stilling til (eller dens tid er bevidst omfordelt af en
        # bruger), og må IKKE gøres kortere af en genimport – kun evt.
        # udvides, som hidtil (se de to grene nedenfor).
        #
        # Er den NYE udlæsning selv markeret ufuldstændig (kortet læst midt i
        # vagten), må den ALDRIG lægges fuldt ind, uanset status – ellers vil
        # en ældre, ufuldstændig fil (importeret efter den komplette, fx pga.
        # mappenavne der sorteres alfabetisk og ikke efter udlæsningsdato)
        # kunne slette allerede kendte, korrekte pauser/segmenter (bekræftet
        # 2026-08-10: Alexander B. Knudsen 3/8).
        can_resync_fully = (
            existing.status == ActivityStatus.pending
            and existing.parent_activity_id is None
            and not act.is_likely_incomplete
        )

        if can_resync_fully:
            if (
                act.start_time != existing.start_time
                or act.end_time != existing.end_time
                or new_segments != (existing.segments or [])
                or new_pause_intervals != (existing.pause_intervals or [])
            ):
                existing.start_time = act.start_time
                existing.end_time = act.end_time
                existing.segments = new_segments
                existing.pause_intervals = new_pause_intervals
                existing.availability_time_pct = act.availability_time_pct
                existing.rest_pause_pct = act.rest_pause_pct
                existing.other_work_pct = act.other_work_pct
                existing.driving_pct = act.driving_pct
                existing.is_likely_incomplete = act.is_likely_incomplete
                changed = True

            if changed:
                # Nested transaktion (SAVEPOINT): der findes desværre ældre,
                # overlappende duplikat-aktiviteter for nogle medarbejdere
                # (fra før tidsoverlap-matchningen ovenfor blev indført) –
                # synkroniseres denne aktivitets start/sluttid til en tid en
                # ANDEN allerede gemt aktivitet (samme medarbejder) allerede
                # har, rammer det det unikke index (employee_id, start_time).
                # Uden SAVEPOINT ville det fejle HELE batch-importens
                # transaktion (alle andre allerede flushede, gyldige
                # aktiviteter i samme kørsel) i stedet for kun denne ene
                # (bekræftet 2026-09-04 ved genimport for Finn Thor Eriksen).
                try:
                    with db.begin_nested():
                        db.flush()
                except IntegrityError:
                    return "skipped_conflict", {
                        "employee_id": existing.employee_id,
                        "activity_id": existing.id,
                        "start_time": act.start_time.isoformat(),
                        "end_time": act.end_time.isoformat(),
                    }
                return "updated", None
            return "skipped_duplicate", None

        if act.start_time < existing.start_time:
            # Analogt med udvidelse ved et senere sluttidspunkt herunder: en
            # ny fil (eller en rettet parser) kan afsløre et TIDLIGERE reelt
            # starttidspunkt end det hidtil gemte. Tilføj kun de nye
            # segmenter/pauser der ligger FØR det hidtidige starttidspunkt –
            # rør ikke ved det der allerede er gemt fra og med det gamle
            # starttidspunkt, af samme grund som ved sluttidspunktet nedenfor
            # (mulige manuelle rettelser må ikke gå tabt).
            cutoff = existing.start_time
            existing.segments = [
                s for s in new_segments if _dt_now.fromisoformat(s[1]) <= cutoff
            ] + (existing.segments or [])
            existing.pause_intervals = [
                p for p in new_pause_intervals if _dt_now.fromisoformat(p[1]) <= cutoff
            ] + (existing.pause_intervals or [])
            existing.start_time = act.start_time
            _recalculate_pcts(existing)
            # Godkendt/deaktiveret aktivitet dækker nu en længere periode end
            # det, der blev taget stilling til – genåbnes til afventende.
            _reopen_for_review()
            changed = True

        if act.end_time > existing.end_time:
            # En senere kortudlæsning kan dække en mere komplet dag (senere
            # sluttidspunkt) end den tidligere importerede. Tilføj kun den NYE
            # tid efter det hidtidige sluttidspunkt – allerede gemte segmenter
            # røres ikke, da en bruger kan have rettet/tilpasset dem manuelt
            # (fx via "Ret linje" eller "Tilpas pause"), og den slags må ikke
            # gå tabt ved en simpel genimport.
            cutoff = existing.end_time
            existing.segments = (existing.segments or []) + [
                s for s in new_segments if _dt_now.fromisoformat(s[0]) >= cutoff
            ]
            existing.pause_intervals = (existing.pause_intervals or []) + [
                p for p in new_pause_intervals if _dt_now.fromisoformat(p[0]) >= cutoff
            ]
            existing.end_time = act.end_time
            _recalculate_pcts(existing)
            # Opdater ufuldstændig-flaget efter den nye, mere komplette fil –
            # rydder flaget hvis dagen nu er komplet, eller sætter det hvis
            # den nye fil stadig ser ufuldstændig ud.
            existing.is_likely_incomplete = act.is_likely_incomplete
            # Godkendt/deaktiveret aktivitet er nu blevet længere end det, der
            # blev taget stilling til – genåbnes til afventende, så tiden skal
            # godkendes igen.
            _reopen_for_review()
            changed = True
        # (Ingen gren for act.end_time <= existing.end_time her: en
        # godkendt/deaktiveret/split aktivitet må kun UDVIDES ved genimport,
        # aldrig gøres kortere eller få sine segmenter overskrevet – se
        # can_resync_fully ovenfor, som allerede har håndteret og returneret
        # for det trygge tilfælde (pending, ikke split).)

        if changed:
            # Samme SAVEPOINT-begrundelse som i can_resync_fully-grenen ovenfor.
            try:
                with db.begin_nested():
                    db.flush()  # gør ændringen synlig i denne transaktion; committes samlet til sidst
            except IntegrityError:
                return "skipped_conflict", {
                    "employee_id": existing.employee_id,
                    "activity_id": existing.id,
                    "start_time": act.start_time.isoformat(),
                    "end_time": act.end_time.isoformat(),
                }
            return "updated", None
        return "skipped_duplicate", None

    natural_period = get_or_create_period_for_date(act.start_time.date(), db)
    if natural_period.status == PayPeriodStatus.closed and not allow_closed_period:
        # Vagten hører til en allerede lukket lønperiode ("sen registrering") –
        # opret den IKKE endnu. Brugeren skal først bekræfte i en pop-up om
        # vagten skal importeres (og dermed rulles frem til næste åbne periode,
        # se get_billing_period) eller helt springes over.
        return "pending_closed_period", {
            "employee": f"{employee.first_name} {employee.last_name}",
            "employee_id": employee.id,
            "start_time": act.start_time.isoformat(),
            "end_time": act.end_time.isoformat(),
            "period_start": natural_period.start_date.isoformat(),
            "period_end": natural_period.end_date.isoformat(),
        }

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
    try:
        # Nested transaktion (SAVEPOINT): hvis en samtidig import allerede har
        # indsat samme vagt (race condition, se det unikke indeks på Activity),
        # fanger vi kun DENNE aktivitets konflikt her – uden det ville hele
        # importens batch-transaktion (mange andre allerede flushede, gyldige
        # aktiviteter) rulles tilbage sammen med den. db.flush() tildeler
        # activity.id uden en fuld transaktions-commit pr. aktivitet.
        with db.begin_nested():
            db.add(activity)
            db.flush()
    except IntegrityError:
        return "skipped_duplicate", None

    ok, flags = should_auto_approve(activity, db)
    if ok:
        activity.status = ActivityStatus.approved
        activity.auto_approved = True
        activity.auto_approval_flags = []
        activity.approved_by = "AUTO"
        activity.approved_at = _dt_now.utcnow()
        db.flush()
        update_baseline_from_activity(activity, db)
    else:
        activity.auto_approval_flags = flags
        db.flush()

    return "new", None
