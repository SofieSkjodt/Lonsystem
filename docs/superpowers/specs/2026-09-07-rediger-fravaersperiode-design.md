# Rediger fraværsperiode (fra/til-dato)

## Baggrund

I aktivitetsoversigten og vagtplanen kan man i dag oprette et fravær over en periode
(fx en uges ferie). Det opretter én uafhængig `Activity`-række pr. hverdag i perioden
(`confirmManualActivity()`s `isRange`-gren i `app.js`) – der er ingen kobling mellem
dagene i databasen. Det betyder at en oprettet periode i dag kun kan rettes dag for
dag: man kan ikke ændre periodens start- eller slutdato som én handling.

Denne ændring gør det muligt at redigere en fraværsperiodes fra/til-dato samlet,
mens de enkelte dage stadig oprettes/vises/tælles som individuelle aktiviteter, præcis
som i dag.

## Omfang

- Gælder kun de eksisterende periode-typer (`_RANGE_TYPES` i `app.js`): `ferie`,
  `feriefri`, `barsel`, `sygdom`, `paragraf_56_syg`, `graviditetsbetinget_sygdom`,
  `skole_kursus`, `afspadsering`.
- Gælder kun perioder oprettet EFTER denne ændring. Allerede oprettede
  fraværsperioder (før ændringen) har intet gruppe-id og kan derfor fortsat kun
  redigeres dag for dag, som i dag – der laves ingen datamigrering, der gætter
  gruppering af gamle sammenhængende dage.
- Gælder både Aktivitetsoversigten og Vagtplanen, da begge bruger samme
  opret-/rediger-modal (`modal-manual-activity` / `modal-activity`).

## Datamodel

Nyt felt på `Activity`: `absence_group_id` (String(36), nullable, indekseret).

- Sættes KUN når en flerdags-periode oprettes (dvs. `isRange`-grenen i
  `confirmManualActivity()`, når "Til dato" er udfyldt for en af periode-typerne).
  Frontend genererer ét fælles UUID (`crypto.randomUUID()`) FØR løkken over
  periodens hverdage, og sender det samme værdi med i hver enkelt
  `POST /api/activities`-kald for perioden.
- Enkeltdags-aktiviteter (inkl. enkeltdags "periode" hvor "Til dato" ikke er
  udfyldt) får IKKE et gruppe-id (`null`).
- Migration: idempotent kolonnetilføjelse i `session.py`s `_migrate()`, samme
  mønster som de øvrige `activities`-kolonner (`PRAGMA table_info` + `ALTER TABLE
  ADD COLUMN` hvis kolonnen mangler).
- Nyt index (`ix_activities_absence_group`) på `absence_group_id`, da opslag sker
  pr. gruppe-id.

## Backend

### Schemas (`schemas.py`)
- `ActivityCreate.absence_group_id: Optional[str] = Field(default=None, max_length=36)`
- `ActivityResponse.absence_group_id: Optional[str] = None`

### `create_manual_activity` (`activities.py`)
Gemmer `body.absence_group_id` uændret på den nye `Activity`-række (ingen
server-side generering – frontend styrer det, da flere separate POST-kald skal
dele samme værdi).

### Nyt: `GET /api/activities/absence-group/{group_id}`
Returnerer alle aktiviteter med det angivne `absence_group_id`, sorteret efter
`start_time`. 404 hvis gruppen er tom. Bruges af frontend til at hente hele
gruppen (kan strække sig over flere lønperioder end den der aktuelt vises), så
"Fra dato"/"Til dato" kan udfyldes korrekt uanset hvilken periode brugeren har
åbnet aktivitetsoversigten i.

### Nyt: `PATCH /api/activities/absence-group/{group_id}`
Body: `{ new_start_date: date, new_end_date: date }`.

1. Henter alle aktiviteter i gruppen. 404 hvis tom. 400 hvis `new_end_date <
   new_start_date`.
2. Udleder fra en vilkårlig eksisterende række i gruppen: `employee_id`,
   `activity_type`, `vehicle_number`, `terminsdato` (hvis relevant for typen),
   `comment`, `source`.
3. Beregner ny hverdags-dato-liste (mandag–fredag, samme filter som
   `getWeekdayDates()` i `app.js`) for `[new_start_date, new_end_date]`. 400 hvis
   listen er tom ("Ingen hverdage i den valgte periode").
