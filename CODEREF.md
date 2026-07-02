# PS Løn – Kode-referenceguide (token-optimeret)

## Stack
FastAPI + SQLite (WAL) + vanilla HTML/JS.  
**Daglig drift:** `cd app && uvicorn main:app --host 0.0.0.0 --port 8000`  
**Under udvikling:** `cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload` (auto-genstart ved .py-ændringer)  
Ændringer i `.py`-filer kræver servergenstart. Ændringer i `app.js`/`style.css`/`index.html` træder i kraft ved browser-reload (cache-busting via `app_js_mtime`).  
CVR: læses altid fra Stamdata → CVR-nummer (MasterCvrNumber). Lønperiode: faste 14-dage (start beregnet fra dato).  
Auth: SessionMiddleware (session-cookie, 1 dag). Seed-admin: initialer=`admin`, adgangskode=`admin` (skift ved første login).

---

## Filer
```
app/
  main.py                      # FastAPI app, SessionMiddleware, router-inkludering, cache-busting
  auth.py                      # hash_password, verify_password, get_current_user, require_roles, log_action
  database/
    models.py                  # SQLAlchemy-modeller inkl. AppUser, AuditLog, UserRole
    schemas.py                 # Pydantic-skemaer (ActivityApprove/Deactivate har IKKE approved_by – fra session)
    session.py                 # get_db(), init_db() (seeder ADM-admin hvis ingen brugere)
  routers/
    auth.py                    # POST /api/auth/login, /logout; GET /api/auth/me
    users.py                   # /api/users CRUD + /api/users/audit-log (admin-only)
    roles.py                   # /api/roles CRUD (admin-only); dynamisk rollestyring
    activities.py              # /api/activities (CRUD + godkend/deaktiver/split/absence-types) – alle roller
    employees.py               # /api/employees (CRUD + anciennitet-alerts + dismiss + agreement-types) – alle roller
    payroll_router.py          # /api/payroll (preview, prøvekørsel, CSV, PDF) – admin+lonbogholder
    absence_overview_router.py # /api/absence-overview (data, export-per-employee, export-per-type) – absence_overview perm
    timeseddel_router.py       # /api/timesedler – timeseddel-eksport pr. medarbejder
    stamdata.py                # /api/stamdata – CVR-numre, løntypekoder, overtidssatser, helligdage (admin)
    vehicles.py                # /api/vehicles – alle roller
    import_ddd.py              # /api/import-ddd-from, browse-ddd-* – admin+lonbogholder
    auto_approval_router.py    # POST /api/auto-approval/rebuild-baselines, GET /baseline-summary (manage_baselines perm)
  calculators/
    overtime.py                # calculate_overtime() → OvertimeResult
    pay_period.py              # get_or_create_period_for_date(), is_even_week()
    rates_loader.py            # load_agreement_types/overtime_rates/salt_supplement_rate()
    pay_rates.py               # DANLOEN_CODE_* konstanter (NORMAL/OT_*/SALT/AFSPADSERING/SYGDOM/PARAGRAF_56/BARN_1SYGEDAG – "1" placeholder, DB-værdier er authoritative)
    day_type.py                # Dag-klassifikation og lønberegning for lørdage, søndage og helligdage (SH-betaling)
    holidays.py                # easter_date() + danish_holidays(year) – genererer helligdage via Computus
    auto_approval.py           # should_auto_approve(activity, db) → (bool, list[str]); MIN_SAMPLES=5
    baseline_updater.py        # update_baseline_from_activity(), rebuild_baselines_for_employee()
  parsers/ddd_parser.py        # .ddd-filparsing
  templates/index.html         # Eneste HTML-side (alle modaler herinde)
  static/
    js/app.js                  # Al frontend-logik (~3100 linjer)
    css/style.css              # Styling

# Excel-filer i app/ (læses uden genstart):
app/Fraværstyper.xlsx          # Kolonne A, række 2+ → fraværstyper
app/Overenskomsttyper og timesatser.xlsx  # Kol A=navn, B=timesats
app/Overtid satser.xlsx        # Kol A=navn, B=sats (3 rækker)
app/Salttillæg.xlsx            # Celle B1 = salttillæg pr. time
```

