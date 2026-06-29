# Søn/Helligdage Lønberegning – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementer korrekte lønregler for lørdage, søndage og helligdage i `_calculate_employee()` — SH-betaling (kode 4/63), dag-type-specifik overtidsberegning og korrekt CSV-output til Danløn.

**Architecture:** En ny `app/calculators/day_type.py` klassificerer en dato som normal/lørdag/søndag/helligdag og beregner per-dag SH-timer og særlig overtid. `OvertimeResult` udvides med to additive supplement-felter (`sh_kode8_hours`, `sh_kode9_hours`). `_calculate_employee()` i `payroll_router.py` slår helligdage op fra DB, bruger den nye klassifikation per dag og akkumulerer SH-totaler i result-dict. CSV-eksporten tilføjer SH-rækker og fusionerer supplement-timerne med de eksisterende OT-rækker.

**Tech Stack:** Python 3.11, SQLAlchemy 2, FastAPI, SQLite (WAL), Decimal-aritmetik

## Global Constraints

- Kode 4 = SH-betaling fuldlønnet; kode 63 = SH-betaling timelønnet
- Kode 8 = overtid 1-3 timer (OT_13_KEY); kode 9 = øvrig overtid (OT_EXTRA_KEY)
- SH-betaling er **additiv** — lægges oveni kørselsløn
- Helligdag trumfer altid lørdag/søndag
- Tids-tillæg (before/evening/night windows) tilsidesættes på alle særlige dage (lørdag, søndag, helligdage)
- Timelønnet: `emp.fuldloennet == False`; fuldlønnet: `emp.fuldloennet == True`
- Lørdag med garanterede timer: normal dag — kun kode 1, ingen tillæg
- Lørdag uden garanterede timer + kørsel: kode 1 + kode 8 (første 3t) + kode 9 (resten)
- Søndag / andre helligdage: alle garanterede timer → SH; kørsel → kode 1 + kode 9
- 1. maj: garanti/2 → SH; kørsel FØR 12:00 → kode 1; EFTER 12:00: første 3t → kode 8, resten → kode 9
- Grundlovsdag: garanti/2 → SH; kørsel FØR 12:00 → kode 1; EFTER 12:00: alle → kode 9
- Ingen tests-mappe i projektet — verifikation sker med manuel server-genstart + Python-CLI-checks
- Servernstart: `cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

---

## Berørte filer

| Fil | Ændring |
|-----|---------|
| `app/calculators/overtime.py` | Tilføj `sh_kode8_hours` og `sh_kode9_hours` til `OvertimeResult` |
| `app/calculators/day_type.py` | **Ny fil**: `DayType`, `classify_day`, `compute_sh_hours`, `calculate_special_day_overtime` |
| `app/calculators/pay_rates.py` | Tilføj `DANLOEN_CODE_SH_FULDLOENNET = "4"` og `DANLOEN_CODE_SH_TIMELOENNET = "63"` |
| `app/database/session.py` | Tilføj `_ensure_sh_pay_types()` + kald fra `init_db()` |
| `app/routers/payroll_router.py` | `_calculate_employee()`: holiday-lookup, dag-klassifikation, SH-totaler, ny `day_kr`-formel; CSV: SH-rækker + fusioner |

---

### Task 1: Udvid `OvertimeResult` og opret dag-type-beregner

**Files:**
- Modify: `app/calculators/overtime.py` — tilføj to felter til `OvertimeResult`
- Create: `app/calculators/day_type.py` — ny fil med al dag-type-logik

**Interfaces:**
- Produces:
  - `OvertimeResult.sh_kode8_hours: Decimal` (default `Decimal("0")`)
  - `OvertimeResult.sh_kode9_hours: Decimal` (default `Decimal("0")`)
  - `DayType` enum med værdierne `NORMAL`, `SATURDAY`, `SUNDAY`, `HOLIDAY_FULL`, `HOLIDAY_HALF_1MAJ`, `HOLIDAY_HALF_GRUNDLOV`
  - `classify_day(d: date, holiday_map: dict[date, Any]) -> DayType`
  - `compute_sh_hours(day_type: DayType, guaranteed_hours: Decimal) -> Decimal`
  - `calculate_special_day_overtime(start: datetime, end: datetime, day_type: DayType, guaranteed_hours: Decimal, pause_intervals: list) -> OvertimeResult`

- [ ] **Step 1: Tilføj `sh_kode8_hours` og `sh_kode9_hours` til `OvertimeResult` i `app/calculators/overtime.py`**

Find `@dataclass`-blokken for `OvertimeResult` (linje ~31). Den slutter med:
```python
    supplements: dict = field(default_factory=dict)
