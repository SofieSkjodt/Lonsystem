# Design: Synlighed af disponentgrupper i aktivitetsoversigten

**Dato:** 2026-08-21
**Status:** Godkendt til implementeringsplan

## Baggrund

Under Stamdata → Disponentgrupper skal det være muligt at vælge, hvilke af de
oprettede grupper (og dermed også deres medarbejdere) der skal ses i
aktivitetsoversigten. I dag vises ALLE aktive medarbejdere altid i
aktivitetsoversigtens gitter, uanset disponentgruppe — den eksisterende
"Alle afdelinger"-dropdown (`filter-dispatcher-group`) er kun et midlertidigt,
ikke-gemt filter man selv vælger ved hvert besøg.

## Beslutninger (afklaret med bruger)

1. **Global indstilling**, administreret i Stamdata — gælder ens for alle
   brugere, ikke en personlig præference.
2. **Default = synlig.** Alle eksisterende grupper sættes til synlig ved
   udrulning. Nye grupper er synlige som standard ved oprettelse.
3. **Medarbejder med flere grupper:** vises i aktivitetsoversigten, så snart
   mindst ÉN af vedkommendes grupper er markeret synlig.
4. **Medarbejder uden nogen gruppe:** behandles som "ingen synlig gruppe" og
   skjules fra aktivitetsoversigten.
5. **Skjulte grupper forsvinder helt** fra afdelings-filterets dropdown i
   aktivitetsoversigten — kan ikke midlertidigt "kigges ind i" via filteret.
   De kan stadig ses/redigeres i Stamdata, og deres medarbejdere/aktiviteter er
   upåvirkede i Medarbejdere, Tillæg, Fraværsoversigt og Vagtplan.

   **Opdateret 2026-08-24:** Lønkørsel (preview, prøvekørsel, CSV-eksport og
   PDF-timesedler) medtager nu KUN medarbejdere med mindst én synlig
   disponentgruppe — samme regel som aktivitetsoversigten. Dette er en
   bevidst ændring af den oprindelige beslutning fra 2026-08-21, hvor
   Lønkørsel/CSV/PDF udtrykkeligt IKKE skulle påvirkes. Fraværsoversigt og
   Vagtplan er fortsat upåvirkede og viser alle aktive medarbejdere.

**Forudsætning før udrulning:** medarbejder 34362 (Magne Sørensen) har i dag
ingen disponentgruppe og ville blive skjult fra aktivitetsoversigten med det
samme. Han tildeles disponentgruppen "2 - Kran" som en del af implementeringen
(via den normale medarbejder-opdaterings-mekanisme, så det fremgår af
audit-loggen som en almindelig medarbejderredigering).

## Arkitektur

**Ingen ændring af `/api/activities` eller `/api/employees`** — disse bruges
af mange andre visninger og skal fortsætte med at returnere alt. Filtreringen
foretages udelukkende i frontend (`app.js`), i de tre funktioner der allerede
bygger aktivitetsoversigten:

- `fillDispatcherGroupFilter()` — afdelings-dropdown
- `fillEmployeeFilter()` — medarbejder-dropdown
- `renderActivitiesTable()` — selve gitterets rækker (`emps`-listen)

Dette holder ændringen isoleret til aktivitetsoversigten uden at skulle
tilføje et nyt query-parameter, der skal trækkes igennem alle andre kaldere.

### Datamodel

`dispatcher_groups`-tabellen får en ny kolonne:

```
visible_in_activity_overview BOOLEAN NOT NULL DEFAULT 1
```

Migreres i `session.py: _migrate()` efter det etablerede mønster (tjek
`PRAGMA table_info`, `ALTER TABLE ... ADD COLUMN ... DEFAULT 1` hvis kolonnen
ikke findes).

### Schemas

`DispatcherGroupResponse` (schemas.py) får feltet
`visible_in_activity_overview: bool = True`. Da denne response bruges begge
steder — `/api/stamdata/dispatcher-groups` (admin-CRUD) OG
`/api/employees/dispatcher-groups` (letvægts-liste til aktivitetsoversigtens
filtre) — kræver det ingen ekstra endpoint.

### Backend — Stamdata CRUD (`stamdata.py`)

- `DispatcherGroupBody` får `visible_in_activity_overview: Optional[bool] = None`.
- `create_dispatcher_group`: sætter `True` som default hvis feltet ikke er
  angivet i body.
- `update_dispatcher_group`: opdaterer feltet hvis angivet (samme mønster som
  `name`/`description`).
- `_dispatcher_group_row()`: medtager feltet i responsen.
- Kræver samme `stamdata`-tilladelse som resten af disponentgruppe-CRUD'en —
  ingen ny permission.

### Frontend — Stamdata-fanen

- Tabellen "Disponentgrupper" (index.html, `sd-pane-dispatcher`) får en ny
  kolonne "Vis i aktivitetsoversigt" med et Ja/Nej-badge (samme visuelle
  mønster som `include_in_csv` på løntypekoder).
- Modal `modal-stamdata-dispatcher` får et checkbox-felt (samme opbygning som
  de øvrige checkbokse i Stamdata-modalerne), krydset som default ved
  oprettelse af ny gruppe.
- `loadStamdataDispatcherGroups()`, `openStamdataDispatcherModal()` og
  `confirmStamdataDispatcher()` udvides til at læse/skrive det nye felt.

### Frontend — Aktivitetsoversigten

Ny lille hjælpefunktion, fx `_empHasVisibleGroup(emp)`, der slår op i
`state.dispatcherGroups` (som allerede indeholder synlighedsflaget efter
schema-udvidelsen) og returnerer `true` hvis mindst én af `emp`'s grupper har
`visible_in_activity_overview === true`. Medarbejdere uden grupper giver
`false`.

- `fillDispatcherGroupFilter()`: filtrerer `state.dispatcherGroups` til kun
  synlige grupper, før dropdown-listen bygges.
- `fillEmployeeFilter()`: `visible`-listen filtreres yderligere med
  `_empHasVisibleGroup(e)`.
- `renderActivitiesTable()`: `emps`-listen (linje ~303) filtreres yderligere
  med `_empHasVisibleGroup(e)`, efter det eksisterende `e.active`-filter.

## Ikke i scope

- Ingen ændring af Fraværsoversigt, Vagtplan eller medarbejderlisten i
  Stamdata — disse viser fortsat alle aktive medarbejdere uanset
  disponentgruppe-synlighed.
- Ingen personlig/bruger-specifik indstilling — kun den globale Stamdata-flag.
- Ingen mulighed for midlertidigt at "vise skjulte grupper alligevel" via
  filteret — det kræver at gå ind i Stamdata og slå gruppen til igen.

(Se opdateringen 2026-08-24 ovenfor: Lønkørsel/CSV/PDF er IKKE længere
undtaget — de filtreres nu på samme måde som aktivitetsoversigten.)
