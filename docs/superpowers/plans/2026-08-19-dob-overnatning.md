# DOB-overnatning (løntypekode 43) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tilføj et "DOB"-afkrydsningsfelt til opret-aktivitet-modalens Overnatning-type, så overnatningen registreres under løntypekode 43 (DOB_overnatning) i stedet for kode 14, når krydset sættes.

**Architecture:** DOB-overnatning repræsenteres som en ny `activity_type`-værdi (`"dob_overnatning"`), ikke et boolean-felt — dette matcher den allerede eksisterende, brugeroprettede løntypekode `dob_overnatning` (Danløn-kode 43, `csv_rate_source="supplement:5"`), som systemets generiske CSV-motor (`_user_pay_type_rows()`) allerede matcher aktiviteter mod via `activity_type == code_key`. Ingen ny databasekolonne, ingen migration. Tre steder i `_calculate_employee()` der i dag kun kender `"overnatning"` udvides til også at matche `"dob_overnatning"`, så den behandles identisk mht. ikke at tælle som arbejdstid.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), Pydantic, vanilla JS, openpyxl.

## Global Constraints

- Ingen ny databasekolonne eller migration — `dob_overnatning` er en streng-værdi i det eksisterende, ubegrænsede `activity_type`-felt (`String(50)`).
- Løntypekoden `dob_overnatning` (id 25 i `master_pay_types`) og tillægget `DOB_overnatning` (id 5 i `master_supplement_rates`, 597 kr) er allerede oprettet af brugeren via Stamdata — må IKKE genoprettes eller ændres af denne plan.
- `export_csv`/`export_csv_post` i `app/routers/payroll_router.py` må IKKE ændres — kode 43-linjen kommer automatisk via den eksisterende `_user_pay_type_rows()`-mekanisme.
- DOB-flaget kan IKKE rettes efter oprettelse — ingen ændring af "Rediger aktivitet"-modalen.
- Spec: `docs/superpowers/specs/2026-08-19-dob-overnatning-design.md`

---

## Task 1: Valideringsfix for `activity_type="dob_overnatning"`

**Files:**
- Modify: `app/database/schemas.py:157-163` (`ActivityCreate.end_after_start`)
- Test: `tests/test_dob_overnatning.py` (ny fil)

**Interfaces:**
- Produces: `ActivityCreate(activity_type="dob_overnatning", start_time=X, end_time=X)` validerer uden fejl (samme som i dag for `"overnatning"`)

- [ ] **Step 1: Skriv fejlende test for validator-udvidelsen**

```python
# tests/test_dob_overnatning.py
from datetime import datetime

import pytest
from pydantic import ValidationError

from database.schemas import ActivityCreate


def test_activity_create_allows_equal_start_end_for_dob_overnatning():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    activity = ActivityCreate(
        employee_id=1,
        activity_type="dob_overnatning",
        start_time=midnight,
        end_time=midnight,
    )
    assert activity.activity_type == "dob_overnatning"


def test_activity_create_still_allows_equal_start_end_for_overnatning():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    activity = ActivityCreate(
        employee_id=1,
        activity_type="overnatning",
        start_time=midnight,
        end_time=midnight,
    )
    assert activity.activity_type == "overnatning"


def test_activity_create_rejects_equal_start_end_for_normal():
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    with pytest.raises(ValidationError):
        ActivityCreate(
            employee_id=1,
            activity_type="normal",
            start_time=midnight,
            end_time=midnight,
        )
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v`
Expected: FAIL på `test_activity_create_allows_equal_start_end_for_dob_overnatning` med
`ValidationError: Sluttid skal være efter starttid` — de to andre tests PASSER allerede
(uændret nuværende adfærd).

- [ ] **Step 3: Udvid validatoren**

I `app/database/schemas.py`, ret (linje 157-163) fra:

```python
    @model_validator(mode="after")
    def end_after_start(self):
        if self.activity_type == "overnatning":
            return self
        if self.end_time <= self.start_time:
            raise ValueError("Sluttid skal være efter starttid")
        return self
```

til:

```python
    @model_validator(mode="after")
    def end_after_start(self):
        if self.activity_type in ("overnatning", "dob_overnatning"):
            return self
        if self.end_time <= self.start_time:
            raise ValueError("Sluttid skal være efter starttid")
        return self
```

