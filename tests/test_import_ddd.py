import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

import shutil
import tempfile
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import ActivityStatus, PayPeriodStatus, AppUser, AgreementKind, Activity, Employee, Base
from parsers.ddd_parser import ParsedActivity
from calculators.pay_period import get_or_create_period_for_date
from routers.import_ddd import _import_activity, _process_import_results, decline_closed_period_import, DeclineClosedPeriodRequest, DeclinedCandidate, import_ddd_from, ImportFromRequest
from conftest import make_activity


def _parsed(start, end, segments, pauses):
    return ParsedActivity(
        tachograph_card_number="X",
        start_time=start,
        end_time=end,
        availability_time_pct=Decimal("0"),
        rest_pause_pct=Decimal("0"),
        other_work_pct=Decimal("0"),
        driving_pct=Decimal("0"),
        source_file="test.ddd",
        pause_intervals=pauses,
        segments=segments,
        is_likely_incomplete=False,
    )


def test_older_incomplete_readout_does_not_erase_already_complete_shift(db, employee):
    """
    En vagt er allerede importeret fuldt ud (fx fra en senere kortudlæsning,
    der pga. mappesortering blev behandlet FØRST). Genimporteres en ÆLDRE,
    ufuldstændig udlæsning af den samme vagt (kortere sluttidspunkt, ingen
    pause fundet endnu), må den ikke slette de allerede kendte pauser/segmenter.
    """
    start = datetime(2026, 8, 3, 5, 45)
    full_end = datetime(2026, 8, 3, 14, 30)
    full_segments = [
        (datetime(2026, 8, 3, 5, 45), datetime(2026, 8, 3, 11, 16), "work"),
        (datetime(2026, 8, 3, 11, 16), datetime(2026, 8, 3, 11, 41), "rest"),
        (datetime(2026, 8, 3, 11, 41), full_end, "driving"),
    ]
    full_pauses = [(datetime(2026, 8, 3, 11, 16), datetime(2026, 8, 3, 11, 41))]
    act = make_activity(db, employee, start=start, end=full_end, status=ActivityStatus.pending)
    act.segments = [[s.isoformat(), e.isoformat(), n] for s, e, n in full_segments]
    act.pause_intervals = [[s.isoformat(), e.isoformat()] for s, e in full_pauses]
    db.commit()

    incomplete_end = datetime(2026, 8, 3, 8, 8)
    incomplete = _parsed(
        start, incomplete_end,
        segments=[(start, incomplete_end, "work")],
        pauses=[],
    )

    _import_activity(incomplete, db, employee)
    db.refresh(act)

    assert act.end_time == full_end
    assert act.pause_intervals == [[s.isoformat(), e.isoformat()] for s, e in full_pauses]
    assert len(act.segments) == len(full_segments)


def test_later_more_complete_readout_still_extends_shift(db, employee):
    """Modsat tilfælde skal stadig virke: en SENERE, mere komplet udlæsning
    (længere sluttidspunkt) skal stadig udvide vagten og tilføje dens nye
    segmenter/pauser, uden at røre allerede gemte segmenter før cutoff."""
    start = datetime(2026, 8, 3, 5, 45)
    partial_end = datetime(2026, 8, 3, 8, 8)
    act = make_activity(db, employee, start=start, end=partial_end, status=ActivityStatus.pending)
    act.segments = [[start.isoformat(), partial_end.isoformat(), "work"]]
    act.pause_intervals = []
    db.commit()

    full_end = datetime(2026, 8, 3, 14, 30)
    complete = _parsed(
        start, full_end,
        segments=[
            (start, partial_end, "work"),
            (partial_end, datetime(2026, 8, 3, 11, 16), "work"),
            (datetime(2026, 8, 3, 11, 16), datetime(2026, 8, 3, 11, 41), "rest"),
            (datetime(2026, 8, 3, 11, 41), full_end, "driving"),
        ],
        pauses=[(datetime(2026, 8, 3, 11, 16), datetime(2026, 8, 3, 11, 41))],
    )

    result, _ = _import_activity(complete, db, employee)
    db.refresh(act)

    assert result == "updated"
    assert act.end_time == full_end
    assert len(act.pause_intervals) == 1


