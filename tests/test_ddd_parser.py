import struct
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime, timedelta

from parsers.ddd_parser import (
    _build_activities, _utc_to_local, ACTIVITY_REST, ACTIVITY_WORK, ACTIVITY_DRIVING,
)


def _pack(changes):
    """changes: list af (minut_fra_midnat, aktivitet) for driver-slot (slot=0)."""
    return b"".join(struct.pack(">H", (activity & 0x3) << 11 | (minute & 0x7FF))
                     for minute, activity in changes)


def test_short_mid_shift_readout_flagged_incomplete_even_with_nonzero_km():
    """
    Reproducerer Anders Jersild Nielsen 31/7: kortet udlæses midt i vagten
    (kun 1t23m data), men km-distancen for dagen er allerede skrevet (114),
    så det gamle "distance==0"-krav overså den. Skal stadig markeres
    sandsynligvis ufuldstændig ud fra den korte varighed.
    """
    day = datetime(2026, 7, 31)
    changes = [(0, ACTIVITY_REST), (274, ACTIVITY_WORK), (357, ACTIVITY_WORK)]
    daily_records = [(day, 114, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].is_likely_incomplete is True


def test_full_length_shift_ending_non_rest_not_flagged():
    """
    Modsat tilfælde: en vagt på ni timer, der (fordi chaufføren tog kortet
    ud lige efter arbejdet) heller ikke slutter i hvil, og hvor km allerede
    er skrevet – skal IKKE markeres ufuldstændig, da varigheden er en hel
    normal arbejdsdag.
    """
    day = datetime(2026, 7, 31)
    changes = [(0, ACTIVITY_REST), (274, ACTIVITY_WORK), (274 + 540, ACTIVITY_WORK)]
    daily_records = [(day, 320, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].is_likely_incomplete is False


def test_zero_distance_short_shift_still_flagged():
    """Den oprindelige, allerede bekræftede sag (km==0) skal stadig virke."""
    day = datetime(2026, 8, 3)
    changes = [(0, ACTIVITY_REST), (345, ACTIVITY_WORK), (485, ACTIVITY_DRIVING)]
    daily_records = [(day, 0, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].is_likely_incomplete is True


def test_full_shift_ending_in_rest_not_flagged():
    """En vagt der afsluttes normalt (ender i hvil) skal aldrig markeres
    ufuldstændig, uanset varighed eller km-distance."""
    day = datetime(2026, 7, 31)
    changes = [(0, ACTIVITY_REST), (274, ACTIVITY_WORK), (357, ACTIVITY_REST), (400, ACTIVITY_REST)]
    daily_records = [(day, 0, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].is_likely_incomplete is False


def test_stale_minute_zero_status_skipped_after_long_gap():
    """
    Reproducerer Peter Mike Rasmussen 28/7: forrige dags reelle vagt slutter
    kl. 17:40 (minut 1060). Næste dags record starter kl. 00:00 med en
    videreført "arbejde"-status, der ikke ændrer sig før kl. 05:00 (minut
    300) – over 8 timer efter forrige vagts afslutning. Den fastfrosne
    status skal springes over, og vagten skal starte ved den næste RIGTIGE
    registrering (05:00), ikke ved midnat.
    """
    day1 = datetime(2026, 7, 27)
    day1_changes = [(0, ACTIVITY_REST), (300, ACTIVITY_WORK), (1060, ACTIVITY_WORK)]
    day2 = day1 + timedelta(days=1)
    day2_changes = [(0, ACTIVITY_WORK), (300, ACTIVITY_WORK), (310, ACTIVITY_DRIVING), (700, ACTIVITY_WORK)]
    daily_records = [
        (day1, 200, _pack(day1_changes)),
        (day2, 200, _pack(day2_changes)),
    ]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    expected_start = _utc_to_local(day2 + timedelta(minutes=300))
    day2_shift = next(a for a in acts if a.start_time.date() == expected_start.date())
    assert day2_shift.start_time == expected_start


def test_minute_zero_status_kept_when_gap_since_prior_shift_is_short():
    """
    Modsat tilfælde: forrige dags reelle vagt slutter sent (kl. 23:20,
    minut 1400) – kun 40 minutter før næste dags minut 0. Her ligner den
    videreførte status en ægte fortsættelse af en vagt, der går over
    midnat, og skal IKKE springes over.
    """
    day1 = datetime(2026, 7, 27)
    day1_changes = [(0, ACTIVITY_REST), (300, ACTIVITY_WORK), (1400, ACTIVITY_WORK)]
    day2 = day1 + timedelta(days=1)
    day2_changes = [(0, ACTIVITY_WORK), (300, ACTIVITY_WORK), (310, ACTIVITY_DRIVING), (700, ACTIVITY_WORK)]
    daily_records = [
        (day1, 200, _pack(day1_changes)),
        (day2, 200, _pack(day2_changes)),
    ]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    # Vagten bygger bro over midnat, så det er ÉN sammenhængende aktivitet
    # der starter dagen før og slutter dagen efter, ikke en ny startende kl. 00:00.
    assert len(acts) == 1
    assert acts[0].start_time.date() == _utc_to_local(day1 + timedelta(minutes=300)).date()
    assert acts[0].end_time == _utc_to_local(day2 + timedelta(minutes=700))


def test_entire_day_becomes_ghost_when_only_stale_status_and_nothing_real():
    """
    Reproducerer Jesper Frederiksen 16/5: efter at den fastfrosne
    minut-0-status er sprunget over, er der INGEN reel aktivitet tilbage
    den dag (kortet blev aldrig rigtig brugt). Dagen skal forsvinde helt
    som selvstændig vagt, ikke krympe til en kort spøgelsesvagt.
    """
    day1 = datetime(2026, 7, 27)
    day1_changes = [(0, ACTIVITY_REST), (300, ACTIVITY_WORK), (1060, ACTIVITY_WORK)]
    day2 = day1 + timedelta(days=1)
    day2_changes = [(0, ACTIVITY_WORK), (300, ACTIVITY_WORK)]  # ingen reel aktivitet efter minut 300
    daily_records = [
        (day1, 200, _pack(day1_changes)),
        (day2, 0, _pack(day2_changes)),
    ]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert all(a.start_time.date() != day2.date() for a in acts)