---

## DB-modeller (models.py)

### Employee (tabel: employees)
| Felt | Type | Bemærk |
|---|---|---|
| employee_number | String | Lønnummer, unik |
| tachograph_card_number | String nullable | Førerkortnummer |
| agreement_kind | Enum(hourly_fixed/hourly_flexible) | |
| agreement_type | String | Fra Excel-ark |
| work_schedule | JSON | `{"even":[0..6],"odd":[0..6]}` timer man-søn |
| dispatcher_group | String nullable | Afdeling |
| hire_date / termination_date | Date | Ansættelses-/slutdato |

### Activity (tabel: activities)
| Felt | Type | Bemærk |
|---|---|---|
| activity_type | String(50) | "normal" eller normaliseret fraværstype-streng |
| status | Enum(pending/approved/deactivated) | |
| approved_by | String | Initialer – kun ved godkendelse |
| approved_at | DateTime | |
| deactivated_by | String nullable | Initialer – kun ved deaktivering (legacy: falder tilbage til approved_by) |
| salt_supplement | Boolean | |
| pause_intervals | JSON | `[["ISO","ISO"],...]` |
| segments | JSON | `[["ISO","ISO","type"],...]` |
| parent_activity_id / split_part | Int | Split-relation |
| vehicle_registration | String | Nummerplade (fx DF67671) |
| vehicle_number | String | Vognnummer |

### Øvrige
- **PayPeriod**: start_date, end_date, status(open/preview/closed)
- **Vehicle**: registration_number (nummerplade), vehicle_number (vognnr)
- **PayrollRun**: pay_period_id, run_type, csv_path, excel_path

### EmployeeBaseline (tabel: employee_baselines)
| Felt | Type | Bemærk |
|---|---|---|
| employee_id | Int FK | |
| weekday | Int | 0=mandag…6=søndag |
| sample_count | Int | Antal godkendte aktiviteter |
| duration_mean_minutes | Numeric | Welford mean |
| duration_m2_minutes | Numeric | Welford M2 (til std-beregning: sqrt(M2/n)) |
| start_hour_mean | Numeric | Starttid som float-timer (7.5 = 07:30) |
| start_hour_m2 | Numeric | Welford M2 |
| salt_count | Int | Antal aktiviteter med salttillæg |

---

## API-endpoints

### /api/activities
| Method | Sti | Beskrivelse |
|---|---|---|
| GET | / | Liste (period_start?, employee_id?) |
| POST | / | Opret manuel aktivitet |
| GET | /period-info | Stats + prev/next periode |
| GET | /absence-types | Fra Fraværstyper.xlsx → [{value,label}] |
| GET | /{id} | Hent én |
| PATCH | /{id} | Rediger |
| POST | /{id}/approve | Body: {approved_by, comment?} |
| POST | /{id}/deactivate | Body: {deactivated_by, comment?} |
| POST | /{id}/reopen | Sæt pending, nulstil approved_* |
| POST | /{id}/split | Body: {split_at: ISO}; begge dele → pending |
| POST | /{id}/undo-edit | Gendan originale tider |
| POST | /{id}/undo-split | Slet children, gendan forælder |
| POST | /auto-approve-pending | Auto-godkend egnede pending-aktiviteter i periode |

### /api/employees
| Method | Sti | Beskrivelse |
|---|---|---|
| GET | / | active_only=true |
| POST | / | Opret |
| PATCH | /{id} | Rediger |
| GET | /agreement-types | [{name, hourly_rate}] fra Excel |
| GET | /anciennitet-alerts | Medarbejdere med ≥9 mdr der mangler variant |

### /api/auto-approval
| Method | Sti | Beskrivelse |
|---|---|---|
| POST | /rebuild-baselines | Genbyg baselines fra historik (manage_baselines) |
| GET | /baseline-summary | Oversigt over baseline-status per medarbejder |

