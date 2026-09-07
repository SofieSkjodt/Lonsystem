# Tilføj pause ved genåbning af aktivitet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** I aktivitetens detaljevisning kan man ved en genåbnet (status `pending`) manuel aktivitet tilføje en ny pause – enten via to hurtig-knapper ("12:00–12:30"/"12:00–12:45") eller via en "+ Tilføj pause"-knap der åbner pause-modalen – i stedet for kun at kunne redigere/slette allerede eksisterende pauser.

**Architecture:** Ren frontend-ændring i `app/static/js/app.js`. "Pauser"-sektionen i `openActivityDetail()` vises fremover altid for aktiviteter uden `segments` (ikke kun når der allerede findes pauser), og får tre nye knapper når `a.status === "pending"`. To nye funktioner (`openActivityPauseAdd`, `addActivityPauseSuggestion`) genbruger den eksisterende pause-modal og `_pauseEditState`-mekanismen med `idx: null` som markør for "tilføj". `_confirmActivityPauseEdit()` udvides til at håndtere `idx === null` som append i stedet for erstatning.

**Tech Stack:** Vanilla JavaScript, intet build-trin, intet JS-testframework i projektet – verifikation sker manuelt i browseren.

## Global Constraints

- Gælder kun manuelt oprettede aktiviteter (`!a.segments || !a.segments.length`)
- De nye knapper vises kun når `a.status === "pending"`
- Ingen ny status-begrænsning på de eksisterende "Ret"/×-knapper (`act-pause-edit-btn`, `act-pause-del-btn`) – de forbliver uændrede
- Samme validering som i dag gælder for både "Ret" og "Tilføj" (pausen skal ligge inden for vagtens tidsrum, ellers samme fejlbesked)
- Ingen ændring af opret-aktivitet-modalens egen pausefunktion (`addManualPause()`, `addPauseSuggestion()`)
- Ingen ændring af takograf-aktiviteters segment-baserede pausehåndtering
- **Denne session committer/pusher IKKE selv** – kun filredigering og verifikation
- Spec: `docs/superpowers/specs/2026-09-07-tilfoej-pause-ved-genaabning-design.md`

---

## Task 1: Vis "Pauser"-sektionen altid + nye knapper for pending aktiviteter

**Files:**
- Modify: `app/static/js/app.js:893-906` (pause-sektionens rendering i `openActivityDetail()`)

**Interfaces:**
- Consumes: `a` (den aktivitet der vises, med felterne `segments`, `pause_intervals`, `status`, `id`) – allerede i scope i `openActivityDetail()`
- Produces: HTML-knapperne `act-pause-add-btn` (data-id) og `act-pause-suggest-btn` (data-id, data-start, data-end) som Task 3 wirer op til nye funktioner

- [ ] **Step 1: Opdater visningsbetingelsen og tilføj knapperne**

Find (linje 893-906):

```js
    ${renderSegmentTable(a)}
    ${(!a.segments || !a.segments.length) && (a.pause_intervals && a.pause_intervals.length) ? `
    <div class="form-group mt-16">
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light)">Pauser (fratrækkes i tidsrummet de afholdes)</label>
      <div style="font-size:13px;padding:4px 8px;background:var(--bg);border-radius:4px">
        ${a.pause_intervals.map((p, i) => `
          <div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid var(--border,#e5e7eb)">
            <span style="flex:1">${formatTime(p[0])} – ${formatTime(p[1])}</span>
            <button class="act-pause-edit-btn" data-idx="${i}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer">Ret</button>
            <button class="act-pause-del-btn" data-idx="${i}" data-id="${a.id}" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:16px;line-height:1;padding:0 2px">&times;</button>
          </div>
        `).join("")}
      </div>
    </div>` : ""}
```

Erstat med:

```js
    ${renderSegmentTable(a)}
    ${(!a.segments || !a.segments.length) ? `
    <div class="form-group mt-16">
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light)">Pauser (fratrækkes i tidsrummet de afholdes)</label>
      ${(a.pause_intervals && a.pause_intervals.length) ? `
      <div style="font-size:13px;padding:4px 8px;background:var(--bg);border-radius:4px">
        ${a.pause_intervals.map((p, i) => `
          <div style="display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid var(--border,#e5e7eb)">
            <span style="flex:1">${formatTime(p[0])} – ${formatTime(p[1])}</span>
            <button class="act-pause-edit-btn" data-idx="${i}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer">Ret</button>
            <button class="act-pause-del-btn" data-idx="${i}" data-id="${a.id}" style="background:none;border:none;color:var(--danger);cursor:pointer;font-size:16px;line-height:1;padding:0 2px">&times;</button>
          </div>
        `).join("")}
      </div>` : ""}
      ${a.status === "pending" ? `
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
        <button type="button" class="btn btn-secondary act-pause-add-btn" data-id="${a.id}" style="font-size:13px;padding:5px 14px">+ Tilføj pause</button>
        <button type="button" class="btn btn-secondary act-pause-suggest-btn" data-id="${a.id}" data-start="12:00" data-end="12:30" style="font-size:13px;padding:5px 14px">12:00–12:30</button>
        <button type="button" class="btn btn-secondary act-pause-suggest-btn" data-id="${a.id}" data-start="12:00" data-end="12:45" style="font-size:13px;padding:5px 14px">12:00–12:45</button>
      </div>` : ""}
    </div>` : ""}
```

- [ ] **Step 2: Verificér i browseren at sektionen nu vises uden eksisterende pauser**

Forudsætning: dev-serveren kører (`preview_start`), der er logget ind.

1. Åbn en manuel aktivitet med status `pending` og ingen pauser (opret evt. en test-aktivitet af typen "normal tid" hvis ingen findes, og ryd den op igen bagefter).
2. Bekræft at "Pauser"-sektionen nu vises med de tre nye knapper og ingen rækker.
3. Åbn en manuel aktivitet med status `approved` (eller `deactivated`) og ingen pauser. Bekræft at "Pauser"-sektionen slet ikke vises (ingen rækker, ingen knapper — uændret fra i dag, da label kun kommer med rækker eller pending-knapper; her er begge fraværende men label vises stadig med tomt indhold — se Step 3 note).
4. Åbn en takograf-importeret aktivitet (med `segments`). Bekræft at "Pauser"-sektionen slet ikke vises, uanset status.

Note til Step 2.3: Bemærk at label'en ("Pauser (fratrækkes...)") altid vises for manuelle aktiviteter uden segments, også uden rækker og uden pending-knapper (fx en `approved` aktivitet uden pauser) — det er en synlig, men harmløs, sideeffekt af at sløjfe `.length`-betingelsen fra ydre container. Bekræft blot at der IKKE er nogen knapper eller rækker i dette tilfælde.

---

## Task 2: Understøt tilføjelse (append) af ny pause i `_confirmActivityPauseEdit`

**Files:**
- Modify: `app/static/js/app.js:1936-1962` (`_confirmActivityPauseEdit`)

