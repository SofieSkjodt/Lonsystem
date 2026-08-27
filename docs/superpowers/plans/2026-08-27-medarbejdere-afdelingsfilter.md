# Afdelingsfilter på Medarbejdere-siden Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Medarbejdere-siden (`data-view="employees"`) får en ny dropdown i toolbaren, så listen kan afgrænses til én disponentgruppe ("afdeling") ad gangen – eller "Ingen gruppe" for medarbejdere uden tilknytning.

**Architecture:** Ren frontend-ændring i `app/templates/index.html` og `app/static/js/app.js`. Ny `<select>` fyldes af en ny `fillEmployeeDispatcherGroupFilter()`-funktion (samme mønster som den eksisterende `fillDispatcherGroupFilter()` til Aktiviteter-fanen, men uden `visible_in_activity_overview`-begrænsningen og med en ekstra "Ingen gruppe"-mulighed). Filtreringen sker klient-side i `renderEmployeeList()` oven på det eksisterende søgefilter – ingen nye API-kald, da `state.employees` og `state.dispatcherGroups` allerede er indlæst globalt.

**Tech Stack:** Vanilla JavaScript, ingen build-trin, intet JS-testframework i projektet – verifikation sker manuelt i browseren mod den kørende dev-server.

## Global Constraints

- Ingen backend-/API-ændringer.
- Ingen ændring af Aktiviteter-fanens `#filter-dispatcher-group` eller Vagtplans gruppefilter.
- Dropdownen viser ALLE disponentgrupper (ikke kun dem med `visible_in_activity_overview = true`).
- Filteret kombineres (AND) med det eksisterende søgefelt og "Vis inaktive"-checkboxen – ingen ændring af deres eksisterende adfærd.
- Ingen persistering ud over normal side-adfærd (nulstilles ved F5, som søgefeltet).
- Spec: `docs/superpowers/specs/2026-08-27-medarbejdere-afdelingsfilter-design.md`

---

## Filstruktur

```
app/
  templates/index.html   # MODIFY: employees-view toolbar (linje 286-299) – ny <select> tilføjes
  static/js/app.js        # MODIFY: ny fillEmployeeDispatcherGroupFilter() (efter linje 5070),
                           #         renderEmployeeList() filtrering (linje 2277-2312),
                           #         loadApp() (linje 5168-5177), Stamdata-reload (linje 4594-4598),
                           #         init() event-listener (linje 5205-5206)
```

---

## Task 1: Afdelingsfilter på Medarbejdere-siden

**Files:**
- Modify: `app/templates/index.html:286-299`
- Modify: `app/static/js/app.js:5062-5070` (ny funktion indsættes efter), `2277-2312`, `5168-5177`, `4594-4598`, `5205-5206`

**Interfaces:**
- Consumes: `state.dispatcherGroups` (`{id, name, description, visible_in_activity_overview, vehicle_id, vehicle_number}[]`, allerede globalt indlæst), `state.employees` (`{..., dispatcher_group: {id, name, ...} | null}[]`), `h()` (eksisterende escape-hjælpefunktion)
- Produces: `fillEmployeeDispatcherGroupFilter() -> void` – ny global funktion i `app.js`, kaldt fra `loadApp()` og fra Stamdata-dispatcher-group-reload-blokken

- [ ] **Step 1: Tilføj `<select>` i `app/templates/index.html`**

Find (linje 286-299):

```html
    <!-- ══════════════ EMPLOYEES VIEW ══════════════ -->
    <div class="view hidden" data-view="employees">
      <div class="toolbar">
        <h2 style="font-size:16px;font-weight:600">Medarbejdere</h2>
        <div class="spacer"></div>
        <input type="text" id="employee-search" placeholder="Søg navn eller lønnr…"
               style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:220px">
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
          <input type="checkbox" id="show-inactive"> Vis inaktive
        </label>
        <button class="btn btn-primary" data-perm-require="manage_employees" onclick="openNewEmployeeModal()">+ Opret medarbejder</button>
      </div>
      <div id="employee-list"></div>
    </div>
```

Erstat med:

