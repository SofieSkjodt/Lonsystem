"""
Overtidsberegning efter kravdokumentet "Ønsker til opsætning+funktioner".

Tre tillægstyper (satser fra "Overtid satser.xlsx"):
- "Overtid 1 time før":      arbejde kl. 05-06
- "Overtid 1-3 timer efter": arbejde kl. 18-21, samt timer ud over normaltid
                             i tidsrummet kl. 06-18
- "Øvrigt overtid":          arbejde kl. 21-05, samt overtidstimer ud over
                             de første 3 (bekræftet af bruger 10/6-2026)

Normaltid pr. dag kommer fra medarbejderens timefordeling (lige/ulige uger).
Alle arbejdstimer tæller med i normal_hours (kode 1), men de REGISTREREDE
normaltimer (7/7,5/8 t) kan kun forbruges i tidsrummet 06-18 – arbejde uden
for dette vindue (nat, "1 time før", aften) er altid rent tillæg og fortærer
ikke normaltids-loftet (bekræftet af bruger 2026-07-02).

Beregningen er daglig (pr. aktivitet).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from calculators.rates_loader import load_overtime_rates

OT_BEFORE_KEY = "Overtid 1 time før"
OT_13_KEY = "Overtid 1-3 timer efter"
OT_EXTRA_KEY = "Øvrigt overtid"

OT_13_MAX = Decimal("3")  # maks. 3 timer i "Overtid 1-3 timer efter"


@dataclass
class OvertimeResult:
    total_hours: Decimal = Decimal("0")
    normal_hours: Decimal = Decimal("0")      # uden tillæg
    ot_before_hours: Decimal = Decimal("0")   # Overtid 1 time før (05-06)
    ot_13_hours: Decimal = Decimal("0")       # Overtid 1-3 timer efter
    ot_extra_hours: Decimal = Decimal("0")    # Øvrigt overtid
    sh_kode8_hours: Decimal = Decimal("0")   # additiv supplement kode 8 på særlige dage
    sh_kode9_hours: Decimal = Decimal("0")   # additiv supplement kode 9 på særlige dage
    # Resterende normaltids-/OT13-loft EFTER denne aktivitet – videreføres til næste
    # aktivitet SAMME dag, når en dag er delt i flere godkendte aktiviteter, så loftet
    # deles for hele dagen i stedet for at blive nulstillet pr. aktivitet.
    normal_remaining_after: Decimal = Decimal("0")
    ot13_remaining_after: Decimal = Decimal("0")
    supplements: dict = field(default_factory=dict)

    def supplement_total(self) -> Decimal:
        return sum(self.supplements.values(), Decimal("0"))


def _window(dt: datetime) -> str:
    """Klassificér et tidspunkt efter tidsvindue."""
    h = dt.hour
    if 5 <= h < 6:
        return "before"      # 05-06
    if 6 <= h < 18:
        return "day"         # 06-18
    if 18 <= h < 21:
        return "evening"     # 18-21
    return "night"           # 21-05


def _segments(start: datetime, end: datetime):
    """Opdel ved hver hel time og midnat."""
    current = start
    while current < end:
        next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        seg_end = min(next_hour, end)
        yield current, seg_end
        current = seg_end


def _work_segments(work_intervals):
    """Time-opdelte segmenter for alle arbejdsintervaller (kronologisk)."""
    for w_start, w_end in work_intervals:
        yield from _segments(w_start, w_end)


def _subtract_pauses(
    start: datetime, end: datetime,
    pauses: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """
    Returnér arbejdsintervaller = [start, end] minus pauseintervaller.
    Pausen fratrækkes dermed i det tidsrum, den faktisk afholdes.
    """
    work = [(start, end)]
    for p_start, p_end in sorted(pauses):
        new_work = []
        for w_start, w_end in work:
            if p_end <= w_start or p_start >= w_end:
                new_work.append((w_start, w_end))  # ingen overlap
                continue
            if p_start > w_start:
                new_work.append((w_start, p_start))
            if p_end < w_end:
                new_work.append((p_end, w_end))
        work = new_work
    return work


def calculate_overtime(
    start: datetime,
    end: datetime,
    normal_daily_hours: Decimal,
    pause_intervals: list[tuple[datetime, datetime]] | None = None,
    rates: dict | None = None,
    normal_remaining: Decimal | None = None,
    ot13_remaining: Decimal | None = None,
    next_day_normal_hours: Decimal | None = None,
) -> OvertimeResult:
    """
    Beregn timefordelingen for én aktivitet (ét skift).
    normal_daily_hours: medarbejderens normaltid for den pågældende dag
    (fra timefordelingen, lige/ulige uge).
    pause_intervals: faktiske pauser – fratrækkes i det tidsrum de afholdes,
    så der ikke gives tillæg for tid, hvor der ikke arbejdes.
    normal_remaining/ot13_remaining: valgfrit resterende loft videreført fra en
    tidligere aktivitet SAMME dag (når dagen er delt i flere godkendte
    aktiviteter) – uden angivelse startes der forfra fra
    normal_daily_hours/OT_13_MAX.
    next_day_normal_hours: en vagt der krydser midnat splittes IKKE i separate
    aktiviteter (bekræftet 2026-07-02), men for medarbejdere med et DAGLIGT
    loft (hourly_fixed) skal OT-1-3-loftet nulstilles til friske 3 timer ved
    midnat for HVER kalenderdag, og normaltids-loftet skifter til den nye dags
    eget garanterede timetal – ellers bliver fx en lørdags-fortsættelse af en
    fredagsvagt fejlagtigt dækket af fredagens (ubrugte) normaltids-loft, selv
    om lørdag ikke har noget loft at forbruge (bekræftet af bruger 2026-08-17,
    jf. Jesper Rosengreen-sagen). Kun angivet af kaldere med et dagligt loft –
    ved None (fx den ugentlige 37t/5t-pulje for hourly_flexible) bevares det
    oprindelige loft helt uændret over midnat, som hidtil.
    """
    result = OvertimeResult()
    if rates is None:
        rates = load_overtime_rates()

    normal_remaining = Decimal(str(normal_daily_hours)) if normal_remaining is None else normal_remaining
    ot13_remaining = OT_13_MAX if ot13_remaining is None else ot13_remaining

    work_intervals = _subtract_pauses(start, end, pause_intervals or [])

    active_date = start.date()

    for seg_start, seg_end in _work_segments(work_intervals):
        duration = Decimal(str((seg_end - seg_start).total_seconds())) / 3600
        if duration <= 0:
            continue

        if seg_start.date() != active_date:
            active_date = seg_start.date()
            if next_day_normal_hours is not None:
                normal_remaining = Decimal(str(next_day_normal_hours))
                ot13_remaining = OT_13_MAX

        result.total_hours += duration

        window = _window(seg_start)

        # Alle arbejdede timer giver normal løn (kode 1). Tillæg er additive.
        result.normal_hours += duration

        if window == "night":
            # 21-05: Øvrigt overtid-tillæg. Registreret normaltid kan kun
            # forbruges i tidsrummet 06-18, så nattetimer fortærer ikke loftet.
            result.ot_extra_hours += duration
        elif window == "before":
            # 05-06: "Overtid 1 time før" regnes separat og fortærer ikke
            # normaltids-loftet (bekræftet af bruger 2026-07-02).
            result.ot_before_hours += duration
        elif window == "evening":
            # 18-21: OT 1-3-tillæg (op til 3 timer), derefter Øvrig-tillæg.
            # Ligger uden for 06-18, så det fortærer heller ikke normaltids-loftet.
            in_13 = min(duration, ot13_remaining)
            result.ot_13_hours += in_13
            ot13_remaining -= in_13
            overflow = duration - in_13
            if overflow > 0:
                result.ot_extra_hours += overflow
        else:
            # 06-18: forbruger normaltid; overtid ud over kap → supplement-tillæg
            as_normal = min(duration, normal_remaining)
            normal_remaining -= as_normal
            rest = duration - as_normal
            if rest > 0:
                in_13 = min(rest, ot13_remaining)
                result.ot_13_hours += in_13
                ot13_remaining -= in_13
                overflow = rest - in_13
                if overflow > 0:
                    result.ot_extra_hours += overflow

    result.supplements = {
        OT_BEFORE_KEY: result.ot_before_hours * rates.get(OT_BEFORE_KEY, Decimal("0")),
        OT_13_KEY:     result.ot_13_hours     * rates.get(OT_13_KEY,     Decimal("0")),
        OT_EXTRA_KEY:  result.ot_extra_hours  * rates.get(OT_EXTRA_KEY,  Decimal("0")),
    }
    result.normal_remaining_after = normal_remaining
    result.ot13_remaining_after = ot13_remaining
    return result
