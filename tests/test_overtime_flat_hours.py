from datetime import datetime
from decimal import Decimal

from calculators.overtime import calculate_flat_hours


def test_flat_hours_counts_all_worked_time_as_normal():
    start = datetime(2026, 8, 24, 6, 0)
    end = datetime(2026, 8, 24, 22, 0)  # 16 timer, ville normalt give aften/nat-tillæg

    result = calculate_flat_hours(start, end)

    assert result.total_hours == Decimal("16")
    assert result.normal_hours == Decimal("16")
    assert result.ot_before_hours == Decimal("0")
    assert result.ot_13_hours == Decimal("0")
    assert result.ot_extra_hours == Decimal("0")
    assert result.sh_kode8_hours == Decimal("0")
    assert result.sh_kode9_hours == Decimal("0")


def test_flat_hours_subtracts_pauses():
    start = datetime(2026, 8, 24, 8, 0)
    end = datetime(2026, 8, 24, 16, 0)  # 8 timer
    pauses = [(datetime(2026, 8, 24, 12, 0), datetime(2026, 8, 24, 12, 30))]  # 0,5 t pause

    result = calculate_flat_hours(start, end, pauses)

    assert result.total_hours == Decimal("7.5")
    assert result.normal_hours == Decimal("7.5")