```html
    <!-- ══════════════ EMPLOYEES VIEW ══════════════ -->
    <div class="view hidden" data-view="employees">
      <div class="toolbar">
        <h2 style="font-size:16px;font-weight:600">Medarbejdere</h2>
        <div class="spacer"></div>
        <input type="text" id="employee-search" placeholder="Søg navn eller lønnr…"
               style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:220px">
        <select id="employee-filter-dispatcher-group" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:180px">
          <option value="">Alle afdelinger</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
          <input type="checkbox" id="show-inactive"> Vis inaktive
        </label>
        <button class="btn btn-primary" data-perm-require="manage_employees" onclick="openNewEmployeeModal()">+ Opret medarbejder</button>
      </div>
      <div id="employee-list"></div>
    </div>
```

- [ ] **Step 2: Tilføj `fillEmployeeDispatcherGroupFilter()` i `app/static/js/app.js`**

Find (linje 5062-5071):

```js
function fillDispatcherGroupFilter() {
  const sel = document.getElementById("filter-dispatcher-group");
  if (!sel) return;
  const cur = sel.value;
  const visibleGroups = state.dispatcherGroups.filter(g => g.visible_in_activity_overview);
  sel.innerHTML = `<option value="">Alle afdelinger</option>` +
    visibleGroups.map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
  if (visibleGroups.find(g => String(g.id) === cur)) sel.value = cur;
}

function fillEmployeeFilter() {
```

Erstat med:

```js
function fillDispatcherGroupFilter() {
  const sel = document.getElementById("filter-dispatcher-group");
  if (!sel) return;
  const cur = sel.value;
  const visibleGroups = state.dispatcherGroups.filter(g => g.visible_in_activity_overview);
  sel.innerHTML = `<option value="">Alle afdelinger</option>` +
    visibleGroups.map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
  if (visibleGroups.find(g => String(g.id) === cur)) sel.value = cur;
}

function fillEmployeeDispatcherGroupFilter() {
  const sel = document.getElementById("employee-filter-dispatcher-group");
  if (!sel) return;
  const cur = sel.value;
  const sorted = state.dispatcherGroups.slice().sort((a, b) => a.name.localeCompare(b.name, "da"));
  sel.innerHTML = `<option value="">Alle afdelinger</option>` +
    `<option value="none">Ingen gruppe</option>` +
    sorted.map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

function fillEmployeeFilter() {
```

- [ ] **Step 3: Filtrér på gruppe i `renderEmployeeList()`**

Find (linje 2277-2288):

```js
function renderEmployeeList() {
  const query = (document.getElementById("employee-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("employee-list");
  container.innerHTML = "";
  let emps = state.employees;
  if (query) {
    emps = emps.filter(e =>
      e.name.toLowerCase().includes(query) ||
      String(e.employee_number).toLowerCase().includes(query)
    );
  }
  emps = emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"));
```

Erstat med:

```js
function renderEmployeeList() {
  const query = (document.getElementById("employee-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("employee-list");
  container.innerHTML = "";
  let emps = state.employees;
  if (query) {
    emps = emps.filter(e =>
      e.name.toLowerCase().includes(query) ||
      String(e.employee_number).toLowerCase().includes(query)
    );
  }
  const groupFilter = document.getElementById("employee-filter-dispatcher-group")?.value || "";
  if (groupFilter === "none") {
    emps = emps.filter(e => !e.dispatcher_group);
  } else if (groupFilter) {
    emps = emps.filter(e => e.dispatcher_group?.id === parseInt(groupFilter));
  }
  emps = emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"));
```

- [ ] **Step 4: Fyld dropdownen ved app-opstart**

Find (linje 5168-5177):

```js
async function loadApp() {
  try {
    [state.employees, state.vehicles, state.dispatcherGroups] = await Promise.all([
      GET("/api/employees"),
      GET("/api/vehicles"),
      GET("/api/employees/dispatcher-groups"),
    ]);
    fillDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (e) { console.error(e); }
```

Erstat med:

```js
async function loadApp() {
  try {
    [state.employees, state.vehicles, state.dispatcherGroups] = await Promise.all([
      GET("/api/employees"),
      GET("/api/vehicles"),
      GET("/api/employees/dispatcher-groups"),
    ]);
    fillDispatcherGroupFilter();
    fillEmployeeDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (e) { console.error(e); }
```

- [ ] **Step 5: Genopfrisk dropdownen når disponentgrupper ændres i Stamdata**

Find (linje 4593-4598):

```js
  // Ny/ændret gruppe kan påvirke medarbejder-modal og filtre
  try {
    state.dispatcherGroups = await GET("/api/employees/dispatcher-groups");
    fillDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (_) {}
```

Erstat med:

```js
  // Ny/ændret gruppe kan påvirke medarbejder-modal og filtre
  try {
    state.dispatcherGroups = await GET("/api/employees/dispatcher-groups");
    fillDispatcherGroupFilter();
    fillEmployeeDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (_) {}
```

- [ ] **Step 6: Tilføj `change`-listener i `init()`**

Find (linje 5205-5206):

```js
  document.getElementById("show-inactive")?.addEventListener("change", loadEmployees);
  document.getElementById("employee-search")?.addEventListener("input", renderEmployeeList);
```

Erstat med:

```js
  document.getElementById("show-inactive")?.addEventListener("change", loadEmployees);
  document.getElementById("employee-search")?.addEventListener("input", renderEmployeeList);
  document.getElementById("employee-filter-dispatcher-group")?.addEventListener("change", renderEmployeeList);
```

- [ ] **Step 7: Manuel browser-verifikation**

Forudsætning: dev-serveren kører (`cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`), og der er logget ind i browser-panelet med en bruger der har `manage_employees` (for at kunne se "Rediger"-knapperne, ikke påkrævet for selve filteret).

1. Åbn Medarbejdere-fanen (sidebar → "Medarbejdere") → bekræft at den nye dropdown vises mellem søgefeltet og "Vis inaktive"-checkboxen, med "Alle afdelinger" valgt som default.
2. Åbn dropdownen → bekræft at den indeholder "Alle afdelinger", "Ingen gruppe" og alle disponentgrupper alfabetisk sorteret – inkl. evt. grupper der i Stamdata → Disponentgrupper har "Vis i aktivitetsoversigt" sat til Nej (til forskel fra Aktiviteter-fanens eget afdelingsfilter, som skjuler dem).
3. Vælg en specifik afdeling → bekræft at kun medarbejdere med den disponentgruppe vises i listen (sammenlign antal med det tal, der står ud for gruppen i Stamdata → Disponentgrupper).
4. Vælg "Ingen gruppe" → bekræft at kun medarbejdere uden nogen disponentgruppe vises.
5. Med en afdeling valgt, skriv noget i søgefeltet → bekræft at listen indsnævres yderligere til navne/lønnumre der matcher inden for den valgte afdeling (AND-kombination).
6. Med en afdeling valgt, sæt flueben i "Vis inaktive" → bekræft at inaktive medarbejdere fra samme afdeling nu også vises, og at det valgte afdelingsfilter forbliver uændret (ikke nulstillet af `loadEmployees()`-genindlæsningen).
7. Vælg "Alle afdelinger" igen → bekræft at hele listen vises igen (minus evt. søgefilter).
8. Gå til Stamdata → Disponentgrupper, opret en ny testgruppe (fx "Test-afdeling") → skift tilbage til Medarbejdere uden at genindlæse siden → åbn dropdownen igen → bekræft at "Test-afdeling" nu er i listen. Slet testgruppen igen bagefter.
9. Genindlæs siden (F5) → bekræft at dropdownen nulstiller til "Alle afdelinger", som søgefeltet også nulstilles.

- [ ] **Step 8: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: afdelingsfilter på Medarbejdere-siden"
```

---

## Self-Review

**Spec coverage:**
- ✅ Simpel enkelt-valg dropdown (ikke multi-select) – Step 1
- ✅ "Alle afdelinger" + "Ingen gruppe" + alle disponentgrupper (ikke kun `visible_in_activity_overview`) – Step 2
- ✅ Klient-side filtrering oven på eksisterende søgefilter – Step 3
- ✅ Dropdown fyldt ved app-opstart uden ekstra API-kald – Step 4
- ✅ Dropdown genopfriskes ved ændringer i Stamdata → Disponentgrupper – Step 5
- ✅ `change`-lytter, ingen ny fetch – Step 6
- ✅ Ingen ændring af Aktiviteter-/Vagtplan-filtre, ingen backend-ændring – ingen af disse filer røres i planen

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, verifikationstrinnet har konkrete handlinger og forventede resultater.

**Type-konsistens:** `fillEmployeeDispatcherGroupFilter() -> void` bruges konsistent på tværs af Step 2 (definition), Step 4 og Step 5 (kald). `groupFilter`-værdien (`""` / `"none"` / streng-id) fra dropdownen i Step 3 matcher `<option value="...">`-værdierne defineret i Step 1 og Step 2. Ingen navnekollision med eksisterende funktioner (`fillDispatcherGroupFilter` vs. `fillEmployeeDispatcherGroupFilter` er bevidst adskilte navne).
