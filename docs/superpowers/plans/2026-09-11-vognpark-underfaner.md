# Vognpark – underfaner "Vognpark"/"Alle" + Dagsplan-filtrering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tilføj et flueben "Vognpark" på hver vogn, der styrer om vognen indgår i Dagsplanens vognkolonne. Vognpark-siden får to underfaner ("Vognpark" = kun markerede vogne, "Alle" = samtlige vogne), samme visuelle mønster som Stamdatas tab-switcher.

**Architecture:** Nyt boolean-felt `Vehicle.vognpark` (samme mønster som `Employee.afloeser`/`fast_bil`), default `false`. `dagsplan_router.py: _build_vehicle_rows()` filtrerer sin `Vehicle`-forespørgsel på feltet. Frontend genbruger den eksisterende `renderVehicleList()`/`modal-vehicle`-infrastruktur, blot udvidet med et fane-filter (`state.vehiclesTab`) og en checkbox.

**Tech Stack:** Python (FastAPI, SQLAlchemy), SQLite, pytest. Vanilla JS/HTML frontend (ingen build-step).

**Spec:** `docs/superpowers/specs/2026-09-11-vognpark-underfaner-design.md`

## Global Constraints

- Default-værdi for `vognpark` er `false` for alle eksisterende OG alle nye vogne (bekræftet under brainstorming) — Dagsplanens vognkolonne vil derfor være tom umiddelbart efter denne opdatering, indtil nogen aktivt markerer vogne.
- "Vognpark"-fanen viser kun `vognpark=true`-vogne; "Alle"-fanen viser samtlige vogne uanset flueben. Begge faner er samme liste (`renderVehicleList()`), filtreret forskelligt — ikke to separate datasæt.
- "Vognpark" er den åbne fane som standard, når man navigerer til Vognpark-siden.
- Ingen ændring til Fast bil-vælgeren (medarbejder-modal) eller vogn-søgningen i "Meld materielt fravær" — begge viser fortsat alle vogne uanset `vognpark`.
- Ingen ny permission — checkboxen gates af den eksisterende `manage_vehicles`-tilladelse; selve fane-skiftet kræver kun `view_vehicles` (uændret, som resten af siden).
- Alle kodeændringer skal følge eksisterende mønstre i `app/database/models.py`, `app/database/schemas.py`, `app/database/session.py`, `app/routers/vehicles.py`, `app/routers/dagsplan_router.py`, `app/templates/index.html`, `app/static/js/app.js`.

---

### Task 1: Datamodel — `Vehicle.vognpark`-felt + migration

**Files:**
- Modify: `app/database/models.py:325-333` (`Vehicle`-klassen)
- Modify: `app/database/session.py:240-246` (`_migrate()`, vehicles-tabel-migrationer)
- Test: `tests/test_vehicle_vognpark_model.py`

**Interfaces:**
- Produces: `Vehicle.vognpark: bool` (default `False`) — bruges af Task 2 (schemas/router) og Task 3 (Dagsplan-filter).

- [ ] **Step 1: Write the failing test**

Opret `tests/test_vehicle_vognpark_model.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database.models import Vehicle


def test_vehicle_vognpark_defaults_to_false(db):
    v = Vehicle(registration_number="BN47449", vehicle_number="52")
    db.add(v)
    db.commit()
    db.refresh(v)
    assert v.vognpark is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vehicle_vognpark_model.py -v`
Expected: FAIL med `AttributeError: 'Vehicle' object has no attribute 'vognpark'`

- [ ] **Step 3: Tilføj kolonnen til `Vehicle`-modellen**

I `app/database/models.py`, linje 325-333, den eksisterende:
```python
class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    registration_number = Column(String, unique=True, nullable=False)  # Registreringsnummer (nummerplade)
    vehicle_number = Column(String, nullable=False)                     # Vognnummer
    description = Column(Text, nullable=True)                           # "Beskrivelse" (Dagsplan kol. 2)
    dispatcher_group_id = Column(Integer, ForeignKey("dispatcher_groups.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
```
udvides med `vognpark`-kolonnen lige efter `dispatcher_group_id`:
```python
class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    registration_number = Column(String, unique=True, nullable=False)  # Registreringsnummer (nummerplade)
    vehicle_number = Column(String, nullable=False)                     # Vognnummer
    description = Column(Text, nullable=True)                           # "Beskrivelse" (Dagsplan kol. 2)
    dispatcher_group_id = Column(Integer, ForeignKey("dispatcher_groups.id"), nullable=True)
    vognpark = Column(Boolean, default=False, nullable=False)           # Indgår i Dagsplanens vognkolonne
    created_at = Column(DateTime, server_default=func.now())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_vehicle_vognpark_model.py -v`
