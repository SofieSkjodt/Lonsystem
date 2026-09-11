# Vognpark – underfaner "Vognpark"/"Alle" + Dagsplan-filtrering – Design

**Dato:** 2026-09-11
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

I dag viser Dagsplanens vognkolonne (`_build_vehicle_rows()`) *alle* vogne i `vehicles`-tabellen, uden mulighed for at udelade nogen. Der er behov for at kunne markere hvilke vogne der reelt indgår i den daglige vogn/chauffør-fordeling, adskilt fra Vognpark-registret som helhed (som fx også kan indeholde vogne der er solgt, i restordre, eller af anden grund ikke skal planlægges dagligt).

Løsningen er et nyt flueben "Vognpark" direkte på vognen, sat ved oprettelse/redigering. Vognpark-siden får to underfaner (samme visuelle tab-switcher-mønster som Stamdata) til at navigere mellem den filtrerede og den fulde liste.

Afklaret under brainstorming:
- **Default-værdi**: `false` for alle eksisterende og alle nye vogne. Det betyder at *ingen* vogne vises i Dagsplanens vognkolonne umiddelbart efter denne opdatering, før nogen aktivt går ind og markerer de relevante vogne. Dette er en bevidst, midlertidig regression i Dagsplan-visningen — se "Vigtig konsekvens" nedenfor.
- **Fanesemantik**: "Vognpark"-fanen er en filtreret delmængde (kun vogne med fluebenet sat). "Alle"-fanen viser samtlige vogne uanset flueben, og er der man opretter/redigerer vogne og sætter fluebenet. Begge faner bruger samme liste-UI (`renderVehicleList()`), blot filtreret forskelligt — ikke to uafhængige datasæt som Stamdatas faner.
- **Standardfane**: "Vognpark" er åben som standard ved navigation til siden (samme princip som Stamdatas første fane er standard).
- **Ingen ændring** til Fast bil-vælgeren (medarbejder-modal) eller vogn-søgningen i "Meld materielt fravær" — begge fortsætter med at kunne vælge blandt *alle* vogne, uanset vognpark-flueben.

## Vigtig konsekvens

Umiddelbart efter denne opdatering vil Dagsplanens vognkolonne være tom, fordi alle eksisterende vogne migreres med `vognpark=false`. Brugeren skal gå ind under Vognpark → "Alle" og markere de vogne der skal indgå i Dagsplanen, før den igen viser noget. Dette er et bevidst valg (bekræftet under brainstorming), ikke en fejl.

Hvis en vogn er "Fast bil" for en medarbejder, men ikke er markeret "Vognpark", vises den stadig ikke i Dagsplan — Fast bil-fallback'et i `effective_vehicle_for_employee()`/`_build_vehicle_rows()` rammer aldrig ind, fordi vognen slet ikke er med i den liste `_build_vehicle_rows()` itererer over. Dette er en ren følgevirkning af filtreringen, ikke ny logik der skal bygges.

## 1. Datamodel

**`Vehicle`** (`app/database/models.py`), ny kolonne:
```python
vognpark = Column(Boolean, default=False, nullable=False)
```

**Migration** (`app/database/session.py: _migrate()`), idempotent, indsættes sammen med de øvrige `vehicles`-kolonne-migreringer (linje ~240-246):
```python
if "vognpark" not in veh_cols:
    conn.execute("ALTER TABLE vehicles ADD COLUMN vognpark BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()
```

## 2. Schemas (`app/database/schemas.py`)

- `VehicleCreate`: `vognpark: bool = False`
- `VehicleUpdate`: `vognpark: Optional[bool] = None`
- `VehicleResponse`: `vognpark: bool`

Ingen validering eller afhængige felter nødvendig — indgår i den almindelige flow i `create_vehicle`/`update_vehicle`, samme som `description`.

## 3. Backend (`app/routers/vehicles.py`)

`create_vehicle`: sætter `vognpark=body.vognpark` på den nye `Vehicle`.
`update_vehicle`: sætter `v.vognpark = body.vognpark` hvis feltet er sendt (`"vognpark" in body.model_fields_set`), samme mønster som `dispatcher_group_id`.

Ingen ændring til `delete_vehicle` eller `list_vehicles` — begge er uafhængige af det nye felt.

## 4. Dagsplan-filtrering (`app/routers/dagsplan_router.py`)

`_build_vehicle_rows()` (linje ~62) filtrerer nu på det nye felt:
```python
for v in db.query(Vehicle).filter(Vehicle.vognpark == True).order_by(Vehicle.vehicle_number).all():
```
Resten af funktionen (Fast bil-fallback, mismatch-advarsel, fraværsflag) er uændret — den opererer allerede kun på de vogne der kommer ud af denne forespørgsel.

`_conflicting_assignment_label()` bruger `_build_vehicle_rows()` internt og er derfor automatisk konsistent: en medarbejder der er "Fast bil" på en ikke-vognpark-markeret vogn tælles ikke som optaget der, hvilket er korrekt, da vognen slet ikke indgår i Dagsplanen.

