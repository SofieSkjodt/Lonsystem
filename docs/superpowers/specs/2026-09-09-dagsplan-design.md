# Dagsplan

## Baggrund

I dag foregår den daglige fordeling af vogne til chauffører manuelt i et Excel-ark
uden for lønsystemet: en liste af vogne/type, hvem der kører hvilken vogn, hvilken
opgave, samt en samlet chaufførliste der viser hvem der er fraværende. Denne
ændring bygger en digital "Dagsplan"-side, der dækker samme behov og kobler sig
til de data, der allerede findes i systemet (medarbejdere, vognpark, vagtplan/
fravær, aktivitetsoversigt).

Kilde: `Dagsplan i PS Løn.docx` (indeholder også et skærmbillede af det nuværende
Excel-ark som reference).

## Omfang

- Ny sidebar-side "Dagsplan" med to underfaner: "Dagsplan" og "Materiel fravær"
  (samme fane-mønster som Stamdata).
- Ny persisteret dag-for-dag tildeling af chauffør/opgave pr. vogn.
- Ny "Fast bil"-indstilling pr. medarbejder, der foreslår en standardtildeling.
- Nyt "materielt fravær"-begreb pr. vogn (periode med kommentar).
- Nye felter på `Vehicle`: `description`, `dispatcher_group_id`.
- Kobling til Aktivitetsoversigten: autoudfyldning af vognnummer ved oprettelse
  af en "normal tid"-aktivitet, samt en advarsel ved uoverensstemmelse.
- To nye permissions: `dagsplan_view`, `dagsplan_edit`.

## Datamodel

### `Vehicle` (nye felter)
| Felt | Type | Bemærk |
|---|---|---|
| `description` | Text, nullable | "Beskrivelse" – vises i Dagsplan kol. 2 |
| `dispatcher_group_id` | Integer FK → `dispatcher_groups.id`, nullable | Ny, separat relation (mange vogne → én gruppe). Erstatter IKKE det eksisterende `DispatcherGroup.vehicle_id` (én "standardvogn" pr. gruppe, fortsat brugt uændret til autoudfyld af vognnummer ved oprettelse af fraværstype-aktiviteter). De to felter løser hver sin opgave og lever side om side. |

Sættes/redigeres i den eksisterende Vognpark-sides opret/rediger-vogn-modal
(kræver fortsat `manage_vehicles`, uændret).

### `Employee` (nye felter)
| Felt | Type | Bemærk |
|---|---|---|
| `fast_bil` | Boolean, default false | Krydsfelt i medarbejder-modalen |
| `fast_bil_vehicle_id` | Integer FK → `vehicles.id`, nullable | Kun udfyldt/relevant hvis `fast_bil=true`. Vognvalget er IKKE begrænset til medarbejderens egen disponentgruppe – alle vogne i vognparken kan vælges. |

### Ny tabel `daily_plan_assignments`
| Felt | Type | Bemærk |
|---|---|---|
| `id` | Integer PK | |
| `date` | Date | |
| `vehicle_id` | Integer FK → `vehicles.id` | |
| `employee_id` | Integer FK → `employees.id`, nullable | Tom række (vogn uden chauffør den dag) er gyldig |
| `task` | String, nullable | "Opgave" |
| `informed` | Boolean, default false | "Chauffør informeret" |
| `created_at`/`updated_at` | DateTime | |

`UniqueConstraint(date, vehicle_id)` – én tildeling pr. vogn pr. dag (upsert).

**"EKSTRA"-rækkerne** (10 stk., til hjælp på pladsen/lærlinge) indgår ALDRIG i
autoudfyldningen af vognnummer på aktiviteter (der er intet rigtigt vognnummer
at udfylde med). *(Opdateret 2026-09-09: de persisteres nu også, i egen tabel
`daily_plan_extra_assignments` – se nedenfor. Oprindeligt var beslutningen at
de KUN skulle leve i frontend-state og nulstilles ved datoskift; brugeren bad
efterfølgende om at få dem gemt, så man kan se dem igen senere.)*

En medarbejder der forsøges tildelt en vogn/EKSTRA-plads, mens vedkommende
allerede har en anden effektiv tildeling samme dag, får en advarsel (409 med en
menneskelæsbar besked) i stedet for at blive blokeret – bekræfter brugeren,
gennemføres dobbelttildelingen alligevel. Samme mønster bruges til at advare,
hvis medarbejderen har registreret fravær den dag. *(Tilføjet 2026-09-09 efter
brugerønske – oprindeligt var her slet ingen validering.)*

