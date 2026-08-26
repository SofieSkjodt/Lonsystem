# Ét tidsfelt i dt-picker – Design

**Dato:** 2026-08-26
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Den delte `dt-picker`-komponent i `app.js` (funktionerne `buildDatetimePicker()`, `readDatetimePicker()`, `setDatetimePicker()`, `_stackDatetimePicker()`) bygger i dag tidsdelen af et tidspunkt som tre separate DOM-elementer:

- `.dt-hour` – tekstfelt, `maxlength="2"`, placeholder "tt"
- `.dt-sep` – et kolon-symbol (`<span>`)
- `.dt-min` – tekstfelt, `maxlength="2"`, placeholder "mm"

`readDatetimePicker()` klemmer (`Math.min`/`Math.max`) de indtastede værdier til gyldige time-/minuttal, fordi felterne er frie tekstfelter uden indbygget validering.

**Ønsket ændring:** Tidsdelen skal være ét felt, der håndterer `tt:mm` – ikke to separate bokse.

## Løsning

### Ét nativt tidsfelt

De tre elementer (`.dt-hour`, `.dt-sep`, `.dt-min`) erstattes af ét `<input type="time" class="dt-time">`. Native browser-tidsvælgere garanterer altid et gyldigt `HH:MM`-format (eller tom streng), så den manuelle clamping i `readDatetimePicker()` kan fjernes.

Native `<input type="time">` viser som standard diskrete op/ned-pile i Chrome/Edge ved hover. Disse fjernes med CSS:

```css
input[type="time"]::-webkit-inner-spin-button,
input[type="time"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
```

`.dt-date`-feltet (native datovælger) er uændret – kun tidsdelen ændres.

### Omfang: hele den delte komponent

`buildDatetimePicker`/`readDatetimePicker`/`setDatetimePicker`/`_stackDatetimePicker` er delte funktioner brugt 8+ steder i `app.js`: opret aktivitet (`manual-start`/`manual-end`), opret/redigér pause (`pause-start`/`pause-end`), "Ret starttid/sluttid" på en eksisterende aktivitet (`edit-start`/`edit-end`), split af aktivitet (`split-at`), og segment-resize (`resize-seg-end`).

Ændringen sker i selve de delte funktioner, så alle disse steder får det nye ét-felts design automatisk uden separate ændringer per brugssted. Funktionssignaturerne (`buildDatetimePicker(id, isoValue)` osv.) er uændrede – ingen kald-steder skal opdateres.

### Detaljerede ændringer

**`buildDatetimePicker(id, isoValue)`** (i dag linje 1317-1332): bygger i dag `.dt-date` + `.dt-hour` + `.dt-sep` + `.dt-min`. Skal i stedet bygge `.dt-date` + ét `<input type="time" class="dt-time">` med `value` sat til `isoValue.slice(11, 16)` (fallback `"06:00"` som i dag, jf. eksisterende default).

**`readDatetimePicker(id)`** (i dag linje 1334-1343): læser i dag `.dt-hour`/`.dt-min` og klemmer dem til gyldige tal. Skal i stedet læse `.dt-time`s værdi direkte (allerede garanteret gyldig af browseren), med fallback til `"00:00"` hvis feltet er tomt (bevarer nuværende adfærd, hvor tomme felter defaulter til `00:00`).

**`setDatetimePicker(id, isoValue)`** (i dag linje 1345-1351): sætter i dag `.dt-hour`/`.dt-min` separat. Skal i stedet sætte `.dt-time`s værdi til `isoValue.slice(11, 16)`.

**`_stackDatetimePicker(id)`** (i dag linje 1301-1315): flytter i dag `.dt-hour`+`.dt-sep`+`.dt-min` ned i en ny række under `.dt-date` (bruges på smalle skærme/i pause-modalen). Skal i stedet flytte det ene `.dt-time`-felt ned i samme række-struktur.

**`applyActivityTypeUI()`** (linje ~1604): skjuler/viser i dag `.dt-hour`/`.dt-sep`/`.dt-min` for dato-kun-aktivitetstyper (ferie, sygdom m.fl., hvor der ikke skal angives et tidspunkt). Skal i stedet blot skjule/vise `.dt-time`.

**`style.css`** (linje 504-506): reglerne for `.dt-picker .dt-hour`/`.dt-min`/`.dt-sep`-bredder erstattes af én regel for `.dt-picker .dt-time`, plus de nye spinner-skjulende regler ovenfor.

## Ikke i scope

- Ingen ændring af `.dt-date`-feltet eller dato-delen af komponenten.
- Ingen backend- eller datamodel-ændringer – de producerede ISO-datotidsstrenge (`YYYY-MM-DDTHH:MM`) er identiske med i dag, så ingen af `app/routers/*.py` eller `app/database/schemas.py` berøres.
- Ingen ændring af hvilke aktivitetstyper der viser/skjuler tidsfeltet (kun *hvordan* feltet er bygget op).

## Test-dækning (til implementeringsplan)

- `buildDatetimePicker("manual-start", "2026-08-24T12:30")` → `.dt-date` har værdien `2026-08-24`, `.dt-time` har værdien `12:30`, ingen `.dt-hour`/`.dt-min`/`.dt-sep`-elementer findes længere i DOM'et.
- `readDatetimePicker("manual-start")` efter ovenstående → returnerer `"2026-08-24T12:30"`.
- `readDatetimePicker(id)` når `.dt-time` er tom → returnerer `"<dato>T00:00"` (bevarer nuværende default-adfærd).
- `setDatetimePicker("manual-start", "2026-08-24T09:15")` → `.dt-time`s værdi bliver `"09:15"`.
- `applyActivityTypeUI()` med en dato-kun-type (fx ferie) → `.dt-time` er skjult (`display:none`); med "Normal tid" → `.dt-time` er synligt.
- Manuel browser-verifikation: opret-aktivitet-modalen, pause-modalen, "Ret starttid/sluttid" i aktivitetsdetaljen, og split-modalen viser alle ét tidsfelt uden synlige op/ned-pile ved hover.