Expected: PASS

- [ ] **Step 5: Tilføj idempotent migration**

I `app/database/session.py`, i `_migrate()`-funktionen, den eksisterende blok (linje 240-246):
```python
        veh_cols = {row[1] for row in conn.execute("PRAGMA table_info(vehicles)")}
        if "description" not in veh_cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN description TEXT")
            conn.commit()
        if "dispatcher_group_id" not in veh_cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN dispatcher_group_id INTEGER")
            conn.commit()
```
udvides med:
```python
        veh_cols = {row[1] for row in conn.execute("PRAGMA table_info(vehicles)")}
        if "description" not in veh_cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN description TEXT")
            conn.commit()
        if "dispatcher_group_id" not in veh_cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN dispatcher_group_id INTEGER")
            conn.commit()
        if "vognpark" not in veh_cols:
            conn.execute("ALTER TABLE vehicles ADD COLUMN vognpark BOOLEAN NOT NULL DEFAULT 0")
            conn.commit()
```
(Bemærk: denne ALTER TABLE-migration rammer kun en eksisterende produktions-SQLite-fil ved opstart — den er, ligesom `description`/`dispatcher_group_id`s tilsvarende migrationer, ikke dækket af pytest, da test-fixturen `db` altid opretter det fulde, aktuelle skema direkte via `Base.metadata.create_all()`.)

- [ ] **Step 6: Commit**

```bash
git add app/database/models.py app/database/session.py tests/test_vehicle_vognpark_model.py
git commit -m "feat: tilføj Vehicle.vognpark-felt"
```

---

### Task 2: Schemas + router — `vognpark` i Vognpark-API'et

**Files:**
- Modify: `app/database/schemas.py:302-325` (`VehicleCreate`, `VehicleUpdate`, `VehicleResponse`)
- Modify: `app/routers/vehicles.py:26-42` (`create_vehicle`), `:45-69` (`update_vehicle`)
- Test: `tests/test_vehicle_vognpark_endpoint.py`

**Interfaces:**
- Consumes: `Vehicle.vognpark` (Task 1).
- Produces: `VehicleCreate.vognpark: bool`, `VehicleUpdate.vognpark: Optional[bool]`, `VehicleResponse.vognpark: bool` — bruges af frontend (Task 4) og af Dagsplan-filteret (Task 3, som læser direkte fra `Vehicle`-modellen, ikke fra disse schemas, men skal være konsistent med dem).

- [ ] **Step 1: Write the failing test**

Opret `tests/test_vehicle_vognpark_endpoint.py` (mønster fra `tests/test_vehicle_dispatcher_group_field.py`):
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database.models import AppUser
from database.schemas import VehicleCreate, VehicleUpdate


def _admin():
    return AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")


def test_create_vehicle_with_vognpark_true(db):
    from routers.vehicles import create_vehicle
    body = VehicleCreate(registration_number="BN47449", vehicle_number="52", vognpark=True)
    resp = create_vehicle(body, current_user=_admin(), db=db)
    assert resp.vognpark is True