### /api/payroll
| Method | Sti | Beskrivelse |
|---|---|---|
| GET | /preview | JSON til lønkørsel-siden |
| GET | /proevekoersel | Excel-fil download |
| POST | /proevekoersel-gem | Gem Excel til mappe |
| POST | /export-csv | Danløn CSV |
| POST | /pdf-timesedler | Dan PDF'er (A4 landscape) |

---

## Schemas (schemas.py) – vigtige
```python
ActivityDeactivate: comment: Optional[str]           # deactivated_by hentes fra session (current_user.initials)
ActivityApprove:    comment: Optional[str]            # approved_by hentes fra session
ActivitySplit:      split_at: datetime
AnciennitetsAlert:  employee_id, employee_name, hire_date, months_employed, suggested_agreement_type
```
**OBS:** `ActivityCreate.activity_type`, `ActivityResponse.activity_type` og `ActivityUpdate.activity_type` er `str` (ikke `ActivityType`-enum). `ActivityType`-enum i `models.py` bevares kun for bagudkompatibilitet; bruges ikke længere til sammenligning i routers. Ændringen muliggør alle dynamiske typer fra `Fraværstyper.xlsx`.

`ActivityCreate` indeholder `pause_intervals: list = Field(default_factory=list)` – sendes fra frontend som `[["ISO","ISO"],...]`. **Alle felter i Activity-modellen skal med i `ActivityCreate`/`ActivityUpdate`**, ellers dropper Pydantic dem stiltiende fra POST-body.

---

## Fraværstyper – normalisering (activities.py:27)
```python
_LABEL_OVERRIDES = {"Kursus/Skole": "skole_kursus"}  # bagudkompatibilitet
# Ellers: lowercase, æ→ae ø→oe å→aa, mellemrum//-/→_, dobbelt__ fjernes
_BACKEND_ONLY_TYPES = {"sygdom_u_8uger"}  # filtreres fra dropdown; tildeles automatisk
```
`ActivityType`-enum i models.py bevares for bagudkompatibilitet (sammenligning). `activity_type`-kolonnen er `String(50)`.

### Sygdom – anciennitetskontrol
`create_manual_activity`: hvis `activity_type == "sygdom"` og `(start_date − hire_date).days < 56` → konverteres til `"sygdom_u_8uger"` (sygdom uden løn).

### Fraværstyper.xlsx indeholder
`Sygdom`, `Sygdom u. 8 uger`, `Afspadsering`, `Ferie`, `§56 syg`, `Barn 1.sygedag`, `Barn 2-3.sygedag`, `Barsel`, `Barsel u. løn`, `Feriefri`, `Graviditetsbetinget sygdom`, `Kursus/Skole`, `Selvbetalt fridag`.

---

## JS – app.js nøglefunktioner

### State & konstanter (linje 5-21)
```js
state = { currentView, currentPeriodStart, periodInfo, activities, employees,
          vehicles, agreementTypes, absenceTypes, selectedActivityId, approvedBy }
TYPE_LABELS = { normal: "Normal tid" }  // + fraværstyper tilføjes dynamisk
ABSENCE_LABELS = {}   // value → UPPERCASE badge-tekst
ABSENCE_TYPES = new Set()  // populeres af loadAbsenceTypes()
```

### Init & data-load
| Funktion | Linje | Hvad |
|---|---|---|
| `init()` | 1594 | Startup: loadAbsenceTypes → loadAgreementTypes → setView |
| `loadAbsenceTypes()` | 810 | GET /absence-types → fylder TYPE_LABELS, ABSENCE_LABELS, ABSENCE_TYPES, #manual-type dropdown |
| `loadActivities()` | 126 | GET + renderActivitiesTable |
| `loadEmployees()` | 949 | GET + renderEmployeeList |
| `loadPayrollPreview()` | 1306 | GET /api/payroll/preview + render |
| `loadAgreementTypes()` | 1006 | Fylder state.agreementTypes |