### Ny tabel `vehicle_absences` (materielt fravær)
| Felt | Type | Bemærk |
|---|---|---|
| `id` | Integer PK | |
| `vehicle_id` | Integer FK → `vehicles.id` | |
| `date_from` | Date | |
| `date_to` | Date, nullable | `null` = samme dag som `date_from` (étdags-fravær) |
| `comment` | Text | Årsag/beskrivelse |
| `created_by` | String, nullable | Initialer |
| `created_at` | DateTime | |

En vogn regnes som materielt fraværende på dato `d`, hvis der findes en række
hvor `date_from <= d <= (date_to ?? date_from)`.

### Migration
Idempotent kolonnetilføjelse i `session.py`s `_migrate()` (samme mønster som
øvrige kolonner: `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` hvis kolonnen
mangler) for `Vehicle`/`Employee`-felterne, samt oprettelse af de to nye tabeller
ved `Base.metadata.create_all` (som resten af skemaet).

## Backend

### Nye permissions (samme mønster som `absence_overview`/`toggle_springer`)
- `dagsplan_view` – se Dagsplan-siden (begge underfaner), read-only.
- `dagsplan_edit` – redigere tildelinger, afkrydse "informeret", melde/fjerne
  materielt fravær.

Tilføjes idempotent ved opstart (samme mønster som
`_ensure_manage_baselines_permission()`); `admin` får dem automatisk som
systemrolle. Øvrige roller tildeles dem ikke som default, men kan gives det via
rolle-editoren.

### `GET /api/dagsplan?date=YYYY-MM-DD`
Kræver `dagsplan_view`. Ét samlet svar for hele dagsvisningen:

- `vehicles`: liste sorteret efter vognnummer – for hver vogn: `vehicle_number`,
  `description`, `dispatcher_group_id`, evt. tildeling (`employee_id`, `task`,
  `informed`), og – hvis en medarbejder er tildelt – et `mismatch_vehicle_number`
  felt (se nedenfor). Vogne med aktivt materielt fravær den dag markeres med
  `absent: true`.
- `employees`: den fulde medarbejderliste (alle aktive medarbejdere, samme
  grundmængde som Aktivitetsoversigten – IKKE påvirket af nedenstående filtre),
  hver med en farvestatus (`assigned` grøn / `absent` rød / `none` grå /
  `comment_only` gul – forrang: gul > rød > grøn > grå, jf. kravet om at forblive
  gul selv når medarbejderen er skrevet i chauffør-kolonnen) og evt. fraværstekst
  (type-label eller vagtplan-kommentar).

Disponentgruppe- og medarbejder-filtrering sker på query-parametre
(`dispatcher_group_id?`, `employee_id?`) og påvirker KUN `vehicles`-listen –
`employees`-listen returneres altid ufiltreret.

**Mismatch-beregning:** for hver tildelt medarbejder slås dagens `normal`-type
aktiviteter op (samme dato som `date`). Findes mindst én med et `vehicle_number`
der afviger fra den tildelte vogns `vehicle_number`, sættes
`mismatch_vehicle_number` til den afvigende værdi (bruges til advarselstrekant +
tooltip "vognnummer i løn: xxx" i frontend). Andre aktivitetstyper (fravær)
indgår ikke i denne sammenligning.

### `PATCH /api/dagsplan/assignment`
Kræver `dagsplan_edit`. Body: `{date, vehicle_id, employee_id?, task?,
informed?}`. Upsert på `(date, vehicle_id)`.

### `POST /api/vehicle-absences`
Kræver `dagsplan_edit`. Body: `{vehicle_id, date_from, date_to?, comment}`.

### `DELETE /api/vehicle-absences/{id}`
Kræver `dagsplan_edit`.

### `GET /api/vehicle-absences?date=YYYY-MM-DD`
Kræver `dagsplan_view`. Liste over materielt fravær der er aktivt på den angivne
dato (bruges af "Materiel fravær"-underfanen, som deler valgt dato med
"Dagsplan"-fanen – ingen egen datonavigation).

### `vehicles.py`
`VehicleCreate`/`VehicleUpdate`/`VehicleResponse` udvides med
`description`/`dispatcher_group_id`. Uændret permission (`manage_vehicles`).

### `employees.py`
`EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse` udvides med
`fast_bil`/`fast_bil_vehicle_id`.

### Autoudfyld ved oprettelse af manuel aktivitet (`create_manual_activity`, `activities.py`)
Hvis `activity_type == "normal"` og request-body'ens `vehicle_number` er tomt:
slå `daily_plan_assignments` op på `(employee_id, start_time.date())`. Findes en
tildeling med en vogn, udfyldes `vehicle_number` fra den. Gælder KUN "normal
tid" – den eksisterende disponentgruppe-baserede autoudfyldning for
fraværstyper (`applyDispatcherGroupVehicleDefault()` i frontend) er uændret og
upåvirket.

