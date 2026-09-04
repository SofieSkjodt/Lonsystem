# Bevar ugemte formularrettelser i aktivitets-detaljevisningen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ugemte rettelser i aktivitets-detaljevisningens formularfelter (starttid, sluttid, vognnummer, km, salttillæg, DOB) overlever, når en segment-korrektion, segment-tilpasning eller pause-redigering/-sletning gemmer sig selv med det samme og genindlæser visningen.

**Architecture:** Ét fælles fix i `openActivityDetail(id)` i `app/static/js/app.js`: fanger de aktuelle formularværdier, hvis modalen allerede er åben for samme aktivitet, og genindsætter dem efter formularen er genopbygget med serverens data. Retter automatisk alle fem eksisterende "gem med det samme + genindlæs"-steder uden at røre dem hver for sig.

**Tech Stack:** Vanilla JavaScript, intet build-trin, intet JS-testframework i projektet – verifikation sker manuelt i browseren. Ren frontend-ændring, ingen backend-berøring.

## Global Constraints

- Ingen backend-ændringer
- Ingen ændring af selve gem-mekanismen for segment-korrektion, pause-redigering eller pause-sletning (kun visningen efter kaldet)
- En helt frisk åbning af detaljevisningen (anden aktivitet, eller modalen var lukket) skal fortsat vise serverens aktuelle data uændret
- **Denne session committer/pusher IKKE selv** – alle steps er begrænset til filredigering og verifikation
- Spec: `docs/superpowers/specs/2026-09-04-bevar-utgemte-rettelser-design.md`

---

## Filstruktur

```
app/
  static/js/app.js   # MODIFY: openActivityDetail() (linje 777-900)
```

---

## Task 1: Bevar ugemte formularværdier på tværs af same-id genindlæsning

**Files:**
- Modify: `app/static/js/app.js:777-900`

**Interfaces:**
- Consumes: `readDatetimePicker(id) -> string|null`, `setDatetimePicker(id, isoValue)`, `state.selectedActivityId` (allerede eksisterende)
- Produces: ingen nye funktioner – ren udvidelse af `openActivityDetail()`s eksisterende adfærd, signatur uændret

- [ ] **Step 1: Fang formularværdier ved genåbning af samme aktivitet**

Find starten af funktionen (linje 777-780):

```js
function openActivityDetail(id) {
  state.selectedActivityId = id;
  const a = _findLoadedActivity(id);
  if (!a) return;
```

Erstat med:

```js
function openActivityDetail(id) {
  const modalEl = document.getElementById("modal-activity");
  const reopeningSameActivity = modalEl.classList.contains("open") && state.selectedActivityId === id;
  let preservedEdits = null;
  if (reopeningSameActivity) {
    preservedEdits = {
      start: readDatetimePicker("edit-start"),
      end: readDatetimePicker("edit-end"),
      vehicle: document.getElementById("edit-vehicle")?.value,
      kmStart: document.getElementById("edit-km-start")?.value,
      kmEnd: document.getElementById("edit-km-end")?.value,
      salt: document.getElementById("edit-salt")?.checked,
      dob: document.getElementById("edit-dob")?.checked,
    };
  }
  state.selectedActivityId = id;
  const a = _findLoadedActivity(id);
  if (!a) return;
```

- [ ] **Step 2: Genindsæt de fangede værdier efter formularen er genopbygget**

Find (linje 898-900):

```js
  // Byg datetime-pickers efter innerHTML er sat
  buildDatetimePicker("edit-start", a.start_time.slice(0, 16));
  buildDatetimePicker("edit-end",   a.end_time.slice(0, 16));
```

Erstat med:

```js
  // Byg datetime-pickers efter innerHTML er sat
  buildDatetimePicker("edit-start", a.start_time.slice(0, 16));
  buildDatetimePicker("edit-end",   a.end_time.slice(0, 16));

  if (preservedEdits) {
    if (preservedEdits.start) setDatetimePicker("edit-start", preservedEdits.start);
    if (preservedEdits.end)   setDatetimePicker("edit-end", preservedEdits.end);
    const vehicleEl = document.getElementById("edit-vehicle");
    if (vehicleEl && preservedEdits.vehicle != null) vehicleEl.value = preservedEdits.vehicle;
    const kmStartEl = document.getElementById("edit-km-start");
    if (kmStartEl && preservedEdits.kmStart != null) kmStartEl.value = preservedEdits.kmStart;
    const kmEndEl = document.getElementById("edit-km-end");
    if (kmEndEl && preservedEdits.kmEnd != null) kmEndEl.value = preservedEdits.kmEnd;
    const saltEl = document.getElementById("edit-salt");
    if (saltEl && preservedEdits.salt != null) saltEl.checked = preservedEdits.salt;
    const dobEl = document.getElementById("edit-dob");
    if (dobEl && preservedEdits.dob != null) dobEl.checked = preservedEdits.dob;
  }
```

