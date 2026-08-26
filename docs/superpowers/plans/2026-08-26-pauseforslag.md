# Pauseforslag ved oprettelse af aktivitet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tilføj to genvejsknapper ("12:00–12:30" og "12:00–12:45") i opret-aktivitet-modalens "Pauser"-sektion, som tilføjer en pause med det samme uden at åbne pause-modalen.

**Architecture:** Ren frontend-ændring i `app/static/js/app.js` og `app/templates/index.html`. Den eksisterende valideringslogik i `confirmPause()` udtrækkes til en delt hjælpefunktion `_validateAndStoreManualPause()`, som både den eksisterende pause-modal og de to nye genvejsknapper bruger. Ingen backend-ændringer.

**Tech Stack:** Vanilla JavaScript (ingen build-trin, intet test-framework i dette projekt for JS). Verifikation sker via `node --check` for syntaks og manuel afprøvning i browseren mod den kørende dev-server.

## Global Constraints

- Ingen nye afhængigheder (vanilla JS, ingen npm/build-trin i dette projekt)
- `app_js_mtime` cache-busting sker automatisk ved filændring (se `app/templates/index.html:1913`) – ingen manuel version-bump nødvendig
- Tidsformat i UI bruger kolon (`HH:MM`), ikke punktum – jf. resten af appens tidsvisning
- Kun opret-aktivitet-modalens pause-flow (`manualPauses`) berøres – redigering af pauser på en allerede oprettet aktivitet (`_pauseEditState.mode === "activity"`) må IKKE ændre adfærd
- Server kræver ikke genstart ved statiske fil-ændringer (`.js`/`.html`) – kun browser-reload
- Spec: `docs/superpowers/specs/2026-08-26-pauseforslag-design.md`

---

## Filstruktur

```
app/
  static/js/app.js       # MODIFY: udtræk _validateAndStoreManualPause(), tilføj addPauseSuggestion()
  templates/index.html   # MODIFY: to nye knapper i manual-pause-section (linje 855-859)
```

---

## Task 1: Pauseforslags-knapper + delt valideringslogik

**Files:**
- Modify: `app/static/js/app.js:1763-1790` (funktionen `confirmPause()`)
- Modify: `app/templates/index.html:855-859` (`manual-pause-section`)

**Interfaces:**
- Consumes: `readDatetimePicker(id) -> string|null` (findes allerede i `app.js`), `manualPauses: Array<[string,string]>` (modul-global, allerede defineret linje 64), `_pauseEditState` (modul-global, allerede defineret linje 66), `renderManualPauses()`, `toast(message, type)` (findes allerede)
- Produces: `_validateAndStoreManualPause(startIso: string, endIso: string) -> boolean` og `addPauseSuggestion(startHHMM: string, endHHMM: string) -> void`, begge globale funktioner i `app.js`

- [ ] **Step 1: Udtræk delt valideringslogik i `app/static/js/app.js`**

Find den nuværende `confirmPause()`-funktion (linje 1763-1790):

```js
function confirmPause() {
  const startIso = readDatetimePicker("pause-start");
  const endIso   = readDatetimePicker("pause-end");
  if (!startIso || !endIso) { toast("Angiv både start- og sluttidspunkt for pausen", "error"); return; }
  if (endIso <= startIso) { toast("Sluttidspunkt skal være efter starttidspunkt", "error"); return; }
  if (_pauseEditState?.mode === "activity") {
    _confirmActivityPauseEdit(startIso, endIso);
    return;
  }
  const actStart = readDatetimePicker("manual-start");
  const actEnd   = readDatetimePicker("manual-end");
  if (actStart && startIso < actStart) {
    toast(`Pausen starter (${startIso.slice(11, 16)}) før vagten begynder (${actStart.slice(11, 16)})`, "error");
    return;
  }
  if (actEnd && endIso > actEnd) {
    toast(`Pausen slutter (${endIso.slice(11, 16)}) efter vagten er slut (${actEnd.slice(11, 16)})`, "error");
    return;
  }
  const entry = [startIso + ":00", endIso + ":00"];
  if (_pauseEditState?.idx != null) {
    manualPauses[_pauseEditState.idx] = entry;
  } else {
    manualPauses.push(entry);
  }
  renderManualPauses();
  closeModal("modal-pause");
}
```

Erstat med:

```js
function _validateAndStoreManualPause(startIso, endIso) {
  const actStart = readDatetimePicker("manual-start");
  const actEnd   = readDatetimePicker("manual-end");
  if (actStart && startIso < actStart) {
    toast(`Pausen starter (${startIso.slice(11, 16)}) før vagten begynder (${actStart.slice(11, 16)})`, "error");
    return false;
  }
  if (actEnd && endIso > actEnd) {
    toast(`Pausen slutter (${endIso.slice(11, 16)}) efter vagten er slut (${actEnd.slice(11, 16)})`, "error");
    return false;
  }
  const entry = [startIso + ":00", endIso + ":00"];
  if (_pauseEditState?.idx != null) {
    manualPauses[_pauseEditState.idx] = entry;
  } else {
    manualPauses.push(entry);
  }
  renderManualPauses();
  return true;
}

function confirmPause() {
  const startIso = readDatetimePicker("pause-start");
  const endIso   = readDatetimePicker("pause-end");
  if (!startIso || !endIso) { toast("Angiv både start- og sluttidspunkt for pausen", "error"); return; }
  if (endIso <= startIso) { toast("Sluttidspunkt skal være efter starttidspunkt", "error"); return; }
  if (_pauseEditState?.mode === "activity") {
    _confirmActivityPauseEdit(startIso, endIso);
    return;
  }
  if (_validateAndStoreManualPause(startIso, endIso)) {
    closeModal("modal-pause");
  }
}

function addPauseSuggestion(startHHMM, endHHMM) {
  const actStartIso = readDatetimePicker("manual-start");
  if (!actStartIso) { toast("Angiv starttidspunkt for aktiviteten først", "error"); return; }
  const dateStr = actStartIso.slice(0, 10);
  _pauseEditState = { mode: "create", idx: null };
  _validateAndStoreManualPause(dateStr + "T" + startHHMM, dateStr + "T" + endHHMM);
}
```

