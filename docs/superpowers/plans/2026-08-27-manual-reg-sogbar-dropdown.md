# Søgbar vogn-dropdown i "Tilføj aktivitet" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vognnummer-feltet (`manual-reg`) i "Tilføj aktivitet"-modalen under Aktivitetsoversigt får samme søgbare, brugerdefinerede dropdown som Stamdata → Disponentgrupper allerede har (substring-søgning i vognnummer/registreringsnummer, klik for at vælge).

**Architecture:** Ren frontend-ændring i `app/static/js/app.js` og `app/templates/index.html`. Den eksisterende anonyme `oninput`-hint-funktion udtrækkes til en navngivet `_updateManualRegHint()`, som både bruges ved direkte indtastning og efter valg fra den nye dropdown. Søge-/render-logikken er en ny, selvstændig funktion (`_renderManualRegDropdown()`), da `manual-reg` er ét almindeligt tekstfelt uden det skjulte id-felt, Stamdata-versionen bruger.

**Tech Stack:** Vanilla JavaScript, ingen build-trin, intet JS-testframework i projektet – verifikation sker manuelt i browseren mod den kørende dev-server.

## Global Constraints

- Ingen nye afhængigheder
- Ingen ændring af validering, det påkrævede-tjek, eller hvordan feltets værdi sendes til backend
- `.oninput`/`.onfocus`-tildelinger (ikke `addEventListener`) genbruges for felter der nulstilles hver gang modalen åbnes, så gentagne åbninger ikke stabler dubletlyttere – samme mønster som feltets eksisterende `oninput`
- Click-uden-for-lukker-dropdown-lytteren tilføjes kun ÉN gang på `document`-niveau (ikke inde i `openManualActivityModal()`), samme mønster som Stamdata-implementeringen
- Spec: `docs/superpowers/specs/2026-08-27-manual-reg-sogbar-dropdown-design.md`

---

## Filstruktur

```
app/
  templates/index.html   # MODIFY: manual-reg-group (linje 845-849) – dropdown-container tilføjes
  static/js/app.js        # MODIFY: udtræk _updateManualRegHint(), tilføj _renderManualRegDropdown()/_selectManualRegVehicle(), opdater oninput-tildeling (linje 1915-1931)
```

---

## Task 1: Søgbar dropdown på manual-reg-feltet

**Files:**
- Modify: `app/templates/index.html:845-849`
- Modify: `app/static/js/app.js:1915-1931` (oninput-tildeling), tilføj nye funktioner før `openManualActivityModal()` (linje 1886)

**Interfaces:**
- Consumes: `state.vehicles` (allerede indlæst globalt, `{id, registration_number, vehicle_number}`), `h()` (eksisterende escape-hjælpefunktion)
- Produces: `_updateManualRegHint() -> void`, `_renderManualRegDropdown(query: string) -> void`, `_selectManualRegVehicle(vehicleNumber: string) -> void` – nye globale funktioner i `app.js`

- [ ] **Step 1: Tilføj dropdown-container i `app/templates/index.html`**

Find (linje 845-849):

```html
      <div class="form-group" id="manual-reg-group">
        <label>Registreringsnummer \ Vognnummer <span style="color:var(--danger)">*</span></label>
        <input type="text" id="manual-reg" placeholder="Fx DF67671 eller 1234" autocomplete="off" style="text-transform:uppercase">
        <div class="form-hint" id="manual-reg-hint" style="margin-top:4px;font-size:12px"></div>
      </div>
```

Erstat med:

```html
      <div class="form-group" id="manual-reg-group" style="position:relative">
        <label>Registreringsnummer \ Vognnummer <span style="color:var(--danger)">*</span></label>
        <input type="text" id="manual-reg" placeholder="Fx DF67671 eller 1234" autocomplete="off" style="text-transform:uppercase">
        <div id="manual-reg-dropdown"
             style="display:none;position:absolute;z-index:20;left:0;right:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);max-height:220px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,.12)"></div>
        <div class="form-hint" id="manual-reg-hint" style="margin-top:4px;font-size:12px"></div>
      </div>
```

- [ ] **Step 2: Tilføj de nye funktioner i `app/static/js/app.js`, før `openManualActivityModal()`**

Find (linje 1886):

```js
function openManualActivityModal(empId = null, dateIso = null, opts = {}) {
```

Tilføj umiddelbart før denne linje:

```js
function _updateManualRegHint() {
  const field = document.getElementById("manual-reg");
  const reg = field.value.trim().toUpperCase();
  field.value = reg;
  const hint = document.getElementById("manual-reg-hint");
  if (!reg) { hint.textContent = ""; return; }
  const v = state.vehicles.find(x =>
    x.registration_number.toUpperCase() === reg ||
    x.vehicle_number.toUpperCase() === reg
  );
  if (v) {
    hint.textContent = `Vogn nr. ${v.vehicle_number} – reg. ${v.registration_number} fundet`;
    hint.style.color = "var(--success, #059669)";
  } else {
    hint.textContent = "Registreringsnummer/vognnummer ikke fundet i Vognpark";
    hint.style.color = "var(--danger, #dc2626)";
  }
}

function _renderManualRegDropdown(query) {
  const dropdown = document.getElementById("manual-reg-dropdown");
  const q = query.trim().toUpperCase();
  const matches = !q ? state.vehicles : state.vehicles.filter(v =>
    v.vehicle_number.toUpperCase().includes(q) || v.registration_number.toUpperCase().includes(q)
  );
  dropdown.innerHTML = matches.length
    ? matches.map(v => `
        <div class="vehicle-search-item" data-num="${h(v.vehicle_number)}"
             style="padding:8px 10px;cursor:pointer;font-size:13px">
          ${h(v.vehicle_number)} <span style="color:var(--text-light)">– ${h(v.registration_number)}</span>
        </div>`).join("")
    : `<div style="padding:8px 10px;color:var(--text-light);font-size:13px">Ingen køretøjer fundet</div>`;
  dropdown.querySelectorAll(".vehicle-search-item").forEach(el => {
    el.addEventListener("mouseover", () => el.style.background = "var(--bg)");
    el.addEventListener("mouseout",  () => el.style.background = "");
    el.addEventListener("click", () => _selectManualRegVehicle(el.dataset.num));
  });
  dropdown.style.display = "block";
}

function _selectManualRegVehicle(vehicleNumber) {
  document.getElementById("manual-reg").value = vehicleNumber;
  document.getElementById("manual-reg-dropdown").style.display = "none";
  _updateManualRegHint();
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#manual-reg, #manual-reg-dropdown")) {
    const dropdown = document.getElementById("manual-reg-dropdown");
    if (dropdown) dropdown.style.display = "none";
  }
});

```

- [ ] **Step 3: Erstat den eksisterende `oninput`-tildeling med de navngivne funktioner**

Find (linje 1915-1931):

```js
  document.getElementById("manual-reg").oninput = function () {
    const reg = this.value.trim().toUpperCase();
    this.value = reg;
    const hint = document.getElementById("manual-reg-hint");
    if (!reg) { hint.textContent = ""; return; }
    const v = state.vehicles.find(x =>
      x.registration_number.toUpperCase() === reg ||
      x.vehicle_number.toUpperCase() === reg
    );
    if (v) {
      hint.textContent = `Vogn nr. ${v.vehicle_number} – reg. ${v.registration_number} fundet`;
      hint.style.color = "var(--success, #059669)";
    } else {
      hint.textContent = "Registreringsnummer/vognnummer ikke fundet i Vognpark";
      hint.style.color = "var(--danger, #dc2626)";
    }
  };
```

Erstat med:

```js
  document.getElementById("manual-reg").oninput = function () {
    _updateManualRegHint();
    _renderManualRegDropdown(this.value);
  };
  document.getElementById("manual-reg").onfocus = function () {
    _renderManualRegDropdown(this.value);
  };
```

- [ ] **Step 4: Manuel browser-verifikation**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet.

1. Åbn "Tilføj aktivitet"-modalen (`openManualActivityModal()`), vælg type "Normal tid".
2. Klik i vognnummer-feltet uden at skrive noget → bekræft at dropdown'en viser alle køretøjer, og at der IKKE er en "— Intet —"-mulighed øverst (til forskel fra Stamdata-versionen).
3. Skriv en delstreng der findes midt i et kendt vognnummer eller registreringsnummer (fx en delstreng af `state.vehicles[0].vehicle_number`) → bekræft at det matchende køretøj vises i listen.
4. Klik på et køretøj i listen → bekræft at feltet udfyldes med vognnummeret, dropdown'en lukker, og hintet nedenunder skifter til den grønne "fundet"-tilstand.
5. Ryd feltet og skriv en værdi der ikke matcher noget køretøj → bekræft at den røde "ikke fundet"-hint fortsat vises, som i dag.
6. Klik uden for feltet/dropdown'en, mens listen er åben → bekræft at den lukker.
7. Bekræft at det eksisterende påkrævede-tjek ved oprettelse er uændret (forsøg at oprette en "Normal tid"-aktivitet med tomt vognnummer-felt → samme fejlbesked som i dag: "Registreringsnummer / Vognnummer er påkrævet").
8. Luk modalen uden at oprette noget – dette er kun UI-verifikation.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: søgbar vogn-dropdown på vognnummer-feltet i Tilføj aktivitet-modalen"
```

---

## Self-Review

**Spec coverage:**
- ✅ Samme substring-søgning på tværs af vognnummer og registreringsnummer som Stamdata-versionen
- ✅ Klik i listen udfylder feltet og lukker dropdown'en
- ✅ Ingen "— Intet —"-mulighed (feltet er påkrævet)
- ✅ Eksisterende hint bevares og opdateres også ved dropdown-valg (`_updateManualRegHint()` udtrukket og genbrugt)
- ✅ Ingen ændring af validering/påkrævet-tjek/backend-payload
- ✅ Ingen ændring af Stamdata-implementeringen

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, verifikationstrinnet har konkrete handlinger og forventede resultater.

**Type-konsistens:**
- `_updateManualRegHint() -> void`, `_renderManualRegDropdown(query: string) -> void`, `_selectManualRegVehicle(vehicleNumber: string) -> void` bruges konsistent i Step 2 og Step 3 – ingen andre steder i `app.js` refererer til disse nye funktioner, så ingen navnekollision at tjekke.

