# Lønafregning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new sidebar fane "Lønafregning" (placed under "Lønkørsel") that shows a period-total table plus one settlement table per employee (headline with rates + a 14-day breakdown), and a CSV export button that is gated on the period being locked (admin can always export).

**Architecture:** A new backend router (`app/routers/payroll_settlement_router.py`) reuses the existing `_calculate_employee()` function from `payroll_router.py` (same data source as "Lønkørsel", no duplicated payroll math) and layers on two small computations: (1) the employee's raw agreement rate + personal supplement rate shown separately in the headline, and (2) a page-wide totals aggregation across all employees. A new frontend view (plain HTML + vanilla JS, following the existing `index.html`/`app.js` patterns — no new frontend framework) renders the period totals, one card per employee, and drives a CSV export flow identical in shape to the existing "Kør løn" folder-picker modal.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (existing `app/` backend), vanilla HTML/JS/CSS (existing `app/templates/index.html` + `app/static/js/app.js` + `app/static/css/style.css`), pytest (existing `tests/`).

## Global Constraints

- Reuse `_calculate_employee()` (`app/routers/payroll_router.py:284`) as the ONLY source of hours/kr calculations — do not re-implement overtime/salt/springer math.
- The page always shows the CURRENT period only (`get_or_create_period_for_date(date.today(), db)`) — no period navigation on this page (user decision 2026-08-25).
- Two new, independent permissions: `payroll_settlement_view` and `payroll_settlement_export` (user decision: "to separate permissions").
- CSV export requires the current period to be `closed` (`PayPeriodStatus.closed`) — EXCEPT for users whose role is `admin`, who can always export (docx: "Administratoren kan eksportere altid").
- Exporting does NOT lock the period (unlike "Kør løn") — it only reads an already-computed/locked period.
- Per-employee headline shows THREE separate figures, never combined: raw overenskomstsats (kr/t), personligt tillæg (kr/t, only if present), springertillæg (kr/t, only if enabled for the period) — user decision: "To adskilte tal" / "Med kr-beløb/sats".
- Per-day rows are NEVER hidden for zero values (docx: "Her tages alle 14 dage i lønperioden – også dage uden aktiviteter. Her vises blot nulværdier i hele linjen.") — this is the opposite of the existing `payrollRow()` helper in `app.js`, which hides zero rows; do not reuse `payrollRow()` for the day table.
- Hour columns (Normal timer / Overtid 1 time før / Overtid 1-3 timer efter / Øvrig overtid) are formatted as `H:MM` (docx: `Tt:mm`), e.g. `7.5` → `"7:30"`. "Total tid" is formatted as decimal with comma, e.g. `7.5` → `"7,50"` (docx: `#,##`). Kr columns use the existing Danish thousands+comma format (`fmtKr()` in JS / a new `_fmt_kr()` in Python), e.g. `1234.5` → `"1.234,50 kr"`.
- Page-level "Total sum for denne periode" and each employee's "Total løn for {navn}" = `calc["total_kr"]` + springertillæg-kr (springer is NOT included in `calc["total_kr"]` today — confirmed via `tests/test_springertillaeg.py` and `payroll_router.py:654`). Do NOT add fraværsbetaling (sygdom/ferie/barsel/feriefri/afspadsering/skole-kursus) into this total — user decision: "Kun arbejdstid: grundløn+tillæg+OT+salt".
- Top total table's "Salttillæg" row is CONDITIONAL — omit entirely if no employee has salt in the period, show it if any employee does (user decision).
- `style.css?v=9` in `index.html:7` MUST be bumped to `v=10` if `style.css` is touched (see `CODEREF.md` cache-busting warning) — `app.js`/`index.html` need no manual bump.

---

## Task 1: Backend permissions

**Files:**
- Modify: `app/auth.py:9-29` (`ALL_PERMISSIONS` dict)
- Modify: `app/static/js/app.js:39-59` (`PERMISSION_LABELS` — must mirror `ALL_PERMISSIONS` exactly, per existing convention)
- Modify: `app/database/session.py` (add migration function + call it from `init_db()`)
- Test: `tests/test_payroll_settlement.py` (new file)

**Interfaces:**
- Produces: two new permission keys usable with `require_permission("payroll_settlement_view")` / `require_permission("payroll_settlement_export")` (from `app/auth.py`).

- [ ] **Step 1: Add the two permissions to `ALL_PERMISSIONS`**

In `app/auth.py`, edit the dict at line 9:

```python
ALL_PERMISSIONS = {
    "payroll":             "Lønkørsel",
    "absence_overview":    "Fraværsoversigt",
    "import_ddd":          "Importer .ddd",
    "user_management":     "Brugerstyring",
    "reopen_period":       "Åbn låst lønperiode",
    "stamdata":            "Stamdata",
    "view_employees":      "Se medarbejdere",
    "manage_employees":    "Tilføj medarbejdere",
    "view_vehicles":       "Se vognpark",
    "manage_vehicles":     "Tilføj vogn",
    "manage_employee_supplements": "Administrér medarbejdertillæg",
    "manage_holidays":     "Administrér helligdage",
    "anciennitet_alert":   "Anciennitetsvarsel",
    "approve_activities":  "Godkend aktiviteter",
    "view_calendar":       "Se aktivitetskalender",
    "toggle_springer":     "Sæt springertillæg",
    "vagtplan_view":       "Se vagtplan",
    "vagtplan_edit_own":   "Redigér egen linje i vagtplan",
    "vagtplan_edit_all":   "Redigér alle linjer i vagtplan",
    "payroll_settlement_view":   "Lønafregning (se)",
    "payroll_settlement_export": "Lønafregning (eksport)",
}
```

- [ ] **Step 2: Mirror the same two entries in the frontend `PERMISSION_LABELS`**

In `app/static/js/app.js`, edit the object at line 39 (add before the closing `};` at line 59):

