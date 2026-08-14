# Design: Springertillæg

**Dato:** 2026-08-14
**Status:** Godkendt

---

## Oversigt

Ny løntypekode "Springertillæg" der giver en fast kr/time-sats oveni normaltimerne, for de medarbejdere der i den enkelte lønperiode skal have den. Om en medarbejder skal have tillægget afgøres af et afkrydsningsfelt pr. medarbejder pr. periode i aktivitetsoversigten — ikke af noget der registreres på selve aktiviteterne.

Timeantallet i CSV-linjen er altid identisk med løntypekode 1's timetal (`calc["normal_hours"]`) for samme medarbejder/periode. Er fluebenet ikke sat, eller er timetallet 0, udelades linjen helt.

Mønsteret følger "Overnatning" (se `2026-06-22-overnatning-design.md`): en fast sats fra `MasterSupplementRate`, en tilhørende løntypekode i `MasterPayType` med en ny `csv_rate_source`-værdi, hardcodet ind i beregningen — ikke den generiske `_user_pay_type_rows()`-mekanisme, da springertillæg ikke er knyttet til en `Activity`-forekomst.

---

## Datamodel

### Ny tabel `employee_springer_flags` (`app/database/models.py`)

```python
class EmployeeSpringerFlag(Base):
    __tablename__ = "employee_springer_flags"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False)
    enabled = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(String, nullable=True)

    employee = relationship("Employee")
    pay_period = relationship("PayPeriod")

    __table_args__ = (
        Index("uq_employee_springer_flags_emp_period", "employee_id", "pay_period_id", unique=True),
    )
```

Oprettes automatisk via `Base.metadata.create_all()` i `init_db()` — ingen manuel migration (samme mønster som `employee_supplements`). Ingen række = ikke sat (default `False`), så en helt ny periode starter med alle medarbejdere ukrydset, uden at der skal seedes noget.

### Ny sats — `MasterSupplementRate`

Ny idempotent seed-funktion `_ensure_springer_supplement_rate()` i `app/database/session.py` (samme mønster som `_ensure_sh_pay_types()`): tilføjer én række `label="Springertillæg", rate=0` hvis den ikke findes. Satsen redigeres bagefter af lønbogholderi under Stamdata → Tillæg (eksisterende generisk UI/endpoint — ingen ændring nødvendig der).

### Ny løntypekode — `MasterPayType`

Samme seed-funktion tilføjer en løntypekode-række hvis `code_key = "SPRINGERTILLAEG"` ikke findes:

```python
MasterPayType(
    code_key="SPRINGERTILLAEG", label="Springertillæg",
    danloen_code="",             # placeholder – udfyldes af lønbogholderi under Løntypekoder, jf. øvrige koder
    include_in_csv=True, sort_order=<næste ledige, pt. 16>,
    csv_quantity_type="hours", csv_rate_source="springer",
    csv_include_rate=True, csv_include_total=False,
)
```

Dukker herefter op i Stamdata → Løntypekoder-fanen som enhver anden kode — Danløn-kode og sortering redigeres der via eksisterende UI.

---

## Backend — sats-opslag og beregning

### `app/calculators/rates_loader.py`

Ny funktion, mønster identisk med `load_overnight_rate_from_db()`:

```python
def load_springer_rate_from_db(db) -> Decimal:
    from database.models import MasterSupplementRate
    row = db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "Springertillæg").first()
    return Decimal(str(row.rate)) if row else Decimal("0")
```

### `app/routers/payroll_router.py`

**`_resolve_rate()`** (linje 107-121): nyt gren:
```python
if rate_src == "springer":
    return float(calc.get("springer_rate", 0))
```

