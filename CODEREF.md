# PS Løn – Kode-referenceguide (token-optimeret)

## Stack
FastAPI + SQLite (WAL) + vanilla HTML/JS.  
**Daglig drift:** `cd app && uvicorn main:app --host 0.0.0.0 --port 8000`  
**Under udvikling:** `cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload` (auto-genstart ved .py-ændringer)  
Ændringer i `.py`-filer kræver servergenstart. `app.js` har automatisk cache-busting (`?v={{ app_js_mtime }}`, filens mtime) – ændringer træder altid i kraft ved reload. `style.css` og `index.html` har IKKE automatisk cache-busting: `style.css?v=N` i `index.html` er et manuelt versionsnummer der SKAL bumpes for hånd, hver gang `style.css` ændres, ellers kan browsere med gammel cache blive hængende på den gamle CSS (skete 2026-07-02: ny `.btn-muted`-regel virkede ikke i browseren, selvom JS-logikken var korrekt, fordi `?v=6` ikke var bumpet).  
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
    baseline_updater.py        # update_baseline_from_activity() – Welford update + downdate-dedup; rebuild_baselines_for_employee()
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
| dispatcher_groups | many-to-many via employee_dispatcher_groups | Se DispatcherGroup nedenfor – medarbejder kan have 0-N grupper |
| hire_date / termination_date | Date | Ansættelses-/slutdato |

### DispatcherGroup (tabel: dispatcher_groups) + EmployeeDispatcherGroup (join-tabel)
| Felt | Type | Bemærk |
|---|---|---|
| name | String unik | Fx "2 - Kran" |
| description | Text nullable | |
CRUD under Stamdata → "Disponentgrupper" (kræver `stamdata`-tilladelse). Lightweight read-only liste til dropdowns: `GET /api/employees/dispatcher-groups` (kun `get_current_user`). Medarbejder-modal bruger afkrydsningsbokse (`EmployeeCreate/Update.dispatcher_group_ids`), ingen primær gruppe. Historik: frem til 2026-07-27 lå dette som en enkelt `employees.dispatcher_group`-streng; migreret til many-to-many (kolonnen droppet, se `session.py: _migrate_dispatcher_groups`).

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
| auto_approved | Boolean | True hvis auto-godkendt |
| auto_approval_flags | JSON | Liste over afvisningsårsager (tom = godkendt) |
| baseline_duration_minutes | Numeric nullable | Varighed (min) der sidst blev bidraget til baseline (deduplication) |
| baseline_start_hour | Numeric nullable | Starttid (decimal timer) der sidst blev bidraget til baseline |

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
| GET | /{id} | Hent én |
| PATCH | /{id} | Rediger |
| GET | /agreement-types | [{name, hourly_rate}] fra Excel |
| GET | /dispatcher-groups | Alle disponentgrupper (kun `get_current_user`) – bruges til afkrydsningsboksene i medarbejder-modalen |
| GET | /anciennitet-alerts | Medarbejdere med ≥9 mdr der mangler variant |

`EmployeeCreate`/`EmployeeUpdate` bruger `dispatcher_group_ids: list[int]` (ikke længere en enkelt streng); `EmployeeResponse.dispatcher_groups` er en liste af `{id, name, description}`. Fuld CRUD på selve grupperne (opret/omdøb/slet) ligger under `/api/stamdata/dispatcher-groups` (kræver `stamdata`-tilladelse) – fane "Disponentgrupper" i Stamdata-viewet.

**Advarsel om mulig dublet ved oprettelse (app.js: `confirmEmployee`, kun ved `id` tom):** Før POST slås navn (for+efternavn, case-insensitive) og førerkortnummer op mod `GET /api/employees?active_only=false`. Navnesammenfald → `modal-emp-duplicate-warning` med to knapper: "Ændre" (luk advarslen, bliv i oprettelsesmodalen) og "OK, opret alligevel" (kalder `_saveEmployee` med det gemte `_pendingEmployeeBody`). Match på førerkortnummer skjuler OK-knappen (`btn-emp-duplicate-ok`) – kan kun rettes, ikke ignoreres, da kolonnen stadig er unik i DB.

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
| POST | /export-csv | Danløn CSV – afviser (400) hvis perioden allerede er `closed`, eller der er `pending`-aktiviteter i perioden |
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
| `confirmEmployee()` | 1682 | Validerer, kører dublet-tjek (kun ved oprettelse), kalder `_saveEmployee` |
| `_saveEmployee(id, body)` | 1729 | Selve POST/PATCH – udtrukket fra `confirmEmployee` så dublet-advarslen kan kalde den bagefter |
| `_showEmployeeDuplicateWarning(body, nameMatches, cardMatches)` | 1746 | Bygger og åbner `modal-emp-duplicate-warning`; skjuler OK-knappen ved førerkort-match |
| `checkAnciennitetsAlerts()` | ~1786 | GET /anciennitet-alerts; server filtrerer allerede dismissed; viser modal |
| `dismissAnciennitetsAlert(id)` | ~1650 | POST /api/employees/{id}/dismiss-anciennitet (server-side, ikke localStorage) |
| `buildScheduleTable(schedule)` / `readScheduleTable()` | 1540 / 1578 | Se "Timefordeling – fra/til-tid" nedenfor |

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