**Interfaces:**
- Consumes: `_pauseEditState` (global, sat af Task 3's `openActivityPauseAdd`/`addActivityPauseSuggestion` med `idx: null`, eller af eksisterende `openActivityPauseEdit` med et tal-`idx`)
- Produces: uændret ekstern signatur `_confirmActivityPauseEdit(startIso, endIso)` — kaldes fra `confirmPause()` (linje 1889-1891, uændret) og fra Task 3's `addActivityPauseSuggestion`

- [ ] **Step 1: Udvid append-logikken**

Find (linje 1948-1950):

```js
  const newPauses = a.pause_intervals.map((p, i) =>
    i === idx ? [startIso + ":00", endIso + ":00"] : p
  );
```

Erstat med:

```js
  const newPauses = idx == null
    ? [...(a.pause_intervals || []), [startIso + ":00", endIso + ":00"]]
    : a.pause_intervals.map((p, i) => i === idx ? [startIso + ":00", endIso + ":00"] : p);
```

- [ ] **Step 2: Opdater succes-toasten så den passer til begge veje**

Find (linje 1960, inde i samme funktion):

```js
    toast("Pause opdateret", "success");
```

Erstat med:

```js
    toast(idx == null ? "Pause tilføjet" : "Pause opdateret", "success");
```

- [ ] **Step 3: Verificér manuelt at eksisterende "Ret"-flow stadig virker**

1. Åbn en manuel aktivitet (status `pending`) med mindst én eksisterende pause.
2. Klik "Ret" på pausen, ændr tidspunktet, bekræft.
3. Bekræft toast "Pause opdateret" og at pausen er opdateret (ikke duplikeret) i listen.
4. Ryd op: gendan pausens oprindelige tidspunkt hvis dette var en rigtig produktionsaktivitet.

---

## Task 3: Nye funktioner til at åbne/tilføje pause fra detaljevisningen + knap-wiring

**Files:**
- Modify: `app/static/js/app.js` — tilføj to nye funktioner lige efter `openActivityPauseEdit` (efter linje 1934, før `async function _confirmActivityPauseEdit`)
- Modify: `app/static/js/app.js:964-969` — tilføj wiring for de to nye knap-klasser

**Interfaces:**
- Consumes: `_pauseEditState` (global), `buildDatetimePicker`, `_stackDatetimePicker`, `openModal`, `state.activities`, `_confirmActivityPauseEdit(startIso, endIso)` (fra Task 2)
- Produces: `openActivityPauseAdd(actId)`, `addActivityPauseSuggestion(actId, startHHMM, endHHMM)` — kaldes fra de nye knapper (`act-pause-add-btn`, `act-pause-suggest-btn`) tilføjet i Task 1

- [ ] **Step 1: Tilføj de to nye funktioner**

Indsæt efter linje 1934 (efter `openActivityPauseEdit`'s afsluttende `}`, før `async function _confirmActivityPauseEdit`):

```js
function openActivityPauseAdd(actId) {
  const a = state.activities.find(x => x.id === actId);
  if (!a) return;
  _pauseEditState = { mode: "activity", activityId: actId, idx: null };
  const n = (a.pause_intervals ? a.pause_intervals.length : 0) + 1;
  document.getElementById("pause-modal-title").textContent = "Pause " + n;
  const dateStr = a.start_time.slice(0, 10);
  buildDatetimePicker("pause-start", dateStr + "T00:00");
  buildDatetimePicker("pause-end",   dateStr + "T00:00");
  _stackDatetimePicker("pause-start");
  _stackDatetimePicker("pause-end");
  openModal("modal-pause");
}

function addActivityPauseSuggestion(actId, startHHMM, endHHMM) {
  const a = state.activities.find(x => x.id === actId);
  if (!a) return;
  const dateStr = a.start_time.slice(0, 10);
  _pauseEditState = { mode: "activity", activityId: actId, idx: null };
  _confirmActivityPauseEdit(dateStr + "T" + startHHMM, dateStr + "T" + endHHMM);
}
```

- [ ] **Step 2: Wire de nye knapper op**

Find (linje 964-969, umiddelbart efter `.seg-resize-btn`-wiringen):

```js
  document.querySelectorAll("#modal-activity-body .act-pause-edit-btn").forEach(btn => {
    btn.addEventListener("click", () => openActivityPauseEdit(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
  document.querySelectorAll("#modal-activity-body .act-pause-del-btn").forEach(btn => {
    btn.addEventListener("click", () => deleteActivityPause(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
```

Erstat med:

```js
  document.querySelectorAll("#modal-activity-body .act-pause-edit-btn").forEach(btn => {
    btn.addEventListener("click", () => openActivityPauseEdit(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
  document.querySelectorAll("#modal-activity-body .act-pause-del-btn").forEach(btn => {
    btn.addEventListener("click", () => deleteActivityPause(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
  document.querySelectorAll("#modal-activity-body .act-pause-add-btn").forEach(btn => {
    btn.addEventListener("click", () => openActivityPauseAdd(parseInt(btn.dataset.id)));
  });
  document.querySelectorAll("#modal-activity-body .act-pause-suggest-btn").forEach(btn => {
    btn.addEventListener("click", () => addActivityPauseSuggestion(parseInt(btn.dataset.id), btn.dataset.start, btn.dataset.end));
  });
```

- [ ] **Step 3: Manuel browser-verifikation — hurtig-knap tilføjer pause med det samme**

1. Åbn en manuel aktivitet med status `pending` og ingen pauser (fx samme test-aktivitet som i Task 1, eller opret en ny og ryd op bagefter).
2. Klik "12:00–12:30".
3. Bekræft: pausen tilføjes med det samme (ingen modal åbnes), toast "Pause tilføjet" vises, og pausen fremgår nu i listen med "Ret"/×-knapper.
4. Bekræft at "Sum, effektiv tid" og "Sum, pause" i visningen er opdateret til at afspejle den nye pause.
5. Ryd op: fjern testpausen igen (via ×-knappen) hvis dette var en rigtig produktionsaktivitet, så aktiviteten er tilbage i sin oprindelige tilstand.

- [ ] **Step 4: Manuel browser-verifikation — "+ Tilføj pause" åbner modalen forudfyldt**

1. På samme (eller en anden) manuel `pending`-aktivitet uden pauser, klik "+ Tilføj pause".
2. Bekræft at pause-modalen åbner med titlen "Pause 1" og dato forudfyldt til aktivitetens startdato (tidspunkt 00:00).
3. Indtast et gyldigt tidsrum inden for vagten, klik "Tilføj"/bekræft.
4. Bekræft: modalen lukker, pausen fremgår i listen, toast "Pause tilføjet" vises.
5. Ryd op: fjern testpausen igen hvis dette var en rigtig produktionsaktivitet.

- [ ] **Step 5: Manuel browser-verifikation — validering afviser pause uden for vagtens tidsrum**

1. På en `pending`-aktivitet, klik "+ Tilføj pause", indtast et tidsrum der ligger FØR aktivitetens starttidspunkt.
2. Bekræft fejlbesked: "Pausen starter (HH:MM) før vagten begynder (HH:MM)" — samme besked som ved "Ret" af en eksisterende pause.
3. Gentag med et tidsrum EFTER aktivitetens sluttidspunkt, bekræft: "Pausen slutter (HH:MM) efter vagten er slut (HH:MM)".
4. Bekræft at ingen pause blev tilføjet i begge tilfælde.

- [ ] **Step 6: Manuel browser-verifikation — knapperne vises IKKE for approved/deactivated, "Ret"/× uændret**

1. Åbn en manuel aktivitet med status `approved` (eller `deactivated`) der HAR mindst én eksisterende pause.
2. Bekræft: "+ Tilføj pause"/hurtig-knapperne vises IKKE.
3. Bekræft: de eksisterende "Ret"/×-knapper på de allerede oprettede pauser er stadig synlige og virker som før.

- [ ] **Step 7: Kør fuld test-suite som slutkontrol**

```bash
cd app && python -m pytest ../tests/ -q
```

Forventet: alle tests `PASSED` (ren frontend-ændring, ingen backend-berøring forventes at påvirke resultatet).

---

## Self-Review

**Spec coverage:**
- ✅ Sektionen vises altid for aktiviteter uden `segments` (Task 1)
- ✅ Nye knapper kun ved `status === "pending"` (Task 1)
- ✅ "+ Tilføj pause" åbner modal forudfyldt med aktivitetens dato (Task 3, `openActivityPauseAdd`)
- ✅ Hurtig-knapper gemmer direkte uden at åbne modal (Task 3, `addActivityPauseSuggestion`)
- ✅ `_confirmActivityPauseEdit` udvidet til append ved `idx === null` (Task 2)
- ✅ Samme validering (før vagtstart/efter vagtslut) gælder uændret for begge veje (Task 2 genbruger valideringen 1:1, ingen ændring af valideringslogikken selv)
- ✅ Eksisterende "Ret"/×-knapper uændrede, ingen ny status-begrænsning (Task 1 rører kun den ydre container og de nye knapper, ikke `act-pause-edit-btn`/`act-pause-del-btn`)
- ✅ Ingen ændring af opret-modalens `addManualPause()`/`addPauseSuggestion()` (urørt)
- ✅ Ingen ændring af segment-baseret takograf-pausehåndtering (`renderSegmentTable`, urørt)
- ✅ Alle seks scenarier fra spec'ens "Test-dækning" er dækket af manuelle verifikationssteps (Task 1 Step 2, Task 3 Step 3-6)

**Placeholder-scan:** Ingen TBD/TODO/"tilføj passende fejlhåndtering" — al kode er komplet og eksplicit.

**Type-konsistens:**
- `openActivityPauseAdd(actId)` og `addActivityPauseSuggestion(actId, startHHMM, endHHMM)` matcher navngivningen fra spec'en præcist.
- `_pauseEditState = { mode: "activity", activityId: actId, idx: null }` bruger samme shape som den eksisterende `{ mode: "activity", activityId: actId, idx }` fra `openActivityPauseEdit`.
- `_confirmActivityPauseEdit(startIso, endIso)`-signaturen er uændret; kaldes både fra `confirmPause()` (eksisterende) og direkte fra `addActivityPauseSuggestion` (nyt) — begge veje sætter `_pauseEditState` korrekt inden kald.
- `idx == null` (løs lighed) bruges bevidst for at fange både `undefined` og `null`, konsistent med den eksisterende `_pauseEditState?.idx != null`-tjek i `_validateAndStoreManualPause`.