```js
const PERMISSION_LABELS = {
  payroll:             "Lønkørsel",
  absence_overview:    "Fraværsoversigt",
  import_ddd:          "Importer .ddd",
  user_management:     "Brugerstyring",
  reopen_period:       "Åbn låst lønperiode",
  stamdata:            "Stamdata",
  view_employees:      "Se medarbejdere",
  manage_employees:    "Tilføj medarbejdere",
  view_vehicles:       "Se vognpark",
  manage_vehicles:     "Tilføj vogn",
  manage_holidays:     "Administrér helligdage",
  anciennitet_alert:   "Anciennitetsvarsel",
  approve_activities:  "Godkend aktiviteter",
  view_calendar:       "Se aktivitetskalender",
  manage_employee_supplements: "Administrér medarbejdertillæg",
  toggle_springer:     "Sæt springertillæg",
  vagtplan_view:       "Se vagtplan",
  vagtplan_edit_own:   "Redigér egen linje i vagtplan",
  vagtplan_edit_all:   "Redigér alle linjer i vagtplan",
  payroll_settlement_view:   "Lønafregning (se)",
  payroll_settlement_export: "Lønafregning (eksport)",
};
```

- [ ] **Step 3: Write the failing test for the migration function**

Create `tests/test_payroll_settlement.py`:

```python
from datetime import date
from decimal import Decimal

import pytest


def test_ensure_payroll_settlement_permissions_adds_to_lonbogholder(db, monkeypatch):
    from database.models import Role
    from database.session import _ensure_payroll_settlement_permissions
    import database.session as session_module
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=["payroll"]))
    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False, permissions=["payroll"]))
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()

    _ensure_payroll_settlement_permissions()

    lonbogholder = db.query(Role).filter(Role.name == "lonbogholder").first()
    db.refresh(lonbogholder)
    assert "payroll_settlement_view" in lonbogholder.permissions
    assert "payroll_settlement_export" in lonbogholder.permissions

    disponent = db.query(Role).filter(Role.name == "disponent").first()
    db.refresh(disponent)
    assert "payroll_settlement_view" not in disponent.permissions

    # Idempotent — running again doesn't duplicate or error
    _ensure_payroll_settlement_permissions()
    db.refresh(lonbogholder)
    assert lonbogholder.permissions.count("payroll_settlement_view") == 1
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd tests && python -m pytest test_payroll_settlement.py -v`
Expected: FAIL with `ImportError: cannot import name '_ensure_payroll_settlement_permissions'`

- [ ] **Step 5: Implement the migration function**

In `app/database/session.py`, add this function right after `_ensure_toggle_springer_permission()` (ends at line 653):

```python
def _ensure_payroll_settlement_permissions():
    """Tilføjer payroll_settlement_view + payroll_settlement_export til lonbogholder-rollen (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "lonbogholder").first()
        if role and not role.is_system:
            perms = list(role.permissions or [])
            changed = False
            for p in ("payroll_settlement_view", "payroll_settlement_export"):
                if p not in perms:
                    perms.append(p)
                    changed = True
            if changed:
                role.permissions = perms
                db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af payroll_settlement-tilladelser: {e}")
    finally:
        db.close()
```

Then add the call to `init_db()` (around line 56, right after `_ensure_toggle_springer_permission()`):

```python
    _ensure_toggle_springer_permission()
    _ensure_payroll_settlement_permissions()
    _ensure_springer_pay_type()
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd tests && python -m pytest test_payroll_settlement.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/auth.py app/static/js/app.js app/database/session.py tests/test_payroll_settlement.py
git commit -m "feat: tilføj payroll_settlement_view/export-tilladelser"
```

---

## Task 2: Backend — preview endpoint + calculation helpers

**Files:**
- Create: `app/routers/payroll_settlement_router.py`
- Modify: `app/main.py` (register the new router)
- Test: `tests/test_payroll_settlement.py` (append)

**Interfaces:**
- Consumes: `_calculate_employee(emp, start, end, db) -> dict` (`app/routers/payroll_router.py:284`), `_active_employees(db, employee_id=None) -> list[Employee]` (`app/routers/payroll_router.py:669`), `_safe_save_dir(raw_path: str) -> Path` (`app/routers/payroll_router.py:68`), `load_agreement_types_from_db(db) -> dict[str, Decimal]` and `get_active_supplement_for_period(db, employee_id, period_start, period_end) -> Optional[EmployeeSupplement]` (`app/calculators/rates_loader.py`), `get_or_create_period_for_date(d, db)` (`app/calculators/pay_period.py`).
- Produces: `_employee_settlement_data(emp, start, end, db) -> dict` with keys `employee_id, employee_number, employee_name, agreement_type, agreement_rate, personal_supplement_rate, springer_enabled, springer_rate, springer_kr, normal_hours, hourly_rate, ot_before_hours, ot_13_hours, ot_extra_hours, ot_rates, salt_kr, total_kr, days` (each `days[i]` = the corresponding `calc["days"][i]` dict with `ot_13`/`ot_extra` already folded in with `sh_kode8`/`sh_kode9`). `_page_totals(employees_data: list[dict]) -> dict` with keys `grundtimeloen_incl_tillaeg_kr, ot_before_kr, ot_13_kr, ot_extra_kr, salt_kr, total_kr`. `GET /api/payroll-settlement/preview` JSON: `{period_start, period_end, period_status, page_totals, employees}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_payroll_settlement.py`:

