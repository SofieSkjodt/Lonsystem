# "Ændret af"-felt på aktiviteter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Når en bruger gemmer en ændring på en aktivitet, skal brugerens initialer vises i et felt "Ændret af" i aktivitetens detaljevisning; feltet er skjult indtil aktiviteten er ændret første gang, og en senere ændring fra en anden bruger overskriver initialerne.

**Architecture:** Genbrug det eksisterende `*_by`-initialer-mønster (`created_by`, `approved_by`, `deactivated_by` på `Activity`; `updated_by` på `SystemSettings`). Ny nullable `Activity.updated_by`-kolonne sættes ubetinget til `current_user.initials` i `PATCH /api/activities/{id}` (`update_activity`), eksponeres via `ActivityResponse`, og vises betinget i aktivitets-detaljepanelet i `app.js`.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / SQLite, Pydantic schemas, vanilla JS frontend.

## Global Constraints

- Ingen ændring af `PATCH`-endpointets øvrige adfærd udover at sætte `updated_by`.
- Der føres ikke historik over tidligere redigeringer — kun seneste ændrers initialer gemmes.
- Feltet er `NULL` indtil første ændring og overskrives ubetinget ved hver efterfølgende ændring.
- Design-spec: `docs/superpowers/specs/2026-09-10-aendret-af-felt-design.md`

---

### Task 1: Backend — `updated_by`-felt på Activity

**Files:**
- Modify: `app/database/models.py` (Activity-klassen, ved siden af `created_by`/`approved_by`/`deactivated_by`, omkring linje 157-164)
- Modify: `app/database/session.py` (`_migrate()`, omkring linje 147-171, samme sektion som `deactivated_by`-migrationen)
- Modify: `app/database/schemas.py` (`ActivityResponse`, omkring linje 151-156)
- Modify: `app/routers/activities.py` (`_to_response()` omkring linje 263-266, og `update_activity()` omkring linje 662-706)
- Test: `tests/test_activity_updated_by.py`

**Interfaces:**
- Consumes: `Activity` model (SQLAlchemy), `ActivityUpdate`/`ActivityResponse` schemas, `AppUser.initials`, eksisterende `update_activity(activity_id, body, current_user, db)` router-funktion.
- Produces: `Activity.updated_by: Optional[str]` (DB-kolonne), `ActivityResponse.updated_by: Optional[str]` — bruges af Task 2 (frontend) til at afgøre om "Ændret af"-linjen skal vises.

- [ ] **Step 1: Skriv de fejlende tests**

Opret `tests/test_activity_updated_by.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

from database.models import Activity, ActivitySource, ActivityStatus, AppUser
from database.schemas import ActivityUpdate
from calculators.pay_period import get_or_create_period_for_date


def _user(initials="LB1"):
    return AppUser(name="Test", initials=initials, role="lonbogholder", password_hash="x")


def _activity(db, employee, start=None, end=None):
    start = start or datetime(2026, 1, 5, 6, 0)
    end = end or datetime(2026, 1, 5, 14, 0)
    period = get_or_create_period_for_date(start.date(), db)
    a = Activity(
        employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.manual,
        activity_type="normal", start_time=start, end_time=end,
        status=ActivityStatus.pending, pause_intervals=[], segments=[],
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_updated_by_is_none_before_any_edit(db, employee):
    a = _activity(db, employee)
    assert a.updated_by is None


def test_update_activity_sets_updated_by_to_editor_initials(db, employee):
    from routers.activities import update_activity
    a = _activity(db, employee)
    resp = update_activity(a.id, ActivityUpdate(comment="Rettet kommentar"),
                            current_user=_user("LB1"), db=db)
    assert resp.updated_by == "LB1"


def test_update_activity_overwrites_updated_by_with_latest_editor(db, employee):
    from routers.activities import update_activity
    a = _activity(db, employee)
    update_activity(a.id, ActivityUpdate(comment="Første rettelse"),
                     current_user=_user("LB1"), db=db)
    resp = update_activity(a.id, ActivityUpdate(comment="Anden rettelse"),
                            current_user=_user("DSP"), db=db)
    assert resp.updated_by == "DSP"
```

- [ ] **Step 2: Kør testene for at bekræfte de fejler**

Run: `python -m pytest tests/test_activity_updated_by.py -v`
Expected: FAIL — `AttributeError: 'Activity' object has no attribute 'updated_by'` (eller tilsvarende, da kolonnen/feltet ikke findes endnu).

- [ ] **Step 3: Tilføj `updated_by`-kolonnen til modellen**

I `app/database/models.py`, i `Activity`-klassen, lige efter `deactivated_by`-linjen (omkring linje 164):

```python
    deactivated_by = Column(String, nullable=True)  # initialer – sat ved deaktivering
    updated_by = Column(String, nullable=True)  # initialer – seneste bruger der ændrede aktiviteten
```

- [ ] **Step 4: Tilføj migration i session.py**

I `app/database/session.py`, i `_migrate()`, lige efter `deactivated_by`-migrationsblokken (omkring linje 149-150), tilføj:

