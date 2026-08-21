# Disponentgruppe-synlighed i aktivitetsoversigten Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Gør det muligt i Stamdata → Disponentgrupper at vælge, hvilke grupper (og dermed deres medarbejdere) der vises i aktivitetsoversigten — en global on/off-flag pr. gruppe.

**Architecture:** Ny boolean-kolonne `visible_in_activity_overview` på `dispatcher_groups` (default `true`), eksponeret via det eksisterende `DispatcherGroupResponse`-schema. Filtreringen sker udelukkende client-side i `app.js`'s tre aktivitetsoversigt-funktioner — `/api/activities` og `/api/employees` forbliver uændrede, så alle andre visninger er upåvirkede.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (WAL), vanilla JS/HTML frontend, pytest.

## Global Constraints

- Ændringer i `.py`-filer kræver servergenstart; `app.js` har automatisk cache-busting og kræver kun browser-refresh.
- Ingen ny permission — genbruger den eksisterende `stamdata`-tilladelse på disponentgruppe-CRUD'en.
- `/api/activities` og `/api/employees` (den generelle liste-endpoint) må IKKE ændre adfærd — kun aktivitetsoversigtens tre frontend-filterfunktioner må filtrere efter den nye flag.
- Default for eksisterende og nye grupper er `synlig` (`true`).
- Medarbejder uden nogen disponentgruppe skal betragtes som "ingen synlig gruppe" og skjules fra aktivitetsoversigten.
- Se det fulde design: [docs/superpowers/specs/2026-08-21-disponentgruppe-synlighed-design.md](../specs/2026-08-21-disponentgruppe-synlighed-design.md)

---

## Task 1: Data-fix — tildel Magne Sørensen (34362) disponentgruppen "2 - Kran"

Medarbejder-id 79 (Magne Sørensen, lønnr. 34362) har i dag ingen disponentgruppe. Når Task 5/6 er live, vil han derfor forsvinde fra aktivitetsoversigten, fordi "ingen gruppe" behandles som "ingen synlig gruppe". Denne rettelse skal ske FØR eller SAMTIDIG med resten af featuren ruller ud i produktion, så han ikke bliver usynlig et øjeblik.

**Files:**
- Create (temporært, køres én gang, committes IKKE): `C:\Users\SofieThraneSkjødt\AppData\Local\Temp\claude\C--Users-SofieThraneSkj-dt-OneDrive---Poul-Schou-A-S-Skrivebord-L-nsystem\c3b86f7c-3215-4fac-9604-449d273f16b9\scratchpad\link_magne_to_kran.py`

**Interfaces:**
- Consumes: `database.session.SessionLocal`, `database.models.Employee`, `database.models.DispatcherGroup` (ingen ændring af disse i denne task).
- Produces: intet der andre tasks er afhængige af — ren datarettelse.

- [x] **Step 1: Skriv verifikations-/rettelsesscriptet**

```python
# scratchpad/link_magne_to_kran.py
import sys
sys.path.insert(0, r"C:\Users\SofieThraneSkjødt\OneDrive - Poul Schou A S\Skrivebord\Lønsystem\app")

from database.session import SessionLocal
from database.models import Employee, DispatcherGroup

db = SessionLocal()
try:
    emp = db.query(Employee).filter(Employee.employee_number == "34362").one()
    print("Før:", emp.name, "grupper:", [g.name for g in emp.dispatcher_groups])
    assert emp.dispatcher_groups == [], "Forventede ingen eksisterende grupper — stop og undersøg"

    kran = db.query(DispatcherGroup).filter(DispatcherGroup.name == "2 - Kran").one()
    emp.dispatcher_groups = [kran]
    db.commit()

    db.refresh(emp)
    print("Efter:", emp.name, "grupper:", [g.name for g in emp.dispatcher_groups])
finally:
    db.close()
```

- [x] **Step 2: Kør scriptet mod den rigtige database**

Run: `python "C:\Users\SofieThraneSkjødt\AppData\Local\Temp\claude\C--Users-SofieThraneSkj-dt-OneDrive---Poul-Schou-A-S-Skrivebord-L-nsystem\c3b86f7c-3215-4fac-9604-449d273f16b9\scratchpad\link_magne_to_kran.py"`