```python
def _setup_rates(db, employee, hourly=Decimal("150.00")):
    from database.models import MasterAgreementType, MasterOvertimeRate
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=hourly))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("50")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("75")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("100")))
    db.commit()


def test_employee_settlement_data_separates_agreement_and_personal_rate(db, employee):
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import EmployeeSupplement
    from routers.payroll_settlement_router import _employee_settlement_data
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSupplement(employee_id=employee.id, name="Ikke overenskomstmæssigt tillæg",
                               type="Timebaseret", value=Decimal("10.00"),
                               start_date=date(2025, 1, 1)))
    db.commit()

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    assert data["agreement_rate"] == 150.00
    assert data["personal_supplement_rate"] == 10.00
    assert data["hourly_rate"] == 160.00  # kombineret sats bruges fortsat til selve beregningen
    assert data["springer_enabled"] is False
    assert data["springer_kr"] == 0
    assert len(data["days"]) == 14  # alle dage i perioden, også uden aktivitet


def test_employee_settlement_data_includes_springer_kr_in_total(db, employee):
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import EmployeeSpringerFlag, MasterSupplementRate
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    from datetime import datetime
    from database.models import ActivityStatus
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("20.00")))
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=True))
    db.commit()
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    assert data["springer_enabled"] is True
    assert data["springer_rate"] == 20.00
    assert data["springer_kr"] == pytest.approx(8.0 * 20.00)
    assert data["total_kr"] == pytest.approx(8.0 * 150.00 + 8.0 * 20.00)


def test_page_totals_aggregates_across_employees():
    from routers.payroll_settlement_router import _page_totals
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    employees_data = [
        {"normal_hours": 74.0, "hourly_rate": 150.0, "springer_kr": 0.0,
         "ot_before_hours": 1.0, "ot_13_hours": 2.0, "ot_extra_hours": 0.0,
         "ot_rates": {OT_BEFORE_KEY: 50.0, OT_13_KEY: 75.0, OT_EXTRA_KEY: 100.0},
         "salt_kr": 0.0, "total_kr": 11250.0},
        {"normal_hours": 70.0, "hourly_rate": 160.0, "springer_kr": 1600.0,
         "ot_before_hours": 0.0, "ot_13_hours": 0.0, "ot_extra_hours": 3.0,
         "ot_rates": {OT_BEFORE_KEY: 50.0, OT_13_KEY: 75.0, OT_EXTRA_KEY: 100.0},
         "salt_kr": 200.0, "total_kr": 11500.0},
    ]
    totals = _page_totals(employees_data)
    assert totals["grundtimeloen_incl_tillaeg_kr"] == pytest.approx(74.0 * 150.0 + 70.0 * 160.0 + 1600.0)
    assert totals["ot_before_kr"] == pytest.approx(1.0 * 50.0)
    assert totals["ot_13_kr"] == pytest.approx(2.0 * 75.0)
    assert totals["ot_extra_kr"] == pytest.approx(3.0 * 100.0)
    assert totals["salt_kr"] == pytest.approx(200.0)
    assert totals["total_kr"] == pytest.approx(11250.0 + 11500.0)


def test_payroll_settlement_preview_returns_current_period_only(db, employee):
    from routers.payroll_settlement_router import payroll_settlement_preview
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)

    result = payroll_settlement_preview(current_user=_dummy_user(), db=db)

    assert "page_totals" in result
    assert len(result["employees"]) == 1
    assert result["employees"][0]["employee_number"] == employee.employee_number


def _dummy_user():
    from database.models import AppUser
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _assign_visible_dispatcher_group(db, employee):
    """_active_employees() (payroll_router.py:669) udelukker medarbejdere uden
    mindst én disponentgruppe med visible_in_activity_overview=True (tilføjet i
    commit 01d4c0c) — den delte 'employee'-fixture i conftest.py har ingen
    grupper, så enhver test der rammer preview/export skal selv tildele én.
    NB: dette afslørede at to EKSISTERENDE tests i test_springertillaeg.py
    (test_export_csv_post_includes_springer_line_when_enabled og
    test_export_csv_post_omits_springer_line_when_disabled) allerede fejler af
    samme årsag på main — det er en fortilstående regression, IKKE noget denne
    plan skal rette, men værd at nævne til brugeren."""
    from database.models import DispatcherGroup
    group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)
    db.add(group)
    db.commit()
    db.refresh(group)
    employee.dispatcher_groups.append(group)
    db.commit()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd tests && python -m pytest test_payroll_settlement.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'routers.payroll_settlement_router'`

- [ ] **Step 3: Create the router with the preview endpoint and helpers**

Create `app/routers/payroll_settlement_router.py`:

```python
"""
Lønafregning:
- /api/payroll-settlement/preview           – JSON til Lønafregning-siden (periodetotaler
                                              + pr. medarbejder headline + 14-dages tabel)
- /api/payroll-settlement/downloads-folder  – forslag til gem-mappe (samme mønster som Lønkørsel)
- /api/payroll-settlement/browse-folder     – native mappevælger
- /api/payroll-settlement/export-csv        – CSV med Dato/Lønnummer/timer/kr/vognnummer pr.
                                              dag pr. medarbejder; kræver låst periode (admin altid)
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import require_permission
from database.models import AppUser
from database.session import get_db

from calculators.overtime import OT_13_KEY, OT_BEFORE_KEY, OT_EXTRA_KEY
from calculators.pay_period import get_or_create_period_for_date
from calculators.rates_loader import get_active_supplement_for_period, load_agreement_types_from_db

from routers.payroll_router import _active_employees, _calculate_employee

router = APIRouter(prefix="/api/payroll-settlement", tags=["payroll-settlement"])

_view_access = require_permission("payroll_settlement_view")
_export_access = require_permission("payroll_settlement_export")


def _employee_settlement_data(emp, start: date, end: date, db: Session) -> dict:
    """Headline-info (satser vist separat) + periodetotal for én medarbejder,
    oven på den fælles _calculate_employee()-beregning (samme datakilde som Lønkørsel)."""
    calc = _calculate_employee(emp, start, end, db)

    agreement_rate = load_agreement_types_from_db(db).get(emp.agreement_type, Decimal("0"))
    supplement = get_active_supplement_for_period(db, emp.id, start, end)
    personal_supplement_rate = supplement.value if supplement else Decimal("0")

    springer_kr = (
        Decimal(str(calc["normal_hours"])) * Decimal(str(calc["springer_rate"]))
        if calc["springer_enabled"] else Decimal("0")
    )
    total_kr_with_springer = Decimal(str(calc["total_kr"])) + springer_kr

    days = [
        {**day, "ot_13": day["ot_13"] + day.get("sh_kode8", 0),
         "ot_extra": day["ot_extra"] + day.get("sh_kode9", 0)}
        for day in calc["days"]
    ]

    return {
        "employee_id": calc["employee_id"],
        "employee_number": calc["employee_number"],
        "employee_name": calc["employee_name"],
        "agreement_type": calc["agreement_type"],
        "agreement_rate": float(agreement_rate),
        "personal_supplement_rate": float(personal_supplement_rate),
        "springer_enabled": calc["springer_enabled"],
        "springer_rate": calc["springer_rate"],
        "springer_kr": float(springer_kr),
        "normal_hours": calc["normal_hours"],
        "hourly_rate": calc["hourly_rate"],
        "ot_before_hours": calc["ot_before_hours"],
        "ot_13_hours": calc["ot_13_hours"] + calc["sh_kode8_hours"],
        "ot_extra_hours": calc["ot_extra_hours"] + calc["sh_kode9_hours"],
        "ot_rates": calc["ot_rates"],
        "salt_kr": calc["salt_kr"],
        "total_kr": float(total_kr_with_springer),
        "days": days,
    }


def _page_totals(employees_data: list) -> dict:
    """Periodetotaler for hele siden – aggregeret på tværs af alle medarbejdere.
    Rækkerne er informative highlights, ikke en udtømmende opsummering: total_kr
    kan afvige fra summen af de øvrige rækker (fx søgnehelligdags-godtgørelse og
    fraværsbetaling indgår i total_kr, men har ingen egen række her)."""
    grundtimeloen_kr = sum(e["normal_hours"] * e["hourly_rate"] + e["springer_kr"] for e in employees_data)
    ot_before_kr = sum(e["ot_before_hours"] * e["ot_rates"].get(OT_BEFORE_KEY, 0) for e in employees_data)
    ot_13_kr = sum(e["ot_13_hours"] * e["ot_rates"].get(OT_13_KEY, 0) for e in employees_data)
    ot_extra_kr = sum(e["ot_extra_hours"] * e["ot_rates"].get(OT_EXTRA_KEY, 0) for e in employees_data)
    salt_kr = sum(e["salt_kr"] for e in employees_data)
    total_kr = sum(e["total_kr"] for e in employees_data)
    return {
        "grundtimeloen_incl_tillaeg_kr": round(grundtimeloen_kr, 2),
        "ot_before_kr": round(ot_before_kr, 2),
        "ot_13_kr": round(ot_13_kr, 2),
        "ot_extra_kr": round(ot_extra_kr, 2),
        "salt_kr": round(salt_kr, 2),
        "total_kr": round(total_kr, 2),
    }


def _resolve_current_period(db: Session):
    return get_or_create_period_for_date(date.today(), db)


@router.get("/preview")
def payroll_settlement_preview(current_user: AppUser = Depends(_view_access), db: Session = Depends(get_db)):
    period = _resolve_current_period(db)
    employees = _active_employees(db)
    employees_data = [_employee_settlement_data(e, period.start_date, period.end_date, db) for e in employees]
    employees_data.sort(key=lambda e: e["employee_name"] or "")
    return {
        "period_start": period.start_date.isoformat(),
        "period_end": period.end_date.isoformat(),
        "period_status": period.status.value,
        "page_totals": _page_totals(employees_data),
        "employees": employees_data,
    }
```

- [ ] **Step 4: Register the router in `main.py`**

In `app/main.py`, edit the import at line 15:

```python
from routers import import_ddd, employees, activities, payroll_router, vehicles, employee_supplements, vagtplan_comments, payroll_settlement_router
```

And add the include right after `app.include_router(payroll_router.router)` (line 95):

```python
app.include_router(payroll_router.router)
app.include_router(payroll_settlement_router.router)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd tests && python -m pytest test_payroll_settlement.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add app/routers/payroll_settlement_router.py app/main.py tests/test_payroll_settlement.py
git commit -m "feat: preview-endpoint for Lønafregning (periodetotaler + medarbejder-headlines)"
```

---

## Task 3: Backend — CSV export endpoint

**Files:**
- Modify: `app/routers/payroll_settlement_router.py` (append)
- Test: `tests/test_payroll_settlement.py` (append)

**Interfaces:**
- Consumes: `_safe_save_dir(raw_path: str) -> Path` (`app/routers/payroll_router.py:68`), `log_action(db, user, action, entity_type, entity_id, details)` (`app/auth.py:88`), `PayPeriodStatus` (`app/database/models.py`).
- Produces: `_fmt_hm(decimal_hours: float) -> str`, `_fmt_decimal_comma(v: float) -> str`, `_fmt_kr_da(v: float) -> str`, `POST /api/payroll-settlement/export-csv` (body `{output_folder: str}`) → `{filename, path}`, `GET /api/payroll-settlement/downloads-folder` → `{path}`, `GET /api/payroll-settlement/browse-folder?initial=` → `{path}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_payroll_settlement.py`:

```python
def test_fmt_hm_converts_decimal_hours_to_hm():
    from routers.payroll_settlement_router import _fmt_hm
    assert _fmt_hm(7.5) == "7:30"
    assert _fmt_hm(0) == "0:00"
    assert _fmt_hm(1.0) == "1:00"


def test_fmt_decimal_comma_uses_danish_comma():
    from routers.payroll_settlement_router import _fmt_decimal_comma
    assert _fmt_decimal_comma(7.5) == "7,50"
    assert _fmt_decimal_comma(0) == "0,00"


def test_fmt_kr_da_uses_thousands_dot_and_comma_decimal():
    from routers.payroll_settlement_router import _fmt_kr_da
    assert _fmt_kr_da(1234.5) == "1.234,50"
    assert _fmt_kr_da(0) == "0,00"


def test_export_settlement_csv_rejects_open_period_for_non_admin(db, employee, tmp_path):
    from fastapi import HTTPException
    from database.models import AppUser
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    non_admin = AppUser(name="Test", initials="LB1", role="lonbogholder", password_hash="x")

    with pytest.raises(HTTPException) as exc:
        export_settlement_csv(ExportSettlementCsvRequest(output_folder=str(tmp_path)),
                               current_user=non_admin, db=db)
    assert exc.value.status_code == 400


def test_export_settlement_csv_allows_admin_on_open_period(db, employee, tmp_path):
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)

    result = export_settlement_csv(ExportSettlementCsvRequest(output_folder=str(tmp_path)),
                                    current_user=_dummy_user(), db=db)

    csv_files = list(tmp_path.glob("lonafregning_*.csv"))
    assert len(csv_files) == 1
    assert result["filename"] == csv_files[0].name


def test_export_settlement_csv_allows_non_admin_on_closed_period(db, employee, tmp_path):
    from database.models import AppUser
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import PayPeriodStatus
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date.today(), db)
    period.status = PayPeriodStatus.closed
    db.commit()
    _assign_visible_dispatcher_group(db, employee)
    non_admin = AppUser(name="Test", initials="LB1", role="lonbogholder", password_hash="x")

    result = export_settlement_csv(ExportSettlementCsvRequest(output_folder=str(tmp_path)),
                                    current_user=non_admin, db=db)

    assert (tmp_path / result["filename"]).exists()


def test_export_settlement_csv_content_has_lonnummer_column_and_all_14_days(db, employee, tmp_path):
    from datetime import datetime
    from database.models import ActivityStatus
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    result = export_settlement_csv(ExportSettlementCsvRequest(output_folder=str(tmp_path)),
                                    current_user=_dummy_user(), db=db)

    content = (tmp_path / result["filename"]).read_text(encoding="utf-8")
    lines = [l for l in content.splitlines() if l]
    header = lines[0].split(";")
    assert header == ["Dato", "Lønnummer", "Normal timer", "Overtid 1 time før",
                       "Overtid 1-3 timer efter", "Øvrig overtid", "Total tid",
                       "Total i kr.", "Vognnummer", "Beløb"]
    # 14 dagsrækker + 1 "Total løn for"-række for den ene medarbejder
    assert len(lines) == 1 + 14 + 1
    assert employee.employee_number in lines[1]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd tests && python -m pytest test_payroll_settlement.py -v -k "export_settlement or fmt_hm or fmt_decimal or fmt_kr_da"`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the formatting helpers and the export endpoint**

Append to `app/routers/payroll_settlement_router.py` (add these imports at the top alongside the existing ones):

```python
import csv
import io
import logging
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

from auth import log_action
from database.models import PayPeriodStatus
from routers.payroll_router import _safe_save_dir
```

Then append at the end of the file:

```python
def _fmt_hm(decimal_hours: float) -> str:
    """Konverterer decimaltimer til 'Tt:mm'-format, fx 7.5 -> '7:30'."""
    total_minutes = round((decimal_hours or 0) * 60)
    hh, mm = divmod(total_minutes, 60)
    return f"{hh}:{mm:02d}"


def _fmt_decimal_comma(v: float) -> str:
    """Decimaltal med dansk komma, fx 7.5 -> '7,50'."""
    return f"{(v or 0):.2f}".replace(".", ",")


def _fmt_kr_da(v: float) -> str:
    """Dansk kr-format med tusindtalspunktum og kommadecimal, fx 1234.5 -> '1.234,50'."""
    return f"{(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@router.get("/downloads-folder")
def get_downloads_folder(current_user: AppUser = Depends(_export_access)):
    """Returnerer brugerens Downloads-mappe som forslag til gem-placering."""
    return {"path": str(Path.home() / "Downloads")}


@router.get("/browse-folder")
def browse_folder(initial: str = "", current_user: AppUser = Depends(_export_access)):
    """Åbner en native Windows-mappevælger og returnerer den valgte sti."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", True)
    start = initial if initial else str(Path.home() / "Downloads")
    chosen = filedialog.askdirectory(initialdir=start, title="Vælg mappe til CSV-fil")
    root.destroy()
    if not chosen:
        return {"path": None}
    return {"path": str(Path(chosen))}


class ExportSettlementCsvRequest(BaseModel):
    output_folder: str


@router.post("/export-csv")
def export_settlement_csv(body: ExportSettlementCsvRequest,
                          current_user: AppUser = Depends(_export_access),
                          db: Session = Depends(get_db)):
    """
    Eksporterer Lønafregning som CSV: én række pr. dag pr. medarbejder (alle 14
    dage) plus en 'Total løn for'-række, med lønnummer tilføjet. Kræver at den
    aktuelle periode er låst – administratorer kan altid eksportere.
    """
    period = _resolve_current_period(db)
    is_admin = current_user.role == "admin"
    if period.status != PayPeriodStatus.closed and not is_admin:
        raise HTTPException(
            400,
            "Lønperioden skal være låst, før den kan eksporteres. Kør løn under Lønkørsel-fanen først.",
        )

    employees = _active_employees(db)
    employees_data = [_employee_settlement_data(e, period.start_date, period.end_date, db) for e in employees]
    employees_data.sort(key=lambda e: e["employee_name"] or "")

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Dato", "Lønnummer", "Normal timer", "Overtid 1 time før",
                      "Overtid 1-3 timer efter", "Øvrig overtid", "Total tid",
                      "Total i kr.", "Vognnummer", "Beløb"])
    for e in employees_data:
        for day in e["days"]:
            d = date.fromisoformat(day["date"])
            vognnummer = day["absence_type"] or day["vehicle_number"] or ""
            writer.writerow([
                d.strftime("%d-%m-%Y"), e["employee_number"],
                _fmt_hm(day["normal"]), _fmt_hm(day["ot_before"]),
                _fmt_hm(day["ot_13"]), _fmt_hm(day["ot_extra"]),
                _fmt_decimal_comma(day["total_hours"]), _fmt_kr_da(day["total_kr"]),
                vognnummer, _fmt_kr_da(day["total_kr"]),
            ])
        writer.writerow([f"Total løn for {e['employee_name']}", "", "", "", "", "", "",
                          "", "", _fmt_kr_da(e["total_kr"])])

    filename = f"lonafregning_{period.start_date.isoformat()}_{period.end_date.isoformat()}.csv"
    save_dir = _safe_save_dir(body.output_folder)
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logging.error(f"Kan ikke oprette mappe '{save_dir}': {exc}")
        raise HTTPException(400, "Mappen kunne ikke oprettes – tjek stien og rettigheder")
    try:
        (save_dir / filename).write_bytes(output.getvalue().encode("utf-8"))
    except PermissionError:
        raise HTTPException(
            400,
            f"Kunne ikke gemme filen '{filename}' – tjek om den er åben i Excel eller et andet program, og prøv igen.",
        )

    log_action(db, current_user, "payroll_settlement_export", "pay_period", period.id,
               f"Lønafregning eksporteret for periode {period.start_date} – {period.end_date}")
    db.commit()

    return {"filename": filename, "path": str(save_dir / filename)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd tests && python -m pytest test_payroll_settlement.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add app/routers/payroll_settlement_router.py tests/test_payroll_settlement.py
git commit -m "feat: CSV-eksport for Lønafregning (låst periode kræves, admin altid)"
```

