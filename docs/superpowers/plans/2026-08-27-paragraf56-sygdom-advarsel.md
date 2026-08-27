# §56-advarsel ved oprettelse af Sygdom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opretter en bruger en "Sygdom"-aktivitet for en medarbejder med aktiv §56, skal en advarselsmodal lade brugeren vælge mellem at beholde Sygdom eller skifte til den allerede eksisterende type "§56 syg" (`paragraf_56_syg`).

**Architecture:** Ren frontend – ingen backend-ændringer. En Promise-baseret bekræftelsesmodal indsættes som første handling i `confirmManualActivity()`. Da `sygdom` og `paragraf_56_syg` allerede behandles identisk overalt i `app.js` (feltvisning, periode-oprettelse, validering), er det tilstrækkeligt at ændre værdien af `#manual-type`-selecten FØR resten af funktionen læser den – ingen anden kode skal ændres.

**Tech Stack:** Vanilla JavaScript, ingen build-trin, intet JS-testframework i projektet – verifikation sker manuelt i browseren.

## Global Constraints

- Ingen backend-ændringer.
- Ingen ny fraværstype – `paragraf_56_syg` findes allerede og behandles identisk med `sygdom`.
- Annulleres advarslen (kryds eller klik udenfor), oprettes INGEN aktivitet, og "Tilføj aktivitet"-modalen forbliver åben og uændret.
- Advarslen udløses UDELUKKENDE når den valgte type er præcis `"sygdom"` – ikke andre fraværstyper, heller ikke hvis `paragraf_56_syg` vælges direkte.
- Spec: `docs/superpowers/specs/2026-08-27-paragraf56-sygdom-advarsel-design.md`

---

## Filstruktur

```
app/
  templates/index.html   # MODIFY: ny modal-paragraf56-sygdom-confirm (efter modal-paragraf56-list, linje ~737)
  static/js/app.js        # MODIFY: ny _confirmParagraf56SygdomOverride()/_resolveParagraf56SygdomChoice(),
                           #         nyt tjek som første handling i confirmManualActivity() (linje ~2051)
```

---

## Task 1: §56-advarsel ved oprettelse af Sygdom

**Files:**
- Modify: `app/templates/index.html` (efter linje 737)
- Modify: `app/static/js/app.js` (ny funktioner + `confirmManualActivity()`, linje 2051)

**Interfaces:**
- Consumes: `state.employees` (`paragraf_56`-feltet, allerede indlæst), `h()`, `openModal()`/`closeModal()` (eksisterende hjælpefunktioner)
- Produces: `_confirmParagraf56SygdomOverride(emp) -> Promise<"keep"|"switch"|"cancel">`, `_resolveParagraf56SygdomChoice(choice: string) -> void` – nye globale funktioner i `app.js`

- [ ] **Step 1: Tilføj `modal-paragraf56-sygdom-confirm` i `app/templates/index.html`, lige efter `modal-paragraf56-list`**

Find:

```html
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-paragraf56-list')">Luk</button>
    </div>
  </div>
</div>

<!-- Activity detail modal -->
```

Erstat med:

```html
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-paragraf56-list')">Luk</button>
    </div>
  </div>
</div>

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

<!-- Activity detail modal -->
```

- [ ] **Step 2: Tilføj `_confirmParagraf56SygdomOverride()` og `_resolveParagraf56SygdomChoice()` i `app/static/js/app.js`, lige før `confirmManualActivity()`**

Find:

```js
async function confirmManualActivity() {
  const start   = readDatetimePicker("manual-start");
  const end     = readDatetimePicker("manual-end");
  const actType = document.getElementById("manual-type").value;
  const tilDato = document.getElementById("manual-til-dato").value;
  const empId   = parseInt(document.getElementById("manual-employee").value);

  if (_manualActivityContext.vagtplan && actType === "__none__") {
```

Erstat med:

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