- [ ] **Step 4: Kør testen og bekræft at alle tre passerer**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/database/schemas.py tests/test_dob_overnatning.py
git commit -m "feat: tillad dob_overnatning med ens start-/sluttid ved oprettelse"
```

---

## Task 2: Sats-loader for DOB-overnatning

**Files:**
- Modify: `app/calculators/rates_loader.py` (tilføj funktion efter `load_dagpenge_rate_from_db()`, linje 174-180)
- Test: `tests/test_dob_overnatning.py` (udvid)

**Interfaces:**
- Consumes: intet nyt
- Produces: `load_dob_overnight_rate_from_db(db) -> Decimal` — bruges af Task 3

- [ ] **Step 1: Skriv fejlende test**

Tilføj til `tests/test_dob_overnatning.py`:

```python
def test_load_dob_overnight_rate_from_db_returns_seeded_rate(db):
    from decimal import Decimal
    from database.models import MasterSupplementRate
    from calculators.rates_loader import load_dob_overnight_rate_from_db
    db.add(MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True))
    db.commit()
    assert load_dob_overnight_rate_from_db(db) == Decimal("597.00")


def test_load_dob_overnight_rate_from_db_returns_zero_when_missing(db):
    from decimal import Decimal
    from calculators.rates_loader import load_dob_overnight_rate_from_db
    assert load_dob_overnight_rate_from_db(db) == Decimal("0")
```

Denne test bruger fixturen `db` fra `tests/conftest.py` (in-memory SQLite, samme mønster som
`tests/test_springertillaeg.py`).

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v -k dob_overnight_rate`
Expected: FAIL med `ImportError: cannot import name 'load_dob_overnight_rate_from_db'`

- [ ] **Step 3: Tilføj funktionen**

I `app/calculators/rates_loader.py`, tilføj efter `load_dagpenge_rate_from_db()` (efter linje 180,
før `load_overtime_rates_by_id_from_db`):

```python
def load_dob_overnight_rate_from_db(db) -> Decimal:
    """DOB-overnatningens tillægssats – brugeroprettet via Stamdata → Tillæg,
    intet Excel-fallback (i modsætning til load_overnight_rate_from_db)."""
    from database.models import MasterSupplementRate
    row = db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "DOB_overnatning").first()
    return Decimal(str(row.rate)) if row else Decimal("0")
```

- [ ] **Step 4: Kør testen og bekræft at begge passerer**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v -k dob_overnight_rate`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/calculators/rates_loader.py tests/test_dob_overnatning.py
git commit -m "feat: tilføj load_dob_overnight_rate_from_db"
```

---

## Task 3: Beregning — `_calculate_employee()` behandler DOB-overnatning

**Files:**
- Modify: `app/routers/payroll_router.py:41-51` (import-blok)
- Modify: `app/routers/payroll_router.py:310` (indlæs DOB-sats)
- Modify: `app/routers/payroll_router.py:378` (dag-gruppering)
- Modify: `app/routers/payroll_router.py:399-406` (totals-init + overnight_dates/overnight_count)
- Modify: `app/routers/payroll_router.py:425` (acts_today-filter)
- Modify: `app/routers/payroll_router.py:621-623` (retur-dict)
- Test: `tests/test_dob_overnatning.py` (udvid)

**Interfaces:**
- Consumes: `load_dob_overnight_rate_from_db(db) -> Decimal` (Task 2)
- Produces: `_calculate_employee(...)`'s retur-dict indeholder nu `dob_overnight_count: int`,
  `dob_overnight_rate: float`, `dob_overnight_kr: float` — bruges af Task 4 og Task 6

- [ ] **Step 1: Skriv fejlende tests**

Tilføj til `tests/test_dob_overnatning.py`:

```python
from datetime import date, datetime
from decimal import Decimal

import pytest

from database.models import ActivityStatus, MasterAgreementType, MasterOvertimeRate, MasterSupplementRate
from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY


def _setup_rates(db, employee, hourly=Decimal("150.00")):
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=hourly))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.add(MasterSupplementRate(label="Overnatning", rate=Decimal("95.00")))
    db.add(MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True))
    db.commit()


def test_calculate_employee_dob_overnight_excluded_from_kode14_count(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 17), date(2026, 8, 23), db)

    assert calc["overnight_count"] == 0
    assert calc["dob_overnight_count"] == 1
    assert calc["dob_overnight_rate"] == pytest.approx(597.00)
    assert calc["dob_overnight_kr"] == pytest.approx(597.00)


def test_calculate_employee_regular_overnight_still_counts_as_kode14(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 17), date(2026, 8, 23), db)

    assert calc["overnight_count"] == 1
    assert calc["overnight_kr"] == pytest.approx(95.00)
    assert calc["dob_overnight_count"] == 0
    assert calc["dob_overnight_kr"] == 0.0


def test_calculate_employee_dob_overnight_not_counted_as_work_hours(db, employee):
    from routers.payroll_router import _calculate_employee
    from conftest import make_activity
    _setup_rates(db, employee)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 8, 20), date(2026, 8, 20), db)

    assert calc["normal_hours"] == 0.0
    day = next(d for d in calc["days"] if d["date"] == "2026-08-20")
    assert day["overnight"] == 1
    assert day["absence_type"] is None
```

- [ ] **Step 2: Kør testene og bekræft at de DOB-specifikke fejler**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v -k calculate_employee`
Expected: FAIL på alle tre med `KeyError: 'dob_overnight_count'` (feltet findes ikke endnu i
retur-dictet). `test_calculate_employee_regular_overnight_still_counts_as_kode14` fejler også
pga. samme manglende felt (assertion på `dob_overnight_count`).

- [ ] **Step 3: Udvid import-blokken**

I `app/routers/payroll_router.py`, ret linje 41-51 fra:

```python
from calculators.rates_loader import (
    load_agreement_types_from_db,
    load_overtime_rates_from_db,
    load_salt_supplement_rate_from_db,
    load_overnight_rate_from_db,
    load_dagpenge_rate_from_db,
    load_springer_rate_from_db,
    load_overtime_rates_by_id_from_db,
    load_supplement_rates_by_id_from_db,
    get_active_supplement_for_period,
)
```

til:

```python
from calculators.rates_loader import (
    load_agreement_types_from_db,
    load_overtime_rates_from_db,
    load_salt_supplement_rate_from_db,
    load_overnight_rate_from_db,
    load_dob_overnight_rate_from_db,
    load_dagpenge_rate_from_db,
    load_springer_rate_from_db,
    load_overtime_rates_by_id_from_db,
    load_supplement_rates_by_id_from_db,
    get_active_supplement_for_period,
)
```

- [ ] **Step 4: Indlæs DOB-satsen**

I `app/routers/payroll_router.py`, ret linje 310 fra:

```python
    overnight_rate = load_overnight_rate_from_db(db)
```

til:

```python
    overnight_rate = load_overnight_rate_from_db(db)
    dob_overnight_rate = load_dob_overnight_rate_from_db(db)
```

- [ ] **Step 5: Udvid dag-grupperingen (linje 378)**

Ret:

```python
        if act.activity_type == "overnatning" or _ABSENCE_LABELS.get(act.activity_type):
```

til:

```python
        if act.activity_type in ("overnatning", "dob_overnatning") or _ABSENCE_LABELS.get(act.activity_type):
```

- [ ] **Step 6: Tilføj totals-init og udvid overnight_dates/overnight_count (linje 399-406)**

Ret:

```python
        "salt_hours": Decimal("0"), "salt_kr": Decimal("0"),
        "overnight_count": 0,
    }
    days = []
    total_kr = Decimal("0")

    # Overnatning håndteres som kolonne (ikke fraværsrække) – forhåndsberegn datoer
    overnight_dates = {a.start_time.date() for a in activities if a.activity_type == "overnatning"}
    totals["overnight_count"] = sum(1 for a in activities if a.activity_type == "overnatning")
```

til:

```python
        "salt_hours": Decimal("0"), "salt_kr": Decimal("0"),
        "overnight_count": 0,
        "dob_overnight_count": 0,
    }
    days = []
    total_kr = Decimal("0")

    # Overnatning håndteres som kolonne (ikke fraværsrække) – forhåndsberegn datoer.
    # DOB-overnatning tælles med i overnight_dates (samme dag-markering), men holdes
    # ude af overnight_count (kode 14) – den har sin egen tælling og sats (kode 43).
    overnight_dates = {a.start_time.date() for a in activities if a.activity_type in ("overnatning", "dob_overnatning")}
    totals["overnight_count"] = sum(1 for a in activities if a.activity_type == "overnatning")
    totals["dob_overnight_count"] = sum(1 for a in activities if a.activity_type == "dob_overnatning")