## Timefordeling – fra/til-tid (2026-07-27, app.js)
`work_schedule`-formatet er uændret (`{"even":[7 tal],"odd":[7 tal]}` – kun beregnede timetal persisteres, ikke klokketider). I medarbejder-modalen kan hver dag udfyldes med ÉT af to input: et timetal-felt (`.sched-even`/`.sched-odd`) eller et fra/til-tidspar (`.sched-even-start`/`-end`). Fra/til vinder altid, hvis begge er udfyldt: `_hoursFromTimes()` beregner timer (sluttid−starttid, wrapper til næste dag hvis negativt – dvs. vagt over midnat), overskriver timetal-feltet live via `input`-listener, og `readScheduleTable()` genberegner defensivt fra fra/til ved selve gemningen (falder tilbage til timetal-feltets værdi hvis fra/til er tomme). `_updateScheduleTotals()` opdaterer et "Ugentligt timeantal"-total pr. uge-kolonne (`#sched-even-total`/`#sched-odd-total`) på hver ændring, uanset input-metode. Ved rediger af eksisterende medarbejder er kun timetal-felterne udfyldt (fra/til gemmes ikke, kun det beregnede resultat).

---

## Rollerettigheder – approve_activities / view_calendar (2026-07-27, session.py)
`_ensure_activity_permissions()` tilføjer disse to nye tilladelser til ALLE eksisterende roller ved opstart (idempotent) – seed-data for nye roller (`_seed_roles()`) inkluderer dem også fra start. Følger samme mønster som `_ensure_anciennitet_alert_permission()`/`_ensure_manage_baselines_permission()`.

---

## UI-robusthed for modaler og dato-vælger (2026-07-27, app.js)
`openModal(id)` nulstiller nu `.modal-body`s scroll-position til top ved hver åbning (før: bevarede scroll fra sidste gang modalen var åben – mærkbart i medarbejder-modalen efter man havde scrollet ned til timefordelingen). `buildDatePicker`s klik-handler måler nu popup-højden og flipper til at åbne OPAD i stedet for nedad, hvis nedad ville skubbe kalenderen uden for viewportet (fx felter langt nede i en scrollet modal) – se `_dpBindEvents()`.

---