Expected output:
```
Før: Magne Sørensen grupper: []
Efter: Magne Sørensen grupper: ['2 - Kran']
```

Hvis `assert`-linjen fejler (dvs. han allerede har en gruppe), STOP og undersøg — data har ændret sig siden denne plan blev skrevet, og rettelsen skal genovervejes i stedet for at overskrive noget ukendt.

- [x] **Step 3: Slet det temporære script**

Scriptet er en engangsrettelse af data, ikke en del af applikationens kildekode — det skal ikke committes.

Run: `rm "C:\Users\SofieThraneSkjødt\AppData\Local\Temp\claude\C--Users-SofieThraneSkj-dt-OneDrive---Poul-Schou-A-S-Skrivebord-L-nsystem\c3b86f7c-3215-4fac-9604-449d273f16b9\scratchpad\link_magne_to_kran.py"`

Ingen `git commit` for denne task — det er en ren databaseændring, ikke en kodeændring.

---

## Task 2: DB-model + migration for `visible_in_activity_overview`

**Files:**
- Modify: `app/database/models.py:168-179` (klassen `DispatcherGroup`)
- Modify: `app/database/session.py:126-133` (funktionen `_migrate()`)
- Test: `tests/test_dispatcher_group_visibility.py` (ny fil)

**Interfaces:**
- Produces: `DispatcherGroup.visible_in_activity_overview` (Python-attribut, `bool`, default `True`) — bruges af Task 3 og 4.

- [x] **Step 1: Skriv den fejlende test for kolonnens default-værdi**

```python
# tests/test_dispatcher_group_visibility.py
from database.models import DispatcherGroup


def test_new_dispatcher_group_defaults_to_visible(db):
    group = DispatcherGroup(name="Testgruppe")
    db.add(group)
    db.commit()
    db.refresh(group)
    assert group.visible_in_activity_overview is True
```

- [x] **Step 2: Kør testen og bekræft at den fejler**

Run: `cd tests && python -m pytest test_dispatcher_group_visibility.py -v`
Expected: FAIL — `AttributeError: 'DispatcherGroup' object has no attribute 'visible_in_activity_overview'` (eller lignende, da kolonnen ikke findes endnu).

- [x] **Step 3: Tilføj kolonnen til modellen**

I `app/database/models.py`, i klassen `DispatcherGroup` (linje 168-179), tilføj feltet efter `description`:

```python
class DispatcherGroup(Base):
    __tablename__ = "dispatcher_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    visible_in_activity_overview = Column(Boolean, nullable=False, default=True)

    employees = relationship(
        "Employee",
        secondary="employee_dispatcher_groups",
        back_populates="dispatcher_groups"
    )
```

- [x] **Step 4: Kør testen igen og bekræft at den nu passerer**

Run: `cd tests && python -m pytest test_dispatcher_group_visibility.py -v`
Expected: PASS

- [x] **Step 5: Tilføj migration for eksisterende (produktions-)databaser**

I `app/database/session.py`, i funktionen `_migrate()`, indsæt en ny kolonne-tjek-blok efter den eksisterende `employee_supplements`-indeks-blok (efter linje 133, `conn.commit()` for `ix_activities_employee_start_source`, og før kommentaren "Migrer eksisterende faste sats-kilde-værdier"):

```python
        dg_cols = {row[1] for row in conn.execute("PRAGMA table_info(dispatcher_groups)")}
        if "visible_in_activity_overview" not in dg_cols:
            conn.execute(
                "ALTER TABLE dispatcher_groups ADD COLUMN visible_in_activity_overview "
                "BOOLEAN NOT NULL DEFAULT 1"
            )
            conn.commit()
```

Denne blok skal stå inde i den eksisterende `with _sqlite3.connect(str(DB_PATH)) as conn:`-kontekst i `_migrate()`, på samme indrykningsniveau som de øvrige `ALTER TABLE`-tjek i funktionen.

- [x] **Step 6: Commit**

```bash
git add app/database/models.py app/database/session.py tests/test_dispatcher_group_visibility.py
git commit -m "feat: tilføj visible_in_activity_overview til DispatcherGroup"
```

---

## Task 3: Schema — eksponer feltet i `DispatcherGroupResponse`

**Files:**
- Modify: `app/database/schemas.py:22-27`
- Test: `tests/test_dispatcher_group_visibility.py` (udvid)

