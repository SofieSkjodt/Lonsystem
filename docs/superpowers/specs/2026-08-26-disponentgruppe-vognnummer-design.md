# Disponentgruppe → ét vognnummer på fraværsregistrering – Design

**Dato:** 2026-08-26
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

I dag skal brugeren manuelt indtaste og matche et vognnummer/registreringsnummer, når der registreres **enhver** aktivitet – også fraværstyper (ferie, sygdom, barsel osv.), hvor et vognnummer reelt ikke har noget med fraværet at gøre. Feltet er påkrævet (`app.js`, `confirmManualActivity()`, linje ~2046-2059) og skal matche et køretøj i vognparken, ellers vises en fejl.

**Ønsket ændring:** Ved registrering af enhver fraværstype skal vognnummeret automatisk foreslås ud fra medarbejderens disponentgruppe. For at det skal give entydig mening, ændres disponentgruppe fra en mange-til-mange-relation (en medarbejder kan i dag være i flere grupper) til at en medarbejder fremover kun kan tilhøre **én** disponentgruppe. Hver disponentgruppe kan tilknyttes ét vognnummer via Stamdata.

Nuværende data: 72 aktive medarbejdere, heraf 2 med mere end én gruppe i dag (Andreas Lentz: Miljø + BN; Nick Vinge: Makulering + Miljø).

## 1. Datamodel

**`Employee`** (`app/database/models.py`): `dispatcher_groups`-relationen (mange-til-mange via `employee_dispatcher_groups`) erstattes af:
```python
dispatcher_group_id = Column(Integer, ForeignKey("dispatcher_groups.id"), nullable=True)
dispatcher_group = relationship("DispatcherGroup", back_populates="employees")
```

**`DispatcherGroup`**: `employees`-relationen bliver en almindelig one-to-many (`back_populates="dispatcher_group"`). Nyt felt:
```python
vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
vehicle = relationship("Vehicle")
```

**`EmployeeDispatcherGroup`**-klassen (junction-tabellen) fjernes helt fra `models.py`.

### Migration (idempotent, samme stil som eksisterende `_migrate_dispatcher_groups()` i `session.py`)

Ny funktion, kaldt fra `init_db()` **efter** den eksisterende `_migrate_dispatcher_groups()`:

1. Tilføj `employees.dispatcher_group_id`-kolonnen (nullable) hvis den mangler (rå `ALTER TABLE`, samme mønster som `visible_in_activity_overview`-migrationen).
2. Tilføj `dispatcher_groups.vehicle_id`-kolonnen (nullable) hvis den mangler.
3. For hver medarbejder med rækker i `employee_dispatcher_groups`:
   - 1 gruppe → sæt `dispatcher_group_id` til den.
   - 0 grupper → forbliver `NULL`.
   - >1 gruppe → sæt til den alfabetisk først sorterede gruppes id (efter `DispatcherGroup.name`). Med nuværende data giver det: Andreas Lentz → "5 - Miljø", Nick Vinge → "4 - Makulering" (bekræftet af bruger).
4. Drop `employee_dispatcher_groups`-tabellen.
5. Idempotent: tjek at `employee_dispatcher_groups` stadig findes / at `dispatcher_group_id`-kolonnen mangler, før data-trinnet køres igen – samme vagt-mønster som den eksisterende migration bruger for sin egen legacy-kolonne.

## 2. API og schemas

**`app/database/schemas.py`:**
- `EmployeeCreate.dispatcher_group_ids: list[int]` → `dispatcher_group_id: Optional[int] = None`
- `EmployeeUpdate.dispatcher_group_ids: Optional[list[int]]` → `dispatcher_group_id: Optional[int] = None`
- `EmployeeResponse.dispatcher_groups: list[DispatcherGroupResponse]` → `dispatcher_group: Optional[DispatcherGroupResponse] = None`
- `DispatcherGroupResponse` får `vehicle_id: Optional[int] = None` og `vehicle_number: Optional[str] = None` (denormaliseret, så frontend ikke selv skal slå køretøjet op)

**`app/routers/employees.py`:**
- `_resolve_dispatcher_groups(db, ids) -> list[DispatcherGroup]` → `_resolve_dispatcher_group(db, id) -> Optional[DispatcherGroup]` (enkelt opslag; 400 ved ukendt id)
- `_to_response()`: `dispatcher_groups=[...]` → `dispatcher_group=DispatcherGroupResponse.model_validate(emp.dispatcher_group) if emp.dispatcher_group else None`
- `create_employee`: `data = body.model_dump(exclude={"dispatcher_group_id"})`; `emp.dispatcher_group = _resolve_dispatcher_group(db, body.dispatcher_group_id)`
- `update_employee`: for at kunne **fjerne** en medarbejder fra sin gruppe (sætte til "ingen"), skal det skelnes mellem "feltet blev ikke sendt" og "feltet blev eksplicit sat til `null`". Dette gøres med Pydantic v2's `body.model_fields_set` i stedet for det nuværende `is not None`-tjek:
  ```python
  if "dispatcher_group_id" in body.model_fields_set:
      emp.dispatcher_group = _resolve_dispatcher_group(db, body.dispatcher_group_id)
  ```