## DDD-import (parsers/ddd_parser.py)
Filens dato/minutter er **UTC** – konverteres til Europe/Copenhagen (DST-korrekt via `zoneinfo`) i `_build_activities` for start_time/end_time/segments/pause_intervals. Kræver `tzdata`-pakken (i requirements.txt – Windows har ingen egen IANA-tidszonedatabase).
**Kortnummer**: rå felt i filen er 16 tegn (`[A-Z]{2}\d{14}`), men kun de første 14 tegn (`driverIdentification`) er det stabile nummer til medarbejder-matching – sidste 2 cifre er udskiftnings-/fornyelsesindeks og ændrer sig ved kortfornyelse. `_extract_card_number()` matcher det fulde felt, returnerer kun de første 14 tegn.
**Dagsstart**: changes[0] er altid en hvil-post ved minut 0 (videreført status, ikke reel pause). Er der en ekstra hvil-post lige efter (før første arbejde/kørsel) er det chaufførens faktiske dagsstart – bruges som `day_start_minute` så en indledende kort pause vises i arbejdstiden (og i `pause_intervals`), men forbliver ubetalt.
**Skip-årsager**: `_import_activity()` returnerer `new`/`updated`/`skipped_unknown_card`/`skipped_duplicate` – tælles separat af `_process_import_results()` og logges som én `ddd_import`-hændelse (log_action) med fuld opsummering inkl. konkrete ukendte kortnumre. Frontend viser resultatet i `modal-import-result` (success-visning eller opdelt årsagsliste) i stedet for kun en toast. `scan_ddd_folder()` returnerer nu `(results, errors)` – parse-fejl ved mappescanning ryger i `errors` i stedet for kun `print()` til konsollen.
**Genimport af samme dag med mere komplet data**: Dedup matcher på `(employee_id, start_time, source=tachograph)`. Har en ny udlæsning et SENERE `end_time` end den eksisterende aktivitet (fx fordi kortet først blev downloadet midt på dagen og senere igen efter vagtens afslutning), udvides `end_time`/`segments`/`pause_intervals`/procentfelter i stedet for at blive sprunget over som duplikat. Var aktiviteten `approved`/`deactivated`, genåbnes den til `pending` (approved_by/approved_at/deactivated_by nulstilles) så den udvidede tid skal godkendes igen, før den tæller med i løn. Kun km-felterne blev opdateret ved duplikat før denne rettelse (2026-07-02) – resten af den nye tid gik tabt for altid ved delvise kortudlæsninger.
**Km-start/km-slut**: `_extract_daily_odometer()` finder en kæde af 20-byte (km, UTC-tidsstempel)-par (mindst 5 i træk, ingen fast offset) – tidsstemplet matcher dagens `day_start_minute`. `km_end = km_start + distance` (dagens egen activityDayDistance), IKKE næste tabelpost (håndterer køretøjsskift korrekt). Kortet gemmer kun et begrænset antal poster, så ikke alle dage har km-data. Erstatter den tidligere CardVehiclesUsed-baserede søgning, som byggede på en forkert byte-offset-antagelse.

---

## Periodegrænser i aktivitetsoversigten og sen registrering (2026-07-27)
**Visning af aktiviteter der krydser periodegrænsen:** `list_activities()` i `activities.py` filtrerer ikke længere kun på `pay_period_id` – et OR-filter medtager også aktiviteter hvor `start_time` ligger før periodens startdato, men `end_time` ligger på/efter den (fx en søndagsvagt der starter sidst i forrige periode og fortsætter ind i den viste periode). Kun aktiviteter der faktisk krydser grænsen påvirkes.

**Sen registrering på en allerede lukket periode:** ny hjælpefunktion `get_billing_period()` i `pay_period.py` – hvis den relevante dato hører til en periode med `status == closed`, returneres i stedet den PÅFØLGENDE periode (kalder `get_or_create_period_for_date()` på `end_date + 1 dag`). Bruges ved oprettelse af aktivitet (`POST /api/activities`), redigering af starttid (`PUT /api/activities/{id}`) og DDD-import (`_process_activity` i `import_ddd.py`). `reopen`-endpointet er bevidst IKKE ændret – en genåbnet aktivitet bevarer sin oprindelige `pay_period_id`; det er kun visningen (ovenstående OR-filter), der sørger for at den stadig ses i den efterfølgende periodes oversigt.

**Split af søn-/helligdagsvagter over midnat i aktivitetsoversigten (frontend, app.js):** en kørselsvagt (`activity_type == "normal"`) der starter på søndag/helligdag og strækker sig over midnat vises nu opdelt pr. kalenderdag i gitteret (matcher `_split_into_day_pieces()` i lønberegningen) – hvert stykke viser sit eget `HH:MM–HH:MM` i sin egen datokolonne, klik åbner altid den oprindelige aktivitet (`_orig_id`). Vagter der starter hverdage/lørdage er uændrede (kun start/slut-badge i hver ende).

---

## Danløn CSV-struktur (payroll_router.py)

Kolonner: `CVR ; medarbejdernr ; Danløn-kode ; timer/antal ; sats ; (total)`

Én række per løntype der har antal > 0 OG `include_in_csv=true` i Stamdata → Løntypekoder
(`master_pay_types`). Koden, enheden (timer/antal) og om sats/total skal med er alt sammen
konfigureret pr. type i den tabel – DB er authoritative, ikke hardkodede konstanter:

| code_key | Danløn-kode (default) | Enhed | Bemærkning |
|---|---|---|---|
| NORMAL | 1 | timer | |
| OT_BEFORE | 7 | timer | |
| OT_13 | 8 | timer | inkl. søgnehelligdags-kode8 |
| OT_EXTRA | 9 | timer | inkl. søgnehelligdags-kode9 |
| SALT | 6 | timer | |
| OVERNATNING | 14 | antal | `csv_quantity_type="count"` |
| AFSPADSERING | 71 | timer | total (ikke sats) vises |
| SYGDOM / PARAGRAF_56 / BARSEL | 51 | timer | samme kode for alle tre (§56 bruger dagpengesats, de øvrige medarbejderens timesats) |
| BARN_1SYGEDAG | 15 | timer | dagpengesats |
| FERIEFRI | 81 | timer/antal | enhed styres af Stamdata (se `_builtin_absence_qty()` nedenfor) |
| SKOLE_KURSUS | 2 | timer | total (ikke sats) vises |
| SH_FULDLOENNET / SH_TIMELOENNET | 4 / 63 | timer | søgnehelligdag |
| `ferie` (brugerdefineret type) | 60 | timer | `include_in_csv=false` som default – ferie tælles og vises i UI, men skrives IKKE til CSV før det slås til i Stamdata |

**Case-bug rettet (2026-07-30):** `_get_pay_type_data()` slog op med den rå (case-sensitive)
`code_key` fra DB, mens `_user_pay_type_rows()` slog op med `.upper()`. For alle indbyggede
typer (som allerede er SKREVET MED STORE BOGSTAVER i DB) gjorde det ingen forskel, men for
brugerdefinerede typer med små bogstaver (fx `ferie`) matchede opslaget aldrig – koden,
`include_in_csv`, `csv_include_rate`/`csv_include_total` faldt derfor altid tilbage til
default (kode "1", altid inkluderet). Konsekvens: ferietimer blev skrevet ud som Normal tid
(kode 1) i stedet for kode 60, og kunne optræde som en ekstra "kode 1"-linje der lagde sig til
den rigtige normaltid i Danløn. Rettet ved at normalisere opslaget til store bogstaver.

**`_builtin_absence_qty(pt, key, activity_type, hours_value, emp_id, start, end, db)`:** ny
hjælpefunktion der lader Stamdatas `csv_quantity_type` ("timer"/"antal") styre antallet også
for indbyggede fraværstyper (i dag kun brugt til FERIEFRI) – uden den bruges altid det
akkumulerede timeantal fra `_calculate_employee()`, uanset stamdata-indstillingen.

**`_afspadsering_hours(emp, act)`:** en afspadsering-aktivitet der er lavet som en periode
("Til dato" udfyldt ved oprettelse, spænder over flere kalenderdage) tæller 7,4 t (eller
medarbejderens skemalagte timer) **pr. hverdag** i perioden, uanset de faktiske klokketider på
aktiviteten. En enkeltdags-aktivitet (delvis fridag) bruger stadig den reelle varighed. Uden
denne skelnen blev en flerdags-periode talt som rå klokketid (kan blive 30-100+ timer for en
uges fri, hvis aktiviteten fx er registreret som "fredag 06:00 → følgende fredag 14:00").

`_calculate_employee()` returnerer `sygdom_hours` og `afspadsering_hours` separat i result-dict.

**Periodegrænse-bug rettet (2026-07-30):** Aktivitets-forespørgslen i `_calculate_employee()`
filtrerede tidligere på `Activity.start_time >= start`, dvs. en vagt der starter søndag aften i
DEN FORRIGE periode og fortsætter forbi midnat ind i den nye periodes mandag blev slet ikke
hentet for den nye periode – hverken den forrige periodes dagsløkke (som stopper ved sin egen
`end_date`) eller den nye periodes forespørgsel fangede mandagsdelen, så de timer forsvandt
fuldstændigt fra lønberegningen i begge perioder. Rettet ved at forespørgslen nu bruger overlap
(`start_time < periodeslut+1 AND end_time > periodestart`) i stedet for kun `start_time`. Den
eksisterende søndags-splitning (`_split_into_day_pieces()`) håndterer herefter automatisk at
fordele timerne korrekt til de to perioders egne dage – ingen dobbelttælling, da hver periodes
dagsløkke kun summerer datoer inden for sit eget interval. Bekræftet med et konkret tilfælde
(vagt 12/7 19:00 → 13/7 19:00): før fix talte kun de 5 timer inden midnat (i forrige periode),
efter fix talte forrige periode stadig kun de 5 timer og den nye periode fik de resterende 19
timer – i alt 24 timer bevaret, ingen dubletter.