**Interfaces:**
- Consumes: `DispatcherGroup.visible_in_activity_overview` (fra Task 2).
- Produces: `DispatcherGroupResponse.visible_in_activity_overview: bool` — bruges af Task 4 (stamdata-endpoints) og af frontend (Task 5, 6) via både `/api/stamdata/dispatcher-groups` og `/api/employees/dispatcher-groups`.

- [x] **Step 1: Skriv den fejlende test**

```python
# tilføj i tests/test_dispatcher_group_visibility.py
from database.schemas import DispatcherGroupResponse


def test_dispatcher_group_response_includes_visibility_field(db):
    group = DispatcherGroup(name="Testgruppe 2", visible_in_activity_overview=False)
    db.add(group)
    db.commit()
    db.refresh(group)

    response = DispatcherGroupResponse.model_validate(group)

    assert response.visible_in_activity_overview is False
```

- [x] **Step 2: Kør testen og bekræft at den fejler**

Run: `cd tests && python -m pytest test_dispatcher_group_visibility.py -v`
Expected: FAIL — Pydantic-fejl (`AttributeError` eller manglende felt), da `DispatcherGroupResponse` endnu ikke har feltet.

- [x] **Step 3: Tilføj feltet til schemaet**

I `app/database/schemas.py`, opdatér `DispatcherGroupResponse` (linje 22-27):

```python
class DispatcherGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    visible_in_activity_overview: bool = True

    model_config = {"from_attributes": True}
```

- [x] **Step 4: Kør testene igen og bekræft at de passerer**

Run: `cd tests && python -m pytest test_dispatcher_group_visibility.py -v`
Expected: PASS (begge tests i filen)

- [x] **Step 5: Commit**

```bash
git add app/database/schemas.py tests/test_dispatcher_group_visibility.py
git commit -m "feat: eksponer visible_in_activity_overview i DispatcherGroupResponse"
```

---

## Task 4: Stamdata CRUD — læs/skriv feltet via `/api/stamdata/dispatcher-groups`

**Files:**
- Modify: `app/routers/stamdata.py:532-573` (`DispatcherGroupBody`, `_dispatcher_group_row`, `create_dispatcher_group`), `app/routers/stamdata.py:577-603` (`update_dispatcher_group`)
- Test: `tests/test_dispatcher_group_visibility.py` (udvid)

**Interfaces:**
- Consumes: `DispatcherGroup` (Task 2), `DispatcherGroupResponse`-mønster (Task 3), `log_action` (allerede importeret i `stamdata.py`).
- Produces: `create_dispatcher_group(body, current_user, db)` og `update_dispatcher_group(group_id, body, current_user, db)` accepterer nu `visible_in_activity_overview` i `body`; `_dispatcher_group_row(r)` returnerer nøglen `"visible_in_activity_overview"`. Bruges direkte af Task 5's frontend-kald.

- [x] **Step 1: Skriv de fejlende tests**

```python
# tilføj i tests/test_dispatcher_group_visibility.py
from database.models import AppUser
from routers.stamdata import (
    DispatcherGroupBody,
    create_dispatcher_group,
    update_dispatcher_group,
    _dispatcher_group_row,
)


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_create_dispatcher_group_defaults_to_visible(db):
    body = DispatcherGroupBody(name="Ny gruppe")
    result = create_dispatcher_group(body, current_user=_dummy_user(), db=db)
    assert result["visible_in_activity_overview"] is True


def test_create_dispatcher_group_can_be_created_hidden(db):
    body = DispatcherGroupBody(name="Skjult gruppe", visible_in_activity_overview=False)
    result = create_dispatcher_group(body, current_user=_dummy_user(), db=db)
    assert result["visible_in_activity_overview"] is False


def test_update_dispatcher_group_can_toggle_visibility(db):
    created = create_dispatcher_group(
        DispatcherGroupBody(name="Skal skjules"), current_user=_dummy_user(), db=db
    )
    updated = update_dispatcher_group(
        created["id"],
        DispatcherGroupBody(visible_in_activity_overview=False),
        current_user=_dummy_user(),
        db=db,
    )
    assert updated["visible_in_activity_overview"] is False


def test_dispatcher_group_row_includes_visibility_key(db):
    created = create_dispatcher_group(
        DispatcherGroupBody(name="Rå række"), current_user=_dummy_user(), db=db
    )
    assert "visible_in_activity_overview" in created
```

