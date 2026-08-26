# Ét tidsfelt i dt-picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erstat de to separate tt/mm-tekstfelter i den delte `dt-picker`-komponent med ét nativt `<input type="time">`-felt, uden synlige op/ned-pile, overalt hvor komponenten bruges.

**Architecture:** Ren frontend-ændring i fire delte hjælpefunktioner i `app/static/js/app.js` (`buildDatetimePicker`, `readDatetimePicker`, `setDatetimePicker`, `_stackDatetimePicker`) plus ét skjul/vis-sted og CSS. Da alle 8+ brugssteder (opret aktivitet, opret/redigér pause, ret starttid/sluttid, split, segment-resize) går gennem disse samme funktioner med uændrede signaturer, kræver ændringen ingen opdatering af kald-stederne.

**Tech Stack:** Vanilla JavaScript, CSS. Ingen build-trin eller JS-testframework i dette projekt – verifikation sker ved at køre JS-udsagn direkte i browserens konsol (samme metode som virkede for det seneste frontend-arbejde, `node` er ikke installeret i miljøet).

## Global Constraints

- Ingen nye afhængigheder
- Funktionssignaturer (`buildDatetimePicker(id, isoValue)`, `readDatetimePicker(id)`, `setDatetimePicker(id, isoValue)`, `_stackDatetimePicker(id)`) er UÆNDREDE – ingen af de 8+ kald-steder i `app.js` må ændres
- Producerede ISO-datotidsstrenge (`YYYY-MM-DDTHH:MM`) skal være identiske med i dag – ingen backend-/schema-ændringer
- `.dt-date`-feltet og dato-delen af komponenten røres ikke
- Cache-busting af `app.js`/`style.css` sker automatisk ved filændring (`app_js_mtime` i `index.html:1913`) – ingen manuel version-bump
- Spec: `docs/superpowers/specs/2026-08-26-et-tidsfelt-design.md`

---

## Filstruktur

```
app/
  static/js/app.js    # MODIFY: 4 funktioner (linje 1301-1351) + 1 skjul/vis-sted (linje 1601-1609)
  static/css/style.css # MODIFY: linje 503-506 (dt-picker tidsfelt-styling + spinner-fjernelse)
```

---

## Task 1: Ét tidsfelt i dt-picker-komponenten

**Files:**
- Modify: `app/static/js/app.js:1301-1351` (`_stackDatetimePicker`, `buildDatetimePicker`, `readDatetimePicker`, `setDatetimePicker`)
- Modify: `app/static/js/app.js:1601-1609` (skjul/vis-logik i `applyActivityTypeUI`)
- Modify: `app/static/css/style.css:503-506`

**Interfaces:**
- Consumes: ingen nye afhængigheder
- Produces: `buildDatetimePicker(id: string, isoValue: string|null) -> void`, `readDatetimePicker(id: string) -> string|null`, `setDatetimePicker(id: string, isoValue: string) -> void`, `_stackDatetimePicker(id: string) -> void` – alle med uændrede signaturer og returtyper, men bygger/læser nu `.dt-time` i stedet for `.dt-hour`/`.dt-sep`/`.dt-min`

- [ ] **Step 1: Erstat `_stackDatetimePicker` i `app/static/js/app.js`**

Find (linje 1301-1315):

```js
function _stackDatetimePicker(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const dateEl = el.querySelector(".dt-date");
  const hourEl = el.querySelector(".dt-hour");
  const sepEl  = el.querySelector(".dt-sep");
  const minEl  = el.querySelector(".dt-min");
  if (!dateEl || !hourEl || !sepEl || !minEl) return;
  el.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  dateEl.style.width = "100%";
  const timeRow = document.createElement("div");
  timeRow.style.cssText = "display:flex;align-items:center;gap:6px;";
  timeRow.append(hourEl, sepEl, minEl);
  el.append(timeRow);
}
```

Erstat med:

```js
function _stackDatetimePicker(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const dateEl = el.querySelector(".dt-date");
  const timeEl = el.querySelector(".dt-time");
  if (!dateEl || !timeEl) return;
  el.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  dateEl.style.width = "100%";
  const timeRow = document.createElement("div");
  timeRow.style.cssText = "display:flex;align-items:center;gap:6px;";
  timeRow.append(timeEl);
  el.append(timeRow);
}
```

- [ ] **Step 2: Erstat `buildDatetimePicker` i `app/static/js/app.js`**

Find (linje 1317-1332):