```

- [ ] **Step 7: Udvid acts_today-filteret (linje 425)**

Ret:

```python
        acts_today = [a for a in acts_by_date.get(cur, []) if a.activity_type != "overnatning"]
```

til:

```python
        acts_today = [a for a in acts_by_date.get(cur, []) if a.activity_type not in ("overnatning", "dob_overnatning")]
```

- [ ] **Step 8: Tilføj felterne til retur-dictet (linje 621-623)**

Ret:

```python
        "overnight_count":    totals["overnight_count"],
        "overnight_rate":     float(overnight_rate),
        "overnight_kr":       float(_round2(Decimal(str(totals["overnight_count"])) * overnight_rate)),
```

til:

```python
        "overnight_count":    totals["overnight_count"],
        "overnight_rate":     float(overnight_rate),
        "overnight_kr":       float(_round2(Decimal(str(totals["overnight_count"])) * overnight_rate)),
        "dob_overnight_count": totals["dob_overnight_count"],
        "dob_overnight_rate":  float(dob_overnight_rate),
        "dob_overnight_kr":    float(_round2(Decimal(str(totals["dob_overnight_count"])) * dob_overnight_rate)),
```

- [ ] **Step 9: Kør testene og bekræft at alle passerer**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v`
Expected: PASS (alle tests fra Task 1-3)

- [ ] **Step 10: Commit**

```bash
git add app/routers/payroll_router.py tests/test_dob_overnatning.py
git commit -m "feat: behandl dob_overnatning i _calculate_employee (kode 14 vs. 43-opdeling)"
```

---

## Task 4: Integrationstest — CSV-eksport genererer kode 43-linjen automatisk

**Files:**
- Test: `tests/test_dob_overnatning.py` (udvid)

**Interfaces:**
- Consumes: `_calculate_employee(...)`'s `dob_overnight_*`-felter (Task 3), den eksisterende
  `_user_pay_type_rows()`-mekanisme (uændret), `export_csv_post` (uændret)
- Produces: intet nyt for andre opgaver — denne opgave bekræfter blot at designets kernepræmis
  (kode 43 kræver ingen ændring af eksportfunktionerne) faktisk holder

- [ ] **Step 1: Skriv integrationstest**

Tilføj til `tests/test_dob_overnatning.py`:

```python
def _dummy_user():
    from database.models import AppUser
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_export_csv_post_splits_overnight_into_kode14_and_kode43(db, employee, tmp_path):
    from datetime import timedelta
    from database.models import MasterPayType, ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_router import export_csv_post, ExportCsvRequest
    from conftest import make_activity

    employee.cvr_number = "13246505"
    _setup_rates(db, employee)
    dob_supp = db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "DOB_overnatning").first()
    db.add(MasterPayType(
        code_key="OVERNATNING", label="Overnatning", danloen_code="14",
        include_in_csv=True, sort_order=6, csv_quantity_type="count", csv_rate_source="overnight",
    ))
    db.add(MasterPayType(
        code_key="dob_overnatning", label="DOB_overnatning", danloen_code="43",
        is_user_created=True, include_in_csv=True, sort_order=17,
        csv_quantity_type="count", csv_rate_source=f"supplement:{dob_supp.id}",
    ))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 8, 20), db)
    # Begge dage afledes af den faktiske periode (ikke hardcodede datoer) for at
    # garantere at de falder inden for samme lønperiode, uanset periodens grænser.
    midnight_a = datetime.combine(period.start_date, datetime.min.time())
    midnight_b = midnight_a + timedelta(days=1)
    make_activity(db, employee, midnight_a, midnight_a, activity_type="overnatning",
                  status=ActivityStatus.approved)
    make_activity(db, employee, midnight_b, midnight_b, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    body = ExportCsvRequest(period_start=period.start_date.isoformat(), output_folder=str(tmp_path))
    export_csv_post(body, current_user=_dummy_user(), db=db)

    csv_files = list(tmp_path.glob("danloen_*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text(encoding="utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    codes = {l.split(";")[2] for l in lines}
    assert "14" in codes, f"Forventede kode 14 (Overnatning) i linjerne: {lines}"
    assert "43" in codes, f"Forventede kode 43 (DOB_overnatning) i linjerne: {lines}"
    code14_line = next(l for l in lines if l.split(";")[2] == "14")
    code43_line = next(l for l in lines if l.split(";")[2] == "43")
    assert code14_line.split(";")[3] == "100"  # 1 stk * 100 (fmt() ganger med 100)
    assert code43_line.split(";")[3] == "100"
    assert code43_line.split(";")[4] == "59700"  # 597,00 kr * 100
```