```python
        if "updated_by" not in act_cols2:
            conn.execute("ALTER TABLE activities ADD COLUMN updated_by VARCHAR")
            conn.commit()
```

(`act_cols2` er allerede hentet via `PRAGMA table_info(activities)` tidligere i samme funktion — genbrug den eksisterende variabel, ikke en ny forespørgsel.)

- [ ] **Step 5: Tilføj feltet til ActivityResponse-schemaet**

I `app/database/schemas.py`, i `ActivityResponse`, lige efter `deactivated_by`-feltet (omkring linje 151):

```python
    deactivated_by: Optional[str] = None
    updated_by: Optional[str] = None
```

- [ ] **Step 6: Map feltet i `_to_response()`**

I `app/routers/activities.py`, i `_to_response()`, lige efter `deactivated_by=a.deactivated_by,` (omkring linje 265):

```python
        deactivated_by=a.deactivated_by,
        updated_by=a.updated_by,
```

- [ ] **Step 7: Sæt feltet i `update_activity()`**

I `app/routers/activities.py`, i `update_activity()` (omkring linje 679-680), lige efter løkken der sætter felterne fra `body`:

```python
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(a, field, value)
    a.updated_by = current_user.initials
```

- [ ] **Step 8: Kør testene for at bekræfte de består**

Run: `python -m pytest tests/test_activity_updated_by.py -v`
Expected: PASS (3 passed)

- [ ] **Step 9: Kør hele testsuiten for at sikre ingen regressioner**

Run: `python -m pytest -q`
Expected: Alle eksisterende tests fortsat grønne (samme antal passerede tests som før denne opgave, plus de 3 nye).

- [ ] **Step 10: Commit**

```bash
git add app/database/models.py app/database/session.py app/database/schemas.py app/routers/activities.py tests/test_activity_updated_by.py
git commit -m "feat: tilføj updated_by-felt på aktiviteter"
```

---

### Task 2: Frontend — vis "Ændret af" i aktivitets-detaljevisning

**Files:**
- Modify: `app/static/js/app.js` (aktivitets-detaljevisning, omkring linje 1250-1254)

**Interfaces:**
- Consumes: `ActivityResponse.updated_by` (fra Task 1) på aktivitetsobjektet `a` der allerede bruges i detaljevisningen; `h()` (eksisterende HTML-escape-hjælpefunktion, samme funktion der bruges til `approved_by`/`deactivated_by` på linje 1252-1253).
- Produces: Ingen nye grænseflader for andre opgaver — ren visning.

- [ ] **Step 1: Tilføj "Ændret af"-linjen**

I `app/static/js/app.js`, i detaljevisningens template (omkring linje 1253), lige efter linjen for "Deaktiveret af":

```js
      ${a.status === "deactivated" && (a.deactivated_by || a.approved_by) ? `<div class="detail-item"><label>Deaktiveret af</label><span>${h(a.deactivated_by || a.approved_by)}</span></div>` : ""}
      ${a.updated_by ? `<div class="detail-item"><label>Ændret af</label><span>${h(a.updated_by)}</span></div>` : ""}
    </div>
```

(Erstat kun den eksisterende linje efterfulgt af `</div>` — se eksakt eksisterende indhold i filen før redigering.)

- [ ] **Step 2: Genstart backend-serveren**

`.py`-ændringerne fra Task 1 kræver servergenstart (`app.js`/HTML alene kræver kun browser-refresh, men serveren skal alligevel køre med den nye kolonne/schema fra Task 1). Stop en evt. kørende dev-server, ryd `__pycache__` om nødvendigt, og genstart den (fx `uvicorn app.main:app --reload` eller projektets egen launch-konfiguration).

- [ ] **Step 3: Verificér i browseren**

1. Åbn appen i browseren og find en eksisterende aktivitet uden tidligere redigeringer.
2. Åbn aktivitetens detaljevisning — bekræft at "Ændret af" IKKE vises.
3. Ret et felt (fx kommentar eller sluttid) og tryk "Gem ændringer".
4. Åbn detaljevisningen igen — bekræft at "Ændret af" nu vises med den loggede brugers initialer.
5. (Hvis muligt) log ind som en anden bruger, ret aktiviteten igen, og bekræft at "Ændret af" nu viser den nye brugers initialer i stedet for den forrige.

- [ ] **Step 4: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: vis \"Ændret af\" i aktivitets-detaljevisning"
```

---

## Self-Review Notes

- **Spec-dækning:** Alle 5 punkter fra spec'en (model, migration, schema, backend-sætning, frontend-visning) er dækket af Task 1 (punkt 1-4) og Task 2 (punkt 5). Scope-beslutningen (opdater ved alle PATCH-kald, ikke kun "Gem ændringer"-knappen) er implementeret ved at sætte `updated_by` centralt i `update_activity()`, som rammes af alle PATCH-kald til en aktivitet.
- **Placeholder-scan:** Ingen TBD/TODO — alle steps har komplet kode.
- **Typekonsistens:** `updated_by: Optional[str]` bruges konsistent i model (`Column(String, nullable=True)`), schema (`Optional[str] = None`) og frontend (`a.updated_by`, samme mønster som `a.deactivated_by`).