def test_update_vehicle_toggles_vognpark(db):
    from routers.vehicles import create_vehicle, update_vehicle
    created = create_vehicle(VehicleCreate(registration_number="BN47449", vehicle_number="52"),
                              current_user=_admin(), db=db)
    assert created.vognpark is False  # default, jf. Task 1

    updated = update_vehicle(created.id, VehicleUpdate(vognpark=True),
                              current_user=_admin(), db=db)
    assert updated.vognpark is True

    updated_again = update_vehicle(created.id, VehicleUpdate(vognpark=False),
                                    current_user=_admin(), db=db)
    assert updated_again.vognpark is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_vehicle_vognpark_endpoint.py -v`
Expected: FAIL — `test_create_vehicle_with_vognpark_true` fejler med `assert False is True` (pydantic ignorerer stiltiende det ukendte `vognpark`-felt på `VehicleCreate`, og `create_vehicle()` sætter det ikke på `Vehicle`-objektet endnu, så SQLAlchemy-defaulten `False` vinder).

- [ ] **Step 3: Tilføj feltet til de tre schemas**

I `app/database/schemas.py`, linje 302-325, den eksisterende:
```python
class VehicleCreate(BaseModel):
    registration_number: str
    vehicle_number: str
    description: Optional[str] = None
    dispatcher_group_id: Optional[int] = None


class VehicleUpdate(BaseModel):
    registration_number: Optional[str] = None
    vehicle_number: Optional[str] = None
    description: Optional[str] = None
    dispatcher_group_id: Optional[int] = None


class VehicleResponse(BaseModel):
    id: int
    registration_number: str
    vehicle_number: str
    description: Optional[str] = None
    dispatcher_group_id: Optional[int] = None
    dispatcher_group_name: Optional[str] = None
    fast_bil_employee_name: Optional[str] = None

    model_config = {"from_attributes": True}
```
erstattes af:
```python
class VehicleCreate(BaseModel):
    registration_number: str
    vehicle_number: str
    description: Optional[str] = None
    dispatcher_group_id: Optional[int] = None
    vognpark: bool = False


class VehicleUpdate(BaseModel):
    registration_number: Optional[str] = None
    vehicle_number: Optional[str] = None
    description: Optional[str] = None
    dispatcher_group_id: Optional[int] = None
    vognpark: Optional[bool] = None


class VehicleResponse(BaseModel):
    id: int
    registration_number: str
    vehicle_number: str
    description: Optional[str] = None
    dispatcher_group_id: Optional[int] = None
    dispatcher_group_name: Optional[str] = None
    fast_bil_employee_name: Optional[str] = None
    vognpark: bool

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Sæt feltet i `create_vehicle`**

I `app/routers/vehicles.py`, linje 26-42, den eksisterende:
```python
@router.post("", response_model=VehicleResponse, status_code=201)
def create_vehicle(body: VehicleCreate,
                   current_user: AppUser = Depends(require_permission("manage_vehicles")),
                   db: Session = Depends(get_db)):
    reg = body.registration_number.strip()
    if db.query(Vehicle).filter(Vehicle.registration_number == reg).first():
        raise HTTPException(400, "Registreringsnummer eksisterer allerede")
    v = Vehicle(
        registration_number=reg,
        vehicle_number=body.vehicle_number.strip(),
        description=body.description,
        dispatcher_group_id=_resolve_dispatcher_group_id(db, body.dispatcher_group_id),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v
```
`Vehicle(...)`-kaldet udvides med `vognpark`:
```python
    v = Vehicle(
        registration_number=reg,
        vehicle_number=body.vehicle_number.strip(),
        description=body.description,
        dispatcher_group_id=_resolve_dispatcher_group_id(db, body.dispatcher_group_id),
        vognpark=body.vognpark,
    )
```

- [ ] **Step 5: Sæt feltet i `update_vehicle`**

I `app/routers/vehicles.py`, linje 45-69, den eksisterende:
```python
    if body.description is not None:
        v.description = body.description
    if "dispatcher_group_id" in body.model_fields_set:
        v.dispatcher_group_id = _resolve_dispatcher_group_id(db, body.dispatcher_group_id)
    db.commit()
```
udvides med et nyt tjek (samme `is not None`-mønster som `description`, da `vognpark=None` her udelukkende betyder "feltet blev ikke sendt", ikke "sæt til null" — i modsætning til `dispatcher_group_id`, hvor `None` er en gyldig målværdi):
```python
    if body.description is not None:
        v.description = body.description
    if body.vognpark is not None:
        v.vognpark = body.vognpark
    if "dispatcher_group_id" in body.model_fields_set:
        v.dispatcher_group_id = _resolve_dispatcher_group_id(db, body.dispatcher_group_id)
    db.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_vehicle_vognpark_endpoint.py -v`
