# Design: Vagtplan-fane

**Dato:** 2026-08-21
**Status:** Godkendt til implementeringsplan
**Kildekrav:** "Vagtplan i PS Løn.docx" (projektets rod)

## Baggrund

Vagtplanen er i dag et Excel-ark der viser alle medarbejdere, alle datoer,
ugenummer og indtastet fravær/kommentarer (farvekodet pr. fraværstype). Det
skal genskabes som en ny fane "Vagtplan" i systemet, visuelt placeret under
"Fraværsoversigt" i sidebaren. Griddet skal ligne Aktivitetsoversigten, men:

- Der laves ikke lønberegning i Vagtplan.
- Der tilføjes en ugenummer-header-række.
- Excel-arkets kolonne A (afdeling) og række 1 (farvelegende) genskabes ikke.
- Disponentgruppe-filteret skal kunne vælge flere grupper på samme tid
  (multi-select) i stedet for kun én.
- Man skal ved klik i en celle kunne tilføje fraværstype (som i
  Aktivitetsoversigten) ELLER en fritekst-kommentar uden fraværstype.
- Fravær registreret i Vagtplan skal slå igennem i Aktivitetsoversigten med
  "Oprettet af" = "Vagtplan". Deaktivering derfra skal kunne trigge en
  popup om, hvorvidt indtastningen også skal skjules i Vagtplan.
- Alle roller skal kunne se/redigere Vagtplan i dag; der skal kunne skelnes
  mellem "redigér egen linje" og "redigér alle linjer", og der skal kunne
  oprettes en rolle der kun har adgang til Vagtplan.
- En "Fravær i morgen"-knap skal vise en liste over medarbejdere med
  fravær/kommentar i morgendagens celle.

## Beslutninger (afklaret med bruger, 2026-08-21)

1. **Bruger↔medarbejder-kobling:** matches på initialer. `employees` får et
   nyt, valgfrit `initials`-felt (redigeres i medarbejder-modalen). Matches
   mod det eksisterende `app_users.initials`. Medarbejdere uden udfyldte
   initialer kan kun redigeres af en bruger med "redigér alle linjer".
2. **Kilde-markering:** `ActivitySource`-enum udvides med `vagtplan`.
   "Oprettet af" i Aktivitetsoversigten viser teksten "Vagtplan" når
   `source == vagtplan`, i stedet for initialer/"System". `created_by`
   bevares stadig som den faktiske brugers initialer (audit).
3. **Kommentar-datamodel:** kommentarer uden fraværstype gemmes i en ny,
   selvstændig tabel `vagtplan_comments` — ikke som en Activity, og vises
   derfor ikke i Aktivitetsoversigten.
4. **Deaktiveret visning i Vagtplan:** en deaktiveret Vagtplan-aktivitet
   vises som udgangspunkt stadig i griddet, men gråtonet — matcher hvordan
   deaktiverede aktiviteter typisk vises i systemet. Et ekstra valg i
   deaktiver-modalen ("Slet også indtastningen i Vagtplan?") kan i stedet
   skjule den helt fra Vagtplan-griddet (uden at slette databaserækken).
5. **Periodemodel:** Vagtplan er IKKE bundet til lønperioder (14 dage).
   Den navigerer i frie kalender-uger, 4 uger (28 dage) ad gangen;
   frem/tilbage flytter 4 uger.
6. **Klik-interaktion:** genbruger den eksisterende "Opret
   aktivitet"-modal (samme som Aktivitetsoversigtens klik-på-tom-celle,
   `openManualActivityModal(empId, dateIso)`), udvidet med et ekstra,
   Vagtplan-specifikt kommentarfelt og en "Ingen (kun kommentar)"-valgmulighed
   i fraværstype-dropdownen.
7. **Rettighedsstruktur:** tre nye permissions — `vagtplan_view`,
   `vagtplan_edit_own`, `vagtplan_edit_all` — i stedet for kun to. Giver mest
   granularitet i rolle-UI'en.