```js
function buildDatetimePicker(id, isoValue) {
  const el = document.getElementById(id);
  if (!el) return;
  const date = isoValue ? isoValue.slice(0, 10) : "";
  const hh   = isoValue ? isoValue.slice(11, 13) : "06";
  const mm   = isoValue ? isoValue.slice(14, 16) : "00";
  const S = "padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;background:var(--surface);color:var(--text);box-sizing:border-box;";
  const N = `${S}width:62px;flex:0 0 62px;text-align:center;`;
  el.style.cssText = "display:flex;align-items:center;gap:6px;flex-wrap:nowrap;";
  el.innerHTML = `
    <input type="date"   class="dt-date" value="${date}" style="${S}flex:1 1 0;min-width:0;">
    <input type="text" inputmode="numeric" class="dt-hour" maxlength="2" value="${hh}" style="${N}" placeholder="tt">
    <span  class="dt-sep" style="font-weight:600;color:var(--text-light);flex-shrink:0;">:</span>
    <input type="text" inputmode="numeric" class="dt-min"  maxlength="2" value="${mm}" style="${N}" placeholder="mm">
  `;
}
```

Erstat med:

```js
function buildDatetimePicker(id, isoValue) {
  const el = document.getElementById(id);
  if (!el) return;
  const date = isoValue ? isoValue.slice(0, 10) : "";
  const time = isoValue ? isoValue.slice(11, 16) : "06:00";
  const S = "padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;background:var(--surface);color:var(--text);box-sizing:border-box;";
  const N = `${S}width:110px;flex:0 0 110px;`;
  el.style.cssText = "display:flex;align-items:center;gap:6px;flex-wrap:nowrap;";
  el.innerHTML = `
    <input type="date" class="dt-date" value="${date}" style="${S}flex:1 1 0;min-width:0;">
    <input type="time" class="dt-time" value="${time}" style="${N}">
  `;
}
```

- [ ] **Step 3: Erstat `readDatetimePicker` i `app/static/js/app.js`**

Find (linje 1334-1343):

```js
function readDatetimePicker(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const date = el.querySelector(".dt-date")?.value;
  const hRaw = el.querySelector(".dt-hour")?.value;
  const mRaw = el.querySelector(".dt-min")?.value;
  const hh = String(Math.min(23, Math.max(0, parseInt(hRaw, 10) || 0))).padStart(2, "0");
  const mm = String(Math.min(59, Math.max(0, parseInt(mRaw, 10) || 0))).padStart(2, "0");
  return date ? `${date}T${hh}:${mm}` : null;
}
```

Erstat med:

```js
function readDatetimePicker(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const date = el.querySelector(".dt-date")?.value;
  const time = el.querySelector(".dt-time")?.value;
  return date ? `${date}T${time || "00:00"}` : null;
}
```

- [ ] **Step 4: Erstat `setDatetimePicker` i `app/static/js/app.js`**

Find (linje 1345-1351):

```js
function setDatetimePicker(id, isoValue) {
  const el = document.getElementById(id);
  if (!el || !isoValue) return;
  el.querySelector(".dt-date").value  = isoValue.slice(0, 10);
  el.querySelector(".dt-hour").value  = isoValue.slice(11, 13);
  el.querySelector(".dt-min").value   = isoValue.slice(14, 16);
}
```

Erstat med:

```js
function setDatetimePicker(id, isoValue) {
  const el = document.getElementById(id);
  if (!el || !isoValue) return;
  el.querySelector(".dt-date").value = isoValue.slice(0, 10);
  el.querySelector(".dt-time").value = isoValue.slice(11, 16);
}
```

- [ ] **Step 5: Opdater skjul/vis-logikken i `applyActivityTypeUI` i `app/static/js/app.js`**

Find (linje 1601-1609):

```js
  // Skjul/vis tidsfelterne i startpickeren (kun dato for ferie og sygdom)
  const startEl = document.getElementById("manual-start");
  if (startEl) {
    [".dt-hour", ".dt-sep", ".dt-min"].forEach(sel => {
      const el = startEl.querySelector(sel);
      if (el) el.style.display = isDateOnly ? "none" : "";
    });
    startEl.style.maxWidth = isDateOnly ? "220px" : "";
  }
```

Erstat med:

```js
  // Skjul/vis tidsfeltet i startpickeren (kun dato for ferie og sygdom)
  const startEl = document.getElementById("manual-start");
  if (startEl) {
    const timeEl = startEl.querySelector(".dt-time");
    if (timeEl) timeEl.style.display = isDateOnly ? "none" : "";
    startEl.style.maxWidth = isDateOnly ? "220px" : "";
  }
```

- [ ] **Step 6: Opdater CSS i `app/static/css/style.css`**

Find (linje 503-506):

```css
.dt-picker input[type="date"] { flex: 1 1 0; min-width: 0; width: auto !important; }
.dt-picker .dt-hour,
.dt-picker .dt-min  { flex: 0 0 68px; width: 68px !important; }
.dt-picker .dt-sep  { font-weight: 600; color: var(--text-light); flex-shrink: 0; }
```

Erstat med:

```css
.dt-picker input[type="date"] { flex: 1 1 0; min-width: 0; width: auto !important; }
.dt-picker .dt-time { flex: 0 0 110px; width: 110px !important; }
input[type="time"]::-webkit-inner-spin-button,
input[type="time"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
```