- [x] **Step 2: Kør testene og bekræft at de fejler**

Run: `cd tests && python -m pytest test_dispatcher_group_visibility.py -v`
Expected: FAIL på de 4 nye tests — `DispatcherGroupBody` accepterer ikke `visible_in_activity_overview`, og `_dispatcher_group_row` returnerer ikke nøglen.

- [x] **Step 3: Udvid `DispatcherGroupBody`**

I `app/routers/stamdata.py`, linje 532-534:

```python
class DispatcherGroupBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visible_in_activity_overview: Optional[bool] = None
```

- [x] **Step 4: Udvid `_dispatcher_group_row`**

Linje 537-543:

```python
def _dispatcher_group_row(r) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "employee_count": len(r.employees),
        "visible_in_activity_overview": r.visible_in_activity_overview,
    }
```

- [x] **Step 5: Sæt default `True` i `create_dispatcher_group`**

Linje 555-573, tilføj visibility-håndtering i selve `DispatcherGroup(...)`-konstruktøren:

```python
@router.post("/dispatcher-groups", status_code=201)
def create_dispatcher_group(
    body: DispatcherGroupBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.name:
        raise HTTPException(400, "Navn er påkrævet")
    name = body.name.strip()
    if db.query(DispatcherGroup).filter(DispatcherGroup.name == name).first():
        raise HTTPException(400, "En disponentgruppe med dette navn eksisterer allerede")
    row = DispatcherGroup(
        name=name,
        description=(body.description or "").strip() or None,
        visible_in_activity_overview=(
            body.visible_in_activity_overview
            if body.visible_in_activity_overview is not None
            else True
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "dispatcher_group", row.id,
               f"Oprettet disponentgruppe: {row.name}")
    db.commit()
    return _dispatcher_group_row(row)
```

- [x] **Step 6: Opdatér feltet i `update_dispatcher_group` når angivet**

Linje 577-603, tilføj efter `description`-håndteringen (før `db.commit()`):

```python
@router.patch("/dispatcher-groups/{group_id}")
def update_dispatcher_group(
    group_id: int,
    body: DispatcherGroupBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(DispatcherGroup).filter(DispatcherGroup.id == group_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Navn er påkrævet")
        conflict = db.query(DispatcherGroup).filter(
            DispatcherGroup.name == name,
            DispatcherGroup.id != group_id,
        ).first()
        if conflict:
            raise HTTPException(400, "En anden disponentgruppe med dette navn eksisterer allerede")
        row.name = name
    if body.description is not None:
        row.description = body.description.strip() or None
    if body.visible_in_activity_overview is not None:
        row.visible_in_activity_overview = body.visible_in_activity_overview
    db.commit()
    log_action(db, current_user, "stamdata_update", "dispatcher_group", row.id,
               f"Disponentgruppe opdateret: {row.name}")
    db.commit()
    return _dispatcher_group_row(row)
```

- [x] **Step 7: Kør testene igen og bekræft at de passerer**

Run: `cd tests && python -m pytest test_dispatcher_group_visibility.py -v`
Expected: PASS (alle 8 tests i filen nu)

- [x] **Step 8: Kør hele test-suiten for at sikre ingen regression**

Run: `cd tests && python -m pytest -v`
Expected: PASS (alle eksisterende tests upåvirkede)

- [x] **Step 9: Commit**

```bash
git add app/routers/stamdata.py tests/test_dispatcher_group_visibility.py
git commit -m "feat: CRUD-støtte for visible_in_activity_overview i disponentgruppe-stamdata"
```

---

## Task 5: Stamdata-frontend — kolonne + checkbox i disponentgruppe-UI

**Files:**
- Modify: `app/templates/index.html:550-561` (tabel-header + tbody colspan)
- Modify: `app/templates/index.html:1708-1717` (modal-body — nyt checkbox-felt)
- Modify: `app/static/js/app.js:3876-3926` (`loadStamdataDispatcherGroups`, `openStamdataDispatcherModal`, `confirmStamdataDispatcher`)

