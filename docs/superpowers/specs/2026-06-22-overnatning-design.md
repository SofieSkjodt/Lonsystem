# Design: Overnatning som aktivitetstype

**Dato:** 2026-06-22  
**Status:** Godkendt

---

## Oversigt

Tilføj "Overnatning" som selvstændig aktivitetstype i Lønsystemet. Overnatning registreres som en hændelse pr. dag (ikke timerbaseret) og giver en fast sats pr. registrering. Satsen hentes dynamisk fra "Salttillæg og overnatning.xlsx".

---

## Data & backend

### Ingen databasemigrering
`activity_type`-kolonnen er allerede `String(50)` uden enum-begrænsning. "overnatning" er en ny gyldig strengværdi — ingen `ALTER TABLE` nødvendig.

### `app/calculators/rates_loader.py`
Ny funktion `load_overnight_rate() -> Decimal`:
- Åbner "Salttillæg og overnatning.xlsx" via `_load_workbook_safe()`
- Søger kolonne A for rækken med teksten "overnatning" (case-insensitiv)
- Returnerer værdien i kolonne B som `Decimal`
- Kaster `FileNotFoundError` hvis filen mangler, `ValueError` hvis rækken ikke findes eller satsen er tom
- Genindlæser filen ved hvert kald — ændringer i Excel slår igennem uden servergenstart

### `app/calculators/pay_rates.py`
Ny konstant:
```python
DANLOEN_CODE_OVERNATNING = "1"  # Placeholder — erstattes med reelt kode fra lønafdelingen
```

### `app/routers/payroll_router.py` — `_calculate_employee()`
1. Hent `overnight_rate` via `load_overnight_rate()` med try/except (fallback: `Decimal("0")`)
2. Tæl aktiviteter med `activity_type == "overnatning"` i perioden → `overnight_count`
3. Beregn `overnight_kr = Decimal(str(overnight_count)) * overnight_rate`
4. Tilføj til `totals`-dict: `overnight_count`, `overnight_rate`, `overnight_kr`

### CSV-eksport til Danløn
Tilføj én linje pr. medarbejder hvis `overnight_count > 0`:
```
[CVR];[medarbejdernr];[DANLOEN_CODE_OVERNATNING];[antal];[sats]
```
Format følger eksisterende mønster (2 decimaler, komma som decimalseparator). Linjen udelades ved antal = 0.

---

## Modal "Tilføj aktivitet"

### `app/templates/index.html`
Tilføj `<option value="overnatning">Overnatning</option>` til `#manual-type`-dropdown.

### `app/static/js/app.js`
- Når "overnatning" vælges: skjul `#manual-normal-fields` (start-/sluttid, timer, salttillæg) — samme adfærd som fraværstyper
- `start_time` og `end_time` sendes ikke til backend for denne type (feltværdier ignoreres/nulles)

### Backend-modtagelse
Aktivitet oprettes med:
- `activity_type = "overnatning"`
- `start_time = end_time = midnat på aktivitetsdatoen` — `start_time`/`end_time` er `nullable=False` i modellen, så midnat bruges som neutral placeholder; payroll-beregningen ignorerer tiderne for denne type
- Øvrige felter (dato, medarbejder, `created_by`) gemmes som normalt

---

## Lønkørsels-tabel (frontend)

Ny række "Overnatning" i tabellen med kolonner:
- **Antal** — antal overnatning-aktiviteter i perioden
- **Sats** — dynamisk sats fra Excel (kr)
- **Total** — antal × sats (kr)

Rækken vises kun hvis `overnight_count > 0`. Formatering følger øvrige tillægsrækker (f.eks. salttillæg).

---

## Aktivitetsoversigt

"Overnatning"-aktiviteter vises i listen med type-badge som fraværstyper. I detailmodalen vises ingen tidsrækker (de er tomme for denne type).

---

## Åbne punkter

- **Danløn-kode**: `DANLOEN_CODE_OVERNATNING = "1"` er placeholder — lønafdelingen skal oplyse det reelle kode.
- **Validering**: Systemet håndhæver ikke kravet om, at overnatning kun registreres på dage med anden godkendt kørsel — dette er en forretningsregel, der håndteres manuelt.