8. **"Fravær i morgen":** altid reel kalenderdag (dags dato + 1), uafhængigt
   af hvilken 4-ugers periode der aktuelt er navigeret til i griddet.
9. **Teknisk tilgang:** griddet bygges efter samme mønster som
   Aktivitetsoversigten (client-side sammenkædning af `/api/activities`,
   `/api/employees`, `/api/employees/dispatcher-groups`) i stedet for et nyt,
   samlet backend-endpoint. Kun nye, små tilføjelser til backend (se nedenfor).

## Arkitektur

### A. Datamodel

**`employees`:**
- Nyt felt `initials` (String, nullable). Redigeres i medarbejder-modalen.

**`activities`:**
- `ActivitySource`-enum: `tachograph`, `manual`, **`vagtplan`** (ny).
- Nyt felt `hidden_from_vagtplan` (Boolean, default `false`). Sættes til
  `true` via deaktiver-popup'ens ekstra valg; nulstilles automatisk ved
  `reopen`.

**Ny tabel `vagtplan_comments`:**
| Felt | Type | Bemærk |
|---|---|---|
| id | Int PK | |
| employee_id | Int FK → employees | |
| date | Date | |
| text | String | |
| created_by | String(10) | Initialer |
| created_at | DateTime | server_default now |

Unikt indeks på `(employee_id, date)` — én kommentar pr. medarbejder pr. dag.
Uafhængig af `activities`; vises kun i Vagtplan.

### B. Backend / API

**Nye permissions** (`auth.py: ALL_PERMISSIONS`): `vagtplan_view`,
`vagtplan_edit_own`, `vagtplan_edit_all`. Migreres ind på ALLE eksisterende
roller ved opstart (samme mønster som `_ensure_activity_permissions()` i
`session.py`), så nuværende brugere ikke mister adgang.

**`/api/activities`:**
- `source` sættes i dag hardkodet server-side til `manual` i
  `create_manual_activity` — der findes intet `source`-felt på
  `ActivityCreate`. Tilføjes: `ActivityCreate.source: Optional[str] = None`
  (kun `"vagtplan"` er en gyldig klient-angivet værdi, alt andet falder
  tilbage til nuværende `manual`-hardkodning — forhindrer at en klient kan
  forfalske `source: "tachograph"`).
- Det eksisterende `ActivityCreate.comment`-felt er noget andet (en fritekst
  knyttet til selve aktiviteten) og genbruges ikke til Vagtplan-kommentarer —
  de er som beskrevet en helt separat tabel.
- `ActivityResponse` inkluderer `hidden_from_vagtplan`.
- Nyt endpoint `POST /api/activities/{id}/hide-from-vagtplan` (body: `{hidden: bool}`)
  — kræver samme ret som deaktivering. `reopen`-endpointet nulstiller feltet
  til `false`.
- Redigering/oprettelse fra Vagtplan-konteksten valideres server-side mod
  `vagtplan_edit_own`/`vagtplan_edit_all` (i stedet for de almindelige
  aktivitets-rettigheder) — `vagtplan_edit_all` altid tilladt;
  `vagtplan_edit_own` kun tilladt hvis `employee.initials == current_user.initials`.

**Nyt router-modul `vagtplan_comments.py`:**
- `GET /api/vagtplan-comments?from=&to=` — kræver `vagtplan_view`.
- `POST /api/vagtplan-comments` — upsert på `(employee_id, date)`, kræver
  `vagtplan_edit_own` (egen linje) eller `vagtplan_edit_all`.
- `DELETE /api/vagtplan-comments/{id}` — samme rettighedskrav som POST.

**`employees.py`:** `EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse`
udvides med `initials`.

### C. Frontend — grid, filtre, navigation

- Ny sidebar-fane "Vagtplan" (LØN-sektion, mellem "Fraværsoversigt" og
  "REGISTRE"), gated bag `vagtplan_view` (`data-perm-require`-mønster).
