# Permanent sletning af manuelt oprettet normal tid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En manuelt oprettet normal-tid-aktivitet kan slettes permanent via samme "Slet aktiviteten helt"-checkbox som fravær allerede har. Takograf-importeret (system-oprettet) normal tid forbliver begrænset til kun deaktivering.

**Architecture:** Udvider den eksisterende `DELETE /api/activities/{id}`-endpoint (fra commit `f16d743`) med en kildebetinget regel i stedet for en ubetinget type-afvisning. Frontend-checkboxens synlighed og tekst gøres tilsvarende betinget af `is_manual`.

**Tech Stack:** Python/FastAPI (backend), vanilla JavaScript (frontend). Backend testes med pytest; frontend verificeres manuelt i browseren (intet JS-testframework i projektet).

## Global Constraints

- Ingen ændring af deaktiverings-flowet (`POST /{id}/deactivate`) i sig selv
- Fraværstypers eksisterende slette-adfærd er fuldstændig uændret
- `split_children`-tjekket i `delete_activity()` bevares uændret
- **Denne session committer/pusher IKKE selv** – alle steps er begrænset til filredigering og verifikation; du gennemgår og committer selv i VS Code, jf. din instruks
- Spec: `docs/superpowers/specs/2026-09-04-slet-normal-tid-design.md`

---

## Filstruktur

```
app/
  routers/activities.py     # MODIFY: delete_activity() (linje 721-739) – kildebetinget regel
  templates/index.html       # MODIFY: deactivate-hide-vagtplan-group (linje 837-842) – span til dynamisk tekst
  static/js/app.js            # MODIFY: openDeactivateModal() (linje 1267-1276) – synlighed + dynamisk tekst
tests/
  test_vagtplan.py             # MODIFY: erstat test_delete_activity_rejects_normal_activity_type
```

---

## Task 1: Backend – kildebetinget sletteregel

**Files:**
- Modify: `app/routers/activities.py:721-739`
- Modify: `tests/test_vagtplan.py:354-365` (erstatter `test_delete_activity_rejects_normal_activity_type`)

**Interfaces:**
- Consumes: `ActivitySource` (allerede importeret i `activities.py:16`)
- Produces: `delete_activity(activity_id, current_user, db)` – uændret signatur, ny betinget fejlbesked for normal-tid-aktiviteter der ikke er manuelt oprettet

- [ ] **Step 1: Erstat den eksisterende test i `tests/test_vagtplan.py`**

Find (linje 354-365):

```python
def test_delete_activity_rejects_normal_activity_type(db, employee):
    from routers.activities import create_manual_activity, delete_activity
    from database.schemas import ActivityCreate
    from datetime import datetime as _dt
    body = ActivityCreate(
        employee_id=employee.id, activity_type="normal",
        start_time=_dt(2026, 1, 5, 6, 0), end_time=_dt(2026, 1, 5, 14, 0),
    )
    a = create_manual_activity(body, current_user=_dummy_user(), db=db)
    with pytest.raises(HTTPException) as exc:
        delete_activity(a.id, current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400
```

Erstat med:

```python
def test_delete_activity_allows_manually_created_normal_activity(db, employee):
    from routers.activities import create_manual_activity, delete_activity
    from database.schemas import ActivityCreate
    from database.models import Activity
    from datetime import datetime as _dt
    body = ActivityCreate(
        employee_id=employee.id, activity_type="normal",
        start_time=_dt(2026, 1, 5, 6, 0), end_time=_dt(2026, 1, 5, 14, 0),
        vehicle_number="2321",
    )
    a = create_manual_activity(body, current_user=_dummy_user(), db=db)
    assert a.source == ActivitySource.manual
    delete_activity(a.id, current_user=_dummy_user(), db=db)
    assert db.query(Activity).filter(Activity.id == a.id).first() is None


def test_delete_activity_rejects_tachograph_normal_activity(db, employee):
    from routers.activities import delete_activity
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import Activity
    from datetime import datetime as _dt
    period = get_or_create_period_for_date(_dt(2026, 1, 5).date(), db)
    a = Activity(
        employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.tachograph,
        activity_type="normal", start_time=_dt(2026, 1, 5, 6, 0), end_time=_dt(2026, 1, 5, 14, 0),
        status=ActivityStatus.pending, pause_intervals=[], segments=[],
    )
    db.add(a)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        delete_activity(a.id, current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400
```

Tjek at `ActivitySource` og `ActivityStatus` allerede er importeret øverst i `tests/test_vagtplan.py` (samme linje som den eksisterende `from database.models import ActivitySource, ActivityStatus, Activity, AppUser`, jf. linje 43 i filen) – hvis ikke, tilføj importen.