- [ ] **Step 7: Verificér via browser-konsollen at DOM-strukturen er korrekt**

Forudsætning: dev-serveren kører og der er logget ind i browser-panelet (genbrug en allerede kørende session hvis muligt).

Kør i browserens JS-konsol (via `javascript_tool` eller browserens devtools):

```js
buildDatetimePicker("manual-start", "2026-08-24T12:30");
JSON.stringify({
  hasOldFields: !!document.querySelector("#manual-start .dt-hour, #manual-start .dt-sep, #manual-start .dt-min"),
  dateVal: document.querySelector("#manual-start .dt-date").value,
  timeVal: document.querySelector("#manual-start .dt-time").value,
  timeType: document.querySelector("#manual-start .dt-time").type,
});
```

Forventet: `{"hasOldFields":false,"dateVal":"2026-08-24","timeVal":"12:30","timeType":"time"}`

- [ ] **Step 8: Verificér `readDatetimePicker` og default-adfærd for tomt felt**

```js
JSON.stringify({
  normal: readDatetimePicker("manual-start"),
});
```

Forventet: `{"normal":"2026-08-24T12:30"}`

Ryd tidsfeltet og gentest default til `00:00`:

```js
document.querySelector("#manual-start .dt-time").value = "";
readDatetimePicker("manual-start");
```

Forventet: `"2026-08-24T00:00"`

- [ ] **Step 9: Verificér `setDatetimePicker`**

```js
setDatetimePicker("manual-start", "2026-08-24T09:15");
document.querySelector("#manual-start .dt-time").value;
```

Forventet: `"09:15"`

- [ ] **Step 10: Verificér skjul/vis for dato-kun-typer**

Åbn opret-aktivitet-modalen (`openManualActivityModal()`), sæt typen til en dato-kun-type, og bekræft at tidsfeltet skjules:

```js
openManualActivityModal();
document.getElementById("manual-type").value = "ferie";
applyActivityTypeUI();
const hiddenForFerie = document.querySelector("#manual-start .dt-time").style.display === "none";
document.getElementById("manual-type").value = "normal";
applyActivityTypeUI();
const visibleForNormal = document.querySelector("#manual-start .dt-time").style.display !== "none";
JSON.stringify({ hiddenForFerie, visibleForNormal });
```

Forventet: `{"hiddenForFerie":true,"visibleForNormal":true}`

- [ ] **Step 11: Visuel verifikation af de øvrige brugssteder**

Bekræft i browseren (via `read_page`/`get_page_text` eller ved at kalde de relevante åbne-funktioner, jf. tidligere sessions arbejdsmåde når museklik ikke rammer i browser-panelet) at følgende steder også viser ét tidsfelt uden synlige spin-pile:

- Pause-modalen (`addManualPause()` → `pause-start`/`pause-end`)
- "Ret starttid/sluttid" i aktivitetsdetaljen (`edit-start`/`edit-end`)
- Split-modalen (`split-at`)

For hver: kald byggefunktionen og bekræft `.dt-time` findes og `.dt-hour`/`.dt-sep`/`.dt-min` ikke gør, samme mønster som Step 7.

- [ ] **Step 12: Luk alle åbne modaler uden at gemme noget**

```js
closeAllModals();
```

(Dette er kun UI-verifikation – ingen aktivitet eller pause må oprettes eller gemmes i den rigtige database under denne verifikation.)

- [ ] **Step 13: Commit**

```bash
git add app/static/js/app.js app/static/css/style.css
git commit -m "feat: ét tidsfelt (native time-input) i dt-picker-komponenten"
```

---

## Self-Review

**Spec coverage:**
- ✅ `.dt-hour`/`.dt-sep`/`.dt-min` erstattet af ét `<input type="time" class="dt-time">` i alle fire delte funktioner
- ✅ Spinner-pile fjernet via CSS
- ✅ `.dt-date` og dato-logik uændret
- ✅ Alle 8+ brugssteder dækket automatisk, da kun de delte funktioner ændres – signaturer uændrede
- ✅ `applyActivityTypeUI`s skjul/vis-logik opdateret til ny klasse
- ✅ Default til `00:00` ved tomt tidsfelt bevaret (matcher spec'ens test-dækning)
- ✅ Ingen backend-/schema-ændringer nødvendige – verificeret ved at `readDatetimePicker`/`setDatetimePicker` stadig producerer/konsumerer identisk `YYYY-MM-DDTHH:MM`-format

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, alle verifikationstrin har konkrete JS-udsagn og forventede resultater.

**Type-konsistens:**
- Alle fire funktioners signaturer (`buildDatetimePicker(id, isoValue)`, `readDatetimePicker(id) -> string|null`, `setDatetimePicker(id, isoValue)`, `_stackDatetimePicker(id)`) er identiske før og efter – ingen af de 8+ kald-steder i `app.js` (linje 868-869, 1004-1005, 1273, 1756-1759, 1815-1818, 1829-1832, 1886-1887) kræver ændring.
