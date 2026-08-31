"""
Karakteriserings-tests for calculate_overtime() – systemets centrale og mest
rettede beregning (jf. de flere "bekræftet af bruger <dato>"-kommentarer i
overtime.py, herunder Jesper Rosengreen-sagen om midnat-håndtering). Der var
hidtil INGEN direkte test af denne funktion – al dækning skete indirekte via
integrationstests af hele lønberegningen, som ikke systematisk rammer
grænsetilfældene i selve vindues-/loft-logikken.

Disse tests låser den nuværende, allerede brugerbekræftede adfærd fast, så en
fremtidig ændring får et klart "dette brød noget"-signal her, i stedet for at
skulle genopdages i produktion.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime
from decimal import Decimal

from calculators.overtime import (
    calculate_overtime, OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY, OT_13_MAX,
)

_NO_RATES = {OT_BEFORE_KEY: Decimal("0"), OT_13_KEY: Decimal("0"), OT_EXTRA_KEY: Decimal("0")}


def test_shift_fully_within_normal_cap_gives_no_supplement():
    """06-18, under normaltidsloftet -> ren normaltid, intet tillæg."""
    result = calculate_overtime(
        datetime(2026, 6, 1, 7, 0), datetime(2026, 6, 1, 14, 0),  # 7 timer
        normal_daily_hours=Decimal("8"), rates=_NO_RATES,
    )
    assert result.total_hours == Decimal("7")
    assert result.normal_hours == Decimal("7")
    assert result.ot_before_hours == 0
    assert result.ot_13_hours == 0
    assert result.ot_extra_hours == 0
    assert result.normal_remaining_after == Decimal("1")


def test_shift_exceeding_day_window_cap_overflows_to_ot13():
    """06-18, over normaltidsloftet -> overløb til OT 1-3 (additivt, normal_hours dækker stadig alle timer)."""
    result = calculate_overtime(
        datetime(2026, 6, 1, 7, 0), datetime(2026, 6, 1, 17, 0),  # 10 timer
        normal_daily_hours=Decimal("8"), rates=_NO_RATES,
    )
    assert result.normal_hours == Decimal("10")  # alle arbejdede timer, tillæg er additive
    assert result.ot_13_hours == Decimal("2")
    assert result.ot_extra_hours == 0
    assert result.normal_remaining_after == Decimal("0")
    assert result.ot13_remaining_after == Decimal("1")


def test_before_window_gives_ot_before_supplement_without_touching_cap():
    """05-06 ("1 time før") er rent tillæg og fortærer ikke normaltids-loftet."""
    result = calculate_overtime(
        datetime(2026, 6, 1, 5, 0), datetime(2026, 6, 1, 6, 0),
        normal_daily_hours=Decimal("8"), rates=_NO_RATES,
    )
    assert result.ot_before_hours == Decimal("1")
    assert result.normal_remaining_after == Decimal("8")  # upåvirket


def test_evening_window_fills_ot13_then_overflows_to_extra():
    """18-21: OT 1-3 op til 3 timer, derefter Øvrigt overtid - og fortærer ikke normaltids-loftet."""
    result = calculate_overtime(
        datetime(2026, 6, 1, 18, 0), datetime(2026, 6, 1, 22, 0),  # 4 timer
        normal_daily_hours=Decimal("8"), rates=_NO_RATES,
    )
    assert result.ot_13_hours == OT_13_MAX
    assert result.ot_extra_hours == Decimal("1")
    assert result.normal_remaining_after == Decimal("8")  # upåvirket


def test_night_window_gives_ot_extra_without_touching_cap():
    """21-05 (nat) er Øvrigt overtid og fortærer ikke normaltids-loftet."""
    result = calculate_overtime(
        datetime(2026, 6, 1, 22, 0), datetime(2026, 6, 1, 23, 0),
        normal_daily_hours=Decimal("8"), rates=_NO_RATES,
    )
    assert result.ot_extra_hours == Decimal("1")
    assert result.normal_remaining_after == Decimal("8")  # upåvirket


def test_pause_is_subtracted_from_worked_hours():
    """Pauser fratrækkes i det tidsrum, de rent faktisk afholdes."""
    result = calculate_overtime(
        datetime(2026, 6, 1, 7, 0), datetime(2026, 6, 1, 15, 0),  # 8 timer brutto
        pause_intervals=[(datetime(2026, 6, 1, 12, 0), datetime(2026, 6, 1, 12, 30))],  # 30 min pause
        normal_daily_hours=Decimal("8"), rates=_NO_RATES,
    )
    assert result.total_hours == Decimal("7.5")
    assert result.normal_remaining_after == Decimal("0.5")


def test_cap_carries_over_between_two_activities_same_day():
    """Er dagen delt i flere godkendte aktiviteter, deles loftet mellem dem
    via normal_remaining/ot13_remaining i stedet for at nulstilles pr. aktivitet."""
    first = calculate_overtime(
        datetime(2026, 6, 1, 7, 0), datetime(2026, 6, 1, 12, 0),  # 5 timer
        normal_daily_hours=Decimal("8"), rates=_NO_RATES,
    )
    assert first.normal_remaining_after == Decimal("3")

    second = calculate_overtime(
        datetime(2026, 6, 1, 13, 0), datetime(2026, 6, 1, 17, 0),  # 4 timer
        normal_daily_hours=Decimal("8"), rates=_NO_RATES,
        normal_remaining=first.normal_remaining_after,
        ot13_remaining=first.ot13_remaining_after,
    )
    # De sidste 3 timer af loftet forbruges (0 tilbage), 1 times overløb til OT13
    assert second.normal_remaining_after == Decimal("0")
    assert second.ot_13_hours == Decimal("1")


def test_shift_crossing_midnight_resets_cap_to_next_days_own_hours():
    """
    Reproducerer Jesper Rosengreen-sagen: en vagt der krydser midnat splittes
    IKKE i separate aktiviteter, men for en medarbejder med et dagligt loft
    (hourly_fixed) skal loftet nulstille til den NYE dags eget garanterede
    timetal ved midnat - ikke fortsætte med at bruge den forrige dags
    (ubrugte) loft. Fredag aften -> lørdag morgen, hvor lørdag ikke har noget
    garanteret normaltimetal (next_day_normal_hours=0).
    """
    result = calculate_overtime(
        datetime(2026, 6, 5, 22, 0),  # fredag 22:00
        datetime(2026, 6, 6, 8, 0),   # lørdag 08:00
        normal_daily_hours=Decimal("8"),  # fredags normaltid
        next_day_normal_hours=Decimal("0"),  # lørdag: intet garanteret normaltimetal
        rates=_NO_RATES,
    )
    # Lørdagens dagtimer (06-08, 2 timer) skal IKKE dækkes af fredagens
    # ubrugte loft - de skal give OT13-tillæg, da lørdagens eget loft er 0.
    assert result.ot_13_hours == Decimal("2")


def test_shift_crossing_midnight_without_next_day_hours_keeps_old_cap():
    """
    Modsat tilfælde (dokumenteret som den GAMLE, forkerte fortolkning før
    Jesper Rosengreen-fixet): udelades next_day_normal_hours (fx den
    ugentlige pulje for hourly_flexible, hvor loftet IKKE er dagligt),
    bevares det oprindelige loft uændret over midnat - lørdagens dagtimer
    (06-08) dækkes da fejlagtigt af fredagens ubrugte loft, uden tillæg.
    (Nattetimerne 22-05 giver stadig Øvrigt overtid uanset loft-reset -
    det er kun dagtimernes 06-18-loft-forbrug, der er forskellen her.)
    """
    result = calculate_overtime(
        datetime(2026, 6, 5, 22, 0),
        datetime(2026, 6, 6, 8, 0),
        normal_daily_hours=Decimal("8"),
        rates=_NO_RATES,
        # next_day_normal_hours udeladt (None) -> loftet nulstilles ikke
    )
    assert result.ot_13_hours == Decimal("0")  # lørdagens 2 dagtimer "lånte" fejlagtigt af fredagens loft
    assert result.normal_remaining_after == Decimal("6")  # 8 - de 2 lørdags-dagtimer, ikke nulstillet


def test_supplement_amounts_are_hours_times_rate():
    """supplements-dict'et er timer × den relevante sats fra rates-parameteren."""
    result = calculate_overtime(
        datetime(2026, 6, 1, 5, 0), datetime(2026, 6, 1, 6, 0),  # 1 time "1 time før"
        normal_daily_hours=Decimal("8"),
        rates={OT_BEFORE_KEY: Decimal("44.54"), OT_13_KEY: Decimal("0"), OT_EXTRA_KEY: Decimal("0")},
    )
    assert result.supplements[OT_BEFORE_KEY] == Decimal("44.54")
    assert result.supplement_total() == Decimal("44.54")
