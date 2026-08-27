# §56-oversigtsknap på Medarbejdere-siden Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En ny "§56"-knap i Medarbejdere-toolbaren åbner en modal med navn/start-/slutdato for aktive medarbejdere med igangværende §56, filtreret af den aktuelt valgte afdeling.

**Architecture:** Ren frontend – ingen backend-/API-ændringer. Genbruger allerede indlæst `state.employees` (indeholder `paragraf_56`, `paragraf_56_start_date`, `paragraf_56_end_date`, `active`, `dispatcher_group`) og samme afdelingsfilter-værdi som `renderEmployeeList()` allerede læser fra `#employee-filter-dispatcher-group`.

**Tech Stack:** Vanilla JavaScript, ingen build-trin, intet JS-testframework i projektet – verifikation sker manuelt i browseren.

## Global Constraints

- Ingen backend-/API-ændringer.
- Ingen ny rettighed – knappen er synlig for alle der kan se Medarbejdere-siden.
- Modalen viser ALTID kun aktive medarbejdere (`active === true`), uanset "Vis inaktive"-fluebenets tilstand.
- Kun afdelingsfilteret slår igennem – søgefeltet påvirker ikke modalens indhold.
- Spec: `docs/superpowers/specs/2026-08-27-paragraf56-oversigtsknap-design.md`

---

## Filstruktur

```
app/
  templates/index.html   # MODIFY: ny knap i employees-toolbaren (linje ~299), ny modal-paragraf56-list (efter modal-paragraf56-alert, linje ~712)
  static/js/app.js        # MODIFY: ny openParagraf56ListModal()-funktion
```

---

## Task 1: §56-knap og oversigtsmodal

**Files:**
- Modify: `app/templates/index.html:287-302` (toolbar), efter linje 712 (ny modal)
- Modify: `app/static/js/app.js` (ny funktion ved siden af `renderEmployeeList()`)

**Interfaces:**
- Consumes: `state.employees` (`{..., active, paragraf_56, paragraf_56_start_date, paragraf_56_end_date, dispatcher_group}[]`, allerede globalt indlæst), `formatDateShort()`, `h()` (eksisterende hjælpefunktioner), `#employee-filter-dispatcher-group`s aktuelle værdi
- Produces: `openParagraf56ListModal() -> void` – ny global funktion i `app.js`

- [ ] **Step 1: Tilføj §56-knappen i toolbaren i `app/templates/index.html`**

Find (linje 287-302):

```html
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

Erstat med:

```html
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
        <button class="btn btn-secondary" onclick="openParagraf56ListModal()">§56</button>
        <button class="btn btn-primary" data-perm-require="manage_employees" onclick="openNewEmployeeModal()">+ Opret medarbejder</button>
      </div>
      <div id="employee-list"></div>
    </div>
```

- [ ] **Step 2: Tilføj `modal-paragraf56-list` i `app/templates/index.html`, lige efter `modal-paragraf56-alert`**

Find:

```html
<div id="modal-paragraf56-alert" class="modal-overlay">
  <div class="modal" style="width:460px">
    <div class="modal-header">
      <h2 id="paragraf56-alert-title">&#9888; §56-advarsel</h2>
      <button class="modal-close" onclick="closeModal('modal-paragraf56-alert')">&#215;</button>
    </div>
    <div class="modal-body" id="paragraf56-alert-body"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-paragraf56-alert')">Luk</button>
      <button class="btn btn-warning" id="btn-paragraf56-alert-done">Set – afvis</button>
      <button class="btn btn-primary" id="btn-goto-employee-paragraf56">Gå til medarbejder</button>
    </div>
  </div>
</div>
```

Erstat med:

```html
<div id="modal-paragraf56-alert" class="modal-overlay">
  <div class="modal" style="width:460px">
    <div class="modal-header">
      <h2 id="paragraf56-alert-title">&#9888; §56-advarsel</h2>
      <button class="modal-close" onclick="closeModal('modal-paragraf56-alert')">&#215;</button>
    </div>
    <div class="modal-body" id="paragraf56-alert-body"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-paragraf56-alert')">Luk</button>
      <button class="btn btn-warning" id="btn-paragraf56-alert-done">Set – afvis</button>
      <button class="btn btn-primary" id="btn-goto-employee-paragraf56">Gå til medarbejder</button>
    </div>
  </div>
</div>

<div id="modal-paragraf56-list" class="modal-overlay">
  <div class="modal" style="width:480px;max-width:95vw">
    <div class="modal-header">
      <h2>§56-oversigt</h2>
      <button class="modal-close" onclick="closeModal('modal-paragraf56-list')">&#215;</button>
    </div>
    <div class="modal-body">
      <table style="width:100%;font-size:14px;border-collapse:collapse">
        <thead>
          <tr style="text-align:left;border-bottom:1px solid var(--border)">
            <th style="padding:6px 4px">Navn</th>
            <th style="padding:6px 4px">Startdato</th>
            <th style="padding:6px 4px">Slutdato</th>
          </tr>
        </thead>
        <tbody id="paragraf56-list-body"></tbody>
      </table>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-paragraf56-list')">Luk</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Tilføj `openParagraf56ListModal()` i `app/static/js/app.js`, lige efter `renderEmployeeList()`**