def test_corrected_earlier_start_time_extends_existing_activity_not_duplicates(db, employee):
    """
    Reproducerer Mikkel Hørlin 2/9-2026: aktiviteten blev oprindeligt
    importeret med start 07:02 (en parser-bug droppede en 8 min indledende
    hvil). Efter parser-rettelsen beregnes samme vagt nu korrekt til at
    starte 06:54. En genimport skal finde og OPDATERE den eksisterende
    aktivitet (samme vagt, blot et rettet starttidspunkt) – ikke oprette en
    ny, overlappende duplikat-aktivitet.
    """
    old_start = datetime(2026, 9, 2, 7, 2)
    end = datetime(2026, 9, 2, 14, 49)
    act = make_activity(db, employee, start=old_start, end=end, status=ActivityStatus.pending)
    act.segments = [[old_start.isoformat(), end.isoformat(), "driving"]]
    act.pause_intervals = []
    db.commit()

    corrected_start = datetime(2026, 9, 2, 6, 54)
    corrected = _parsed(
        corrected_start, end,
        segments=[
            (corrected_start, old_start, "rest"),
            (old_start, end, "driving"),
        ],
        pauses=[(corrected_start, old_start)],
    )

    result, _ = _import_activity(corrected, db, employee)
    db.refresh(act)

    assert result == "updated"
    assert act.start_time == corrected_start
    assert act.pause_intervals == [[corrected_start.isoformat(), old_start.isoformat()]]
    assert len(act.segments) == 2
    assert db.query(Activity).filter(Activity.employee_id == employee.id).count() == 1


def _test_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_closed_period_candidates_deduped_across_files(db, employee):
    """
    Reproducerer den rapporterede fejl: samme vagt findes i flere .ddd-filer
    (typisk fra flere kortudlæsninger over tid), og vagten falder i en
    allerede lukket lønperiode. closed_period_candidates må kun indeholde
    ÉT eksemplar af vagten, ikke ét pr. fil den er fundet i – ellers ser
    brugeren den samme vagt flere gange i bekræftelses-popup'en.
    """
    employee.tachograph_card_number = "TESTCARD1"
    db.commit()

    closed_date = datetime(2026, 7, 15).date()
    period = get_or_create_period_for_date(closed_date, db)
    period.status = PayPeriodStatus.closed
    db.commit()

    start = datetime(2026, 7, 15, 5, 27)
    end = datetime(2026, 7, 15, 16, 46)
    act1 = _parsed(start, end, segments=[(start, end, "work")], pauses=[])
    act2 = _parsed(start, end, segments=[(start, end, "work")], pauses=[])
    act1.tachograph_card_number = act2.tachograph_card_number = "TESTCARD1"

    results = [(Path("file_a.ddd"), [act1]), (Path("file_b.ddd"), [act2])]

    result = _process_import_results(results, [], _test_user(), db)

    assert len(result["closed_period_candidates"]) == 1


def test_decline_closed_period_import_handles_duplicate_items_in_same_request(db, employee):
    """
    Reproducerer den rapporterede fejl: brugeren trykker "Nej, spring over"
    på en liste hvor samme vagt (samme medarbejder+starttid) optræder to
    gange. Uden fix crasher dette med en IntegrityError på det unikke index
    (employee_id, start_time), og HELE afvisningen mislykkes – ingen af
    vagterne huskes som sprunget over.
    """
    start = datetime(2026, 7, 15, 5, 27)
    end = datetime(2026, 7, 15, 16, 46)
    body = DeclineClosedPeriodRequest(items=[
        DeclinedCandidate(employee_id=employee.id, start_time=start.isoformat(), end_time=end.isoformat()),
        DeclinedCandidate(employee_id=employee.id, start_time=start.isoformat(), end_time=end.isoformat()),
    ])

    # Produktionens SessionLocal bruger autoflush=False (database/session.py) –
    # matcher det her, så testen rammer den samme betingelse som i praksis.
    db.autoflush = False
    result = decline_closed_period_import(body, _test_user(), db)

    assert result["declined"] == 1