async function confirmManualActivity() {
  if (document.getElementById("manual-type").value === "sygdom") {
    const empForCheck = state.employees.find(e => e.id === parseInt(document.getElementById("manual-employee").value));
    if (empForCheck?.paragraf_56) {
      const choice = await _confirmParagraf56SygdomOverride(empForCheck);
      if (choice === "cancel") return;
      if (choice === "switch") document.getElementById("manual-type").value = "paragraf_56_syg";
    }
  }
  const start   = readDatetimePicker("manual-start");
  const end     = readDatetimePicker("manual-end");
  const actType = document.getElementById("manual-type").value;
  const tilDato = document.getElementById("manual-til-dato").value;
  const empId   = parseInt(document.getElementById("manual-employee").value);

  if (_manualActivityContext.vagtplan && actType === "__none__") {
```

- [ ] **Step 3: Manuel browser-verifikation**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet.

1. Åbn Medarbejdere → find en medarbejder UDEN aktiv §56 → åbn "Tilføj aktivitet" for denne medarbejder, vælg type "Sygdom", udfyld en dato → klik "Opret" → bekræft at aktiviteten oprettes normalt UDEN nogen §56-advarsel.
2. Sæt §56 til på en medarbejder (via "Rediger" på Medarbejdere-siden) med en fremtidig slutdato.
3. Åbn "Tilføj aktivitet" for denne medarbejder, vælg type "Sygdom", udfyld en dato → klik "Opret" → bekræft at advarselsmodalen "Aktiv §56-aftale" vises med medarbejderens navn, FØR noget sendes til serveren.
4. Klik "Ja, behold sygdom" → bekræft at aktiviteten oprettes med type Sygdom (vises som "Sygdom" i aktivitetsoversigten).
5. Gentag punkt 3, men klik denne gang "Nej, ændre til §56" → bekræft at aktiviteten i stedet oprettes med type "§56 syg" (vises korrekt i aktivitetsoversigten som §56 syg, ikke Sygdom).
6. Gentag punkt 3 for en PERIODE-sygdom (udfyld "Til dato" med flere hverdage) → vælg "Nej, ændre til §56" → bekræft at ALLE oprettede aktiviteter i perioden får typen §56 syg.
7. Gentag punkt 3, men luk denne gang advarselsmodalen med krydset → bekræft at INGEN aktivitet oprettes, og at "Tilføj aktivitet"-modalen forbliver åben med de indtastede værdier intakte.
8. Gentag punkt 3, men klik denne gang på den mørke baggrund uden for advarselsmodalen → bekræft samme resultat som punkt 7 (annulleret, ingen hængende tilstand – prøv at åbne "Tilføj aktivitet" igen bagefter og bekræft at alt fungerer normalt).
9. Vælg type "§56 syg" direkte (ikke via advarslen) for en medarbejder MED aktiv §56 → bekræft at INGEN advarsel vises (kun "Sygdom" udløser tjekket).
10. Ryd testdata: deaktiver §56 på testmedarbejderen igen, og slet evt. oprettede testaktiviteter (deaktiver dem via aktivitetsoversigten).

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: §56-advarsel ved oprettelse af Sygdom"
```

---

## Self-Review

**Spec coverage:**
- ✅ Advarsel udløses kun for type=sygdom + aktiv §56 – Step 2
- ✅ "Ja, behold sygdom" → uændret opførsel (inkl. 8-ugers-reglen, urørt) – Step 2 (ingen ændring af eksisterende sygdom-logik)
- ✅ "Nej, ændre til §56" → skifter til allerede eksisterende `paragraf_56_syg`-type – Step 2
- ✅ Annullering (kryds/klik udenfor) blokerer oprettelse uden at hænge – Step 1 (`onclick` på selve overlayet) + Step 2 (`_resolveParagraf56SygdomChoice`)
- ✅ Ingen backend-ændringer – ingen backend-filer i planen
- ✅ Ingen ny fraværstype – genbruger eksisterende `paragraf_56_syg`

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, verifikationstrinnet har konkrete handlinger og forventede resultater.

**Type-konsistens:** `_confirmParagraf56SygdomOverride(emp) -> Promise<"keep"|"switch"|"cancel">` og `_resolveParagraf56SygdomChoice(choice)` defineres i Step 2 og bruges konsistent fra HTML'ens `onclick`-attributter i Step 1 (streng-literalerne `'keep'`/`'switch'`/`'cancel'` matcher præcis de værdier `confirmManualActivity()` sammenligner med). `document.getElementById("manual-type").value` læses to gange (tjek + den oprindelige `actType`-linje) – bevidst, ikke en fejl, da værdien kan være ændret af brugerens valg imellem de to læsninger.