**Interfaces:**
- Consumes: `GET /api/stamdata/dispatcher-groups` returnerer nu `visible_in_activity_overview` pr. række (Task 4); `POST`/`PATCH /api/stamdata/dispatcher-groups` accepterer feltet i body (Task 4).
- Produces: intet nyt for andre tasks — dette er UI-slutpunktet for Stamdata-delen.

- [x] **Step 1: Tilføj kolonne til tabel-header, index.html:550-561**

```html
        <!-- Disponentgrupper -->
        <div id="sd-pane-dispatcher" style="display:none">
          <table style="width:100%;border-collapse:collapse;font-size:14px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
            <thead>
              <tr style="background:var(--primary);color:#fff">
                <th style="padding:10px 14px;text-align:left;font-weight:600">Navn</th>
                <th style="padding:10px 14px;text-align:left;font-weight:600">Beskrivelse</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Medarbejdere</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Vis i aktivitetsoversigt</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Handlinger</th>
              </tr>
            </thead>
            <tbody id="stamdata-dispatcher-tbody">
              <tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>
            </tbody>
          </table>
        </div>
```

- [x] **Step 2: Tilføj checkbox til modal, index.html:1708-1718**

```html
    <div class="modal-body">
      <input type="hidden" id="stamdata-dispatcher-id">
      <div class="form-group">
        <label>Navn</label>
        <input type="text" id="stamdata-dispatcher-name" placeholder="fx 11 - Nyt lager">
      </div>
      <div class="form-group">
        <label>Beskrivelse</label>
        <input type="text" id="stamdata-dispatcher-description" placeholder="Valgfri">
      </div>
      <div class="form-group" style="display:flex;align-items:center;gap:8px">
        <input type="checkbox" id="stamdata-dispatcher-visible" style="width:16px;height:16px;cursor:pointer" checked>
        <label for="stamdata-dispatcher-visible" style="margin:0;cursor:pointer">Vis i aktivitetsoversigt</label>
      </div>
    </div>
```

- [x] **Step 3: Opdatér `loadStamdataDispatcherGroups`, app.js:3876-3900**

```js
async function loadStamdataDispatcherGroups() {
  const tbody = document.getElementById("stamdata-dispatcher-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/dispatcher-groups");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-light)">Ingen disponentgrupper oprettet endnu</td></tr>`;
      return;
    }
    const badge = (v, yes, no) => v
      ? `<span style="color:var(--primary);font-weight:600">${yes}</span>`
      : `<span style="color:var(--text-light)">${no}</span>`;
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;color:var(--text-light)">${h(r.description || "")}</td>
        <td style="padding:10px 14px;text-align:center">${r.employee_count}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.visible_in_activity_overview, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataDispatcherModal(${r.id},${jq(r.name)},${jq(r.description || "")},${r.visible_in_activity_overview})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataDispatcher(${r.id},${jq(r.name)},${r.employee_count})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
  // Ny/ændret gruppe kan påvirke medarbejder-modal og filtre
  try { state.dispatcherGroups = await GET("/api/employees/dispatcher-groups"); fillDispatcherGroupFilter(); } catch (_) {}
}
```

- [x] **Step 4: Opdatér `openStamdataDispatcherModal`, app.js:3902-3908**

```js
function openStamdataDispatcherModal(id, name, description, visible) {
  document.getElementById("stamdata-dispatcher-id").value = id || "";
  document.getElementById("stamdata-dispatcher-name").value = name || "";
  document.getElementById("stamdata-dispatcher-description").value = description || "";
  document.getElementById("stamdata-dispatcher-visible").checked = id ? !!visible : true;
  document.getElementById("stamdata-dispatcher-title").textContent = id ? "Rediger disponentgruppe" : "Ny disponentgruppe";
  openModal("modal-stamdata-dispatcher");
}
```

- [x] **Step 5: Opdatér `confirmStamdataDispatcher`, app.js:3910-3926**

```js
async function confirmStamdataDispatcher() {
  const id   = document.getElementById("stamdata-dispatcher-id").value;
  const name = document.getElementById("stamdata-dispatcher-name").value.trim();
  const description = document.getElementById("stamdata-dispatcher-description").value.trim();
  const visible = document.getElementById("stamdata-dispatcher-visible").checked;
  if (!name) { toast("Navn er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/dispatcher-groups/${id}`, { name, description, visible_in_activity_overview: visible });
      toast("Disponentgruppe opdateret");
    } else {
      await POST("/api/stamdata/dispatcher-groups", { name, description, visible_in_activity_overview: visible });
      toast("Disponentgruppe oprettet");
    }
    closeModal("modal-stamdata-dispatcher");
    await loadStamdataDispatcherGroups();
  } catch (e) { toast(e.message, "error"); }
}
```

- [x] **Step 6: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: Stamdata-UI for visible_in_activity_overview på disponentgrupper"
```