## Frontend (`app.js` + `index.html`)

### Sidebar
Ny post `data-view="dagsplan"` med `data-perm-require="dagsplan_view"`, placeret
mellem "Vagtplan" og "DDD-import".

### Fanestruktur
To underfaner på Dagsplan-siden (samme tab-switch-mønster som Stamdata):
"Dagsplan" og "Materiel fravær". Begge deler samme valgte dato (ét
state-felt, fx `state.dagsplan.date`).

### Underfane "Dagsplan"
- Topbar: dato-navigation (◀ / date-picker / ▶, default dags dato), overskrift
  "Dagsplan – d. [dato]", disponentgruppe-filter, medarbejder-filter (søgbar) –
  begge filtre påvirker kun hovedtabellen.
- Hovedtabel (5 kolonner): Vognnummer | Beskrivelse | Chauffør (søgbar
  select/combobox, samme mønster som andre medarbejder-søgefelter i appen) |
  Opgave (tekstfelt) | Informeret (checkbox). Efterfulgt af 10 faste
  "EKSTRA"-rækker (ingen beskrivelse, samme redigerbare felter, men INGEN
  persistering og INGEN vognnummer-autoudfyldning ved brug).
  - Er medarbejderens `fast_bil_vehicle_id` sat, foreslås vedkommende som
    default chauffør på den vogns række (kan altid ændres). Har medarbejderen
    fravær den dag, vises vedkommende stadig på sin faste vogn, men rødt.
  - Ved `mismatch_vehicle_number`: ⚠️-ikon ved chaufførnavnet, tooltip
    "vognnummer i løn: {mismatch_vehicle_number}".
  - Vogne med `absent: true` (materielt fravær) vises rødt.
- Sideliste (separat lille tabel ved siden af, ALDRIG påvirket af filtrene): den
  fulde medarbejderliste, farvekodet, med fraværstekst.
- Uden `dagsplan_edit`: samme visning, men alle inputs/knapper er
  read-only/deaktiverede (samme mønster som andre steder i appen –
  `data-perm-require`/`btn-muted`).

### Underfane "Materiel fravær"
- "Meld materielt fravær"-knap (kræver `dagsplan_edit`) → modal: vognvalg,
  "Fra dato" (default: fanens valgte dato), "Til dato" (valgfri – tom betyder
  étdags-fravær), kommentar.
- Tabel over dagens meldte fravær: Vognnummer | Periode | Kommentar, med en
  slet-knap (kræver `dagsplan_edit`).

### Vognpark-siden (`data-view="vehicles"`, eksisterende)
Opret/rediger-vogn-modalen udvides med "Beskrivelse" (tekstfelt) og
disponentgruppe (samme dropdown-mønster som medarbejder-modalens
disponentgruppe-felt). Uændret permission (`manage_vehicles`).

### Medarbejder-modalen (`modal-employee`, eksisterende)
Nyt "Fast bil"-krydsfelt; når krydset, vises et søgbart vognnummer-felt
(`fast_bil_vehicle_id`), ubegrænset af disponentgruppe.

## Tests
- `daily_plan_assignments`: upsert (opret + opdater eksisterende), unik pr.
  (date, vehicle_id).
- `vehicle_absences`: opret med/uden `date_to`, korrekt "aktiv på dato"-logik,
  sletning.
- Autoudfyld: `create_manual_activity` udfylder vognnummer for "normal tid" fra
  dagens tildeling, rører IKKE ved fraværstyper, overskriver ALDRIG et allerede
  udfyldt vognnummer.
- `GET /api/dagsplan`: filtrering påvirker kun `vehicles`, aldrig `employees`;
  mismatch-felt sættes korrekt ved afvigende vognnummer på en "normal
  tid"-aktivitet; farveprioritet (gul > rød > grøn > grå) på medarbejderlisten.
- Permission-tjek: `dagsplan_view`/`dagsplan_edit` håndhæves på alle nye
  endpoints.

## Ikke omfattet
- Ingen ændring af den eksisterende disponentgruppe-baserede
  autoudfyldning for fraværstyper.
- Ingen tilbagevirkende migrering/gruppering af historiske Excel-data.
- "EKSTRA"-rækkerne indgår ikke i nogen lønberegning eller
  vognnummer-autoudfyldning (kun i "Fast bil"/rigtige vogne).