- [ ] **Step 2: Kør testen**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v -k splits_overnight`
Expected: PASS uden at nogen produktionskode i denne opgave er ændret — bekræfter at
`_user_pay_type_rows()` allerede fanger `dob_overnatning`-aktiviteter korrekt via
`code_key == activity_type`-match. Fejler testen i stedet (fx forkert kode eller manglende linje),
er det et signal om at en antagelse i designet er forkert — undersøg før du fortsætter, ret IKKE
`export_csv_post` blindt.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dob_overnatning.py
git commit -m "test: bekræft at CSV-eksport splitter overnatning i kode 14/43 uden kodeændring"
```

---

## Task 5: Prøvekørsel-Excel — DOB Overnatning-totalrække

**Files:**
- Modify: `app/routers/payroll_router.py:762-766` (`_build_proevekoersel_workbook`)
- Test: `tests/test_dob_overnatning.py` (udvid)

**Interfaces:**
- Consumes: `calc["dob_overnight_kr"]` (Task 3)
- Produces: intet nyt for andre opgaver

- [ ] **Step 1: Skriv fejlende test**

Tilføj til `tests/test_dob_overnatning.py`:

```python
def test_proevekoersel_workbook_includes_dob_overnight_row(db, employee):
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_router import _build_proevekoersel_workbook
    from conftest import make_activity

    _setup_rates(db, employee)
    period = get_or_create_period_for_date(date(2026, 8, 20), db)
    midnight = datetime(2026, 8, 20, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    wb = _build_proevekoersel_workbook([employee], period, db)
    ws = wb.active
    labels = [row[3] for row in ws.iter_rows(values_only=True) if row[3]]
    assert "DOB Overnatning (kr.)" in labels
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v -k proevekoersel`
Expected: FAIL — `"DOB Overnatning (kr.)" not in labels`

- [ ] **Step 3: Tilføj rækken**

I `app/routers/payroll_router.py`, ret (linje 762-766) fra:

```python
        if on_kr > 0:
            ws.append([calc["employee_name"], calc["employee_number"], "", "Overnatning (kr.)",
                       "", "", "", "", "", "", "", "", "", "", round(on_kr, 2)])
            for cell in ws[ws.max_row]:
                cell.font = bold
        ws.append([])
```

til:

```python
        if on_kr > 0:
            ws.append([calc["employee_name"], calc["employee_number"], "", "Overnatning (kr.)",
                       "", "", "", "", "", "", "", "", "", "", round(on_kr, 2)])
            for cell in ws[ws.max_row]:
                cell.font = bold
        dob_on_kr = calc.get("dob_overnight_kr", 0.0)
        if dob_on_kr > 0:
            ws.append([calc["employee_name"], calc["employee_number"], "", "DOB Overnatning (kr.)",
                       "", "", "", "", "", "", "", "", "", "", round(dob_on_kr, 2)])
            for cell in ws[ws.max_row]:
                cell.font = bold
        ws.append([])
```

- [ ] **Step 4: Kør testen og bekræft at den passerer**