(Verifikation i browser sker samlet i Task 7, efter Task 6 også er implementeret.)

---

## Task 6: Aktivitetsoversigt — filtrér grupper og medarbejdere efter synlighed

**Files:**
- Modify: `app/static/js/app.js:4295-4302` (`fillDispatcherGroupFilter`)
- Modify: `app/static/js/app.js:4304-4316` (`fillEmployeeFilter`)
- Modify: `app/static/js/app.js:214-230` og `:303-306` (`renderActivitiesTable` — filter + `emps`-liste)
- Modify: `app/static/js/app.js:4291-4293` (tilføj ny hjælpefunktion `_empHasVisibleGroup` ved siden af `_empInGroup`)

**Interfaces:**
- Consumes: `state.dispatcherGroups` (nu inkl. `visible_in_activity_overview` pr. Task 3+4), `state.employees[].dispatcher_groups` (uændret struktur, samme `DispatcherGroupResponse`-liste).
- Produces: `_empHasVisibleGroup(emp)` — bruges i `fillEmployeeFilter` og `renderActivitiesTable`.

Ingen automatiserede tests for denne task — projektet har ingen JS-testopsætning, og al frontend-adfærd i denne kodebase verificeres manuelt i browseren (jf. eksisterende mønster for `app.js`-ændringer). Verifikation sker i Task 7.

- [x] **Step 1: Tilføj `_empHasVisibleGroup`, app.js — lige efter `_empInGroup` (linje 4291-4293)**

```js
function _empInGroup(emp, groupId) {
  return (emp.dispatcher_groups || []).some(g => String(g.id) === String(groupId));
}

function _empHasVisibleGroup(emp) {
  const visibleIds = new Set(
    (state.dispatcherGroups || [])
      .filter(g => g.visible_in_activity_overview)
      .map(g => String(g.id))
  );
  return (emp.dispatcher_groups || []).some(g => visibleIds.has(String(g.id)));
}
```

- [x] **Step 2: Filtrér `fillDispatcherGroupFilter` til kun synlige grupper (linje 4295-4302)**

```js
function fillDispatcherGroupFilter() {
  const sel = document.getElementById("filter-dispatcher-group");
  if (!sel) return;
  const cur = sel.value;
  const visibleGroups = state.dispatcherGroups.filter(g => g.visible_in_activity_overview);
  sel.innerHTML = `<option value="">Alle afdelinger</option>` +
    visibleGroups.map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
  if (visibleGroups.find(g => String(g.id) === cur)) sel.value = cur;
}
```

- [x] **Step 3: Filtrér `fillEmployeeFilter` til medarbejdere med mindst én synlig gruppe (linje 4304-4316)**

```js
function fillEmployeeFilter() {
  const sel = document.getElementById("filter-employee");
  const cur = sel.value;
  const groupFilter = document.getElementById("filter-dispatcher-group")?.value || "";
  let visible = state.employees.filter(e => _empHasVisibleGroup(e));
  if (groupFilter) visible = visible.filter(e => _empInGroup(e, groupFilter));
  const placeholder = groupFilter ? "Alle i afdelingen" : "Alle medarbejdere";
  sel.innerHTML = `<option value="">${placeholder}</option>` +
    visible.slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  if (visible.find(e => String(e.id) === cur)) sel.value = cur;
}
```

- [x] **Step 4: Filtrér `emps`-listen i `renderActivitiesTable` (linje ~303-306)**

Find i `renderActivitiesTable()`:

```js
  // Rækker: medarbejdere (filtreret hvis valgt), sorteret efter navn
  let emps = state.employees.filter(e => e.active);
  if (groupFilter) emps = emps.filter(e => _empInGroup(e, groupFilter));
  if (empFilter) emps = emps.filter(e => e.id === parseInt(empFilter));
  emps.sort((x, y) => x.name.localeCompare(y.name, "da"));
```