def _file_backed_session_factory():
    """Rigtig fil-baseret SQLite (ikke :memory:), så to uafhængige sessioner/
    tråde kan pege på samme database – nødvendigt for at kunne reproducere en
    ægte race condition mellem to samtidige requests. `timeout` sætter SQLites
    busy-timeout, så en tråd der rammer databasens skrive-lås venter på den
    anden i stedet for straks at fejle med 'database is locked' – ligesom en
    rigtig samtidig anmodning ville."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(
        f"sqlite:///{tmp.name}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_concurrent_import_of_same_shift_does_not_duplicate_activity():
    """
    Reproducerer racet ved samtidig import med to RIGTIGE tråde: to samtidige
    import-requests (fx et dobbeltklik, eller to brugere der importerer
    overlappende filer) kan begge slå den samme vagt op og finde intet, FØR
    nogen af dem har committet – og begge forsøge at indsætte den. Uden en
    unik spærre i databasen ville det give to Activity-rækker for samme
    medarbejder+starttidspunkt+kilde (= dobbelttalte timer i lønnen).
    """
    import threading

    Session = _file_backed_session_factory()
    setup = Session()
    emp = Employee(
        employee_number="9001",
        first_name="Test",
        last_name="Chauffør",
        agreement_kind=AgreementKind.hourly_fixed,
        agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    setup.add(emp)
    setup.commit()
    emp_id = emp.id
    setup.close()

    start = datetime(2026, 8, 3, 5, 45)
    end = datetime(2026, 8, 3, 14, 30)

    barrier = threading.Barrier(2)
    outcomes = {}

    def _run(key):
        session = Session()
        emp_local = session.query(Employee).filter(Employee.id == emp_id).first()
        act = _parsed(start, end, segments=[(start, end, "work")], pauses=[])
        barrier.wait()  # begge tråde slår "existing" op ~samtidig
        try:
            result, _ = _import_activity(act, session, emp_local)
            session.commit()
            outcomes[key] = result
        except Exception as exc:
            session.rollback()
            outcomes[key] = f"crashed: {exc!r}"
        finally:
            session.close()

    t1 = threading.Thread(target=_run, args=("t1",))
    t2 = threading.Thread(target=_run, args=("t2",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    check = Session()
    total = (
        check.query(Activity)
        .filter(Activity.employee_id == emp_id, Activity.start_time == start)
        .count()
    )
    check.close()

    assert not any(v.startswith("crashed") for v in outcomes.values() if isinstance(v, str)), outcomes
    assert total == 1, f"forventede 1 aktivitet, fandt {total} – begge tråde: {outcomes}"


@pytest.fixture
def outside_home_dir():
    """Rigtig, men TOM mappe uden for hjemmemappen (direkte under drev-roden,
    fx C:\\) - IKKE selve drev-roden. Et fuldt rglob-scan af hele C:\\ i en
    test tager for evigt og er selve den bug, disse tests verificerer er
    rettet, så vi bruger en garanteret lille mappe i stedet."""
    outside_root = Path(Path.home().anchor)
    tmp = Path(tempfile.mkdtemp(dir=str(outside_root), prefix="lonsystem-test-"))
    assert not str(tmp).startswith(str(Path.home()))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_ddd_from_rejects_source_folder_outside_home(db, outside_home_dir):
    """
    source_folder skulle hidtil kun eksistere - man kunne angive fx "C:\\"
    og udløse et fuldt rekursivt scan af hele drevet. Nu skal stien være
    under den tilladte rod (Path.home(), se utils/safe_paths.py).
    """
    body = ImportFromRequest(source_folder=str(outside_home_dir))

    with pytest.raises(Exception) as exc_info:
        import_ddd_from(body, current_user=_test_user(), db=db)
    assert getattr(exc_info.value, "status_code", None) == 400


def test_import_ddd_from_skips_source_files_outside_home_as_error(db, outside_home_dir):
    """source_files uden for hjemmemappen skal fejle pr.-fil (tilføjes til
    errors), ikke stoppe hele importen - i modsætning til source_folder, som
    er ét samlet valg og derfor kan afvises helt."""
    outside_file = outside_home_dir / "fil.ddd"
    outside_file.write_bytes(b"")

    body = ImportFromRequest(source_files=[str(outside_file)])

    result = import_ddd_from(body, current_user=_test_user(), db=db)

    assert result["files_processed"] == 0
    assert any("hjemmemappe" in e for e in result["errors"])
