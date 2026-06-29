import sys
from datetime import datetime
from decimal import Decimal
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from calculators.overtime import calculate_overtime

NORMAL = Decimal("7")

def check(name, start, end, expected):
    r = calculate_overtime(start, end, NORMAL)
    actual = (r.ot_before_hours, r.normal_hours, r.ot_13_hours, r.ot_extra_hours)
    ok = all(a == Decimal(str(e)) for a, e in zip(actual, expected))
    print(f"{name}: {'OK' if ok else 'FEJL'} - foer={r.ot_before_hours} normal={r.normal_hours} ot13={r.ot_13_hours} oevrig={r.ot_extra_hours} (forventet {expected})")

def check_p(name, start, end, pauses, expected):
    r = calculate_overtime(start, end, NORMAL, pauses)
    actual = (r.ot_before_hours, r.normal_hours, r.ot_13_hours, r.ot_extra_hours)
    ok = all(a == Decimal(str(e)) for a, e in zip(actual, expected))
    print(f"{name}: {'OK' if ok else 'FEJL'} - foer={r.ot_before_hours} normal={r.normal_hours} ot13={r.ot_13_hours} oevrig={r.ot_extra_hours} (forventet {expected})")

# normal_hours = ALLE arbejdede timer (tillæg er additive oven på normal løn)

# Eksempel 1: kl. 4-14 (10t) -> normal=10, foer=1, ot13=3, oevrig=1
# Nattimer (04-05) og førtimer (05-06) giver normal løn + tillæg
check("Eksempel 1", datetime(2026, 6, 8, 4), datetime(2026, 6, 8, 14), (1, 10, 3, 1))
# Eksempel 2: kl. 8-18 (10t) -> normal=10, foer=0, ot13=3, oevrig=0
check("Eksempel 2", datetime(2026, 6, 8, 8), datetime(2026, 6, 8, 18), (0, 10, 3, 0))
# Eksempel 3: kl. 10-20 (10t) -> normal=10, foer=0, ot13=3, oevrig=0
check("Eksempel 3", datetime(2026, 6, 8, 10), datetime(2026, 6, 8, 20), (0, 10, 3, 0))

D = datetime
# Pause i normal-tidsrummet: 4-14 m. pause 12:00-12:30 -> ot13=2.5, normal=9.5
check_p("Pause 06-18 ", D(2026,6,8,4), D(2026,6,8,14), [(D(2026,6,8,12), D(2026,6,8,12,30))], (1, "9.5", "2.5", 1))
# Pause i 18-21-tillægget: 10-21 m. pause 19:00-19:30 -> normal=10.5, ot13=3, oevrig=0.5
check_p("Pause 18-21 ", D(2026,6,8,10), D(2026,6,8,21), [(D(2026,6,8,19), D(2026,6,8,19,30))], (0, "10.5", 3, "0.5"))
# Pause om natten: 21-03 m. pause 23:00-23:30 -> normal=5.5, oevrig=5.5
check_p("Pause 21-05 ", D(2026,6,8,21), D(2026,6,9,3), [(D(2026,6,8,23), D(2026,6,8,23,30))], (0, "5.5", 0, "5.5"))
# Pause kl. 05-06: 5-13 m. pause 05:30-05:45 -> foer=0.75, normal=7.75, ot13=0.75
check_p("Pause 05-06 ", D(2026,6,8,5), D(2026,6,8,13), [(D(2026,6,8,5,30), D(2026,6,8,5,45))], ("0.75", "7.75", "0.75", 0))