**`app/routers/stamdata.py`:**
- `DispatcherGroupBody` får `vehicle_id: Optional[int] = None`
- `create_dispatcher_group`: validerer at et angivet `vehicle_id` findes i vognparken (400 "Ukendt køretøj" hvis ikke), sætter `row.vehicle_id`
- `update_dispatcher_group`: samme `model_fields_set`-teknik som ovenfor, så et vognnummer også kan fjernes fra en gruppe igen:
  ```python
  if "vehicle_id" in body.model_fields_set:
      if body.vehicle_id is not None and not db.query(Vehicle).filter(Vehicle.id == body.vehicle_id).first():
          raise HTTPException(400, "Ukendt køretøj")
      row.vehicle_id = body.vehicle_id
  ```
- `_dispatcher_group_row()`: tilføj `"vehicle_id": r.vehicle_id, "vehicle_number": r.vehicle.vehicle_number if r.vehicle else None`

**`app/routers/payroll_router.py`** (linje 715):
```python
return [e for e in employees if e.dispatcher_group and e.dispatcher_group.visible_in_activity_overview]
```

**`app/routers/absence_overview_router.py`** (`employee_options()` linje ~192-199, `export_per_employee()` linje ~223-233):
- `used_group_ids = {e.dispatcher_group_id for e in emps if e.dispatcher_group_id}`
- `"dispatcher_group_id": e.dispatcher_group_id` (singular nøgle – det gamle `dispatcher_group_ids`-felt i dette specifikke svar bruges ikke af frontend i dag, så omdøbning er uden risiko)
- `Employee.dispatcher_groups.any(DispatcherGroup.id == dispatcher_group_id)` → `Employee.dispatcher_group_id == dispatcher_group_id`
- Kommentaren "Medarbejderen vises under alle sine tilknyttede grupper" fjernes/forenkles, da den ikke længere er relevant med præcis én gruppe

## 3. Frontend – medarbejder- og stamdata-UI

**Medarbejder-modalen** (`index.html` + `app.js`): "Disponentgrupper"-sektionen med afkrydsningsfelter (`#emp-dispatcher-groups`, `_renderDispatcherGroupCheckboxes()`) erstattes af ét `<select id="emp-dispatcher-group">` med en "— Ingen —"-mulighed øverst, i stil med de øvrige dropdowns i modalen. `openEditEmployeeModal()` sætter blot `select.value = e.dispatcher_group?.id ?? ""`. `confirmEmployee()` sender `dispatcher_group_id: value ? parseInt(value) : null` i stedet for en liste.

**Gruppemedlemskabs-tjek i `app.js`** (bruges til vagtplan-/aktivitetsoversigt-filtrering – disse forbliver multi-select-filtre for hvilke grupper der VISES, det er kun den enkelte medarbejders eget tilhørsforhold der bliver 1:1): `_empInGroup()`, `_empHasVisibleGroup()`, og de tre direkte `.some()`-tjek (linje 247, 317, 5052) opdateres til at sammenligne mod `e.dispatcher_group?.id` i stedet for at søge i en liste.

**Stamdata → Disponentgrupper-modalen** (`modal-stamdata-dispatcher`): nyt "Vognnummer"-felt mellem "Beskrivelse" og "Vis i aktivitetsoversigt". Da det skal kunne søges i (fx skrive en delstreng og se alle matchende køretøjer, uanset hvor i teksten den findes – native `<datalist>` er ikke konsistent på tværs af browsere for dette), bygges en lille brugerdefineret søge-dropdown fra bunden:

- Tekstfelt (`#stamdata-dispatcher-vehicle-search`) + skjult felt til det valgte køretøjs id (`#stamdata-dispatcher-vehicle-id`) + en absolut-positioneret resultatliste (`#stamdata-dispatcher-vehicle-dropdown`) der vises under feltet
- Mens der skrives, filtreres `state.vehicles` på om `vehicle_number` **eller** `registration_number` indeholder den indtastede tekst (case-insensitive, hvor som helst i strengen – ikke kun fra start), og alle matches vises som klikbare rækker
- Klik på en række udfylder tekstfeltet med vognnummeret og gemmer køretøjets id i det skjulte felt, og lukker listen
- Et tomt tekstfelt betyder "intet køretøj tilknyttet" (`vehicle_id: null` ved gem)
- Ved åbning af redigér-gruppe forudfyldes tekstfeltet med det aktuelle vognnummer og det skjulte felt med køretøjets id

