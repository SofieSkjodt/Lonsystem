"""
Dag-klassifikation og lønberegning for søndage og helligdage.

Regler bekræftet af bruger 2026-06-23 (se memory/project_lonsystem_son_helligdage.md),
lørdags-særreglen fjernet igen 2026-07-02 (se memory/project_lonsystem_ot_before_kvote.md):
- Helligdag trumfer altid lørdag/søndag
- Tids-tillæg tilsidesættes på søndage/helligdage – IKKE på lørdage
- Lørdag er ikke længere en "særlig dag" beregningsmæssigt – den går altid
  gennem calculate_overtime() med lørdagens egne garanterede timer som loft
- SH-betaling (kode 4/63) er additiv – lægges oveni kørselsløn
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from calculators.overtime import OT_13_MAX, OvertimeResult, _subtract_pauses


class DayType(Enum):
    NORMAL = "normal"
    SATURDAY = "saturday"
    SUNDAY = "sunday"
    HOLIDAY_FULL = "holiday_full"
    HOLIDAY_HALF_1MAJ = "holiday_half_1maj"
    HOLIDAY_HALF_GRUNDLOV = "holiday_half_grundlov"


def classify_day(d: date, holiday_map: dict) -> DayType:
    """
    Klassificér en dato som dagtype.
    holiday_map: {date: Holiday-objekt} med .half_day_from og .name.
    Helligdag trumfer lørdag/søndag.
    """
    hol = holiday_map.get(d)
    if hol is not None:
        if hol.half_day_from is not None:
            if "maj" in hol.name.lower():
                return DayType.HOLIDAY_HALF_1MAJ
            return DayType.HOLIDAY_HALF_GRUNDLOV
        return DayType.HOLIDAY_FULL
    wd = d.weekday()  # 0=mandag … 5=lørdag, 6=søndag
    if wd == 5:
        return DayType.SATURDAY
    if wd == 6:
        return DayType.SUNDAY
    return DayType.NORMAL


def compute_sh_hours(day_type: DayType, guaranteed_hours: Decimal) -> Decimal:
    """
    Beregnede SH-timer (kode 4/63) for en dag.
    Lørdage giver ingen SH-betaling.
    """
    if day_type in (DayType.SUNDAY, DayType.HOLIDAY_FULL):
        return guaranteed_hours
    if day_type in (DayType.HOLIDAY_HALF_1MAJ, DayType.HOLIDAY_HALF_GRUNDLOV):
        return guaranteed_hours / Decimal("2")
    return Decimal("0")


def _hours_after_noon(work_intervals: list[tuple[datetime, datetime]], noon: datetime) -> Decimal:
    """Antal arbejdstimer i work_intervals der falder efter 'noon'."""
    total = Decimal("0")
    for ws, we in work_intervals:
        if we <= noon:
            continue
        effective_start = max(ws, noon)
        total += Decimal(str((we - effective_start).total_seconds())) / Decimal("3600")
    return total


def _total_work_hours(work_intervals: list[tuple[datetime, datetime]]) -> Decimal:
    return sum(
        Decimal(str((we - ws).total_seconds())) / Decimal("3600")
        for ws, we in work_intervals
    )


def calculate_special_day_overtime(
    start: datetime,
    end: datetime,
    day_type: DayType,
    pause_intervals: list | None = None,
    kode8_remaining: Decimal | None = None,
) -> OvertimeResult:
    """
    Beregn timefordeling for en kørsel på en søndag/helligdag.

    Lørdag regnes IKKE længere som en særlig dag (bekræftet af bruger
    2026-07-02) – lørdag går altid gennem calculate_overtime() med lørdagens
    egne garanterede timer (typisk 0) som loft, ligesom en almindelig hverdag.
    "Uden garanterede timer"-lørdage rammer dermed automatisk den normale
    dagvindues-logik (kode 8 for de første op til 3 dagtimer, kode 9 for
    resten), da normaltids-loftet er 0.

    Returnerer OvertimeResult hvor:
    - normal_hours  = alle kørte timer (kode 1)
    - sh_kode8_hours = additivt supplement kode 8 (OT_13-sats)
    - sh_kode9_hours = additivt supplement kode 9 (OT_EXTRA-sats)
    - ot_before/ot_13/ot_extra = altid 0 (tids-tillæg tilsidesættes)

    kode8_remaining: valgfrit resterende 3-timers kode 8-loft videreført fra en
    tidligere aktivitet SAMME særlige dag (når dagen er delt i flere godkendte
    aktiviteter) – uden angivelse startes der forfra fra OT_13_MAX (3 timer).
    Videreføres til den næste aktivitet via result.ot13_remaining_after.
    """
    result = OvertimeResult()
    work_intervals = _subtract_pauses(start, end, pause_intervals or [])
    total_driven = _total_work_hours(work_intervals)

    result.total_hours = total_driven
    result.normal_hours = total_driven  # alle kørte timer → kode 1

    remaining8 = OT_13_MAX if kode8_remaining is None else kode8_remaining

    if day_type in (DayType.SUNDAY, DayType.HOLIDAY_FULL):
        # Alle kørte timer får kode 9 supplement
        result.sh_kode9_hours = total_driven

    elif day_type == DayType.HOLIDAY_HALF_1MAJ:
        # Timer efter kl. 12:00: første (resterende) 3 → kode 8, resten → kode 9
        # Forudsætning: kørsel spænder ikke over midnat (særlige dage er altid ét-dags-aktiviteter)
        noon = start.replace(hour=12, minute=0, second=0, microsecond=0)
        after_noon = _hours_after_noon(work_intervals, noon)
        kode8 = min(after_noon, remaining8)
        kode9 = max(Decimal("0"), after_noon - kode8)
        result.sh_kode8_hours = kode8
        result.sh_kode9_hours = kode9
        remaining8 -= kode8

    elif day_type == DayType.HOLIDAY_HALF_GRUNDLOV:
        # Timer efter kl. 12:00: alle → kode 9
        # Forudsætning: kørsel spænder ikke over midnat (særlige dage er altid ét-dags-aktiviteter)
        noon = start.replace(hour=12, minute=0, second=0, microsecond=0)
        result.sh_kode9_hours = _hours_after_noon(work_intervals, noon)

    result.ot13_remaining_after = remaining8
    return result