- `renderVagtplanTable()` (ny funktion, app.js) — samme grid-opbygning som
  `renderActivitiesTable()`, men:
  - 28 dage i stedet for 14.
  - Ekstra header-række med ugenummer (spænder 7 kolonner pr. uge).
  - Ingen afdelings-kolonne.
  - Frem/tilbage-knapper flytter 4 uger; en "I dag"-knap springer til
    perioden der indeholder dags dato.
- Medarbejder-filter: som i dag.
- Disponentgruppe-filter: multi-select (checkboxes i dropdown), alle grupper
  valgt som default. Kun i Vagtplan — Aktivitetsoversigtens eksisterende
  enkelt-select filter er upåvirket.
- Intet statusfilter.
- Celleindhold: fraværsbadge (farvet som i Aktivitetsoversigten, gråtonet
  hvis `status == deactivated`), evt. kommentar-tekst uden farve/badge.
  Begge kan vises samtidig i samme celle.

### D. Klik-interaktion

- Klik på tom celle → `openManualActivityModal(empId, dateIso, {vagtplan: true})`.
  I Vagtplan-kontekst:
  - Fraværstype-dropdown får en ekstra valgmulighed "Ingen (kun kommentar)"
    i toppen.
  - Et nyt, valgfrit kommentar-textarea vises altid.
  - Vælges en rigtig fraværstype: opretter Activity (`source: "vagtplan"`)
    som i dag; er kommentarfeltet også udfyldt, upsertes samtidig en
    `vagtplan_comments`-række for startdatoen.
  - Vælges "Ingen (kun kommentar)": ingen Activity oprettes, kun
    kommentaren gemmes (kommentarfeltet er da obligatorisk).
- Klik på celle med eksisterende fraværsaktivitet → almindelig
  aktivitetsdetalje-modal (uændret fra Aktivitetsoversigten).
- Klik på celle med kun en kommentar → let redigér/slet-dialog for
  kommentaren.

### E. Sammenspil med Aktivitetsoversigt

- "Oprettet af" viser "Vagtplan" for aktiviteter med `source == vagtplan`.
- Deaktiver-modalen (`modal-deactivate`) får et ekstra checkbox-valg "Slet
  også indtastningen i Vagtplan?" når den deaktiverede aktivitet har
  `source == vagtplan`:
  - Nej (default): aktiviteten forbliver synlig i Vagtplan-griddet, men
    gråtonet.
  - Ja: `POST /{id}/hide-from-vagtplan` med `hidden: true` — aktiviteten
    forsvinder fra Vagtplan-griddet; databaserækken/løn-historikken er
    upåvirket.
- `reopen` nulstiller `hidden_from_vagtplan` til `false`.

### F. Roller & rettigheder

- Se afsnit B. Den efterspurgte "rolle der kun kan se/redigere Vagtplan"
  kræver ingen ny kode — allerede muligt via eksisterende rolle-administration
  (opret rolle, tildel kun `vagtplan_view` + ønsket edit-ret).

### G. "Fravær i morgen"-knap

- Knap i Vagtplan-toolbaren. Henter fravær-aktiviteter og kommentarer for
  reel dags dato + 1 (uafhængigt af den aktuelt viste 4-ugers periode).
- Modal med simpel liste: navn (kolonne 1), fraværstype/kommentar-tekst
  (kolonne 2). Medarbejdere uden fravær/kommentar i morgen udelades.

## Ikke i scope

- Ingen lønberegning eller godkend/deaktiver-flow i selve Vagtplan-griddet
  (sker fra Aktivitetsoversigten som i dag).
- Ingen ændring af Aktivitetsoversigtens eksisterende enkelt-select
  disponentgruppe-filter.
- Ingen kobling til den verserende, endnu ikke implementerede
  "disponentgruppe-synlighed"-funktion (`visible_in_activity_overview`) —
  den er scopet specifikt til Aktivitetsoversigten.
- Ingen selvstændig historik-visning for Vagtplan-ændringer ud over den
  eksisterende audit-log.
