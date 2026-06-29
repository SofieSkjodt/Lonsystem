# Helligdagskalender — Design spec
**Dato:** 2026-06-23  
**Status:** Godkendt af bruger

---

## Formål

Implementer en helligdagskalender i systemet der:
1. Automatisk genererer danske helligdage for løbende 5 år fremad
2. Giver admin mulighed for manuelt at tilføje og slette helligdage
3. Viser helligdage som farvemarkering i aktivitetskalenderen (alle brugere)
4. Fungerer som datalag til fremtidig lønberegningsintegration

Løn-regler for arbejde på helligdage implementeres i en separat fase.

---

## Arkitektur

**Tilgang: Generer-og-gem (Tilgang A)**

Alle helligdage gemmes i en `holidays`-tabel. Auto-generatoren kører ved serveropstart (`init_db`) og tilføjer manglende år op til `i dag + 5 år` (idempotent). Databasen er eneste sandhedskilde. Admin kan slette og tilføje frit.

---

## Datamodel

### Ny tabel: `holidays`

| Felt | Type | Beskrivelse |
|------|------|-------------|
| `id` | Integer, PK | |
| `date` | Date, unique, not null | Helligdagens dato |
| `name` | String(200), not null | Fx "Påskedag", "1. maj" |
| `half_day_from` | String(5), nullable | "12:00" = fri fra middag; NULL = heldagshelligdag |
| `is_auto_generated` | Boolean, default True | True = genereret af systemet |

Ingen FK-relationer. Tabellen oprettes af `Base.metadata.create_all` ved første kørsel.

---

## Helligdage der auto-genereres

### Faste datoer (samme hvert år)

| Dato | Navn | Halvdag fra |
|------|------|-------------|
| 1. januar | Nytårsdag | — |
| 1. maj | 1. maj | 12:00 |
| 5. juni | Grundlovsdag | 12:00 |
| 24. december | Juleaftensdag | — |
| 25. december | 1. juledag | — |
| 26. december | 2. juledag | — |
| 31. december | Nytårsaftensdag | — |

### Påskebaserede (beregnes via Computus-algoritmen)

| Offset fra påskedag | Navn |
|---------------------|------|
| Påske − 3 dage | Skærtorsdag |
| Påske − 2 dage | Langfredag |
| Påske + 0 dage | Påskedag |
| Påske + 1 dag | 2. påskedag |
| Påske + 39 dage | Kristi Himmelfartsdag |
| Påske + 49 dage | Pinsedag |
| Påske + 50 dage | 2. pinsedag |

Note: Store Bededag medtages ikke (afskaffet fra 2024).

---

## Holiday-beregner

Ny fil: `app/calculators/holidays.py`

```python
def easter_date(year: int) -> date:
    """Beregn påskedato via anonym Gregoriansk Computus."""
    ...

def get_holidays_for_year(year: int) -> list[dict]:
    """Returnér liste af {date, name, half_day_from, is_auto_generated=True}."""
    ...
```

`_seed_holidays()` i `session.py` kalder `get_holidays_for_year()` for hvert år i `[current_year, current_year + 4]` og indsætter kun rækker der ikke allerede eksisterer (ON CONFLICT DO NOTHING via try/except unique violation).

---

## Permission

- Ny permission: `manage_holidays` — label "Administrér helligdage"
- Tilføjes til `ALL_PERMISSIONS` i `auth.py`
- Tilføjes til `PERMISSION_LABELS` i `app.js`
- Tildeles `admin`-rollen som standard (via `_seed_roles` opdateres ikke eksisterende roller — admin sætter selv via Roller-UI)
- Vises som afkrydsningsfelt i Roller-UI automatisk

---

## API-endpoints

Alle under `/api/stamdata/holidays`:

| Method | URL | Auth | Beskrivelse |
|--------|-----|------|-------------|
| GET | `/api/stamdata/holidays` | Alle indloggede | Hent alle helligdage; valgfri `?year=2026` filter |
| POST | `/api/stamdata/holidays` | `manage_holidays` | Opret helligdag manuelt |
| DELETE | `/api/stamdata/holidays/{id}` | `manage_holidays` | Slet helligdag |
| POST | `/api/stamdata/holidays/generate/{year}` | `manage_holidays` | (Gen)generer helligdage for ét år |

### Request body (POST opret):
```json
{ "date": "2026-07-04", "name": "Særlig fridag", "half_day_from": null }
```

### Response (GET):
```json
[
  { "id": 1, "date": "2026-01-01", "name": "Nytårsdag", "half_day_from": null, "is_auto_generated": true },
  { "id": 2, "date": "2026-05-01", "name": "1. maj", "half_day_from": "12:00", "is_auto_generated": true }
]
```

---

## UI

### Stamdata → "Helligdage"-fane (kun `manage_holidays`)

- Tab-knap skjules med `data-perm-require="manage_holidays"`
- Tabel: Dato | Navn | Halvdag fra | Type | Handlinger
- Sorteret kronologisk
- "Slet"-knap på alle rækker
- "+ Tilføj"-knap i toolbar → modal med: dato-picker, navn-felt, halvdag-checkbox + tidsfelt (vises kun hvis checkbox er sat)
- "Generer år"-knap → lille dropdown/input med årstal → kald `POST /generate/{year}`

### Aktivitetskalender — helligdagsmarkering (alle brugere)

- Kalenderens dag-kolonner hentes fra `/api/stamdata/holidays?year=YYYY` ved periodelæsning
- Kolonner der er helligdage: header-celle får baggrund `#adc730`
- Halvdagshelligdage: samme baggrundsfarve `#adc730` + lille "½"-tekst under datoen
- Tooltip ved hover: helligdagets navn (og halvdagstidspunkt)

---

## Berørte filer

| Fil | Ændring |
|-----|---------|
| `app/database/models.py` | Ny `Holiday`-klasse |
| `app/database/session.py` | `_seed_holidays()` + kald fra `init_db()` |
| `app/calculators/holidays.py` | Ny fil: `easter_date()` + `get_holidays_for_year()` |
| `app/auth.py` | `manage_holidays` i `ALL_PERMISSIONS` |
| `app/routers/stamdata.py` | 4 nye endpoints |
| `app/templates/index.html` | Helligdage-tab + ny modal + `data-perm-require` |
| `app/static/js/app.js` | Tab-logik, `loadStamdataHolidays()`, kalendermarkering |

---

## Fremtidig fase (ikke i scope nu)

- Lønberegningsintegration: `_calculate_employee()` i `payroll_router.py` slår op i `holidays`-tabellen for at anvende helligdagstillæg
- Aktivitetsregistrering: advarsel når der registreres aktivitet på helligdag