### Aktiviteter
| Funktion | Linje | Hvad |
|---|---|---|
| `renderActivitiesTable()` | 138 | 14-dages grid-rendering |
| `renderCellActivity(a)` | 220 | Badge-HTML for én aktivitet i grid |
| `openActivityDetail(id)` | ~360 | Åbner modal-activity; Aktivitetsfordeling-bjælken beregner pause-% for manuelle aktiviteter uden segmentdata |
| `saveActivityTimes()` | 467 | PATCH tider |
| `quickApprove(id)` | 258 | Sætter selectedActivityId → openApproveModal |
| `quickDeactivate(id)` | 262 | Sætter selectedActivityId → openDeactivateModal |
| `quickReopen(id)` | 266 | POST /reopen direkte |
| `openApproveModal()` | 491 | Fylder #approve-by, åbner modal-approve |
| `confirmApprove()` | 500 | POST /approve |
| `openDeactivateModal()` | 535 | Fylder #deactivate-by, åbner modal-deactivate |
| `confirmDeactivate()` | 541 | POST /deactivate |
| `modalDeactivate()` | 531 | Fra modal → openDeactivateModal |
| `modalReopen()` | 553 | POST /reopen fra modal |
| `openSplitModal()` | 563 | Åbner modal-split |
| `confirmSplit()` | 581 | POST /split |
| `undoEdit()` | 447 | POST /undo-edit |
| `undoSplit()` | 457 | POST /undo-split |

### Manuel aktivitet
| Funktion | Linje | Hvad |
|---|---|---|
| `openManualActivityModal()` | ~1120 | Nulstiller form + manualPauses, sætter type=normal, åbner modal |
| `updateManualTypeVisibility()` | ~919 | Skjuler/viser felter afhængig af type; kalder defaults; skjuler pause-sektion for dato-kun-typer |
| `applyFerieDefaults()` | ~970 | Dato-kun, 06:00 + normaltimer (fallback 7,4 t) |
| `applySygdomDefaults()` | ~994 | Identisk med ferie; dato-kun |
| `applyAfspadseringDefaults()` | ~1014 | 06:00 + normaltimer (fallback 7,4 t); tidsfelter synlige |
| `confirmManualActivity()` | ~1200 | POST /api/activities inkl. pause_intervals |
| `renderManualPauses()` | ~1074 | Opdaterer #manual-pauses-list med tilføjede pauser + slet-knapper |
| `addManualPause()` | ~1087 | Validerer at starttid er sat; åbner modal-pause med korrekt titel og dato |
| `confirmPause()` | ~1100 | Læser pause-picker, validerer, tilføjer til manualPauses, lukker modal |
| `deleteManualPause(idx)` | ~1112 | Fjerner pause ved index og re-renderer listen |

**Dato-kun typer** (tidsfelter + sluttidsgruppe skjules): `ferie`, `sygdom`.  
**Heldagsstandard, redigerbar**: `afspadsering`.  
**Normal tid**: slutdato synkroniseres automatisk med startdato ved datoændring (kan tilsidesættes).  
**Pauser**: `let manualPauses = []` (modul-scope). Nulstilles ved åbning af modal. Medsendes som `pause_intervals` i POST. Fratrækkes i `_duration_minutes()` (backend) og lønberegning (via `_subtract_pauses()` i `overtime.py`).

### Medarbejdere
| Funktion | Linje | Hvad |
|---|---|---|
| `renderEmployeeList()` | 959 | HTML for medarbejderlisten |
| `openNewEmployeeModal()` | 1019 | Nulstiller form |
| `openEditEmployee(id)` | 1037 | Fylder form med eksisterende data |
| `confirmEmployee()` | 1064 | POST eller PATCH; auto-dismiss anciennitet hvis agreement_type ændres |
| `checkAnciennitetsAlerts()` | 1119 | GET /anciennitet-alerts; server filtrerer allerede dismissed; viser modal |
| `dismissAnciennitetsAlert(id)` | 1112 | POST /api/employees/{id}/dismiss-anciennitet (server-side, ikke localStorage) |

### Lønkørsel
| Funktion | Linje | Hvad |
|---|---|---|
| `renderPayrollPreview(data)` | 1316 | Bygger medarbejder-kort HTML |
| `payrollRow(label,hours,rate)` | 1371 | Én datatabelrække (4 kolonner: label/timer/sats/DKK) |
| `payrollRowSalt(label,hours,rate,kr)` | 1381 | Salt-rækken |
| `proevekoersel(employeeId)` | 1391 | Åbner mappe-modal |
| `exportCsv()` | 1429 | Åbner CSV-modal |
| `openPdfModal()` | 1496 | Åbner PDF-modal |