---

## Task 4: Frontend — sidebar, view HTML, CSV modal, CSS

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/css/style.css`

**Interfaces:**
- Produces: sidebar item `data-view="payroll-settlement"` gated by `data-perm-require="payroll_settlement_view"`; view block with `#settlement-period-label`, `#settlement-preview-container`, `#btn-settlement-export` (gated by `data-perm-require="payroll_settlement_export"`); modal `#modal-settlement-csv` with `#settlement-csv-folder`, `#settlement-csv-browse-btn`, `#settlement-csv-result`. New CSS classes `.settlement-table`, `.settlement-table th`, `.settlement-table td` for the 9-column day breakdown (reusing the existing green Lønkørsel palette).

- [ ] **Step 1: Bump the CSS cache-buster version**

In `app/templates/index.html:7`:

```html
<link rel="stylesheet" href="/static/css/style.css?v=10">
```

- [ ] **Step 2: Add the sidebar item**

In `app/templates/index.html`, insert right after the "Lønkørsel" sidebar item (line 90-92):

```html
      <div class="sidebar-item" data-view="payroll" data-perm-require="payroll">
        <span class="icon">💰</span> Lønkørsel
      </div>
      <div class="sidebar-item" data-view="payroll-settlement" data-perm-require="payroll_settlement_view">
        <span class="icon">🧾</span> Lønafregning
      </div>
      <div class="sidebar-item" data-view="absence-overview" data-perm-require="absence_overview">
```

- [ ] **Step 3: Add the view block**

In `app/templates/index.html`, insert right after the closing `</div>` of the "PAYROLL VIEW" block (after line 186, before the "ABSENCE OVERVIEW VIEW" comment):

```html
    <!-- ══════════════ PAYROLL SETTLEMENT VIEW ══════════════ -->
    <div class="view hidden" data-view="payroll-settlement">
      <div class="toolbar" style="flex-wrap:nowrap">
        <h2 style="font-size:16px;font-weight:600;white-space:nowrap">Lønafregning –
          <span id="settlement-period-label" style="font-weight:400;color:var(--text-light)">indlæser...</span>
        </h2>
        <div class="spacer"></div>
        <button class="btn btn-secondary" onclick="loadPayrollSettlement()">&#128260; Opdater</button>
        <button id="btn-settlement-export" class="btn btn-success" onclick="exportSettlementCsv()"
                data-perm-require="payroll_settlement_export"
                title="Kræver at lønperioden er låst (medmindre du er administrator)">&#128190; Eksportér CSV</button>
      </div>
      <div id="settlement-preview-container"></div>
    </div>

```

- [ ] **Step 4: Add the CSV export modal**

In `app/templates/index.html`, insert right after the closing `</div>` of `#modal-csv` (after line 1232):

```html
<!-- Lønafregning CSV-eksport-modal -->
<div id="modal-settlement-csv" class="modal-overlay">
  <div class="modal" style="width:480px">
    <div class="modal-header">
      <h2>Eksportér lønafregning (CSV)</h2>
      <button class="modal-close" onclick="closeModal('modal-settlement-csv')">&#215;</button>
    </div>
    <div class="modal-body">
      <p style="margin-bottom:16px;font-size:14px;line-height:1.5">CSV-filen indeholder timer, kr. og vognnummer pr. dag for hver medarbejder i den aktuelle lønperiode.</p>
      <div class="form-group">
        <label>Gem CSV-fil i mappe <span style="color:var(--danger)">*</span></label>
        <div style="display:flex;gap:8px">
          <input type="text" id="settlement-csv-folder" placeholder="Sti til mappe..." style="flex:1">
          <button type="button" class="btn btn-secondary" onclick="browseSettlementCsvFolder()" id="settlement-csv-browse-btn">Gennemse</button>
        </div>
      </div>
      <div id="settlement-csv-result" style="font-size:13px;color:var(--text-light)"></div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-settlement-csv')">Annuller</button>
      <button class="btn btn-success" onclick="confirmExportSettlementCsv()">Eksportér</button>
    </div>
  </div>
</div>
```

- [ ] **Step 5: Add CSS for the 9-column day-breakdown table**

In `app/static/css/style.css`, add right after the existing `.payroll-row .label { color: var(--text-light); }` rule (after line 646):

