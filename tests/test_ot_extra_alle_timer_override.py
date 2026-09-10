import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime
from decimal import Decimal

from calculators.overtime import (
    calculate_flat_hours, override_ot_extra_alle_timer, OT_EXTRA_KEY,
)
from calculators.day_type import calculate_special_day_overtime, DayType

_RATES = {OT_EXTRA_KEY: Decimal("50")}


def test_flat_hours_override_moves_everything_to_normal_plus_ot_extra():
    """Hverdag/lørdag: 10 timer (ville normalt give aften/nat-tillæg) -> alt bliver normal + kode 9."""
    result = calculate_flat_hours(
        datetime(2026, 9, 10, 6, 0), datetime(2026, 9, 10, 16, 0),  # 10 timer
    )
    overridden = override_ot_extra_alle_timer(result, is_special_day=False, rates=_RATES)

    assert overridden.total_hours == Decimal("10")
    assert overridden.normal_hours == Decimal("10")
    assert overridden.ot_before_hours == Decimal("0")
    assert overridden.ot_13_hours == Decimal("0")
    assert overridden.ot_extra_hours == Decimal("10")
    assert overridden.supplements[OT_EXTRA_KEY] == Decimal("500")  # 10 * 50


def test_special_day_override_forces_kode9_for_whole_day_never_kode8():
    """1. maj: vagt 08-16 (4t før, 4t efter kl. 12) -> uden override ville de 4
    eftermiddagstimer normalt give kode 8 (op til 3t) + kode 9 (resten).
    Med override: ALLE 8 timer -> kode 9, aldrig kode 8."""
    result = calculate_special_day_overtime(
        datetime(2026, 5, 1, 8, 0), datetime(2026, 5, 1, 16, 0),
        DayType.HOLIDAY_HALF_1MAJ,
    )
    # Uden override: kode8=3, kode9=1 (kontrollerer testens forudsætning)
    assert result.sh_kode8_hours == Decimal("3")
    assert result.sh_kode9_hours == Decimal("1")

    overridden = override_ot_extra_alle_timer(result, is_special_day=True, rates=_RATES)

    assert overridden.total_hours == Decimal("8")
    assert overridden.normal_hours == Decimal("8")
    assert overridden.sh_kode8_hours == Decimal("0")
    assert overridden.sh_kode9_hours == Decimal("8")
    assert overridden.ot_extra_hours == Decimal("0")  # denne sti bruger sh_kode9, ikke ot_extra