### Datetime-pickers
| Funktion | Linje | Hvad |
|---|---|---|
| `buildDatetimePicker(id, isoValue)` | 603 | Injecter dato+time-inputs i #id |
| `readDatetimePicker(id)` | 620 | → ISO-streng |
| `setDatetimePicker(id, isoValue)` | 631 | Sætter værdier |
| `buildDatePicker(id, val)` | 644 | Ren dato-picker |
| `setDatePicker(id, iso)` / `readDatePicker(id)` | 791/787 | |

### Format-hjælpere (linje 1551+)
```js
formatDate(iso)      // "15-06-2026"
formatTime(iso)      // "08:00"
formatDateTime(iso)  // "15-06-2026 08:00"
formatDuration(min)  // "8t 30m"
fmtHours(h)          // "8.50 t"
fmtKr(v)             // "1.234,56 kr"
statusLabel(s)       // "Afventer"/"Godkendt"/"Deaktiveret"
```

---

## HTML – vigtige modal-id'er og element-id'er

### Modaler
| id | Formål |
|---|---|
| modal-activity | Aktivitetsdetalje + rediger |
| modal-approve | Godkend (initialer + kommentar) |
| modal-deactivate | Deaktiver (initialer + kommentar) |
| modal-split | Split aktivitet |
| modal-manual-activity | Opret manuel aktivitet |
| modal-pause | Tilføj pause til manuel aktivitet (titel: "Pause N") |
| modal-employee | Opret/rediger medarbejder |
| modal-anciennitet | Anciennitetspåmindelse |
| modal-proevekoersel | Mappe-vælger til prøvekørsel |
| modal-export-csv | Mappe/periode til CSV |
| modal-pdf | Mappe-vælger til PDF |
| modal-admin | Genåbn lønperiode |

### Nøgle-inputs
| id | Formål |
|---|---|
| approve-by | Initialer i godkend-modal |
| approve-comment | Kommentar i godkend-modal |
| deactivate-by | Initialer i deaktiver-modal |
| deactivate-comment | Kommentar i deaktiver-modal |
| manual-type | Aktivitetstype-dropdown (opret) – "Normal tid" hardkodet, resten dynamisk |
| manual-pause-section | Div der indeholder pauseliste + "Tilføj pause"-knap (skjult for dato-kun-typer) |
| manual-pauses-list | Div med de tilføjede pauser (renderes af renderManualPauses) |
| pause-modal-title | h2 i modal-pause – sættes til "Pause 1", "Pause 2" osv. |
| pause-start / pause-end | dt-picker-divs i modal-pause (dato skjult, kun HH:MM vises) |
| edit-salt | Salttillæg checkbox (disabled hvis status ≠ pending) |
| filter-status | Statusfilter i toolbar |
| filter-employee | Medarbejderfilter |
| filter-dispatcher-group | Afdelingsfilter |
| period-label | Viser perioden |
| grid-head / grid-body | Aktivitetstabel |

---

## Brand-farver (CSS-variabler i style.css)
```css
--primary:       #317423   /* top-bar, payroll-header-baggrund */
--primary-dark:  #26631e
--accent:        #78b21a
--light-tint:    #d4edcc   /* payroll-col-header baggrund */
--danger:        rød
```

---

## Anciennitet – server-side dismiss
Gemmes i `employees.anciennitet_dismissed_at` (DateTime, nullable).  
`POST /api/employees/{id}/dismiss-anciennitet` sætter feltet til `utcnow()`.  
`GET /api/employees/anciennitet-alerts` springer medarbejdere over, hvor feltet ikke er `None`.  
Nulstilles automatisk på serveren, hvis `agreement_type` ændres via `PATCH /{id}`.  
Manuel dismiss: "Ændring foretaget"-knap (id: `btn-anciennitet-done`) → `dismissAnciennitetsAlert(id)` i app.js.

---