```css
/* ── Payroll settlement (Lønafregning) day table ── */
.settlement-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.settlement-table th {
  background: #d4edcc;
  color: var(--primary-dark);
  font-weight: 700;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.settlement-table td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.settlement-table td.num { text-align: right; }
.settlement-table tr:last-child td { border-bottom: none; }
.settlement-table tr.settlement-total-row td { font-weight: 700; background: #f0fdf4; }
```

- [ ] **Step 6: Manually verify the HTML is well-formed**

Run: `python -c "import xml.dom.minidom" ` is not applicable (this is HTML, not XML) — instead, start the dev server and check the browser console for errors (covered in Task 6). No automated test for this step; proceed to commit.

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html app/static/css/style.css
git commit -m "feat: HTML/CSS for Lønafregning-fanen (sidebar, side, CSV-modal)"
```

---

## Task 5: Frontend — JS load/render/export logic

**Files:**
- Modify: `app/static/js/app.js`

**Interfaces:**
- Consumes: `GET`, `POST` (`app/static/js/app.js:89-90`), `h()` (`escapeHtml`, line 12), `fmtKr()` (line 4759), `formatDate()` (line 4738), `formatDateShort()` (line 4741), `toast()`, `openModal()`, `closeModal()`, `setLoading()`, `state.currentUser`.
- Produces: `loadPayrollSettlement()`, `renderPayrollSettlement(data)`, `fmtHM(hours)`, `fmtDecimalComma(v)`, `exportSettlementCsv()`, `browseSettlementCsvFolder()`, `confirmExportSettlementCsv()`. Wires `"payroll-settlement"` into `setView()`.

- [ ] **Step 1: Wire the new view into `setView()`**

In `app/static/js/app.js`, edit the function at line 118-134:

```js
function setView(view) {
  state.currentView = view;
  document.querySelectorAll(".sidebar-item").forEach(el =>
    el.classList.toggle("active", el.dataset.view === view));
  document.querySelectorAll(".view").forEach(el =>
    el.classList.toggle("hidden", el.dataset.view !== view));

  if (view === "activities")        loadActivities();
  if (view === "employees")         loadEmployees();
  if (view === "payroll")           loadPayrollPreview();
  if (view === "payroll-settlement") loadPayrollSettlement();
  if (view === "absence-overview")  loadAbsenceOverview();
  if (view === "vehicles")          loadVehicles();
  if (view === "employee-supplements") loadEmployeeSupplementsView();
  if (view === "users-admin")       loadUsersAdminView();
  if (view === "stamdata")          loadStamdata();
  if (view === "vagtplan")          loadVagtplan();
}
```

- [ ] **Step 2: Add the load/render/format/export functions**

In `app/static/js/app.js`, insert a new section right after `confirmExportCsv()` (after line 3111, before the `// ── Absence Overview ──` comment):