Expected: PASS

- [ ] **Step 7: Run hele test-suiten for regression**

Run: `pytest -v`
Expected: PASS — `tests/test_vehicle_dispatcher_group_field.py` og øvrige eksisterende vogn-tests må ikke ændre resultat, da `vognpark` default er `False` overalt hvor feltet ikke eksplicit sættes.

- [ ] **Step 8: Commit**

```bash
git add app/database/schemas.py app/routers/vehicles.py tests/test_vehicle_vognpark_endpoint.py
git commit -m "feat: eksponer vognpark i Vognpark-API'et"
```

---

### Task 3: Dagsplan-filtrering — kun `vognpark=true`-vogne i vognkolonnen

**Files:**
- Modify: `app/routers/dagsplan_router.py:62` (`_build_vehicle_rows()`)
- Modify: `tests/test_dagsplan_router.py:21-26` (`_vehicle()`-testhjælper), tilføj nye tests

**Interfaces:**
- Consumes: `Vehicle.vognpark` (Task 1).
- Produces: ingen nye offentlige funktioner — `_build_vehicle_rows()`'s eksisterende signatur/returtype (`list[DagsplanVehicleRow]`) er uændret, kun dens indhold filtreres nu.

- [ ] **Step 1: Opdatér test-helperen så eksisterende tests fortsat er dækkende**

I `tests/test_dagsplan_router.py`, linje 21-26, den eksisterende:
```python
def _vehicle(db, number="52", reg="BN47449"):
    v = Vehicle(registration_number=reg, vehicle_number=number)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v
```
erstattes af:
```python
def _vehicle(db, number="52", reg="BN47449", vognpark=True):
    v = Vehicle(registration_number=reg, vehicle_number=number, vognpark=vognpark)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v
```
(Alle eksisterende kald af `_vehicle(...)` i denne fil forudsætter allerede at vognen indgår i Dagsplanen — `vognpark=True` som default bevarer den forudsætning uændret. Nye tests nedenfor overstyrer eksplicit med `vognpark=False`.)

- [ ] **Step 2: Write the failing tests**

Tilføj nederst i `tests/test_dagsplan_router.py`:
```python
def test_vehicle_without_vognpark_flag_excluded_from_dagsplan(db):
    from routers.dagsplan_router import get_dagsplan
    _vehicle(db, vognpark=False)
    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert resp.vehicles == []


def test_fast_bil_on_non_vognpark_vehicle_hidden_and_no_conflict(db, employee):
    """En vogn der ikke er markeret 'Vognpark' må hverken vises i Dagsplanen via
    Fast bil-fallback, eller tælle som en eksisterende tildeling ved konflikttjek
    når medarbejderen tildeles en anden (vognpark-markeret) vogn."""
    from routers.dagsplan_router import get_dagsplan, upsert_assignment
    v_not_in_fleet = _vehicle(db, "52", "BN47449", vognpark=False)
    v_in_fleet = _vehicle(db, "60", "AB12345", vognpark=True)
    employee.fast_bil = True
    employee.fast_bil_vehicle_id = v_not_in_fleet.id
    db.commit()

    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert len(resp.vehicles) == 1
    assert resp.vehicles[0].vehicle_number == "60"
    assert resp.vehicles[0].employee_id is None  # Fast bil-fallback rammer ikke en vogn uden for Dagsplanen

    # Ingen 409-konflikt, selvom medarbejderen "burde" være optaget via Fast bil på v_not_in_fleet
    row = upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v_in_fleet.id,
                                                       employee_id=employee.id),
                            current_user=_user(), db=db)
    assert row.employee_id == employee.id
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_dagsplan_router.py -v`
Expected: de to nye tests FAILER (`_build_vehicle_rows()` returnerer stadig alle vogne, uanset `vognpark`) — `test_vehicle_without_vognpark_flag_excluded_from_dagsplan` fejler fordi `resp.vehicles` indeholder én vogn i stedet for at være tom. Alle andre (eksisterende) tests i filen skal fortsat PASSE, da `_vehicle()`-helperen nu sætter `vognpark=True` som default.