## DDD-import (parsers/ddd_parser.py)
Filens dato/minutter er **UTC** – konverteres til Europe/Copenhagen (DST-korrekt via `zoneinfo`) i `_build_activities` for start_time/end_time/segments/pause_intervals. Kræver `tzdata`-pakken (i requirements.txt – Windows har ingen egen IANA-tidszonedatabase).
**Kortnummer**: rå felt i filen er 16 tegn (`[A-Z]{2}\d{14}`), men kun de første 14 tegn (`driverIdentification`) er det stabile nummer til medarbejder-matching – sidste 2 cifre er udskiftnings-/fornyelsesindeks og ændrer sig ved kortfornyelse. `_extract_card_number()` matcher det fulde felt, returnerer kun de første 14 tegn.
**Dagsstart**: changes[0] er altid en hvil-post ved minut 0 (videreført status, ikke reel pause). Er der en ekstra hvil-post lige efter (før første arbejde/kørsel) er det chaufførens faktiske dagsstart – bruges som `day_start_minute` så en indledende kort pause vises i arbejdstiden (og i `pause_intervals`), men forbliver ubetalt.
**Skip-årsager**: `_import_activity()` returnerer `new`/`updated`/`skipped_unknown_card`/`skipped_duplicate` – tælles separat af `_process_import_results()` og logges som én `ddd_import`-hændelse (log_action) med fuld opsummering inkl. konkrete ukendte kortnumre. Frontend viser resultatet i `modal-import-result` (success-visning eller opdelt årsagsliste) i stedet for kun en toast. `scan_ddd_folder()` returnerer nu `(results, errors)` – parse-fejl ved mappescanning ryger i `errors` i stedet for kun `print()` til konsollen.
**Genimport af samme dag med mere komplet data**: Dedup matcher på `(employee_id, start_time, source=tachograph)`. Har en ny udlæsning et SENERE `end_time` end den eksisterende aktivitet (fx fordi kortet først blev downloadet midt på dagen og senere igen efter vagtens afslutning), udvides `end_time`/`segments`/`pause_intervals`/procentfelter i stedet for at blive sprunget over som duplikat. Var aktiviteten `approved`/`deactivated`, genåbnes den til `pending` (approved_by/approved_at/deactivated_by nulstilles) så den udvidede tid skal godkendes igen, før den tæller med i løn. Kun km-felterne blev opdateret ved duplikat før denne rettelse (2026-07-02) – resten af den nye tid gik tabt for altid ved delvise kortudlæsninger.
**Km-start/km-slut**: `_extract_daily_odometer()` finder en kæde af 20-byte (km, UTC-tidsstempel)-par (mindst 5 i træk, ingen fast offset) – tidsstemplet matcher dagens `day_start_minute`. `km_end = km_start + distance` (dagens egen activityDayDistance), IKKE næste tabelpost (håndterer køretøjsskift korrekt). Kortet gemmer kun et begrænset antal poster, så ikke alle dage har km-data. Erstatter den tidligere CardVehiclesUsed-baserede søgning, som byggede på en forkert byte-offset-antagelse.

---

## Danløn CSV-struktur (payroll_router.py)

Kolonner: `CVR ; medarbejdernr ; Danløn-kode ; timer ; sats`

Én række per type der har timer > 0:

| Danløn-kode | Indhold |
|---|---|
| DANLOEN_CODE_NORMAL | Normal tid |
| DANLOEN_CODE_OT_BEFORE | Overtid før |
| DANLOEN_CODE_OT_13 | Overtid 1-3 timer |
| DANLOEN_CODE_OT_EXTRA | Øvrig overtid |
| DANLOEN_CODE_SALT | Salttillæg |
| DANLOEN_CODE_AFSPADSERING | Afspadsering (medarbejderens timesats) |
| DANLOEN_CODE_SYGDOM | Sygdom med løn (medarbejderens timesats) |

**Ekskluderet fra CSV**: `ferie`, `sygdom_u_8uger`, `fri`, `skole_kursus` + alle øvrige fraværstyper.

`_calculate_employee()` returnerer `sygdom_hours` og `afspadsering_hours` separat i result-dict.