```js
// ── Lønafregning ─────────────────────────────────────────────────────────
async function loadPayrollSettlement() {
  setLoading(true);
  try {
    const data = await GET("/api/payroll-settlement/preview");
    renderPayrollSettlement(data);
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function fmtHM(hours) {
  const totalMinutes = Math.round((hours || 0) * 60);
  const hh = Math.floor(totalMinutes / 60), mm = totalMinutes % 60;
  return `${hh}:${String(mm).padStart(2, "0")}`;
}

function fmtDecimalComma(v) {
  return (v || 0).toFixed(2).replace(".", ",");
}

function renderPayrollSettlement(data) {
  state.settlementPeriodClosed = data.period_status === "closed";
  document.getElementById("settlement-period-label").textContent =
    `${formatDateShort(data.period_start)} – ${formatDateShort(data.period_end)}`;

  const container = document.getElementById("settlement-preview-container");
  container.innerHTML = "";

  if (!state.settlementPeriodClosed) {
    const info = document.createElement("div");
    info.className = "alert-banner mb-16";
    info.innerHTML = `<span class="icon">ℹ️</span><div class="text"><h4>Perioden er ikke låst endnu</h4>Eksport kræver, at lønnen er kørt for perioden under Lønkørsel (administratorer kan eksportere alligevel).</div>`;
    container.appendChild(info);
  }

  const t = data.page_totals;
  const totalCard = document.createElement("div");
  totalCard.className = "payroll-employee";
  totalCard.innerHTML = `
    <div class="payroll-emp-header"><div class="payroll-emp-info"><h3>Total sum for perioden</h3></div></div>
    <div class="payroll-rows">
      <div class="payroll-row"><div class="label">Grundtimeløn inkl. tillæg</div><div></div><div></div><div class="text-right">${fmtKr(t.grundtimeloen_incl_tillaeg_kr)}</div></div>
      <div class="payroll-row"><div class="label">Overtid Timen før</div><div></div><div></div><div class="text-right">${fmtKr(t.ot_before_kr)}</div></div>
      <div class="payroll-row"><div class="label">Overtid 1-3 time efter</div><div></div><div></div><div class="text-right">${fmtKr(t.ot_13_kr)}</div></div>
      <div class="payroll-row"><div class="label">Overtid</div><div></div><div></div><div class="text-right">${fmtKr(t.ot_extra_kr)}</div></div>
      ${t.salt_kr > 0 ? `<div class="payroll-row"><div class="label">Salttillæg</div><div></div><div></div><div class="text-right">${fmtKr(t.salt_kr)}</div></div>` : ""}
      <div class="payroll-row total"><div>Total sum for denne periode</div><div></div><div></div><div class="text-right">${fmtKr(t.total_kr)}</div></div>
    </div>`;
  container.appendChild(totalCard);

  if (data.employees.length === 0) {
    container.innerHTML += `<div class="empty-state"><div class="icon">🧾</div><h3>Ingen aktive medarbejdere</h3></div>`;
    return;
  }

  for (const emp of data.employees) {
    const el = document.createElement("div");
    el.className = "payroll-employee";
    const headlineParts = [`${h(emp.agreement_type)} (${emp.agreement_rate.toFixed(2)} kr/t)`];
    if (emp.personal_supplement_rate > 0) {
      headlineParts.push(`Personligt tillæg: ${emp.personal_supplement_rate.toFixed(2)} kr/t`);
    }
    if (emp.springer_enabled) {
      headlineParts.push(`Springertillæg: ${emp.springer_rate.toFixed(2)} kr/t`);
    }
    const dayRows = emp.days.map(day => {
      const vognnummer = day.absence_type || day.vehicle_number || "";
      return `<tr>
        <td>${formatDate(day.date)}</td>
        <td class="num">${fmtHM(day.normal)}</td>
        <td class="num">${fmtHM(day.ot_before)}</td>
        <td class="num">${fmtHM(day.ot_13)}</td>
        <td class="num">${fmtHM(day.ot_extra)}</td>
        <td class="num">${fmtDecimalComma(day.total_hours)}</td>
        <td class="num">${fmtKr(day.total_kr)}</td>
        <td>${h(vognnummer)}</td>
        <td class="num">${fmtKr(day.total_kr)}</td>
      </tr>`;
    }).join("");
    el.innerHTML = `
      <div class="payroll-emp-header">
        <div class="emp-avatar" style="width:34px;height:34px;font-size:13px">${h(emp.employee_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase())}</div>
        <div class="payroll-emp-info">
          <h3>${h(emp.employee_name)}</h3>
          <div class="emp-meta">${h(emp.employee_number)} · ${headlineParts.map(h).join(" · ")}</div>
        </div>
      </div>
      <div style="overflow-x:auto">
        <table class="settlement-table">
          <thead><tr>
            <th>Dato</th><th>Normal timer</th><th>Overtid 1 time før</th>
            <th>Overtid 1-3 timer efter</th><th>Øvrig overtid</th><th>Total tid</th>
            <th>Total i kr.</th><th>Vognnummer</th><th>Beløb</th>
          </tr></thead>
          <tbody>
            ${dayRows}
            <tr class="settlement-total-row">
              <td colspan="6">Total løn for ${h(emp.employee_name)}</td>
              <td class="num">${fmtKr(emp.total_kr)}</td><td></td><td class="num">${fmtKr(emp.total_kr)}</td>
            </tr>
          </tbody>
        </table>
      </div>`;
    container.appendChild(el);
  }
}

async function exportSettlementCsv() {
  const isAdmin = state.currentUser?.role === "admin";
  if (state.settlementPeriodClosed === false && !isAdmin) {
    toast("Lønperioden skal være låst, før den kan eksporteres. Kør løn under Lønkørsel-fanen først.", "error");
    return;
  }
  document.getElementById("settlement-csv-result").textContent = "";
  try {
    const res = await GET("/api/payroll-settlement/downloads-folder");
    document.getElementById("settlement-csv-folder").value = res.path;
  } catch { /* lad feltet stå tomt */ }
  openModal("modal-settlement-csv");
}

async function browseSettlementCsvFolder() {
  const btn = document.getElementById("settlement-csv-browse-btn");
  btn.disabled = true; btn.textContent = "Venter...";
  try {
    const current = document.getElementById("settlement-csv-folder").value.trim();
    const res = await GET(`/api/payroll-settlement/browse-folder?initial=${encodeURIComponent(current)}`);
    if (res.path) document.getElementById("settlement-csv-folder").value = res.path;
  } catch { toast("Kunne ikke åbne mappevælger", "error"); }
  finally { btn.disabled = false; btn.textContent = "Gennemse"; }
}

async function confirmExportSettlementCsv() {
  const folder = document.getElementById("settlement-csv-folder").value.trim();
  if (!folder) { toast("Angiv en mappe at gemme CSV-filen i", "error"); return; }
  setLoading(true);
  try {
    const result = await POST("/api/payroll-settlement/export-csv", { output_folder: folder });
    toast(`Lønafregning eksporteret: ${result.filename}`, "success");
    closeModal("modal-settlement-csv");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}
```

- [ ] **Step 3: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: JS-visning og CSV-eksport for Lønafregning"
```

---

## Task 6: Manual browser verification

**Files:** none (verification only)

- [ ] **Step 1: Start the dev server**

Run: `cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

- [ ] **Step 2: Log in as admin and open the new fane**

Log in with `admin`/`admin`. Confirm the "Lønafregning" sidebar item appears directly under "Lønkørsel". Click it and confirm:
- The period label shows the current period's dates.
- The top "Total sum for perioden" card shows Grundtimeløn/OT-rows and a grand total; the "Salttillæg" row only appears if some employee has salt this period.
- Each employee has a card with a headline showing `overenskomsttype (sats kr/t)`, and — only when applicable — `Personligt tillæg: X kr/t` and `Springertillæg: X kr/t`.
- Each employee's day table has exactly 14 rows (including zero-value days), formatted as `H:MM` for the four hour columns and `X,XX` for "Total tid".

- [ ] **Step 3: Verify the export gating**

With the current period NOT locked: confirm the info banner is shown, and clicking "Eksportér CSV" as admin still opens the folder-picker modal (admin bypass). Export to a scratch folder and open the resulting `lonafregning_*.csv` — confirm the header row and that a "Total løn for {navn}" row appears after each employee's 14 day-rows.

Then log in as a non-admin user with `payroll_settlement_export` (e.g. a `lonbogholder`), with the period still open: confirm clicking "Eksportér CSV" shows the toast error and does NOT open the modal. Lock the period via "Kør løn" under Lønkørsel, then retry — confirm the export now succeeds for the non-admin user too.

- [ ] **Step 4: Verify permission gating**

As a user WITHOUT `payroll_settlement_view` (e.g. a bare `disponent` before any manual role edit), confirm the "Lønafregning" sidebar item is hidden entirely. Grant `payroll_settlement_view` only (not `_export`) via the Brugere → role editor, reload, and confirm the fane is visible but the "Eksportér CSV" button is hidden.

- [ ] **Step 5: Report results**

No commit for this task — report pass/fail for each check above.