**`_calculate_employee()`** (linje 251+): efter det eksisterende opslag af `salt_rate`/`overnight_rate` (linje 278-279):
```python
springer_rate = load_springer_rate_from_db(db)
springer_enabled = db.query(EmployeeSpringerFlag).filter(
    EmployeeSpringerFlag.employee_id == emp.id,
    EmployeeSpringerFlag.pay_period_id == period_id,   # se note nedenfor om period_id
    EmployeeSpringerFlag.enabled == True,
).first() is not None
```
Tilføjes til returdict: `"springer_rate": float(springer_rate)`, `"springer_enabled": springer_enabled`.

**Note om periode-id i `_calculate_employee()`:** funktionen tager i dag `start`/`end` som datoer, ikke et `PayPeriod`-objekt/id, og kaldes fra 8 steder i `payroll_router.py`/`timeseddel_router.py` — nogle af dem (tidssedler/preview) med et frit valgt `from_date`/`to_date`, der ikke nødvendigvis er en hel, officiel 14-dages periode. At tilføje `period_id` som ny parameter ville derfor kræve at ændre alle 8 kaldssteder og opfinde et periode-begreb for de frie datointervaller, hvor der ikke findes noget naturligt. I stedet slås perioden op **internt** i `_calculate_employee()` via `get_or_create_period_for_date(start, db)` (samme funktion `_resolve_period()` allerede bruger) — det er den periode, hvis `start_date` er nærmest før/lig `start`. For de almindelige CSV-/lønkørsel-kald er `start` allerede periodens egen `start_date`, så opslaget rammer altid den korrekte periode. For frie datointervaller (tidssedler/preview) bruges den periode, der indeholder `start`-datoen — et fornuftigt, deterministisk valg, men et åbent punkt hvis en bruger engang kører en tidsseddel/preview hen over en periodegrænse (se "Åbne punkter").

### CSV-eksport — begge `raw_rows`-lister (linje 778-795 og 883-900)

Ny betinget linje, tilføjet lige efter `"NORMAL"`:
```python
raw_rows = [
    ("NORMAL", calc["normal_hours"], calc["hourly_rate"]),
    ("SPRINGERTILLAEG", calc["normal_hours"] if calc.get("springer_enabled") else 0, calc.get("springer_rate", 0)),
    ...
```
Den eksisterende sløjfe (`if not _in_csv(key) or qty == 0: continue`) udelader linjen automatisk når fluebenet ikke er sat (qty bliver 0) — ingen ekstra betingelse nødvendig i selve løkken.

---

## Permission

Ny permission `toggle_springer` i `ALL_PERMISSIONS` (`app/auth.py`), label "Sæt springertillæg". Ny idempotent funktion `_ensure_toggle_springer_permission()` i `app/database/session.py`, mønster identisk med `_ensure_activity_permissions()` (linje 466-486): tilføjes til **alle** eksisterende roller (ikke kun én), jf. beslutning om at give den til alle roller for nu. Kaldes fra `init_db()`.

Nyt endpoint (se nedenfor) beskyttes med `Depends(require_permission("toggle_springer"))`.

---

## Nyt endpoint

I `app/routers/activities.py` (samme fil som `period-info`):

```
POST /api/activities/springer-flag
Body: { employee_id: int, pay_period_id: int, enabled: bool }
```

- Kræver `toggle_springer`.
- Afvises med 400 hvis perioden (`pay_period_id`) har `status == closed` — samme regel som aktiviteter kan ikke redigeres efter lønkørsel.
- Upsert: findes rækken for `(employee_id, pay_period_id)`, opdateres `enabled`+`updated_at`+`updated_by`; ellers oprettes ny.
- Returnerer den opdaterede status.

---

## Aktivitetsoversigt (frontend)

### `app/static/js/app.js` — `renderActivitiesTable()` (linje 314-316)