**Kør løn – låsning (2026-07-02):** `export_csv_post()` i `payroll_router.py` afviser med 400, hvis (a) perioden allerede har `status == PayPeriodStatus.closed`, eller (b) der findes `pending`-aktiviteter for aktive medarbejdere i perioden – begge dele skal være håndteret (godkendt/deaktiveret) først. Perioden sættes først til `closed` EFTER at CSV-filen er skrevet succesfuldt (ikke før) – en fejlet fil-skrivning (fx filen åben i Excel → `PermissionError`) fanges og giver en klar fejlbesked i stedet for at låse perioden uden gyldig eksport. Samme `PermissionError`-fangst er i `proevekoersel_gem()` (Excel-prøvekørsel).

**OBS – to forskellige "hvilken periode hører aktiviteten til"-kilder:** `pay_period_id` (sat ved oprettelse via `get_billing_period()`) styrer hvad Aktiviteter-fanen og tælleren (`period-info`) viser. Den faktiske lønberegning (`_calculate_employee()`, og dermed også pending-tjekket i `export_csv_post()`) bruger derimod `start_time`-datointervallet, UAFHÆNGIGT af `pay_period_id`. De to kan gå ud af sync: `get_billing_period()` ruller en aktivitet frem til NÆSTE åbne periode, hvis dens naturlige periode er `closed` på oprettelsestidspunktet ("sen registrering"). Genåbnes perioden senere, flytter `reopen_period()` (2026-07-02) automatisk sådanne aktiviteter tilbage (matchet på `start_time`), så de ikke bliver usynlige/fanget mellem to perioder.

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

**Vagter der krydser midnat – kun søndag/helligdag splittes (2026-07-02):** Normaltids-/OT13-loftet hører til VAGTEN (den dag den startede), ikke kalenderdagen – en fredag-til-lørdag-vagt bruger fredagens loft, indtil det er brugt op, helt automatisk via `calculate_overtime()`s kronologiske segment-løkke (intet split nødvendigt, loft-baserede dagtyper NORMAL/SATURDAY kan altid deles op i én sammenhængende beregning). Undtagelsen er søndage/helligdage, hvor reglen er loft-uafhængig ("alle kørte timer → kode 9, uanset tidspunkt") – en vagt der STARTER på en søndag/helligdag SKAL derfor splittes ved midnat (`_split_into_day_pieces()` i `payroll_router.py`), så resten af vagten falder tilbage til den følgende dags egne regler. `_calculate_employee()` afgør splittet via `classify_day(act.start_time.date(), holiday_map) in _ABSOLUTE_DAY_TYPES`. `DayType.SATURDAY` bruger nu altid `calculate_overtime()` (aldrig `calculate_special_day_overtime()`) – lørdagens tidligere særregel ("ingen garanterede timer → første 3 kørte timer = kode 8") er fjernet, da den modsagde de faktiske forventede tal; med lørdagens eget (typisk 0) loft rammer den normale dagvindues-logik automatisk samme resultat.

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
Ændringer i `app.js`/`index.html` kræver kun browser-refresh (`app.js` cache-buster er automatisk).  
Ændringer i `style.css` kræver ALTID at versionsnummeret i `index.html` (`style.css?v=N`) bumpes manuelt – ellers cacher browsere den gamle fil.  
Ændringer i `.py`-filer: stop server, ryd `__pycache__`, genstart.

### Deaktiver knap + advarsel ved klik (i stedet for `disabled`-attribut)
Når en handling skal blokeres MED forklaring (ikke bare forsvinde): brug en CSS-klasse (fx `btn-muted`, se `style.css`) i stedet for `disabled`-attributten – en reelt `disabled` knap sender ikke klik-events, så en `toast()`-advarsel kan ikke vises. Mønster: `renderX()` sætter `btn.classList.toggle("btn-muted", betingelse)`, og handler-funktionen selv (fx `exportCsv()`) tjekker betingelsen først og kalder `toast(...)` + `return` før resten af logikken. Eksempel: "Kør løn"-knappen (`btn-koer-loen`) er nedtonet og viser en advarsel, hvis perioden allerede er låst (`state.periodClosed`) eller der er afventende aktiviteter (`state.hasUnresolvedPending`) – se `renderPayrollPreview()` og `exportCsv()` i `app.js`. Server-siden validerer det samme uafhængigt (`export_csv_post()` i `payroll_router.py`) som forsvar i dybden.