- [ ] **Step 4: Filtrér `_build_vehicle_rows()`**

I `app/routers/dagsplan_router.py`, linje 62, den eksisterende:
```python
    for v in db.query(Vehicle).order_by(Vehicle.vehicle_number).all():
```
erstattes af:
```python
    for v in db.query(Vehicle).filter(Vehicle.vognpark == True).order_by(Vehicle.vehicle_number).all():
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_dagsplan_router.py -v`
Expected: PASS (alle tests i filen, inkl. de to nye)

- [ ] **Step 6: Run hele test-suiten for regression**

Run: `pytest -v`
Expected: PASS — `tests/test_dagsplan_activity_autofill.py` og `tests/test_dagsplan_datamodel.py` bruger ikke `_build_vehicle_rows()`/`get_dagsplan()` og skal derfor være upåvirkede (de tester hhv. `effective_vehicle_for_employee()`, som IKKE ændres i denne opgave, og ren datamodel uden router-kald).

- [ ] **Step 7: Commit**

```bash
git add app/routers/dagsplan_router.py tests/test_dagsplan_router.py
git commit -m "feat: filtrér Dagsplanens vognkolonne på Vehicle.vognpark"
```

---

### Task 4: Frontend — underfaner på Vognpark-siden + flueben i vogn-modalen

**Files:**
- Modify: `app/templates/index.html:379-389` (view `vehicles`, tab-switcher)
- Modify: `app/templates/index.html:1710-1717` (`modal-vehicle`, ny checkbox)
- Modify: `app/static/js/app.js:15-38` (`state`), `:3494-3606` (Vehicles-sektion)

**Interfaces:**
- Consumes: `VehicleResponse.vognpark` (Task 2), body-feltet `vognpark` på `POST/PATCH /api/vehicles` (Task 2).

- [ ] **Step 1: Tilføj tab-switcher til Vognpark-siden**

I `app/templates/index.html`, linje 379-389, den eksisterende:
```html
    <!-- ══════════════ VEHICLES VIEW ══════════════ -->
    <div class="view hidden" data-view="vehicles">
      <div class="toolbar">
        <h2 style="font-size:16px;font-weight:600">Vognpark</h2>
        <div class="spacer"></div>
        <input type="text" id="vehicle-search" placeholder="Søg reg.nr. eller vognnr…"
               style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:220px">
        <button class="btn btn-primary" data-perm-require="manage_vehicles" onclick="openNewVehicleModal()">+ Opret vogn</button>
      </div>
      <div id="vehicle-list"></div>
    </div>
```
erstattes af:
```html
    <!-- ══════════════ VEHICLES VIEW ══════════════ -->
    <div class="view hidden" data-view="vehicles">
      <div class="toolbar">
        <h2 style="font-size:16px;font-weight:600">Vognpark</h2>
        <div class="spacer"></div>
        <input type="text" id="vehicle-search" placeholder="Søg reg.nr. eller vognnr…"
               style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:220px">
        <button class="btn btn-primary" data-perm-require="manage_vehicles" onclick="openNewVehicleModal()">+ Opret vogn</button>
      </div>

      <!-- Tab-switcher -->
      <div style="display:flex;gap:4px;margin-bottom:16px;border-bottom:2px solid var(--border)">
        <button id="veh-tab-vognpark" onclick="switchVehiclesTab('vognpark')"
                style="padding:7px 18px;border:none;border-bottom:2px solid var(--primary);margin-bottom:-2px;background:transparent;font-size:13px;font-weight:700;color:var(--primary);cursor:pointer">
          Vognpark
        </button>
        <button id="veh-tab-all" onclick="switchVehiclesTab('all')"
                style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer">
          Alle
        </button>
      </div>

      <div id="vehicle-list"></div>
    </div>
```

- [ ] **Step 2: Tilføj checkbox i `modal-vehicle`**