Find:

```js
    div.addEventListener("click", () => {
      if (state.currentUser?.permissions?.includes("manage_employees")) openEditEmployee(e.id);
    });
    container.appendChild(div);
  }
}
```

Erstat med:

```js
    div.addEventListener("click", () => {
      if (state.currentUser?.permissions?.includes("manage_employees")) openEditEmployee(e.id);
    });
    container.appendChild(div);
  }
}

function openParagraf56ListModal() {
  const groupFilter = document.getElementById("employee-filter-dispatcher-group")?.value || "";
  let emps = state.employees.filter(e => e.active && e.paragraf_56);
  if (groupFilter === "none") {
    emps = emps.filter(e => !e.dispatcher_group);
  } else if (groupFilter) {
    emps = emps.filter(e => e.dispatcher_group?.id === parseInt(groupFilter));
  }
  emps = emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"));
  const body = document.getElementById("paragraf56-list-body");
  body.innerHTML = emps.length === 0
    ? `<tr><td colspan="3" style="padding:16px 4px;color:var(--text-light)">Ingen medarbejdere med igangværende §56 i denne afdeling</td></tr>`
    : emps.map(e => `
        <tr>
          <td style="padding:6px 4px;border-bottom:1px solid var(--border)">${h(e.name)}</td>
          <td style="padding:6px 4px;border-bottom:1px solid var(--border)">${formatDateShort(e.paragraf_56_start_date)}</td>
          <td style="padding:6px 4px;border-bottom:1px solid var(--border)">${formatDateShort(e.paragraf_56_end_date)}</td>
        </tr>`).join("");
  openModal("modal-paragraf56-list");
}
```

- [ ] **Step 4: Manuel browser-verifikation**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet.

1. Åbn Medarbejdere-fanen → bekræft at "§56"-knappen vises i toolbaren, ved siden af "+ Opret medarbejder".
2. Uden noget afdelingsfilter valgt, sæt §56 til på 1-2 medarbejdere i forskellige afdelinger (via "Rediger") → klik "§56" → bekræft at modalen viser navn, korrekt startdato og slutdato for alle aktive §56-medarbejdere, sorteret alfabetisk.
3. Vælg en specifik afdeling i afdelingsfilteret → klik "§56" igen → bekræft at modalen nu KUN viser §56-medarbejdere fra den valgte afdeling.
4. Vælg "Ingen gruppe" i afdelingsfilteret → klik "§56" → bekræft at modalen kun viser §56-medarbejdere uden en disponentgruppe.
5. Deaktivér en medarbejder med §56 (sæt "Aktiv" fra) → bekræft at vedkommende IKKE længere optræder i §56-modalen, heller ikke med "Vis inaktive" slået til på selve siden.
6. Skriv noget i søgefeltet der ikke matcher nogen §56-medarbejdere → klik "§56" → bekræft at modalens indhold er UPÅVIRKET af søgefeltet (kun afdelingsfilteret tæller).
7. Vælg en afdeling uden nogen aktive §56-medarbejdere → klik "§56" → bekræft tom-tilstandsbeskeden vises i stedet for en tom tabel.
8. Luk modalen → bekræft normal lukkeadfærd (kryds og "Luk"-knap).

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: §56-oversigtsknap på Medarbejdere-siden"
```

---

## Self-Review

**Spec coverage:**
- ✅ Ny knap, ingen ekstra rettighed – Step 1
- ✅ Ny modal med navn/start-/slutdato – Step 2
- ✅ Filtrerer på aktive + igangværende §56 + samme afdelingsfilter som toolbaren – Step 3
- ✅ Ignorerer søgefelt og "Vis inaktive" – Step 3 (bruger kun `e.active` direkte, ikke det viste/loadede `state.employees`s active_only-tilstand, og læser aldrig `#employee-search`)
- ✅ Tom-tilstand ved ingen match – Step 3
- ✅ Ingen backend-ændringer – ingen backend-filer i planen

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, verifikationstrinnet har konkrete handlinger og forventede resultater.

**Type-konsistens:** `openParagraf56ListModal() -> void` defineres i Step 3 og kaldes fra HTML i Step 1 (`onclick="openParagraf56ListModal()"`). Genbruger `formatDateShort()`/`h()` med samme signaturer som resten af `app.js`. Afdelingsfilter-værdisemantikken (`""`/`"none"`/gruppe-id) matcher præcis `renderEmployeeList()`s eksisterende logik – ingen afvigelse.