Run: `cd app && pytest ../tests/test_dob_overnatning.py -v -k proevekoersel`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/payroll_router.py tests/test_dob_overnatning.py
git commit -m "feat: vis DOB Overnatning (kr.) i prøvekørsel-Excel"
```

---

## Task 6: Frontend — DOB-afkrydsningsfelt og lønkørsel-oversigt

**Files:**
- Modify: `app/templates/index.html:771` (nyt afkrydsningsfelt efter `manual-normal-fields`)
- Modify: `app/static/js/app.js` (`updateManualTypeVisibility()` linje ~1297-1331,
  `openManualActivityModal()` linje ~1584, `confirmManualActivity()` linje ~1665-1681,
  `loadAbsenceTypes()` linje ~1275, lønkørsel-tabellen linje ~2562)

**Interfaces:**
- Consumes: `emp.dob_overnight_count`, `emp.dob_overnight_rate`, `emp.dob_overnight_kr` (fra
  `/api/payroll/preview`, Task 3's retur-dict-felter), `payrollRowOvernight(label, count, rate, kr)`
  (eksisterende funktion, uændret)
- Produces: `POST /api/activities` med `activity_type: "dob_overnatning"` når krydset er sat

Dette repo har intet frontend-testframework — verifikation sker manuelt i browseren (samme
konvention som `docs/superpowers/plans/2026-08-19-dynamisk-sats-kilde.md`, Task 3).

- [ ] **Step 1: Tilføj afkrydsningsfeltet i HTML'en**

I `app/templates/index.html`, indsæt lige efter linje 771 (den lukkende `</div>` for
`manual-normal-fields`, før `<div class="form-group" id="manual-pause-section">`):

```html
      <div class="form-group" id="manual-dob-group" style="display:none">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
          <input type="checkbox" id="manual-dob" style="width:16px;height:16px;cursor:pointer">
          DOB
        </label>
      </div>
```

- [ ] **Step 2: Vis/skjul feltet afhængigt af type, og nulstil ved skift**

I `app/static/js/app.js`, i `updateManualTypeVisibility()`, ret linjen (omkring linje 1304-1305):

```js
  document.getElementById("manual-end-group").style.display     = isDateOnly ? "none" : "";
  document.getElementById("manual-barsel-group").style.display  = isBarsel ? "" : "none";
```

til:

```js
  document.getElementById("manual-end-group").style.display     = isDateOnly ? "none" : "";
  document.getElementById("manual-barsel-group").style.display  = isBarsel ? "" : "none";
  document.getElementById("manual-dob-group").style.display     = isOvernatning ? "" : "none";
  if (!isOvernatning) document.getElementById("manual-dob").checked = false;
```

- [ ] **Step 3: Nulstil feltet ved modal-åbning**

I `app/static/js/app.js`, i `openManualActivityModal()`, ret linjen (omkring linje 1584):

```js
  document.getElementById("manual-salt").checked = false;
```

til:

```js
  document.getElementById("manual-salt").checked = false;
  document.getElementById("manual-dob").checked = false;
```

- [ ] **Step 4: Send `dob_overnatning` som activity_type når krydset er sat**

I `app/static/js/app.js`, i `confirmManualActivity()`, ret overnatnings-grenen (omkring linje
1665-1681) fra:

```js
  if (actType === "overnatning") {
    if (!start) { toast("Angiv dato for overnatningen", "error"); return; }
    const dateStr = start.slice(0, 10);
    const timeStr = dateStr + "T00:00:00";
    try {
      await POST("/api/activities", {
        employee_id: empId,
        activity_type: "overnatning",
        start_time: timeStr,
        end_time:   timeStr,
      });
      toast("Overnatning oprettet", "success");
      closeModal("modal-manual-activity");
      await refreshActivities();
    } catch (e) { toast(e.message, "error"); }
    return;
  }
```

til:

```js
  if (actType === "overnatning") {
    if (!start) { toast("Angiv dato for overnatningen", "error"); return; }
    const isDob = document.getElementById("manual-dob").checked;
    const dateStr = start.slice(0, 10);
    const timeStr = dateStr + "T00:00:00";
    try {
      await POST("/api/activities", {
        employee_id: empId,
        activity_type: isDob ? "dob_overnatning" : "overnatning",
        start_time: timeStr,
        end_time:   timeStr,
      });
      toast(isDob ? "DOB-overnatning oprettet" : "Overnatning oprettet", "success");
      closeModal("modal-manual-activity");
      await refreshActivities();
    } catch (e) { toast(e.message, "error"); }
    return;
  }
```

- [ ] **Step 5: Registrér et pænt label til aktivitetslisten**

I `app/static/js/app.js`, i `loadAbsenceTypes()`, tilføj lige efter `forEach`-loopet (efter linje
1275, `});`, før `} catch (e) { ... }`):

```js
    TYPE_LABELS["dob_overnatning"] = "DOB Overnatning";
    ABSENCE_LABELS["dob_overnatning"] = badgeLabel("DOB Overnatning");
    ABSENCE_TYPES.add("dob_overnatning");