---

## Overtidsberegning (calculators/overtime.py)
```python
OT_BEFORE_KEY = "Overtid 1 time før"
OT_13_KEY     = "Overtid 1-3 timer efter"
OT_EXTRA_KEY  = "Øvrigt overtid"   # NB: med 't' (ikke 'g')
# calculate_overtime(start, end, normal_cap, pauses) → OvertimeResult
# .normal_hours = ALLE arbejdede timer (= total_hours); OT-felter er additive tillæg
# .ot_before_hours, .ot_13_hours, .ot_extra_hours, .total_hours
# pauses = [(datetime, datetime), ...] – fratrækkes via _subtract_pauses() FØR beregning
```
Semantik (v15+): `normal_hours = total_hours` (alle timer efter pausefradrag). OT-koder er supplement-tillæg oven på normaltidsløn, ikke erstatning.

**Loft deles pr. dag, ikke pr. aktivitet (2026-07-02):** `_calculate_employee()` i `payroll_router.py` initialiserer `day_normal_remaining`/`day_ot13_remaining` ÉN gang pr. kalenderdag (før løkken over `acts_today`) og videresender dem til `calculate_overtime()`/`calculate_special_day_overtime()` via `normal_remaining`/`ot13_remaining`/`kode8_remaining`-parametrene; resultatet indeholder `ot.normal_remaining_after`/`ot.ot13_remaining_after` til næste aktivitet samme dag. Uden dette bliver 7-timers normalloft og 3-timers OT13-loft nulstillet for hver aktivitet, hvilket underberegner Øvrigt overtid (kode 9), når én dag er delt i flere godkendte aktiviteter (fx efter split eller flere separat godkendte DDD-fragmenter).

**Registreret normaltid forbruges kun i 06-18 (2026-07-02):** Nat- (21-05), "1 time før"- (05-06) og aften-timer (18-21) fortærer IKKE det registrerede normaltids-loft (`normal_remaining`) – kun arbejde i 06-18-vinduet gør. De giver stadig deres eget tillæg (ot_before/ot_13/ot_extra) og tæller med i `normal_hours` (kode 1), men reducerer ikke hvor meget af 06-18-arbejdet der regnes som "ren" normaltid. Rettelsen ophæver den tidligere "Eksempel 1"-fortolkning i `docs/OVERTIME_RULES.md` (som var en fejllæsning af kravdokumentet, bekræftet af bruger) – se `_test_overtime.py` for opdaterede forventede værdier.

## Pausehåndtering (activities.py + overtime.py)
`_duration_minutes(a)` i `activities.py` fratrækker `pause_intervals` fra brutto-varighed → bruges til "Sum, effektiv tid" i UI og `is_under_4h`/`is_over_12h`.  
`_calculate_employee()` i `payroll_router.py` sender pauser til `calculate_overtime()` som `[(datetime, datetime), ...]` → `_subtract_pauses()` fjerner dem fra arbejdsintervallerne FØR timefordeling.  
Pauser oprettes manuelt via `modal-pause` (kun HH:MM, dato arves fra aktivitetens startdato). Gemt som `[["ISO","ISO"],...]` i `pause_intervals`-kolonnen.

---

## Vigtige mønstre

### Tilføj ny modal-knap-handling
1. HTML: tilføj knap i modal-footer med `onclick="minFunktion()"`
2. JS: skriv `async function minFunktion()` med `POST(...)` + `toast(...)` + `closeAllModals()` + `refreshActivities()`

### Tilføj nyt aktivitetsfelt
1. `models.py`: ny `Column`
2. `schemas.py`: tilføj til `ActivityResponse` + `ActivityCreate`/`ActivityUpdate`
3. `activities.py` `_to_response()`: map feltet
4. `index.html`: vis i modal-activity-body
5. `app.js`: rediger/opret-logik

### Genstart-frit (kun JS/HTML)
Ændringer i `app.js`/`style.css`/`index.html` kræver kun browser-refresh (cache-busting er aktiv).  
Ændringer i `.py`-filer: stop server, ryd `__pycache__`, genstart.