4. Diff mod eksisterende dage (nøgle: `start_time.date()`):
   - **Uændrede dage** (findes i begge lister): rører IKKE aktiviteten.
   - **Fjernede dage** (findes i eksisterende, ikke i ny liste): for hver, slås
     aktivitetens `pay_period` op. Er `status == closed`, afvises HELE kaldet
     med 400 (ingen delvis anvendelse) og fejlbeskeden navngiver den blokerende
     dato ("Kan ikke fjerne {dato} – lønperioden er allerede afsluttet").
     Ellers slettes aktiviteten permanent (samme semantik som eksisterende
     `DELETE /api/activities/{id}`), UANSET om den er `pending`, `approved`
     eller `deactivated`. `log_action` pr. sletning, samme besked-mønster som
     den eksisterende delete-endpoint.
   - **Tilføjede dage** (findes i ny liste, ikke i eksisterende): opretter nye
     `Activity`-rækker med:
     - Samme klokkeslætslogik som `confirmManualActivity()`s `isRange`-gren i
       dag: `afspadsering` bruger medarbejderens skemalagte timer for
       ugedagen og SPRINGER dagen over hvis 0 timer er skemalagt (samlet i en
       `skipped`-liste i svaret); øvrige typer (undtagen `feriefri`, som altid
       bruger 7,4 t) bruger skemalagte timer hvis > 0, ellers 7,4 t fallback.
       Starttidspunkt er altid `06:00`.
     - `vehicle_number`/`terminsdato`/`comment` kopieret fra søskende-dagene
       (trin 2).
     - `pay_period_id` sat via `get_billing_period()` (samme sen
       registrerings-logik som almindelig oprettelse).
     - `status = approved`, `approved_by`/`approved_at` sat med det samme
       (matcher nuværende adfærd: alle fraværstyper auto-godkendes ved
       oprettelse).
     - `absence_group_id` = samme gruppe-id.
5. Alt sker i én DB-transaktion (alt-eller-intet – valideringen af fjernede
   dage i trin 4 sker FØR nogen sletning/oprettelse udføres).
6. Returnerer den opdaterede liste af gruppens aktiviteter (samme form som
   GET-endpointet) plus en evt. `skipped`-liste (datoer sprunget over pga. 0
   skemalagte timer).

Ingen ny rettighed indføres – samme åbne adgang (`get_current_user`) som resten
af aktivitets-endpoints, i tråd med at oprettelse/redigering af aktiviteter i
dag ikke er rettighedsbelagt ud over login.

## Frontend (`app.js` + `index.html`)

### `openActivityDetail(id)`
Har den åbnede aktivitet et `absence_group_id`, indsættes en ny sektion øverst i
`modal-activity-body` (over det eksisterende detail-grid): "Fraværsperiode" med
to date-pickers ("Fra dato"/"Til dato", udfyldt fra gruppens min/max
`start_time.date()` – hentet via `GET /api/activities/absence-group/{id}` når
modalen åbnes) og en dedikeret "Gem periodedatoer"-knap. Den eksisterende
"Ret starttid"/"Ret sluttid" for selve dagen forbliver uændret nedenunder, til
finjustering af klokkeslæt for netop den enkelte dag.

### Gem periodedatoer (ny funktion, fx `saveAbsencePeriodDates()`)
1. Læser de to date-pickers, validerer `til >= fra`.
2. Beregner lokalt hvilke datoer der forsvinder/tilføjes (diff mod de hentede
   gruppe-aktiviteter), og viser en `window.confirm`-dialog der lister præcis
   hvilke datoer der slettes permanent og hvilke der oprettes (sletning er
   irreversibel) – samme stil som det eksisterende overlap-advarselsmønster.
3. For de nye datoer: genbruger det eksisterende overlap-tjek (samme som i
   `isRange`-grenen i dag) og viser samme advarsel hvis en ny dag overlapper en
   kørselsaktivitet.
4. Ved bekræftelse: kalder `PATCH /api/activities/absence-group/{id}`, viser
   evt. "sprunget over"-toast for afspadsering-dage uden skemalagte timer,
   kalder `refreshActivities()`/`loadVagtplan()` (afhængig af visning) og
   lukker modalen.

### Opret-flow (`confirmManualActivity()`)
`isRange`-grenen genererer `crypto.randomUUID()` én gang før løkken og sender
denne værdi som `absence_group_id` i hvert `POST /api/activities`-kald for
perioden.

Vagtplan-visningen bruger samme modal/kode – ingen særskilt håndtering
nødvendig.

## Ikke omfattet
- Ingen tilbagevirkende gruppering af allerede oprettede fraværsperioder.
- Ingen ændring af den eksisterende enkeltdags-redigering (klokkeslæt på én
  bestemt dag i perioden fungerer som i dag, uafhængigt af periode-redigeringen).
- Ingen ny rettighed/permission.