```

Bemærk: `"dob_overnatning"` tilføjes bevidst IKKE til `allTypes`-arrayet (linje 1264) — den skal
ikke fremgå som selvstændig valgmulighed i `#manual-type`-dropdownet, kun tilgås via
DOB-afkrydsningsfeltet.

- [ ] **Step 6: Tilføj DOB Overnatning-linjen i lønkørsel-oversigten**

I `app/static/js/app.js`, ret (linje 2562) fra:

```js
        ${payrollRowOvernight("Overnatning", emp.overnight_count, emp.overnight_rate, emp.overnight_kr)}
```

til:

```js
        ${payrollRowOvernight("Overnatning", emp.overnight_count, emp.overnight_rate, emp.overnight_kr)}
        ${payrollRowOvernight("DOB Overnatning", emp.dob_overnight_count, emp.dob_overnight_rate, emp.dob_overnight_kr)}
```

- [ ] **Step 7: Kør hele backend-testsuiten og bekræft ingen regressioner**

Run: `cd app && pytest ../tests/ -v`
Expected: PASS (alle eksisterende tests + alle nye tests fra Task 1-5)

- [ ] **Step 8: Verificér i browseren**

Start serveren (`cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`), log ind som en
bruger med `payroll`-rettighed:

1. Åbn "Tilføj aktivitet", vælg type "Overnatning" — bekræft at et "DOB"-afkrydsningsfelt vises
   under Registreringsnummer-feltet (Salttillæg-feltet er skjult, som i dag).
2. Vælg en anden type (fx "Normal tid" eller "Ferie") — bekræft at DOB-feltet forsvinder.
3. Vælg "Overnatning" igen, sæt DOB-krydset, angiv en dato, opret. Bekræft toast
   "DOB-overnatning oprettet".
4. Åbn aktivitetslisten — bekræft at den nye aktivitet vises med type-label "DOB Overnatning" (ikke
   den rå streng "dob_overnatning").
5. Opret én almindelig overnatning (uden kryds) samme medarbejder, samme periode.
6. Gå til Lønkørsel-oversigten for medarbejderen — bekræft to separate linjer: "Overnatning" og
   "DOB Overnatning", hver med korrekt antal (1), sats, og total (kr).
7. Kør "Prøvekørsel" (Excel) for perioden — bekræft at arket indeholder både
   "Overnatning (kr.)"- og "DOB Overnatning (kr.)"-rækker for medarbejderen.
8. Kør "Kør løn" (CSV-eksport) for perioden — åbn den genererede CSV-fil og bekræft to linjer for
   medarbejderen: én med Danløn-kode 14 (almindelig overnatnings-sats) og én med kode 43
   (597 kr).

- [ ] **Step 9: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: DOB-afkrydsningsfelt i opret-overnatning-modal + lønkørsel-oversigt"
```

---

## Selvgennemgang (allerede udført af planforfatteren)

- **Spec-dækning:** Kernevalg + modal (Task 6), validering (Task 1), sats-loader (Task 2),
  beregning i `_calculate_employee` (Task 3), CSV-eksport-bekræftelse (Task 4), prøvekørsel-Excel
  (Task 5), frontend-labels (Task 6). Alle spec-afsnit har en task. "Ikke inkluderet"-afsnittet
  (ingen efterredigering, ingen ekstra badge-styling) er bevidst IKKE en task.
- **Placeholder-scan:** Ingen TBD/TODO. Frontend-verifikationen (Task 6, Step 8) er manuel, som
  eksplicit begrundet af projektets manglende frontend-testframework (samme mønster som
  `2026-08-19-dynamisk-sats-kilde.md`, Task 3).
- **Type-konsistens:** `load_dob_overnight_rate_from_db(db) -> Decimal` navngivet identisk i Task 2
  og brugt uændret i Task 3. `dob_overnight_count`/`dob_overnight_rate`/`dob_overnight_kr`
  navngivet identisk i Task 3's retur-dict, Task 4's CSV-antagelse, Task 5's Excel-test, og Task
  6's frontend-forbrug. `activity_type="dob_overnatning"` (lowercase, med underscore) konsistent
  på tværs af alle tasks — matcher den allerede eksisterende `MasterPayType.code_key` i databasen.