og ret til:

```js
  // Rækker: medarbejdere (filtreret hvis valgt), sorteret efter navn
  let emps = state.employees.filter(e => e.active && _empHasVisibleGroup(e));
  if (groupFilter) emps = emps.filter(e => _empInGroup(e, groupFilter));
  if (empFilter) emps = emps.filter(e => e.id === parseInt(empFilter));
  emps.sort((x, y) => x.name.localeCompare(y.name, "da"));
```

- [x] **Step 5: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: skjul disponentgrupper uden visible_in_activity_overview fra aktivitetsoversigten"
```

---

## Task 7: Manuel browser-verifikation

Dette er et frontend-tungt feature uden JS-testramme i projektet — verifikation SKAL ske i en rigtig browser mod en kørende dev-server, jf. projektets generelle krav om at teste UI-ændringer visuelt før de betragtes som færdige.

**Files:** Ingen — ren verifikation, ingen kodeændringer i denne task.

- [x] **Step 1: Genstart serveren (migration + kodeændringer kræver det)**

Run: `cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

- [x] **Step 2: Bekræft migrationen kørte**

Run (i en anden terminal): `python -c "import sqlite3; con=sqlite3.connect('app/database/lonsystem.db'); print([r[1] for r in con.execute('PRAGMA table_info(dispatcher_groups)')])"`
Expected: listen indeholder `visible_in_activity_overview`.

- [x] **Step 3: Åbn appen i browseren og gå til Stamdata → Disponentgrupper**

Bekræft: alle 7 eksisterende grupper viser "Ja" i den nye kolonne "Vis i aktivitetsoversigt" (default-migreret til synlig).

- [x] **Step 4: Rediger en gruppe uden medarbejdere (eller opret en testgruppe) og slå synlighed fra**

Fjern fluebenet i "Vis i aktivitetsoversigt", gem. Bekræft badge'en skifter til "Nej".

- [x] **Step 5: Gå til Aktivitetsoversigt og bekræft gruppen er væk fra afdelings-dropdown'en**

"Alle afdelinger"-dropdownen i toolbaren må IKKE længere vise den skjulte gruppe.

- [x] **Step 6: Bekræft medarbejdere i den skjulte gruppe er væk fra gitteret**

Hvis testgruppen har medarbejdere uden andre synlige grupper, skal de være væk fra rækkerne i aktivitetsoversigten og fra "Alle medarbejdere"-dropdownen.

- [x] **Step 7: Bekræft medarbejder med flere grupper stadig vises, hvis mindst én er synlig**

Find (eller opret temporært) en medarbejder med to grupper, hvor kun én er slået fra — bekræft medarbejderen stadig vises i gitteret.

- [x] **Step 8: Bekræft Magne Sørensen (34362) vises i aktivitetsoversigten**

Søg ham op i "Alle medarbejdere"-dropdownen eller filtrér på "2 - Kran" — bekræft han optræder (jf. Task 1's datarettelse).

- [x] **Step 9: Slå testgruppen synlig igen (eller slet den, hvis den var oprettet kun til testen) og bekræft alt er tilbage til normalt**

- [x] **Step 10: Kør hele test-suiten en sidste gang**

Run: `cd tests && python -m pytest -v`
Expected: PASS (alle tests, inkl. de nye fra Task 2-4)

## Fund under verifikation (rettet)

Manuel test af Step 6/7 afslørede at `filter-employee`-dropdownen i
aktivitetsoversigten ikke opdaterede sig selv, når en gruppes synlighed blev
ændret i Stamdata uden en fuld sideindlæsning bagefter — `loadStamdataDispatcherGroups()`
kaldte `fillDispatcherGroupFilter()` men ikke `fillEmployeeFilter()`, så en
medarbejder hvis eneste gruppe lige var blevet skjult stod tilbage i
dropdownen (men korrekt væk fra selve gitteret). Rettet ved at tilføje
`fillEmployeeFilter()`-kaldet samme sted (`app/static/js/app.js`), committet
separat som `fix: opdatér medarbejder-dropdown live når disponentgruppe-synlighed ændres i Stamdata`.
Verificeret efterfølgende at både dropdown og gitter opdaterer sig korrekt
uden sideindlæsning.