Tabellen i stamdata-oversigten (`loadStamdataDispatcherGroups()`) får en ny "Vognnummer"-kolonne.

## 4. Vognnummer-autoudfyldning ved fraværsregistrering

Ny funktion i `app.js`, efter samme mønster som de eksisterende type-afhængige standardværdi-funktioner (`applyFerieDefaults()`, `applyBarselTerminsdatoDefault()` m.fl.):

```js
function applyDispatcherGroupVehicleDefault() {
  const type = document.getElementById("manual-type").value;
  if (!ABSENCE_TYPES.has(type)) return;
  const regField = document.getElementById("manual-reg");
  if (regField.value.trim()) return; // brugeren har allerede skrevet noget – overskriv ikke
  const empId = parseInt(document.getElementById("manual-employee").value);
  const emp = state.employees.find(e => e.id === empId);
  const vehicleNumber = emp?.dispatcher_group?.vehicle_number;
  if (vehicleNumber) {
    regField.value = vehicleNumber;
    regField.dispatchEvent(new Event("input")); // genbruger eksisterende hint-visning
  }
}
```

Kaldes fra `updateManualTypeVisibility()` (dækker både typeskift og modal-åbning, da funktionen allerede køres i begge tilfælde i dag) og fra `manual-employee`'s eksisterende `onchange`-handler (samme sted som ferie-/sygdoms-standardværdierne genberegnes ved medarbejderskift).

Feltet forbliver almindeligt redigerbart – ingen ændring af den eksisterende "Registreringsnummer/Vognnummer er påkrævet"-validering. Har medarbejderen ingen gruppe, eller har gruppen intet vognnummer, forbliver feltet tomt som i dag, og brugeren skal udfylde det manuelt.

### Rettelse: flerdags-fravær sender i dag ikke vognnummer med

Ved gennemgang af `confirmManualActivity()` blev det opdaget, at flerdags-fraværsregistrering (ferie/sygdom/barsel/afspadsering-periode, linje ~2135-2142) validerer og kræver et vognnummer i UI'et, men **aldrig sender `vehicle_number` med** i sit `POST /api/activities`-kald – værdien går tabt for alle flerdags-fraværsregistreringer. Dette rettes som en del af denne opgave (tilføjer `vehicle_number: foundVehicle?.vehicle_number || null,` til det pågældende POST-kald), da autoudfyldningen ellers ville være virkningsløs for netop flerdags-fravær, som udgør størstedelen af reel fraværsregistrering (ferie, sygdom, barsel).

## Ikke i scope

- Ingen ændring af vagtplanens gruppefilter (forbliver multi-select – det er en visningsfilter, ikke medarbejderens tilhørsforhold).
- Ingen ændring af `manual-reg`-feltets eksisterende fritekst+hint-adfærd i selve opret-aktivitet-modalen (kun disponentgruppe-modalens nye søgefelt bruger den brugerdefinerede dropdown).
- Ingen ændring af den eksisterende validering af, at et vognnummer skal matche et køretøj i vognparken.

## Test-dækning (til implementeringsplan)

- Migration: en medarbejder med 1 gruppe før migrering har samme gruppe efter. En medarbejder med 0 grupper har `dispatcher_group_id = NULL` efter. Andreas Lentz ender med "5 - Miljø", Nick Vinge med "4 - Makulering". `employee_dispatcher_groups`-tabellen findes ikke længere efter migrering. Migrationen er idempotent (kørt to gange giver samme resultat, ingen fejl).
- `create_employee`/`update_employee` med `dispatcher_group_id` sat/ikke sat/eksplicit `null` (fjerner gruppen).
- `create_dispatcher_group`/`update_dispatcher_group` med gyldigt/ugyldigt/eksplicit `null` `vehicle_id`.
- `_active_employees()` i `payroll_router.py` filtrerer korrekt på `dispatcher_group.visible_in_activity_overview` for en medarbejder uden gruppe (ekskluderes) og med gruppe (inkluderes/ekskluderes efter gruppens flag).
- `applyDispatcherGroupVehicleDefault()`: fraværstype + medarbejder med gruppe+vognnummer → feltet udfyldes. Fraværstype + medarbejder uden gruppe → feltet forbliver tomt. Fraværstype + feltet allerede udfyldt manuelt → overskrives ikke. "Normal tid" → funktionen gør intet.
- Flerdags-fraværsregistrering: opret en ferieperiode over flere dage → hver oprettet aktivitet har `vehicle_number` sat (regressionstest for den fundne fejl).
- Stamdata-søgefelt: indtastning af en delstreng der findes midt i et vognnummer eller registreringsnummer viser det matchende køretøj i listen; tomt felt ved gem giver `vehicle_id: null`.