`emp-cell` udvides til at vise et lille afkrydsningsfelt **under** navnet, i samme celle/række:
```js
const springerFlag = state.springerFlags?.[emp.id] === true;
const springerDisabled = p.status === "closed" ? "disabled" : "";
let cells = `<td class="emp-cell" title="${h(emp.name)}">
  ${h(emp.name)}
  <label class="springer-flag-label">
    <input type="checkbox" class="springer-flag-checkbox" data-emp-id="${emp.id}"
      ${springerFlag ? "checked" : ""} ${springerDisabled}> Springertillæg
  </label>
</td>`;
```
Vises for alle medarbejdere i den viste liste (ikke betinget af aktiviteter i perioden), jf. beslutning.

`state.springerFlags` (nyt state-felt, `{employee_id: bool}`) hentes ved periode-load, sammen med de øvrige periode-kald i `loadActivities()`-flowet (linje 200-208):
```js
GET(`/api/activities/springer-flags?pay_period_id=${state.periodInfo.period.id}`).then(r => { state.springerFlags = r; }),
```
(Nyt `GET`-endpoint der returnerer et map for hele perioden — undgår N enkelt-kald.)

Event-listener (tilføjes ved siden af de øvrige body-listeners, linje ~333-343):
```js
body.querySelectorAll(".springer-flag-checkbox").forEach(el => {
  el.addEventListener("change", async e => {
    e.stopPropagation();
    try {
      await POST("/api/activities/springer-flag", {
        employee_id: parseInt(el.dataset.empId),
        pay_period_id: state.periodInfo.period.id,
        enabled: el.checked,
      });
    } catch (err) {
      el.checked = !el.checked;   // rul UI tilbage ved fejl (fx låst periode)
      toast(err.message, "error");
    }
  });
});
```
Checkboxen har `disabled` når perioden er låst (`p.status === "closed"`), så brugeren ikke kan klikke og få en fejl — matcher hvordan andre felter låses ved periodestatus i dag.

---

## Låsning ved periode-status

Fluebenet kan ikke ændres, når perioden er låst (`PayPeriodStatus.closed`) — hverken i UI (disabled) eller backend (400 hvis forsøgt). Genåbnes perioden (`reopen_period`), bliver fluebenet redigerbart igen, ligesom aktiviteter.

---

## Test/verifikation

- **Backend:** opret flag for medarbejder A i periode 1 → kør CSV-eksport → linje med `SPRINGERTILLAEG`, timetal lig `NORMAL`-linjens, korrekt sats. Medarbejder B uden flag → ingen linje. Medarbejder A i periode 2 (intet flag oprettet) → ingen linje (bekræfter nulstilling pr. periode).
- **0-timer-tilfælde:** medarbejder med flag sat, men 0 timer i `normal_hours` (fx kun ferie hele perioden) → ingen linje.
- **Låsning:** forsøg på at ændre flag i låst periode → 400 fra endpoint; checkbox er disabled i UI.
- **Permission:** endpoint afvises uden `toggle_springer`; efter migrering har alle eksisterende roller tilladelsen.
- **Frontend i browser:** åbn aktivitetsoversigt, sæt/fjern flueben for en medarbejder, skift periode frem/tilbage og se at fluebenet er periode-specifikt, genindlæs siden og se at tilstanden er persisteret.

---

## Åbne punkter

- **Danløn-kode**: `danloen_code=""` er placeholder ved seeding — lønbogholderi udfylder den reelle kode under Stamdata → Løntypekoder, samme mønster som øvrige koder afventer lønafdelingen.
- **Sats**: seedes til 0 kr — lønbogholderi sætter den reelle sats under Stamdata → Tillæg efter udrulning.
- **Tidssedler/preview på tværs af periodegrænse**: hvis en tidsseddel-PDF eller lønpreview nogensinde køres med et frit `from_date`/`to_date`-interval, der ikke matcher en hel officiel 14-dages periode, bruges springer-flaget for den periode der indeholder `from_date`. Ingen kendt use-case rammer dette i dag (CSV-eksport og almindelig lønkørsel bruger altid en hel, officiel periode) — nævnes her, hvis det bliver relevant senere.