Bemærk: `mode: "activity"`-grenen i `confirmPause()` er uændret – `_confirmActivityPauseEdit()` kaldes stadig direkte og rammer aldrig den nye hjælpefunktion, så redigering af pauser på en allerede oprettet aktivitet er upåvirket.

- [ ] **Step 2: Tilføj de to genvejsknapper i `app/templates/index.html`**

Find (linje 855-859):

```html
      <div class="form-group" id="manual-pause-section">
        <label style="font-weight:500">Pauser</label>
        <div id="manual-pauses-list"></div>
        <button type="button" class="btn btn-secondary" style="margin-top:6px;font-size:13px;padding:5px 14px" onclick="addManualPause()">+ Tilføj pause</button>
      </div>
```

Erstat med:

```html
      <div class="form-group" id="manual-pause-section">
        <label style="font-weight:500">Pauser</label>
        <div id="manual-pauses-list"></div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
          <button type="button" class="btn btn-secondary" style="font-size:13px;padding:5px 14px" onclick="addManualPause()">+ Tilføj pause</button>
          <button type="button" class="btn btn-secondary" style="font-size:13px;padding:5px 14px" onclick="addPauseSuggestion('12:00', '12:30')">12:00–12:30</button>
          <button type="button" class="btn btn-secondary" style="font-size:13px;padding:5px 14px" onclick="addPauseSuggestion('12:00', '12:45')">12:00–12:45</button>
        </div>
      </div>
```

- [ ] **Step 3: Verificér JS-syntaks**

```bash
cd app/static/js && node --check app.js
```

Forventet: ingen output, exit code 0 (dette projekt har intet build-trin eller unit-test-framework for JS – `node --check` er den eksisterende konvention for at fange syntaksfejl, jf. tidligere brug i denne kodebase).

- [ ] **Step 4: Verificér manuelt i browseren**

Forudsætning: dev-serveren kører (`preview_start` med launch-config `lonsystem`, eller en allerede kørende instans), og der er logget ind i browser-panelet.

1. Åbn opret-aktivitet-modalen (klik "+ Tilføj aktivitet").
2. Udfyld starttid (fx `06:00`) og sluttid (fx `14:00`) for en vilkårlig medarbejder, type "Normal tid".
3. Bekræft at "Pauser"-sektionen nu viser tre knapper: "+ Tilføj pause", "12:00–12:30", "12:00–12:45".
4. Klik "12:00–12:30" → bekræft at "Pause 1" (12:00–12:30 på aktivitetens dato) med det samme fremgår af pause-listen, uden at nogen modal åbnes.
5. Klik "12:00–12:45" → bekræft at "Pause 2" tilføjes ved siden af "Pause 1" (begge bevares).
6. Ryd start-/sluttidsfelterne, og klik et forslag → bekræft fejltoast "Angiv starttidspunkt for aktiviteten først", ingen pause tilføjet.
7. Sæt starttid `18:00` og sluttid `20:00` (uden for kl. 12), klik "12:00–12:30" → bekræft fejltoast om at pausen ligger uden for vagten, ingen pause tilføjet.
8. Bekræft at "+ Tilføj pause" stadig åbner den eksisterende pause-modal og fungerer uændret for et brugerdefineret tidsrum.
9. Luk modalen uden at oprette aktiviteten (dette er kun en UI-verifikation, ingen data skal gemmes i den rigtige database).

- [ ] **Step 5: Commit**

```bash
git add app/static/js/app.js app/templates/index.html
git commit -m "feat: pauseforslag (12:00-12:30 / 12:00-12:45) i opret-aktivitet-modalen"
```

---

## Self-Review

**Spec coverage:**
- ✅ To genvejsknapper med kolon-tidsformat, placeret ved siden af "+ Tilføj pause"
- ✅ Klik tilføjer pausen med det samme, ingen modal/bekræftelse
- ✅ Samme validering og fejlbeskeder som den eksisterende pause-modal (genbrugt via `_validateAndStoreManualPause`)
- ✅ Forslagsknapper vises altid, ingen dynamisk vis/skjul baseret på tidsrum
- ✅ Kun opret-flowet (`_pauseEditState.mode !== "activity"`) påvirkes – eksisterende aktivitets-pause-redigering uændret
- ✅ Alle scenarier fra spec'ens "Test-dækning"-sektion er dækket af verifikationstrinnet (happy path × 2, manglende starttid, uden for tidsrum, uændret eksisterende modal)

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, alle kommandoer er eksakte.

**Type-konsistens:**
- `_validateAndStoreManualPause(startIso: string, endIso: string) -> boolean` defineres i Step 1 og bruges konsistent af både `confirmPause()` og `addPauseSuggestion()`
- `addPauseSuggestion(startHHMM: string, endHHMM: string) -> void` matcher de to `onclick`-kald i Step 2 (`addPauseSuggestion('12:00', '12:30')` / `addPauseSuggestion('12:00', '12:45')`)
