# Design: Dynamisk sats-kilde for løntypekoder

**Dato:** 2026-08-19
**Status:** Godkendt

---

## Oversigt

I dag er "Sats-kilde"-feltet på en brugeroprettet løntypekode (Stamdata → Løntypekoder) et fast,
hardcodet sæt valgmuligheder (`_resolve_rate()` i `app/routers/payroll_router.py` har én
if-gren pr. tillægstype: `ot_before`, `ot_13`, `ot_extra`, `salt`, `overnight`, `dagpenge`,
`springer`). Hver gang der oprettes en ny type under Stamdata → Overtidssatser eller
Stamdata → Tillæg, kræves en kodeændring for at gøre den valgbar som sats-kilde. Der findes
allerede et konkret eksempel på problemet: det brugeroprettede tillæg "DOB_overnatning" kan
slet ikke vælges som sats-kilde noget sted i dag.

Denne ændring gør sats-kilde-dropdownet dynamisk: det bygges fra ALLE rækker der til enhver tid
findes i `master_overtime_rates` og `master_supplement_rates`, så nye rækker automatisk bliver
valgbare uden yderligere kodeændringer.

Feltet er kun relevant for brugeroprettede løntypekoder (`is_user_created = True`) — indbyggede
løntyper (NORMAL, SALT, OVERNATNING m.fl.) har deres sats hardcodet direkte i CSV-eksportens
`raw_rows`-lister og bruger aldrig `_resolve_rate()`.

---

## Ny reference-model for `csv_rate_source`

`MasterPayType.csv_rate_source` er i dag en fri streng (`String(30)`, ingen FK/enum). Værdien
skifter fra faste nøgleord til et generisk, id-baseret skema:

| Værdi | Betydning |
|---|---|
| `hourly` | Medarbejderens overenskomstsats (uændret — indeholder allerede et evt. personligt medarbejdertillæg, jf. `2026-08-13-medarbejder-tillaeg-design.md`) |
| `overtime:<id>` | Reference til `MasterOvertimeRate.id` |
| `supplement:<id>` | Reference til `MasterSupplementRate.id` |

Reference sker via internt id, ikke label — overlever dermed at en rækkes navn ændres. (I praksis
tillader den nuværende rediger-funktion for Overtidssatser/Tillæg kun at ændre selve satsen, ikke
navnet — men id-reference er den robuste løsning uanset.)

Kolonnen forbliver `String(30)` — `"overtime:"`/`"supplement:"` + et heltals-id holder sig
komfortabelt under grænsen for enhver realistisk id-værdi.

---

## Migration af eksisterende data

Kører idempotent i `_migrate()` (`app/database/session.py`), samme sted som al anden
kolonne-/data-migrering i systemet. For hver af de gamle faste værdier slås den tilsvarende
rækkes aktuelle id op på label, og `csv_rate_source` opdateres:

| Gammel værdi | Slås op i | På label |
|---|---|---|
| `ot_before` | `master_overtime_rates` | "Overtid 1 time før" |
| `ot_13` | `master_overtime_rates` | "Overtid 1-3 timer efter" |
| `ot_extra` | `master_overtime_rates` | "Øvrigt overtid" |
| `salt` | `master_supplement_rates` | "Salttillæg" |
| `overnight` | `master_supplement_rates` | "Overnatning" |
| `dagpenge` | `master_supplement_rates` | "Dagpenge §56" |
| `springer` | `master_supplement_rates` | "Springertillæg" |

`hourly` og enhver anden/allerede-migreret værdi rører migrationen ikke ved. Findes label'et
undtagelsesvis ikke (skulle ikke kunne ske i praksis, da disse rækker seedes ved opstart), springes
den pågældende løntypekode over uændret frem for at fejle hele migrationen.

Eksisterende løntypekoder peger efter migrationen på nøjagtig den samme sats som før — ren intern
omkodning, ingen funktionel ændring for dem.

---

## Beregning (`_resolve_rate()`, `app/routers/payroll_router.py`)

```python
def _resolve_rate(rate_src: str, calc: dict) -> float:
    if rate_src.startswith("overtime:"):
        rid = int(rate_src.split(":", 1)[1])
        return float(calc["ot_rates_by_id"].get(rid, 0))
    if rate_src.startswith("supplement:"):
        rid = int(rate_src.split(":", 1)[1])
        return float(calc["supplement_rates_by_id"].get(rid, 0))
    return float(calc["hourly_rate"])
```

To nye funktioner i `app/calculators/rates_loader.py`, samme mønster som `load_overtime_rates_from_db()`:

```python
def load_overtime_rates_by_id_from_db(db) -> dict[int, Decimal]:
    from database.models import MasterOvertimeRate
    return {r.id: Decimal(str(r.rate)) for r in db.query(MasterOvertimeRate).all()}


def load_supplement_rates_by_id_from_db(db) -> dict[int, Decimal]:
    from database.models import MasterSupplementRate
    return {r.id: Decimal(str(r.rate)) for r in db.query(MasterSupplementRate).all()}
```

