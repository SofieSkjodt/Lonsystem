# Datamodel – Lønsystem

## Tabeller

---

### `employees` (Medarbejdere)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| employee_number | TEXT UNIQUE NOT NULL | Medarbejdernummer (Danløn) |
| tachograph_card_number | TEXT UNIQUE | Tachografkortnummer (fra .ddd-fil) |
| name | TEXT NOT NULL | Fulde navn |
| hire_date | DATE NOT NULL | Ansættelsesdato |
| employee_type | TEXT NOT NULL | Se typer nedenfor |
| is_qualified | BOOLEAN | Faglært (ja/nej) |
| qualification_allowance | BOOLEAN | Kvalifikationstillæg (hænger+kran) |
| seniority_override | BOOLEAN | Manuel tilsidesætning af anciennitet (anciennitetstillæg fra dag 1) |
| active | BOOLEAN DEFAULT TRUE | Aktiv medarbejder |
| created_at | DATETIME | Oprettelsestidspunkt |
| updated_at | DATETIME | Sidst opdateret |

**Medarbejdertyper (`employee_type`):**
- `trainee` – Chauffør under oplæring (grundtimeløn: 159,65 kr.)
- `driver` – Chauffør (timeløn nyansættelse: 174,15 kr.)
- `driver_senior` – Chauffør efter 9 mdr. (timeløn: 182,30 kr.)
- `driver_qualified` – Faglært chauffør (timeløn: 186,30 kr.)

Anciennitet beregnes automatisk fra `hire_date`. Pop-up ved 9 måneder hvis `seniority_override = false` og type ikke allerede er senior/faglært.

---

### `pay_periods` (Lønperioder)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| start_date | DATE NOT NULL | Startdato for perioden |
| end_date | DATE NOT NULL | Slutdato (altid start_date + 13 dage = 14 dage) |
| status | TEXT | `open`, `preview`, `closed` |
| closed_at | DATETIME | Tidspunkt for lønkørsel |
| closed_by | TEXT | Initialer på den der lukkede |

**Regler:**
- En periode er altid præcis 14 dage
- Næste periode starter på næste hverdag efter forrige periodes slutdato
- Systemet opretter ny periode automatisk ved behov

---

### `activities` (Aktiviteter/Bjælker)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| employee_id | INTEGER FK | Reference til medarbejder |
| pay_period_id | INTEGER FK | Reference til lønperiode |
| trip_number | TEXT | TurNR (6 cifre, kan være NULL) |
| source | TEXT | `tachograph` eller `manual` |
| start_time | DATETIME NOT NULL | Starttidspunkt |
| end_time | DATETIME NOT NULL | Sluttidspunkt |
| availability_time_pct | DECIMAL | Rådighedstid (%) |
| rest_pause_pct | DECIMAL | Hvil/pause (%) |
| other_work_pct | DECIMAL | Andet arbejde (%) |
| driving_pct | DECIMAL | Kørsel (%) |
| loading_minutes | INTEGER | Pålæsningstid i minutter (kun manuel) |
| unloading_minutes | INTEGER | Aflæsningstid i minutter (kun manuel) |
| status | TEXT | `pending`, `approved`, `deactivated` |
| approved_by | TEXT | Initialer på godkender |
| approved_at | DATETIME | Godkendelsestidspunkt |
| comment | TEXT | Fri kommentar |
| parent_activity_id | INTEGER FK NULL | Hvis splittet: reference til original |
| split_part | INTEGER NULL | 1 = første del (deaktiveret), 2 = anden del (aktiv) |
| created_at | DATETIME | Oprettelsestidspunkt |

**Effektiv tid** = `end_time - start_time` (total tid fra start til slut)

**Farvestatus:**
- `deactivated` → 🔴 Rød
- `approved` → 🟢 Grøn
- `pending` → 🔵 Blå

**Manuelle aktiviteter** vises med `(K)` prefix.

**Split-logik:**
- Original aktivitet splittes i to nye rækker med `parent_activity_id` = original
- Del 1 (`split_part = 1`): status sættes til `deactivated`, regnes ikke med
- Del 2 (`split_part = 2`): kan godkendes normalt

---

### `dispatcher_groups` (Disponentgrupper)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| name | TEXT NOT NULL | Gruppenavn |
| description | TEXT | Beskrivelse |

### `employee_dispatcher_groups` (Mange-til-mange)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| employee_id | INTEGER FK | Medarbejder |
| dispatcher_group_id | INTEGER FK | Disponentgruppe |

---

### `payroll_runs` (Lønkørsler)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| pay_period_id | INTEGER FK | Lønperiode |
| run_type | TEXT | `preview` eller `final` |
| run_at | DATETIME | Tidspunkt |
| run_by | TEXT | Initialer |
| csv_path | TEXT | Sti til genereret CSV (final) |
| excel_path | TEXT | Sti til genereret Excel (preview) |

---

### `holidays` (Helligdage)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| date | DATE UNIQUE NOT NULL | Helligdagens dato |
| name | TEXT NOT NULL | Navn, fx "Påskedag", "1. maj" |
| half_day_from | TEXT NULL | "12:00" = fri fra middag; NULL = heldagshelligdag |
| is_auto_generated | BOOLEAN DEFAULT TRUE | TRUE = genereret af systemet, FALSE = manuel |

**Regler:**
- Tabellen seedes automatisk ved serveropstart via `_seed_holidays()` i `session.py`
- 5 løbende år genereres (indeværende år + 4)
- Seeding er idempotent — eksisterende datoer springes over
- Dato er UNIQUE: hvis en bevægelig helligdag falder samme dag som en fast (fx 2. pinsedag på Grundlovsdag i 2028), vinder den faste helligdag
- Beregning af påskedag sker via anonym Gregoriansk Computus-algoritme i `app/calculators/holidays.py`
- Store Bededag medtages ikke (afskaffet fra 2024)

**Auto-genererede helligdage:**

| Type | Helligdag | Halvdag fra |
|------|-----------|-------------|
| Fast | Nytårsdag (1/1) | — |
| Fast | 1. maj (1/5) | 12:00 |
| Fast | Grundlovsdag (5/6) | 12:00 |
| Fast | Juleaftensdag (24/12) | — |
| Fast | 1. juledag (25/12) | — |
| Fast | 2. juledag (26/12) | — |
| Fast | Nytårsaftensdag (31/12) | — |
| Bevægelig | Skærtorsdag (Påske − 3) | — |
| Bevægelig | Langfredag (Påske − 2) | — |
| Bevægelig | Påskedag | — |
| Bevægelig | 2. påskedag (Påske + 1) | — |
| Bevægelig | Kristi Himmelfartsdag (Påske + 39) | — |
| Bevægelig | Pinsedag (Påske + 49) | — |
| Bevægelig | 2. pinsedag (Påske + 50) | — |

**Permission:** `manage_holidays` — kun brugere med denne rettighed kan oprette og slette helligdage.

---

## Beregningsregler (ikke gemt i DB)

Se `PAYROLL_RULES.md` for detaljerede beregningsregler.

- **Effektiv tid**: `end_time - start_time`
- **Minimum 4 timer**: Vagter under 4 timer markeres `pending` og kræver manuel godkendelse med begrundelse
- **Overtid**: Se `OVERTIME_RULES.md`
- **Ubekvem tid**: Se `PAYROLL_RULES.md`