- [ ] **Step 3: Manuel browser-verifikation – kernescenariet**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet. Find en takograf-importeret aktivitet med mindst én "rest"-segmentlinje, der kan rettes til "Andet arbejde" (`state.activities.find(a => a.segments && a.segments.some(s => s[2] === "rest" && s.length < 4))`).

1. Åbn dens detaljevisning (`openActivityDetail(<id>)`).
2. Ret sluttidsfeltet (`edit-end`) til en ny værdi via `setDatetimePicker("edit-end", "<dato>T<nyt-klokkeslæt>")` – **uden** at trykke "Gem ændringer".
3. Udløs en segment-korrektion på en "rest"-linje via `correctSegment(<id>, <segIdx>)`.
4. Bekræft via `readDatetimePicker("edit-end")` at feltet stadig viser den værdi, du satte i trin 2 – ikke serverens oprindelige sluttid.
5. Bekræft at segmentets type faktisk er rettet (`state.activities.find(a=>a.id===<id>).segments[<segIdx>][2] === "work"`), dvs. selve segment-rettelsen er reelt gemt, uafhængigt af det bevarede formularfelt.

- [ ] **Step 4: Manuel browser-verifikation – de øvrige fire steder**

Gentag samme mønster (ret `edit-end` uden at gemme, udløs handlingen, bekræft `edit-end` er bevaret) for:

1. `correctAllSegments(<id>)` (kræver en aktivitet med mindst én rettelig "rest"-linje).
2. `confirmResizeSegment()`-flowet (åbn via `openResizeSegment(<id>, <segIdx>)`, sæt en ny sluttid i resize-modalen, bekræft).
3. `_confirmActivityPauseEdit()` (via pause-redigeringsflowet – `openActivityPauseEdit(<id>, <idx>)` → ret pausetid → bekræft).
4. `deleteActivityPause(<id>, <idx>)` (kræver en aktivitet med mindst én `pause_intervals`-post – opret evt. en midlertidig test-aktivitet med en pause, hvis ingen findes i den viste periode, og ryd den op igen bagefter).

- [ ] **Step 5: Regressionstjek – frisk åbning er uændret**

1. Luk detaljevisningen helt (`closeModal('modal-activity')`).
2. Åbn en **anden** aktivitet (`openActivityDetail(<andet-id>)`).
3. Bekræft at `edit-start`/`edit-end`/`edit-vehicle` osv. viser netop DENNE aktivitets egne, aktuelle serverværdier – ikke noget bevaret fra en tidligere session.
4. Luk modalen, åbn den SAMME aktivitet igen fra en lukket tilstand (ikke en re-åbning mens den allerede var åben) – bekræft samme ting: friske serverværdier, intet bevaret (da `reopeningSameActivity` kun er sandt, når modalen allerede var åben for samme id).

- [ ] **Step 6: Bekræft at "Gem ændringer" stadig gemmer den bevarede værdi korrekt**

Fra tilstanden opnået i Step 3 (bevaret, ugemt sluttid efter en segment-korrektion): kald `saveActivityTimes()`, og bekræft via `fetch('/api/activities/<id>').then(r=>r.json())` at den gemte `end_time` matcher den værdi, du satte i Step 3 – ikke den oprindelige.

7. Ryd op efter enhver midlertidig test-aktivitet du måtte have oprettet undervejs (deaktiver den, som i tidligere sessioners praksis), og luk modalen.

---

## Self-Review

**Spec coverage:**
- ✅ `openActivityDetail()` bevarer ugemte felter ved genindlæsning af samme aktivitet
- ✅ Dækker alle fem identificerede "gem med det samme + genindlæs"-steder, uden at røre dem hver for sig
- ✅ Frisk åbning (andet id, eller modalen var lukket) er uændret – dækket af Step 5
- ✅ Selve gem-mekanismerne for segment-korrektion/pause er uændrede – kun visningen bagefter

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, verifikationstrinnene har konkrete kald og forventede resultater.

**Type-konsistens:** `preservedEdits`-objektet bruges konsistent mellem Step 1 (fanges) og Step 2 (genindsættes) med samme nøglenavne (`start`, `end`, `vehicle`, `kmStart`, `kmEnd`, `salt`, `dob`). `readDatetimePicker`/`setDatetimePicker` bruges med samme streng-format (`YYYY-MM-DDTHH:MM`, uden sekunder) som de allerede returnerer/forventer andre steder i filen.
