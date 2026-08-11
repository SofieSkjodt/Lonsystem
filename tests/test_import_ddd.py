import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path
from datetime import datetime
from decimal import Decimal

from database.models import ActivityStatus, PayPeriodStatus, AppUser
from parsers.ddd_parser import ParsedActivity
from calculators.pay_period import get_or_create_period_for_date
from routers.import_ddd import _import_activity, _process_import_results, decline_closed_period_import, DeclineClosedPeriodRequest, DeclinedCandidate
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