```

Tilføj de to nye felter **inden** `supplements`:
```python
@dataclass
class OvertimeResult:
    total_hours: Decimal = Decimal("0")
    normal_hours: Decimal = Decimal("0")
    ot_before_hours: Decimal = Decimal("0")
    ot_13_hours: Decimal = Decimal("0")
    ot_extra_hours: Decimal = Decimal("0")
    sh_kode8_hours: Decimal = Decimal("0")   # additiv supplement kode 8 på særlige dage
    sh_kode9_hours: Decimal = Decimal("0")   # additiv supplement kode 9 på særlige dage
    supplements: dict = field(default_factory=dict)
```

- [ ] **Step 2: Verificér at eksisterende kode ikke bryder**

Kør i `app/`-mappen:
```
python -c "from calculators.overtime import OvertimeResult, calculate_overtime; from datetime import datetime; from decimal import Decimal; r = calculate_overtime(datetime(2026,6,23,8,0), datetime(2026,6,23,16,0), Decimal('8'), []); print(r.normal_hours, r.sh_kode8_hours, r.sh_kode9_hours)"
```
Forventet output: `8 0 0` (de nye felter er 0 på normale dage — ingen regression).

- [ ] **Step 3: Opret `app/calculators/day_type.py`**

```python
"""
Dag-klassifikation og lønberegning for lørdage, søndage og helligdage.

Regler bekræftet af bruger 2026-06-23 (se memory/project_lonsystem_son_helligdage.md):
- Helligdag trumfer altid lørdag/søndag
- Tids-tillæg tilsidesættes på alle særlige dage
- SH-betaling (kode 4/63) er additiv – lægges oveni kørselsløn
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from calculators.overtime import OvertimeResult


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


def _subtract_pauses(
    start: datetime, end: datetime,
    pauses: list,
) -> list:
    work = [(start, end)]
    for p_start, p_end in sorted(pauses):
        new_work = []
        for w_start, w_end in work:
            if p_end <= w_start or p_start >= w_end:
                new_work.append((w_start, w_end))
                continue
            if p_start > w_start:
                new_work.append((w_start, p_start))
            if p_end < w_end:
                new_work.append((p_end, w_end))
        work = new_work
    return work


def _hours_after_noon(work_intervals: list, noon: datetime) -> Decimal:
    """Antal arbejdstimer i work_intervals der falder efter 'noon'."""
    total = Decimal("0")
    for ws, we in work_intervals:
        if we <= noon:
            continue
        effective_start = max(ws, noon)
        total += Decimal(str((we - effective_start).total_seconds())) / Decimal("3600")
    return total


def _total_work_hours(work_intervals: list) -> Decimal:
    return sum(
        Decimal(str((we - ws).total_seconds())) / Decimal("3600")
        for ws, we in work_intervals
    )


def calculate_special_day_overtime(
    start: datetime,
    end: datetime,
    day_type: DayType,
    guaranteed_hours: Decimal,
    pause_intervals: list | None = None,
) -> OvertimeResult:
    """
    Beregn timefordeling for en kørsel på en særlig dag.

    Returnerer OvertimeResult hvor:
    - normal_hours  = alle kørte timer (kode 1)
    - sh_kode8_hours = additivt supplement kode 8 (OT_13-sats)
    - sh_kode9_hours = additivt supplement kode 9 (OT_EXTRA-sats)
    - ot_before/ot_13/ot_extra = altid 0 (tids-tillæg tilsidesættes)
    """
    result = OvertimeResult()
    work_intervals = _subtract_pauses(start, end, pause_intervals or [])
    total_driven = _total_work_hours(work_intervals)

    result.total_hours = total_driven
    result.normal_hours = total_driven  # alle kørte timer → kode 1

    if day_type in (DayType.SUNDAY, DayType.HOLIDAY_FULL):
        # Alle kørte timer får kode 9 supplement
        result.sh_kode9_hours = total_driven

    elif day_type == DayType.HOLIDAY_HALF_1MAJ:
        # Timer efter kl. 12:00: første 3 → kode 8, resten → kode 9
        noon = start.replace(hour=12, minute=0, second=0, microsecond=0)
        after_noon = _hours_after_noon(work_intervals, noon)
        kode8 = min(after_noon, Decimal("3"))
        kode9 = max(Decimal("0"), after_noon - Decimal("3"))
        result.sh_kode8_hours = kode8
        result.sh_kode9_hours = kode9

    elif day_type == DayType.HOLIDAY_HALF_GRUNDLOV:
        # Timer efter kl. 12:00: alle → kode 9
        noon = start.replace(hour=12, minute=0, second=0, microsecond=0)
        result.sh_kode9_hours = _hours_after_noon(work_intervals, noon)

    elif day_type == DayType.SATURDAY:
        if guaranteed_hours == Decimal("0"):
            # Ingen garanterede timer: første 3 kørte timer → kode 8, resten → kode 9
            kode8 = min(total_driven, Decimal("3"))
            kode9 = max(Decimal("0"), total_driven - Decimal("3"))
            result.sh_kode8_hours = kode8
            result.sh_kode9_hours = kode9
        # Med garanterede timer: kun kode 1, ingen supplements

    return result
```

- [ ] **Step 4: Verificér dag-type-funktionerne**

```
python -c "
from datetime import date, datetime
from decimal import Decimal
from calculators.day_type import classify_day, compute_sh_hours, calculate_special_day_overtime, DayType

class FakeHol:
    def __init__(self, name, hdf): self.name=name; self.half_day_from=hdf

hmap = {
    date(2026, 1, 1): FakeHol('Nytårsdag', None),
    date(2026, 5, 1): FakeHol('1. maj', '12:00'),
    date(2026, 6, 5): FakeHol('Grundlovsdag', '12:00'),
}

# Klassifikation
print(classify_day(date(2026, 6, 22), hmap))  # Mandag → NORMAL
print(classify_day(date(2026, 6, 20), hmap))  # Lørdag → SATURDAY
print(classify_day(date(2026, 6, 21), hmap))  # Søndag → SUNDAY
print(classify_day(date(2026, 1, 1), hmap))   # Nytårsdag → HOLIDAY_FULL
print(classify_day(date(2026, 5, 1), hmap))   # 1. maj → HOLIDAY_HALF_1MAJ
print(classify_day(date(2026, 6, 5), hmap))   # Grundlovsdag → HOLIDAY_HALF_GRUNDLOV

# SH-timer
print(compute_sh_hours(DayType.SUNDAY, Decimal('7')))          # → 7
print(compute_sh_hours(DayType.HOLIDAY_FULL, Decimal('7')))    # → 7
print(compute_sh_hours(DayType.HOLIDAY_HALF_1MAJ, Decimal('7')))     # → 3.5
print(compute_sh_hours(DayType.HOLIDAY_HALF_GRUNDLOV, Decimal('7'))) # → 3.5
print(compute_sh_hours(DayType.SATURDAY, Decimal('7')))        # → 0

# 1. maj kørsel 09-16 (7t): 4t efter 12 → kode8=3, kode9=1
r = calculate_special_day_overtime(
    datetime(2026,5,1,9,0), datetime(2026,5,1,16,0),
    DayType.HOLIDAY_HALF_1MAJ, Decimal('7'), []
)
print(r.normal_hours, r.sh_kode8_hours, r.sh_kode9_hours)  # → 7 3 1

# Søndag kørsel 09-16 (7t)
r2 = calculate_special_day_overtime(
    datetime(2026,6,21,9,0), datetime(2026,6,21,16,0),
    DayType.SUNDAY, Decimal('7'), []
)
print(r2.normal_hours, r2.sh_kode8_hours, r2.sh_kode9_hours)  # → 7 0 7

# Lørdag u/garanti 06-13 (7t)
r3 = calculate_special_day_overtime(
    datetime(2026,6,20,6,0), datetime(2026,6,20,13,0),
    DayType.SATURDAY, Decimal('0'), []
)
print(r3.normal_hours, r3.sh_kode8_hours, r3.sh_kode9_hours)  # → 7 3 4
"
```

Forventet output (én linje per print):
```
DayType.NORMAL
DayType.SATURDAY
DayType.SUNDAY
DayType.HOLIDAY_FULL
DayType.HOLIDAY_HALF_1MAJ
DayType.HOLIDAY_HALF_GRUNDLOV
7
7
3.5
3.5
0
7 3 1
7 0 7
7 3 4
```

- [ ] **Step 5: Commit**

```
git add app/calculators/overtime.py app/calculators/day_type.py
git commit -m "feat: DayType classifier og special-day overtime beregner"
```

---

### Task 2: Tilføj SH-løntypekoder

**Files:**
- Modify: `app/calculators/pay_rates.py`
- Modify: `app/database/session.py`

**Interfaces:**
- Consumes: `MasterPayType` model
- Produces:
  - `DANLOEN_CODE_SH_FULDLOENNET = "4"` i `pay_rates.py`
  - `DANLOEN_CODE_SH_TIMELOENNET = "63"` i `pay_rates.py`
  - `_ensure_sh_pay_types()` i `session.py` — idempotent INSERT-if-not-exists for `SH_FULDLOENNET` og `SH_TIMELOENNET`

- [ ] **Step 1: Tilføj konstanter til `app/calculators/pay_rates.py`**

Tilføj efter den eksisterende `DANLOEN_CODE_OVERNATNING`-linje:

```python
DANLOEN_CODE_SH_FULDLOENNET = "4"    # SH-betaling fuldlønnet
DANLOEN_CODE_SH_TIMELOENNET = "63"   # SH-udbetaling timelønnet
```

- [ ] **Step 2: Tilføj `_ensure_sh_pay_types()` til `app/database/session.py`**

Find `_seed_holidays()`-funktionen. Tilføj `_ensure_sh_pay_types()` **direkte efter** den:

```python
def _ensure_sh_pay_types():
    """Tilføjer SH-løntypekoder til eksisterende databaser (idempotent)."""
    from database.models import MasterPayType
    from calculators.pay_rates import DANLOEN_CODE_SH_FULDLOENNET, DANLOEN_CODE_SH_TIMELOENNET
    db = SessionLocal()
    try:
        entries = [
            ("SH_FULDLOENNET", "SH-betaling (fuldlønnet)", DANLOEN_CODE_SH_FULDLOENNET, True, 14),
            ("SH_TIMELOENNET", "SH-udbetaling (timelønnet)", DANLOEN_CODE_SH_TIMELOENNET, True, 15),
        ]
        for ck, lbl, code, inc, order in entries:
            if not db.query(MasterPayType).filter(MasterPayType.code_key == ck).first():
                db.add(MasterPayType(
                    code_key=ck, label=lbl, danloen_code=code,
                    include_in_csv=inc, sort_order=order,
                ))
        db.commit()
    except Exception as e:
        db.rollback()
        import logging; logging.error(f"Fejl ved seeding af SH-løntypekoder: {e}")
    finally:
        db.close()
```

- [ ] **Step 3: Kald `_ensure_sh_pay_types()` fra `init_db()`**

Find `init_db()`-funktionen. Den ender med `_seed_holidays()`. Tilføj kaldet:

```python
def init_db():
    from database.models import Base
    Base.metadata.create_all(bind=engine)
    _migrate()
    _seed_roles()
    _seed_admin()
    _seed_master_data()
    _seed_cvr()
    _seed_holidays()
    _ensure_sh_pay_types()    # ← tilføj denne linje
```

- [ ] **Step 4: Verificér at løntyperne oprettes**

Genstart server. Åbn browser-konsol (F12) og kør:
```javascript
fetch("/api/stamdata/pay-types").then(r=>r.json()).then(d=>console.log(d.filter(x=>x.code_key.startsWith("SH"))))
```
Forventet: array med to objekter: `SH_FULDLOENNET` (code "4") og `SH_TIMELOENNET` (code "63").

- [ ] **Step 5: Commit**

```
git add app/calculators/pay_rates.py app/database/session.py
git commit -m "feat: SH-løntypekoder (kode 4 og 63) i stamdata"
```

---

### Task 3: Opdater `_calculate_employee()` i `payroll_router.py`

**Files:**
- Modify: `app/routers/payroll_router.py`

**Interfaces:**
- Consumes:
  - `classify_day(d, holiday_map) -> DayType` fra `calculators.day_type`
  - `compute_sh_hours(day_type, guaranteed_hours) -> Decimal` fra `calculators.day_type`
  - `calculate_special_day_overtime(start, end, day_type, guaranteed_hours, pauses) -> OvertimeResult` fra `calculators.day_type`
  - `DayType` fra `calculators.day_type`
  - `Holiday` model fra `database.models`
  - `emp.fuldloennet: bool` fra `Employee`
- Produces:
  - `calc["sh_fuldloennet_hours"]`: float — SH-timer til kode 4
  - `calc["sh_timeloennet_hours"]`: float — SH-timer til kode 63
  - `calc["sh_kode8_hours"]`: float — additivt supplement kode 8
  - `calc["sh_kode9_hours"]`: float — additivt supplement kode 9
  - Opdateret `calc["total_kr"]` (inkluderer SH-betaling)

- [ ] **Step 1: Tilføj import af dag-type-modulet øverst i `app/routers/payroll_router.py`**

Find blokken:
```python
from calculators.overtime import (
    OT_13_KEY,
    OT_BEFORE_KEY,
    OT_EXTRA_KEY,
    calculate_overtime,
)
```

Erstat med:
```python
from calculators.overtime import (
    OT_13_KEY,
    OT_BEFORE_KEY,
    OT_EXTRA_KEY,
    calculate_overtime,
)
from calculators.day_type import (
    DayType,
    classify_day,
    compute_sh_hours,
    calculate_special_day_overtime,
)
```

- [ ] **Step 2: Tilføj `Holiday` til model-importen i `payroll_router.py`**

Find linjen:
```python
from database.models import Activity, ActivityStatus, ActivityType, Employee, MasterCvrNumber, PayPeriod, PayPeriodStatus
```

Erstat med:
```python
from database.models import Activity, ActivityStatus, ActivityType, Employee, Holiday, MasterCvrNumber, PayPeriod, PayPeriodStatus
```

- [ ] **Step 3: Tilføj SH-totaler til `totals`-dict i `_calculate_employee()`**

Find blokken (linje ~171):
```python
    totals = {
        "normal": Decimal("0"), "ot_before": Decimal("0"),
        "ot_13": Decimal("0"), "ot_extra": Decimal("0"),
        "afspadsering": Decimal("0"),
        "sygdom": Decimal("0"),
        "paragraf_56_syg": Decimal("0"),
        "barn_1sygedag_u_loen": Decimal("0"),
        "feriefri":     Decimal("0"),
        "barsel":       Decimal("0"),
        "skole_kursus": Decimal("0"),
        "salt_hours": Decimal("0"), "salt_kr": Decimal("0"),
        "overnight_count": 0,
    }
```

Erstat med:
```python
    totals = {
        "normal": Decimal("0"), "ot_before": Decimal("0"),
        "ot_13": Decimal("0"), "ot_extra": Decimal("0"),
        "sh_kode8": Decimal("0"), "sh_kode9": Decimal("0"),
        "sh_fuldloennet": Decimal("0"), "sh_timeloennet": Decimal("0"),
        "afspadsering": Decimal("0"),
        "sygdom": Decimal("0"),
        "paragraf_56_syg": Decimal("0"),
        "barn_1sygedag_u_loen": Decimal("0"),
        "feriefri":     Decimal("0"),
        "barsel":       Decimal("0"),
        "skole_kursus": Decimal("0"),
        "salt_hours": Decimal("0"), "salt_kr": Decimal("0"),
        "overnight_count": 0,
    }
```

- [ ] **Step 4: Indlæs helligdagskort til perioden i `_calculate_employee()` — tilføj efter `totals`-dict og `days = []`**

Find linjen:
```python
    days = []
    total_kr = Decimal("0")
```

Erstat med:
```python
    days = []
    total_kr = Decimal("0")

    # Indlæs helligdage for perioden (fra v14-helligdagskalender)
    holiday_rows = db.query(Holiday).filter(
        Holiday.date >= start,
        Holiday.date <= end,
    ).all()
    holiday_map = {h.date: h for h in holiday_rows}
```

- [ ] **Step 5: Tilføj SH-betaling og dag-type-klassifikation i dag-løkken**

Find starten af dag-løkken:
```python
    # Gennemløb alle dage i perioden
    cur = start
    while cur <= end:
        acts_today = acts_by_date.get(cur, [])
        if not acts_today:
```

Erstat **kun** den del (dvs. sæt nye linjer ind efter `acts_today = ...` og INDEN `if not acts_today:`):

```python
    # Gennemløb alle dage i perioden
    cur = start
    while cur <= end:
        acts_today = acts_by_date.get(cur, [])

        # Dag-klassifikation og SH-betaling (gælder uanset om der køres)
        day_type = classify_day(cur, holiday_map)
        guaranteed_today = _normal_hours_for_day(emp, cur)
        sh_h = compute_sh_hours(day_type, guaranteed_today)
        if sh_h > 0:
            if emp.fuldloennet:
                totals["sh_fuldloennet"] += sh_h
            else:
                totals["sh_timeloennet"] += sh_h
            total_kr += sh_h * hourly_rate

        if not acts_today:
```

- [ ] **Step 6: Opdater beregning af kørselstimer for normale aktiviteter**

Find den `else:`-blok der håndterer normale kørselsdage (ikke-fraværsaktiviteter). Den ser sådan ud (linje ~237–275):

```python
                else:
                    normal_cap = _normal_hours_for_day(emp, cur)
                    pauses = [
                        (_dt.fromisoformat(s), _dt.fromisoformat(e))
                        for s, e in (act.pause_intervals or [])
                    ]
                    ot = calculate_overtime(act.start_time, act.end_time, normal_cap, pauses, ot_rates)
                    day_salt_hours = ot.total_hours if act.salt_supplement else Decimal("0")
                    day_salt_kr = day_salt_hours * salt_rate
                    day_kr = (
                        ot.total_hours * hourly_rate
                        + ot.ot_before_hours * ot_rates[OT_BEFORE_KEY]
                        + ot.ot_13_hours * ot_rates[OT_13_KEY]
                        + ot.ot_extra_hours * ot_rates[OT_EXTRA_KEY]
                        + day_salt_kr
                    )
                    totals["normal"]     += ot.normal_hours
                    totals["ot_before"]  += ot.ot_before_hours
                    totals["ot_13"]      += ot.ot_13_hours
                    totals["ot_extra"]   += ot.ot_extra_hours
                    totals["salt_hours"] += day_salt_hours
                    totals["salt_kr"]    += day_salt_kr
                    total_kr             += day_kr
                    days.append({
                        "date": cur.isoformat(),
                        "normal":       float(_round2(ot.normal_hours)),
                        "ot_before":    float(_round2(ot.ot_before_hours)),
                        "ot_13":        float(_round2(ot.ot_13_hours)),
                        "ot_extra":     float(_round2(ot.ot_extra_hours)),
                        "total_hours":  float(_round2(ot.total_hours)),
                        "total_kr":     float(_round2(day_kr)),
                        "absence_type": None,
                        "salt_hours":   float(_round2(day_salt_hours)),
                        "salt_kr":      float(_round2(day_salt_kr)),
                        "start_time":   act.start_time.strftime("%H:%M"),
                        "end_time":     act.end_time.strftime("%H:%M"),
                        "vehicle_number": act.vehicle_number or "",
                    })
```

Erstat med:

```python
                else:
                    pauses = [
                        (_dt.fromisoformat(s), _dt.fromisoformat(e))
                        for s, e in (act.pause_intervals or [])
                    ]
                    if day_type == DayType.NORMAL:
                        ot = calculate_overtime(
                            act.start_time, act.end_time,
                            guaranteed_today, pauses, ot_rates,
                        )
                    else:
                        ot = calculate_special_day_overtime(
                            act.start_time, act.end_time,
                            day_type, guaranteed_today, pauses,
                        )
                    day_salt_hours = ot.total_hours if act.salt_supplement else Decimal("0")
                    day_salt_kr = day_salt_hours * salt_rate
                    day_kr = (
                        ot.normal_hours * hourly_rate
                        + ot.ot_before_hours * ot_rates[OT_BEFORE_KEY]
                        + ot.ot_13_hours * ot_rates[OT_13_KEY]
                        + ot.ot_extra_hours * ot_rates[OT_EXTRA_KEY]
                        + ot.sh_kode8_hours * ot_rates[OT_13_KEY]
                        + ot.sh_kode9_hours * ot_rates[OT_EXTRA_KEY]
                        + day_salt_kr
                    )
                    totals["normal"]     += ot.normal_hours
                    totals["ot_before"]  += ot.ot_before_hours
                    totals["ot_13"]      += ot.ot_13_hours
                    totals["ot_extra"]   += ot.ot_extra_hours
                    totals["sh_kode8"]   += ot.sh_kode8_hours
                    totals["sh_kode9"]   += ot.sh_kode9_hours
                    totals["salt_hours"] += day_salt_hours
                    totals["salt_kr"]    += day_salt_kr
                    total_kr             += day_kr
                    days.append({
                        "date": cur.isoformat(),
                        "normal":       float(_round2(ot.normal_hours)),
                        "ot_before":    float(_round2(ot.ot_before_hours)),
                        "ot_13":        float(_round2(ot.ot_13_hours)),
                        "ot_extra":     float(_round2(ot.ot_extra_hours)),
                        "total_hours":  float(_round2(ot.total_hours)),
                        "total_kr":     float(_round2(day_kr)),
                        "absence_type": None,
                        "salt_hours":   float(_round2(day_salt_hours)),
                        "salt_kr":      float(_round2(day_salt_kr)),
                        "start_time":   act.start_time.strftime("%H:%M"),
                        "end_time":     act.end_time.strftime("%H:%M"),
                        "vehicle_number": act.vehicle_number or "",
                    })
```

**OBS:** `guaranteed_today` er allerede beregnet ovenfor (Step 5). `normal_cap` fjernes.

- [ ] **Step 7: Tilføj SH-felter til return-dict i `_calculate_employee()`**

Find return-dict'en. Den starter med:
```python
    return {
        "employee_id":        emp.id,
```

Find linjen:
```python
        "total_kr":           float(_round2(total_kr)),
        "activity_count":     len(activities),
        "has_pending":        has_pending,
    }
```

Erstat med:
```python
        "total_kr":                float(_round2(total_kr)),
        "activity_count":          len(activities),
        "has_pending":             has_pending,
        "sh_fuldloennet_hours":    float(_round2(totals["sh_fuldloennet"])),
        "sh_timeloennet_hours":    float(_round2(totals["sh_timeloennet"])),
        "sh_kode8_hours":          float(_round2(totals["sh_kode8"])),
        "sh_kode9_hours":          float(_round2(totals["sh_kode9"])),
    }
```

- [ ] **Step 8: Verificér beregningen med server-genstart**

Stop serveren, slet `__pycache__`, genstart:
```
cd app
python -c "import shutil; shutil.rmtree('__pycache__', ignore_errors=True)"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Test i browser-konsol (F12) — vælg en periode der inkluderer en søndag eller helligdag:
```javascript
fetch("/api/payroll/preview").then(r=>r.json()).then(d=>{
  const emp = d.employees[0];
  console.log("SH fuldlønnet:", emp.sh_fuldloennet_hours);
  console.log("SH timelønnet:", emp.sh_timeloennet_hours);
  console.log("SH kode8:", emp.sh_kode8_hours);
  console.log("SH kode9:", emp.sh_kode9_hours);
});
```

Forventet: tal > 0 for medarbejdere med garanterede timer på søndage/helligdage i perioden (evt. 0 hvis ingen sådanne dage i den valgte periode).

Ingen fejl i serverlogs = OK.

- [ ] **Step 9: Commit**

```
git add app/routers/payroll_router.py
git commit -m "feat: SH-beregning og dag-type-overtid i _calculate_employee"
```

---

### Task 4: Opdater CSV-eksporten

**Files:**
- Modify: `app/routers/payroll_router.py` — `export_csv` (GET) og `export_csv_post` (POST)

**Interfaces:**
- Consumes: `calc["sh_fuldloennet_hours"]`, `calc["sh_timeloennet_hours"]`, `calc["sh_kode8_hours"]`, `calc["sh_kode9_hours"]` fra Task 3
- Produces: Danløn-CSV med korrekte koder 4, 63, 8, 9 for SH-dage

- [ ] **Step 1: Opdater `raw_rows` i GET `export_csv`**

Find `raw_rows`-listen i GET `/export-csv` (linje ~543). Den ser sådan ud:
```python
        raw_rows = [
            ("NORMAL",        calc["normal_hours"],               calc["hourly_rate"]),
            ("OT_BEFORE",     calc["ot_before_hours"],            calc["ot_rates"][OT_BEFORE_KEY]),
            ("OT_13",         calc["ot_13_hours"],                calc["ot_rates"][OT_13_KEY]),
            ("OT_EXTRA",      calc["ot_extra_hours"],             calc["ot_rates"][OT_EXTRA_KEY]),
```

Erstat de fire rækker (behold resten af listen uændret):
```python
        raw_rows = [
            ("NORMAL",        calc["normal_hours"],                                              calc["hourly_rate"]),
            ("OT_BEFORE",     calc["ot_before_hours"],                                           calc["ot_rates"][OT_BEFORE_KEY]),
            ("OT_13",         calc["ot_13_hours"] + calc.get("sh_kode8_hours", 0),              calc["ot_rates"][OT_13_KEY]),
            ("OT_EXTRA",      calc["ot_extra_hours"] + calc.get("sh_kode9_hours", 0),           calc["ot_rates"][OT_EXTRA_KEY]),
            ("SH_FULDLOENNET", calc.get("sh_fuldloennet_hours", 0),                              calc["hourly_rate"]),
            ("SH_TIMELOENNET", calc.get("sh_timeloennet_hours", 0),                              calc["hourly_rate"]),
```

- [ ] **Step 2: Opdater skip-betingelse i GET `export_csv`**

Find:
```python
        if calc["activity_count"] == 0 and calc["afspadsering_hours"] == 0 and calc["sygdom_hours"] == 0 and calc["paragraf_56_syg_hours"] == 0 and calc["barn_1sygedag_u_loen_hours"] == 0 and calc["feriefri_hours"] == 0 and calc["barsel_hours"] == 0 and calc["skole_kursus_hours"] == 0:
            continue
```

Erstat med:
```python
        if (calc["activity_count"] == 0
                and calc["afspadsering_hours"] == 0
                and calc["sygdom_hours"] == 0
                and calc["paragraf_56_syg_hours"] == 0
                and calc["barn_1sygedag_u_loen_hours"] == 0
                and calc["feriefri_hours"] == 0
                and calc["barsel_hours"] == 0
                and calc["skole_kursus_hours"] == 0
                and calc.get("sh_fuldloennet_hours", 0) == 0
                and calc.get("sh_timeloennet_hours", 0) == 0):
            continue
```

- [ ] **Step 3: Gentag Step 1 og 2 for POST `export_csv_post`**

Find den tilsvarende `raw_rows`-liste i POST `/export-csv` (linje ~611). Udfør nøjagtigt samme erstatning som Step 1.

Find og erstat den tilsvarende skip-betingelse i POST-funktionen (linje ~607). Udfør nøjagtigt samme erstatning som Step 2.

- [ ] **Step 4: Verificér CSV-indholdet**

Genstart server. Log ind som admin, gå til Lønkørsel. Vælg en periode der indeholder mindst én søndag med godkendte aktiviteter. Tryk "Prøvekørsel" for at se Excel (eller download CSV via browser-konsol):

```javascript
fetch("/api/payroll/export-csv").then(r=>r.text()).then(csv=>console.log(csv.split("\n").slice(0,10).join("\n")))
```

Check at der er rækker med Danløn-kode `4` (fuldlønnet) eller `63` (timelønnet) for medarbejdere med garanterede timer på søndage i perioden.

Kontroller at kode `8` og `9` summer korrekt (inkluderer både regular overtid og SH-supplements).

- [ ] **Step 5: Commit**

```
git add app/routers/payroll_router.py
git commit -m "feat: SH-koder 4/63 og supplement-fusion i Danløn CSV"
```

---

## Spec-dækning ✓

| Regel | Task |
|-------|------|
| `DayType` klassifikation + helligdag trumfer | Task 1 Step 3 |
| `compute_sh_hours` (garanti/2 for halvdage, fuld for hele) | Task 1 Step 3 |
| `calculate_special_day_overtime` — alle 5 dagtyper | Task 1 Step 3 |
| `sh_kode8/sh_kode9` additive felter på `OvertimeResult` | Task 1 Step 1 |
| Tids-tillæg tilsidesættes på særlige dage | Task 1 Step 3 (bruges aldrig på special-days) |
| SH-løntypekoder kode 4 og kode 63 i DB | Task 2 |
| Idempotent seed (eksisterende DB) | Task 2 Step 2 |
| `_calculate_employee()` SH per dag + kørsel-beregning | Task 3 |
| SH-kr til `total_kr` | Task 3 Step 5 |
| SH-timer i result-dict | Task 3 Step 7 |
| CSV: kode 4/63-rækker | Task 4 Step 1+3 |
| CSV: kode 8/9 fusionerer regular + supplement | Task 4 Step 1+3 |
| Skip-betingelse inkluderer SH | Task 4 Step 2+3 |