I `app/templates/index.html`, linje 1710-1717, den eksisterende:
```html
      <div class="form-group">
        <label>Disponentgruppe</label>
        <select id="vehicle-dispatcher-group"><option value="">— Ingen —</option></select>
      </div>
      <div class="form-group" id="vehicle-fast-bil-group" style="display:none">
        <label>Fast bil (medarbejder)</label>
        <input type="text" id="vehicle-fast-bil-employee" disabled style="background:var(--bg);color:var(--text-light)">
      </div>
```
erstattes af:
```html
      <div class="form-group">
        <label>Disponentgruppe</label>
        <select id="vehicle-dispatcher-group"><option value="">— Ingen —</option></select>
      </div>
      <div class="form-group">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
          <input type="checkbox" id="vehicle-vognpark"> Vognpark
        </label>
      </div>
      <div class="form-group" id="vehicle-fast-bil-group" style="display:none">
        <label>Fast bil (medarbejder)</label>
        <input type="text" id="vehicle-fast-bil-employee" disabled style="background:var(--bg);color:var(--text-light)">
      </div>
```

- [ ] **Step 3: Tilføj `vehiclesTab`-state**

I `app/static/js/app.js`, linje 28, den eksisterende:
```javascript
  usersAdminTab: "users",  // aktiv fane i users-admin view
```
udvides med:
```javascript
  usersAdminTab: "users",  // aktiv fane i users-admin view
  vehiclesTab: "vognpark", // aktiv fane i Vognpark-view ("vognpark" | "all")
```

- [ ] **Step 4: Tilføj `switchVehiclesTab()` og opdatér `renderVehicleList()`**

I `app/static/js/app.js`, linje 3511-3525, den eksisterende:
```javascript
function renderVehicleList() {
  const query = (document.getElementById("vehicle-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("vehicle-list");
  container.innerHTML = "";
  let vehicles = state.vehicles;
  if (query) {
    vehicles = vehicles.filter(v =>
      v.registration_number.toLowerCase().includes(query) ||
      String(v.vehicle_number).toLowerCase().includes(query)
    );
  }
```
erstattes af (ny `switchVehiclesTab()`-funktion indsat lige før, og et nyt fane-filter i `renderVehicleList()`):
```javascript
function switchVehiclesTab(tab) {
  state.vehiclesTab = tab;
  ["vognpark", "all"].forEach(t => {
    const btn = document.getElementById(`veh-tab-${t}`);
    if (btn) {
      btn.style.borderBottomColor = t === tab ? "var(--primary)" : "transparent";
      btn.style.color             = t === tab ? "var(--primary)" : "var(--text-light)";
      btn.style.fontWeight        = t === tab ? "700" : "600";
    }
  });
  renderVehicleList();
}

function renderVehicleList() {
  const query = (document.getElementById("vehicle-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("vehicle-list");
  container.innerHTML = "";
  let vehicles = state.vehicles;
  if (state.vehiclesTab === "vognpark") {
    vehicles = vehicles.filter(v => v.vognpark);
  }
  if (query) {
    vehicles = vehicles.filter(v =>
      v.registration_number.toLowerCase().includes(query) ||
      String(v.vehicle_number).toLowerCase().includes(query)
    );
  }
```

- [ ] **Step 5: Initialisér fanen ved indlæsning**

I `app/static/js/app.js`, linje 3494-3502, den eksisterende:
```javascript
async function loadVehicles() {
  setLoading(true);
  try {
    state.vehicles = await GET("/api/vehicles");
    if (!state.dispatcherGroups.length) { try { state.dispatcherGroups = await GET("/api/employees/dispatcher-groups"); } catch (_) {} }
    renderVehicleList();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}
```
`renderVehicleList()`-kaldet erstattes af `switchVehiclesTab(...)` (som selv kalder `renderVehicleList()` efter at have opdateret fane-styling — samme mønster som `loadUsersAdminView()`/`switchUsersAdminTab()`):
```javascript
async function loadVehicles() {
  setLoading(true);
  try {
    state.vehicles = await GET("/api/vehicles");
    if (!state.dispatcherGroups.length) { try { state.dispatcherGroups = await GET("/api/employees/dispatcher-groups"); } catch (_) {} }
    switchVehiclesTab(state.vehiclesTab || "vognpark");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}
```

- [ ] **Step 6: Nulstil checkboxen i `openNewVehicleModal()`**