## 5. Frontend

### Vognpark-modalen (`templates/index.html`, `modal-vehicle`)

Ny checkbox, samme visuelle mønster som andre boolske vogn-/medarbejderfelter:
```html
<div class="form-group">
  <label><input type="checkbox" id="vehicle-vognpark"> Vognpark</label>
</div>
```
Placeres under "Disponentgruppe"-feltet, over det eksisterende (read-only) "Fast bil"-felt.

### Vognpark-siden (`templates/index.html`, view `vehicles`)

Tab-switcher indsat mellem toolbar og `#vehicle-list`, samme CSS/struktur som Stamdatas (`sd-tab-*`/`switchStamdataTab`):
```html
<div style="display:flex;gap:4px;margin-bottom:16px;border-bottom:2px solid var(--border)">
  <button id="veh-tab-vognpark" onclick="switchVehiclesTab('vognpark')" ...>Vognpark</button>
  <button id="veh-tab-all" onclick="switchVehiclesTab('all')" ...>Alle</button>
</div>
```
"Vognpark" får den aktive stil (`border-bottom:2px solid var(--primary)`, `color:var(--primary)`) som standard; "Alle" starter inaktiv — samme visuelle mønster som Stamdata-fanerne.

### `static/js/app.js`

- Nyt state-felt: `state.vehiclesTab = "vognpark"` (initialiseret i `state`-objektet, linje ~21).
- `switchVehiclesTab(tab)`: sætter `state.vehiclesTab`, opdaterer aktiv/inaktiv styling på de to knapper (samme mønster som `switchStamdataTab`), kalder `renderVehicleList()`.
- `renderVehicleList()` (linje ~3511): filtrerer nu også på `state.vehiclesTab === "vognpark" ? v.vognpark : true`, oven i det eksisterende søgefilter.
- `openNewVehicleModal()`: nulstil `vehicle-vognpark` til `false` (unchecked).
- `openEditVehicle(id)`: sæt `vehicle-vognpark`-checkbox fra `v.vognpark`.
- `saveVehicle()`: tilføj `vognpark: document.getElementById("vehicle-vognpark").checked` til `body`.
- Ingen ændring til `loadVehicles()`, `deleteVehicle()`, eller til de øvrige steder der bruger `state.vehicles` (Fast bil-vælger, vogn-søgning i fravær/aktivitet/Stamdata-disponent) — disse forbliver uafhængige af `vognpark`-feltet og af den aktive fane.

Ingen ny permission — checkboxen gates af den eksisterende `manage_vehicles`-tilladelse (samme som resten af `modal-vehicle`), og selve fane-skiftet kræver kun `view_vehicles` (samme som resten af siden).

## Ikke i scope

- Ingen ændring af Fast bil-vælgeren eller "Meld materielt fravær"-vognsøgningen — begge viser fortsat alle vogne uanset `vognpark`-flueben.
- Ingen ny "flåde-gruppe"-tabel eller mange-til-mange-relation — afvist under brainstorming (YAGNI), da et simpelt flueben pr. vogn dækker behovet.
- Ingen automatisk migrering af eksisterende data til `vognpark=true` — bevidst `false` som default, jf. "Vigtig konsekvens" ovenfor.
- Ingen ændring af `DispatcherGroup.vehicle_id` ("standardvogn pr. gruppe") eller den dertilhørende autoudfyldning ved fraværstyper — uafhængig mekanisme, upåvirket.

## Test-dækning (til implementeringsplan)

- Migration: kolonnen tilføjes idempotent til en eksisterende database, eksisterende rækker får `vognpark=false`.
- `VehicleCreate`/`VehicleUpdate`/`VehicleResponse` med `vognpark` — oprettelse (default `false` hvis udeladt, og eksplicit `true`), opdatering (til/fra).
- `GET /api/dagsplan?date=...`: en vogn med `vognpark=false` optræder ikke i `vehicles`-listen i svaret, uanset om den har en gemt `DailyPlanAssignment` eller er nogens "Fast bil". En vogn med `vognpark=true` optræder som hidtil (inkl. mismatch-advarsel og fraværsflag, uændret logik).
- `_conflicting_assignment_label()`: en medarbejder hvis eneste tilknytning er "Fast bil" på en ikke-vognpark-vogn giver ingen konflikt-advarsel ved tildeling andetsteds.
- Frontend: `renderVehicleList()` viser kun `vognpark=true`-vogne på "Vognpark"-fanen og alle vogne på "Alle"-fanen, i begge tilfælde stadig begrænset af søgefeltet.
- `saveVehicle()`: opret/rediger en vogn med fluebenet sat/ikke sat, verificér `vognpark` i den returnerede/efterfølgende hentede vogn.
- Eksisterende funktionalitet uændret: Fast bil-vælger og "Meld materielt fravær"-vognsøgning viser stadig alle vogne uanset flueben og fane.