Begge kaldes én gang pr. medarbejder i `_calculate_employee()` (samme sted de eksisterende
`ot_rates`/`salt_rate`/`overnight_rate`-opslag allerede sker), og resultaterne lægges i
`calc["ot_rates_by_id"]` / `calc["supplement_rates_by_id"]`. Ingen filtrering — alle rækker i de
to tabeller er med, så en ny række er automatisk tilgængelig ved næste lønberegning uden
kodeændring.

De eksisterende navngivne opslag (`salt_rate`, `overnight_rate`, `dagpenge_sats`, `springer_rate`)
bevares uændret — de bruges af de indbyggede løntypers hardcodede CSV-rækker, som ikke går
igennem `_resolve_rate()`.

---

## Beskyttelse mod sletning af en sats der er i brug

`DELETE /api/stamdata/overtime-rates/{id}` og `DELETE /api/stamdata/supplements/{id}`
(`app/routers/stamdata.py`) får hver en ekstra kontrol før sletning:

```python
in_use = db.query(MasterPayType).filter(MasterPayType.csv_rate_source == f"overtime:{rate_id}").first()
if in_use:
    raise HTTPException(400, f"Kan ikke slettes – bruges som sats-kilde af løntypekoden '{in_use.label}'")
```

(tilsvarende `f"supplement:{supplement_id}"` i supplements-sletningen). Fejlbeskeden navngiver den
blokerende løntypekode, så det er tydeligt hvad der skal ændres først. Denne kontrol gælder kun
brugeroprettede rækker i forvejen — systemrækker (`is_user_created=False`) kan slet ikke slettes,
uændret fra i dag.

---

## Frontend — dynamisk dropdown

De to hardcodede `<select>`-blokke i `app/templates/index.html`
(`#new-paytype-ratesrc` og `#stamdata-paytype-ratesrc`) mister deres statiske `<option>`-tags og
udfyldes i stedet af én fælles JS-funktion i `app/static/js/app.js`, kaldet fra begge
modal-åbningsfunktioner (`openNewPayTypeModal()` og `openStamdataPayTypeModal()`):

```js
function _buildRateSourceOptions(selectId, selectedValue) {
  const sel = document.getElementById(selectId);
  let html = `<option value="hourly">Timesats (overenskomst)</option>`;
  if (state.stamdataOvertimeRates?.length) {
    html += `<optgroup label="Overtidssatser">` +
      state.stamdataOvertimeRates.map(r => `<option value="overtime:${r.id}">${h(r.label)}</option>`).join("") +
      `</optgroup>`;
  }
  if (state.stamdataSupplements?.length) {
    html += `<optgroup label="Tillæg">` +
      state.stamdataSupplements.map(r => `<option value="supplement:${r.id}">${h(r.label)}</option>`).join("") +
      `</optgroup>`;
  }
  sel.innerHTML = html;
  sel.value = selectedValue || "hourly";
}
```

Data genbruges fra `state.stamdataOvertimeRates`/`state.stamdataSupplements`, som allerede
indlæses af `loadStamdataOvertimeRates()`/`loadStamdataSupplements()` når Stamdata-fanen åbnes —
ingen nye endpoints. Da løntypekode-modalen kun kan åbnes fra samme Stamdata-view, er disse
altid allerede hentet.

**Visningslabel i løntypekode-tabellen:** `_RATE_SRC_LABELS`-objektet (fast streng-mapping)
erstattes af en funktion der slår det aktuelle navn op via id:

```js
function _rateSourceLabel(rateSrc) {
  if (rateSrc === "hourly" || !rateSrc) return "Timesats";
  const [kind, idStr] = rateSrc.split(":");
  const id = parseInt(idStr);
  const list = kind === "overtime" ? state.stamdataOvertimeRates : state.stamdataSupplements;
  const row = list?.find(r => r.id === id);
  return row ? row.label : rateSrc;
}
```

---

## Test/verifikation

- **Migration:** en løntypekode med `csv_rate_source="salt"` før migration peger efter migration
  på `supplement:<id for Salttillæg>` — og `_resolve_rate()` returnerer nøjagtig samme sats som
  før.
- **`_resolve_rate()`:** dækning for `overtime:<id>`, `supplement:<id>`, `hourly`, samt en ukendt
  streng (falder tilbage til `hourly_rate`, som i dag).
- **Ny type bliver valgbar uden kodeændring:** opret en ny brugerdefineret tillægstype under
  Stamdata → Tillæg, opret en løntypekode med sats-kilde peget på den, kør CSV-eksport → korrekt
  sats i CSV-linjen, uden at have rørt `_resolve_rate()`.
- **Sletningsbeskyttelse:** forsøg på at slette en Overtidssats-/Tillæg-række der er i brug af en
  løntypekode → 400 med navngivet løntypekode i fejlbeskeden. En ikke-brugt brugeroprettet række
  kan stadig slettes som i dag.
- **Frontend i browser:** åbn "opret ny løntypekode", bekræft at dropdownet viser alle aktuelle
  Overtidssatser og Tillæg (inkl. "DOB_overnatning") grupperet under overskrifter; rediger en
  eksisterende brugeroprettet løntypekode og bekræft at dens nuværende sats-kilde er korrekt
  forudvalgt; bekræft at tabellens sats-kilde-kolonne viser det rigtige navn.

---

## Åbne punkter

Ingen.
