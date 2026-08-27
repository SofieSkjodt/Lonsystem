# §56-advarsel ved oprettelse af Sygdom – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Når en bruger i "Tilføj aktivitet"-modalen opretter en aktivitet med fraværstype "Sygdom" for en medarbejder der har en aktiv §56-aftale (`Employee.paragraf_56 = true`), skal systemet advare om det og lade brugeren vælge mellem at beholde Sygdom eller skifte til "§56 syg" i stedet.

**Vigtigt fund under kodegennemgang:** "§56 syg" findes allerede som en fuldt fungerende, valgbar fraværstype i systemet – normaliseret nøgle `paragraf_56_syg` (fra `Fraværstyper.xlsx`/`master_absence_types`, normaliseret af `_normalize_type()` i `activities.py`: `"§56 syg"` → `"paragraf_56_syg"`). Den er allerede en del af `_RANGE_TYPES` og `isSygdom`-gruppen i `app.js`, og behandles fuldstændig identisk med `"sygdom"` hvad angår feltvisning, dato-kun-tilstand og periode-oprettelse (`updateManualTypeVisibility()`). Denne opgave handler derfor UDELUKKENDE om selve advarslen/valget – ingen ny fraværstype, ingen ny backend-logik.

## Løsning

### Frontend – `app/static/js/app.js`

Ny hjælpefunktion, der viser en Promise-baseret bekræftelsesmodal:
```js
let _paragraf56SygdomResolve = null;

function _confirmParagraf56SygdomOverride(emp) {
  return new Promise(resolve => {
    _paragraf56SygdomResolve = resolve;
    document.getElementById("paragraf56-sygdom-confirm-body").innerHTML =
      `<p style="font-size:14px">Medarbejder <strong>${h(emp.name)}</strong> har en aktiv §56-aftale. ` +
      `Skal aktiviteten oprettes som almindelig sygdom, eller ændres til §56 syg?</p>`;
    openModal("modal-paragraf56-sygdom-confirm");
  });
}

function _resolveParagraf56SygdomChoice(choice) {
  closeModal("modal-paragraf56-sygdom-confirm");
  if (_paragraf56SygdomResolve) {
    const r = _paragraf56SygdomResolve;
    _paragraf56SygdomResolve = null;
    r(choice);
  }
}
```

I `confirmManualActivity()`, som allerede første handling i funktionen (før nogen validering), indsættes:
```js
if (document.getElementById("manual-type").value === "sygdom") {
  const emp = state.employees.find(e => e.id === parseInt(document.getElementById("manual-employee").value));
  if (emp?.paragraf_56) {
    const choice = await _confirmParagraf56SygdomOverride(emp);
    if (choice === "cancel") return;
    if (choice === "switch") document.getElementById("manual-type").value = "paragraf_56_syg";
  }
}
```
Da funktionens eksisterende `const actType = document.getElementById("manual-type").value;` læses EFTER dette tjek, fanger resten af funktionen automatisk den evt. ændrede type – ingen anden kode i `confirmManualActivity()` skal ændres, da `sygdom`/`paragraf_56_syg` allerede behandles identisk overalt (periode-oprettelse, validering, POST-body).

**Annullering:** Lukkes modalen via krydset eller ved klik uden for modalen, resolves med `"cancel"`, og `confirmManualActivity()` returnerer med det samme uden at oprette noget.

### HTML – `app/templates/index.html`

Ny modal, placeret ved siden af de øvrige §56-modaler:
```html
<div id="modal-paragraf56-sygdom-confirm" class="modal-overlay" onclick="if(event.target===this)_resolveParagraf56SygdomChoice('cancel')">
  <div class="modal" style="width:440px">
    <div class="modal-header">
      <h2>&#9888; Aktiv §56-aftale</h2>
      <button class="modal-close" onclick="_resolveParagraf56SygdomChoice('cancel')">&#215;</button>
    </div>
    <div class="modal-body" id="paragraf56-sygdom-confirm-body"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="_resolveParagraf56SygdomChoice('keep')">Ja, behold sygdom</button>
      <button class="btn btn-primary" onclick="_resolveParagraf56SygdomChoice('switch')">Nej, ændre til §56</button>
    </div>
  </div>
</div>
```
`onclick`-tjekket på selve overlay-diven (`event.target===this`) sikrer at et klik på den mørke baggrund uden for modal-kortet også resolver Promise'et som `"cancel"` – uden dette ville appens generiske "luk ved klik udenfor"-håndtering (bundet én gang på alle `.modal-overlay`-elementer i `init()`) kun skjule modalen visuelt uden at resolve Promise'et, og `confirmManualActivity()`s `await` ville hænge uendeligt.

## Ikke i scope

- Ingen ændring af den eksisterende 8-ugers-anciennitetsregel for Sygdom (`sygdom` → `sygdom_u_8uger` ved <8 ugers ansættelse) – gælder fortsat kun hvis brugeren vælger "Ja, behold sygdom".
- Ingen ændring af redigering af en allerede oprettet aktivitets type – kun selve oprettelsesflowet i "Tilføj aktivitet".
- Ingen ændring af backend (`routers/activities.py`) – ren frontend-beslutning om hvilken `activity_type`-streng der sendes.
- Ingen ændring af Brugervejledningen i denne omgang.

## Test-dækning (til implementeringsplan)

- Opret Sygdom for en medarbejder UDEN aktiv §56 → ingen advarsel, aktiviteten oprettes normalt som i dag.
- Opret Sygdom for en medarbejder MED aktiv §56, vælg "Ja, behold sygdom" → aktiviteten oprettes med `activity_type=sygdom` (evt. `sygdom_u_8uger` hvis <8 ugers anciennitet, uændret).
- Opret Sygdom for en medarbejder MED aktiv §56, vælg "Nej, ændre til §56" → aktiviteten oprettes med `activity_type=paragraf_56_syg`.
- Samme scenarie for en PERIODE-sygdom (Til dato udfyldt, flere hverdage) – bekræft at alle oprettede aktiviteter i perioden får den valgte type.
- Luk advarselsmodalen (kryds eller klik udenfor) → ingen aktivitet oprettes, "Tilføj aktivitet"-modalen forbliver åben og uændret.
- Andre fraværstyper end Sygdom (fx Ferie, §56 syg valgt direkte) udløser ALDRIG advarslen, uanset §56-status.
