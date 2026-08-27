# Konsistent styling af klokkeslæt-felter – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

I medarbejder-modalens "Timefordeling"-tabel ([index.html:1404](app/templates/index.html:1404)) kan hver dag udfyldes med enten et timetal eller et fra/til-klokkeslæt (`.sched-even-start/-end`, `.sched-odd-start/-end`, se `_scheduleRowCell()` i [app.js:2325](app/static/js/app.js:2325)). Disse felter er rene `<input type="time">` med kun `style="width:88px"` – ingen kant, baggrund eller rundede hjørner – og fremstår derfor med browserens rå standardudseende, i modsætning til alle andre klokkeslæt-felter i appen (aktivitetens start/slut, pausetider), som får en fast, ensartet styling.

**Root cause:** `app/static/css/style.css` har en fælles CSS-regel ([style.css:475-489](app/static/css/style.css:475)) der styler `input[type="text"]`, `input[type="date"]`, `input[type="datetime-local"]`, `input[type="number"]`, `select` og `textarea` ens (kant, `border-radius`, baggrund `var(--surface)`, tekstfarve `var(--text)`, `font-size:13px`). `input[type="time"]` mangler i denne liste – ved en fejl, ikke bevidst, jf. at `.dt-picker`-CSS'en ([style.css:496-504](app/static/css/style.css:496)) allerede forudsætter at `.dt-time`-felter har samme visuelle udtryk som resten. De øvrige klokkeslæt-felter i appen omgår hullet ved at få styling inlinet direkte i JS (`buildDatetimePicker()`s `S`/`N`-konstanter, [app.js:1320-1325](app/static/js/app.js:1320)) – Timefordelingens felter bygges derimod direkte i HTML-templaten uden denne inline-styling.

## Løsning

Tilføj `input[type="time"]` til den eksisterende selector-liste i `style.css:475-480`:

```css
input[type="text"],
input[type="date"],
input[type="datetime-local"],
input[type="number"],
input[type="time"],
select,
textarea {
  ...
}
```

## Effekt og afgrænsning

- Timefordelingens fire klokkeslæt-felter pr. dag (even-start/-end, odd-start/-end) får samme kant/baggrund/rundede hjørner som resten af appens inputs.
- Deres eksisterende inline `style="width:88px"` fortsætter uændret (inline style har højere specificitet end den generelle CSS-regel, så bredden ændres ikke).
- Ingen anden del af appen påvirkes visuelt: der findes kun to andre steder med `input[type="time"]` i kodebasen (`.dt-time` i `buildDatetimePicker()`, brugt til aktivitet-start/-slut og pauser) – de har allerede identisk styling via inline JS-styles, som fortsat vinder over den nye CSS-regel, så der sker ingen ændring der.
- Ingen JS- eller HTML-ændringer nødvendige – ren CSS-tilføjelse.

## Cache-busting

`index.html`s `style.css?v=N`-versionsnummer skal bumpes ét trin ved implementeringen, ellers risikerer browsere med cachet CSS at forblive på det gamle, ustylede udseende (kendt faldgrube i projektet, jf. CODEREF.md).

## Test-dækning (til implementeringsplan)

- Åbn medarbejder-modalen (opret eller rediger) og bekræft visuelt at Timefordelingens fra/til-felter nu har samme kant/baggrund/rundede hjørner som fx aktivitetsmodalens start/slut-felter.
- Bekræft at feltbredden (88px) er uændret, og at funktionaliteten (fra/til beregner stadig timetal automatisk) er upåvirket.
- Bekræft at aktivitetens start/slut-felter og pause-felterne ser visuelt uændrede ud efter ændringen.