I `app/static/js/app.js`, linje 3546-3556, den eksisterende:
```javascript
function openNewVehicleModal() {
  _editingVehicleId = null;
  document.getElementById("vehicle-modal-title").textContent = "Opret vogn";
  document.getElementById("vehicle-reg").value = "";
  document.getElementById("vehicle-num").value = "";
  document.getElementById("vehicle-description").value = "";
  fillVehicleDispatcherGroupSelect(null);
  document.getElementById("vehicle-fast-bil-group").style.display = "none"; // vognen findes ikke endnu - kan ikke være nogens Fast bil
  document.getElementById("vehicle-delete-btn").classList.add("hidden");
  openModal("modal-vehicle");
}
```
`vehicle-description`-linjen udvides med en ny linje for checkboxen:
```javascript
  document.getElementById("vehicle-description").value = "";
  document.getElementById("vehicle-vognpark").checked = false;
```

- [ ] **Step 7: Udfyld checkboxen i `openEditVehicle()`**

I `app/static/js/app.js`, linje 3558-3571, den eksisterende:
```javascript
function openEditVehicle(id) {
  const v = state.vehicles.find(x => x.id === id);
  if (!v) return;
  _editingVehicleId = id;
  document.getElementById("vehicle-modal-title").textContent = "Rediger vogn";
  document.getElementById("vehicle-reg").value = v.registration_number;
  document.getElementById("vehicle-num").value = v.vehicle_number;
  document.getElementById("vehicle-description").value = v.description || "";
  fillVehicleDispatcherGroupSelect(v.dispatcher_group_id);
```
`vehicle-description`-linjen udvides med en ny linje:
```javascript
  document.getElementById("vehicle-description").value = v.description || "";
  document.getElementById("vehicle-vognpark").checked = v.vognpark;
```

- [ ] **Step 8: Send feltet med i `saveVehicle()`**

I `app/static/js/app.js`, linje 3573-3583, den eksisterende:
```javascript
  const body = {
    registration_number: reg,
    vehicle_number: num,
    description: document.getElementById("vehicle-description").value.trim() || null,
    dispatcher_group_id: document.getElementById("vehicle-dispatcher-group").value
      ? parseInt(document.getElementById("vehicle-dispatcher-group").value) : null,
  };
```
erstattes af:
```javascript
  const body = {
    registration_number: reg,
    vehicle_number: num,
    description: document.getElementById("vehicle-description").value.trim() || null,
    vognpark: document.getElementById("vehicle-vognpark").checked,
    dispatcher_group_id: document.getElementById("vehicle-dispatcher-group").value
      ? parseInt(document.getElementById("vehicle-dispatcher-group").value) : null,
  };
```

- [ ] **Step 9: Manuel verifikation i browser**

Start dev-serveren og naviger til Vognpark-siden:
1. Bekræft at to faner vises: "Vognpark" (aktiv/fremhævet som standard) og "Alle".
2. På en frisk/eksisterende database uden markerede vogne: "Vognpark"-fanen viser "Ingen vogne"; "Alle" viser samtlige eksisterende vogne.
3. Opret en ny vogn med "Vognpark"-fluebenet sat → gem → skift til "Vognpark"-fanen → vognen skal nu være synlig der.
4. Redigér en vogn på "Alle"-fanen, fjern fluebenet → gem → skift til "Vognpark"-fanen → vognen skal nu være væk derfra, men stadig synlig på "Alle".
5. Naviger til Dagsplan-fanen, samme dato → bekræft at kun vogne markeret "Vognpark" optræder i vognkolonnen.
6. Søgefeltet (`#vehicle-search`) skal fortsat filtrere korrekt på begge faner.

- [ ] **Step 10: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: underfaner Vognpark/Alle + vognpark-flueben i vogn-modalen"
```

---

## Efter implementering

Kør hele test-suiten en sidste gang (`pytest -v`) og bekræft ingen regressioner, før branchen afsluttes (se `superpowers:finishing-a-development-branch`).

**Husk brugeren på konsekvensen:** efter denne opdatering er Dagsplanens vognkolonne tom, indtil nogen går ind under Vognpark → "Alle" og markerer de relevante vogne med "Vognpark"-fluebenet.