- [ ] **Step 2: Kør de to nye tests og bekræft FAIL**

```bash
cd app && python -m pytest ../tests/test_vagtplan.py -v -k "delete_activity_allows_manually_created_normal or delete_activity_rejects_tachograph_normal"
```

Forventet: `test_delete_activity_allows_manually_created_normal_activity` FEJLER (backend afviser stadig ALT normal tid ubetinget, uanset kilde – `400`-fejl hvor testen forventer succesfuld sletning). `test_delete_activity_rejects_tachograph_normal_activity` PASSERER allerede (den nuværende ubetingede regel afviser også dette tilfælde, blot af en anden – for bred – grund).

- [ ] **Step 3: Opdater `delete_activity()` i `app/routers/activities.py`**

Find (linje 721-739):

```python
def delete_activity(activity_id: int,
                    current_user: AppUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Sletter aktiviteten permanent (ikke bare deaktiverer/skjuler). Kun tilladt for
    fraværsaktiviteter (activity_type != 'normal') – uanset om de er oprettet via
    Vagtplan eller manuelt via Aktivitetsoversigten. Brugt af 'slet aktiviteten
    helt'-checkboksen i deaktiver-modalen, som fjerner aktiviteten fra både
    Vagtplan og Aktivitetsoversigt."""
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(404, "Aktivitet ikke fundet")
    if a.activity_type == "normal":
        raise HTTPException(400, "Kun fraværsaktiviteter kan slettes helt")
    if a.split_children:
        raise HTTPException(400, "Aktiviteten er splittet og kan ikke slettes – fortryd splittet først")
    log_action(db, current_user, "delete_activity", "activity", a.id,
               f"Slettet permanent for {a.employee.name} ({a.start_time.strftime('%d-%m-%Y')}, {a.activity_type})")
    db.delete(a)
    db.commit()
```

Erstat med:

```python
def delete_activity(activity_id: int,
                    current_user: AppUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Sletter aktiviteten permanent (ikke bare deaktiverer/skjuler). Tilladt for alle
    fraværstyper (uanset kilde), samt for normal tid der er oprettet manuelt via
    Aktivitetsoversigten. Takograf-importeret normal tid kan IKKE slettes helt – kun
    deaktiveres – da det er kørselsdata fra kortet. Brugt af 'slet aktiviteten
    helt'-checkboksen i deaktiver-modalen."""
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(404, "Aktivitet ikke fundet")
    if a.activity_type == "normal" and a.source != ActivitySource.manual:
        raise HTTPException(400, "Kun manuelt oprettede aktiviteter med normal tid kan slettes helt")
    if a.split_children:
        raise HTTPException(400, "Aktiviteten er splittet og kan ikke slettes – fortryd splittet først")
    log_action(db, current_user, "delete_activity", "activity", a.id,
               f"Slettet permanent for {a.employee.name} ({a.start_time.strftime('%d-%m-%Y')}, {a.activity_type})")
    db.delete(a)
    db.commit()
```

- [ ] **Step 4: Kør tests og bekræft PASS**

```bash
cd app && python -m pytest ../tests/test_vagtplan.py -v
```

Forventet: alle tests `PASSED`, inkl. de to nye og de allerede eksisterende `test_delete_activity_removes_row_permanently`, `test_delete_activity_allows_absence_regardless_of_source`, `test_delete_activity_rejects_unknown_id`, `test_delete_activity_rejects_split_activity`.

- [ ] **Step 5: Kør fuld test-suite**

```bash
cd app && python -m pytest ../tests/ -q
```

Forventet: alle tests `PASSED`, ingen regressioner.

---

## Task 2: Frontend – betinget checkbox-synlighed og -tekst

**Files:**
- Modify: `app/templates/index.html:837-842`
- Modify: `app/static/js/app.js:1267-1276`

**Interfaces:**
- Consumes: `a.is_manual` (allerede eksisterende felt på det aktivitetsobjekt `_findLoadedActivity()` returnerer)
- Produces: ingen nye funktioner – ren udvidelse af `openDeactivateModal()`s eksisterende logik

- [ ] **Step 1: Pak checkbox-teksten ind i et span med id, i `app/templates/index.html`**

Find (linje 837-842):

```html
      <div class="form-group" id="deactivate-hide-vagtplan-group" style="display:none">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
          <input type="checkbox" id="deactivate-hide-vagtplan" style="width:16px;height:16px;cursor:pointer">
          Slet aktiviteten helt (fjernes permanent fra både Vagtplan og Aktivitetsoversigt)
        </label>
      </div>
```

Erstat med:

```html
      <div class="form-group" id="deactivate-hide-vagtplan-group" style="display:none">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
          <input type="checkbox" id="deactivate-hide-vagtplan" style="width:16px;height:16px;cursor:pointer">
          <span id="deactivate-delete-label-text">Slet aktiviteten helt (fjernes permanent fra både Vagtplan og Aktivitetsoversigt)</span>
        </label>
      </div>
```

- [ ] **Step 2: Opdater `openDeactivateModal()` i `app/static/js/app.js`**

Find (linje 1267-1276):

```js
function openDeactivateModal() {
  document.getElementById("deactivate-comment").value = "";
  document.getElementById("deactivate-hide-vagtplan").checked = false;
  const a = _findLoadedActivity(state.selectedActivityId);
  document.getElementById("deactivate-hide-vagtplan-group").style.display =
    (a && a.activity_type !== "normal") ? "" : "none";
  const lbl = document.getElementById("deactivate-user-label");
  if (lbl) lbl.textContent = state.currentUser ? `Deaktiveres af: ${state.currentUser.name} (${state.currentUser.initials})` : "";
  openModal("modal-deactivate");
}
```

Erstat med:

```js
function openDeactivateModal() {
  document.getElementById("deactivate-comment").value = "";
  document.getElementById("deactivate-hide-vagtplan").checked = false;
  const a = _findLoadedActivity(state.selectedActivityId);
  const canDeleteEntirely = a && (a.activity_type !== "normal" || a.is_manual);
  document.getElementById("deactivate-hide-vagtplan-group").style.display = canDeleteEntirely ? "" : "none";
  if (canDeleteEntirely) {
    document.getElementById("deactivate-delete-label-text").textContent = a.activity_type === "normal"
      ? "Slet aktiviteten helt (fjernes permanent fra Aktivitetsoversigt)"
      : "Slet aktiviteten helt (fjernes permanent fra både Vagtplan og Aktivitetsoversigt)";
  }
  const lbl = document.getElementById("deactivate-user-label");
  if (lbl) lbl.textContent = state.currentUser ? `Deaktiveres af: ${state.currentUser.name} (${state.currentUser.initials})` : "";
  openModal("modal-deactivate");
}
```

- [ ] **Step 3: Manuel browser-verifikation**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet.

1. Åbn detaljevisningen for en **manuelt oprettet normal-tid-aktivitet** (fx en du selv opretter midlertidigt til testen – husk at rydde den op igen bagefter, medmindre du rent faktisk vil slette den som en del af testen), klik "Deaktiver".
2. Bekræft at checkboksen nu vises, med teksten "Slet aktiviteten helt (fjernes permanent fra Aktivitetsoversigt)" – uden Vagtplan-nævnelse.
3. Åbn detaljevisningen for en **takograf-importeret normal-tid-aktivitet** (`state.activities.find(a => a.activity_type === "normal" && !a.is_manual)` i konsollen), klik "Deaktiver".
4. Bekræft at checkboksen IKKE vises for denne aktivitet.
5. Åbn detaljevisningen for en **fraværsaktivitet** (fx `state.activities.find(a => a.activity_type !== "normal")`), klik "Deaktiver".
6. Bekræft at checkboksen fortsat vises, med den oprindelige tekst "Slet aktiviteten helt (fjernes permanent fra både Vagtplan og Aktivitetsoversigt)" – uændret.
7. Bekræft at et faktisk klik på checkboksen + "Bekræft" for den manuelle normal-tid-aktivitet fra trin 1 rent faktisk sletter den permanent (kald evt. `fetch('/api/activities/<id>').then(r=>r.status)` bagefter og bekræft `404`).

- [ ] **Step 4: Kør fuld test-suite igen som slutkontrol**

```bash
cd app && python -m pytest ../tests/ -q
```

Forventet: alle tests `PASSED`.

---

## Self-Review

**Spec coverage:**
- ✅ Backend tillader nu sletning af manuelt oprettet normal tid, afviser fortsat takograf-importeret normal tid
- ✅ Fraværstypers eksisterende adfærd (enhver kilde) er uændret – dækket af de bevarede eksisterende tests
- ✅ `split_children`-tjekket er uændret
- ✅ Checkbox-synlighed udvidet med `is_manual`-betingelse
- ✅ Dynamisk checkbox-tekst uden Vagtplan-nævnelse for normal tid
- ✅ Ingen `git add`/`git commit`-steps nogen steder i planen, jf. den globale begrænsning

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, testene har konkrete assertions, verifikationstrinnet har konkrete handlinger.

**Type-konsistens:** `a.is_manual` (boolean, allerede eksisterende felt) bruges konsistent i Task 2's Step 2 og verifikationstrinnet. `ActivitySource.manual`/`ActivitySource.tachograph` bruges konsistent i Task 1's backend-kode og tests, matcher den eksisterende enum i `database/models.py`.
