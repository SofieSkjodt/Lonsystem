# Afdelingsfilter på Medarbejdere-siden – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Medarbejdere-siden (`index.html`, `data-view="employees"`) har i dag kun et fritekst-søgefelt (`#employee-search`, matcher navn/lønnummer) og en "Vis inaktive"-afkrydsningsboks. Der findes ingen måde at afgrænse listen til én afdeling (disponentgruppe) ad gangen, i modsætning til Aktiviteter-fanen (`#filter-dispatcher-group`) og Vagtplan-fanen (multi-select gruppefilter). Ønsket er et tilsvarende filter på Medarbejdere-siden.

Under brainstormingen blev det afklaret, at det skal være en **simpel enkelt-valg dropdown** (samme mønster som Aktiviteter-fanen), ikke Vagtplans multi-select afkrydsningspanel.

## 1. Omfang og afgrænsning

- Rent frontend – ingen ændringer i backend, API-endpoints eller schemas. `state.employees` og `state.dispatcherGroups` indeholder allerede alt nødvendigt data (begge hentes fuldt ved app-opstart, se `loadApp()`, [app.js:5168-5177](app/static/js/app.js:5168)).
- Filtrering sker klient-side ved re-rendering af den allerede indlæste `state.employees`-liste, på samme måde som det eksisterende `#employee-search`-felt.
- Ingen ændringer til Aktiviteter- eller Vagtplan-fanens egne filtre.
- Ingen persistering ud over almindelig side-adfærd: valget nulstilles ved fuld sideindlæsning (F5), men bevares ved skift mellem faner i samme session – samme adfærd som `#employee-search` og `#show-inactive` allerede har i dag.

## 2. Dropdown-indhold

Dropdownen viser **alle** disponentgrupper fra `state.dispatcherGroups`, uanset deres `visible_in_activity_overview`-flag i Stamdata. Begrundelse: Medarbejdere er en administrativ side til at finde/redigere alle medarbejdere, og bør derfor ikke skjule grupper, som fx kun er slået fra i aktivitetsoversigten af driftsmæssige årsager.

Rækkefølge og valgmuligheder:
1. `Alle afdelinger` (value `""`, default – intet filter)
2. `Ingen gruppe` (value `"none"` – medarbejdere hvor `e.dispatcher_group` er `null`)
3. Én `<option>` pr. disponentgruppe, alfabetisk sorteret efter navn (value = gruppens `id` som streng)

## 3. HTML-ændring

I `app/templates/index.html`, i toolbaren for `data-view="employees"` ([index.html:288-298](app/templates/index.html:288)), tilføjes en ny `<select>` mellem `#employee-search` og "Vis inaktive"-checkboxen:

```html
<select id="employee-filter-dispatcher-group" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:180px">
  <option value="">Alle afdelinger</option>
</select>
```

Selve indholdet (options 2+3 ovenfor) fyldes af JS, ikke hardkodet i HTML – samme mønster som `fillDispatcherGroupFilter()` i dag.

## 4. JS-ændringer (`app/static/js/app.js`)

**Ny funktion**, placeret ved siden af den eksisterende `fillDispatcherGroupFilter()` ([app.js:5062](app/static/js/app.js:5062)):

```js
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
```

**`renderEmployeeList()`** ([app.js:2277](app/static/js/app.js:2277)) udvides til at læse dropdownens værdi og filtrere yderligere, oven på det eksisterende søgefilter:

```js
const groupFilter = document.getElementById("employee-filter-dispatcher-group")?.value || "";
// ... efter det eksisterende query-filter:
if (groupFilter === "none") {
  emps = emps.filter(e => !e.dispatcher_group);
} else if (groupFilter) {
  emps = emps.filter(e => e.dispatcher_group?.id === parseInt(groupFilter));
}
```

**Kald af `fillEmployeeDispatcherGroupFilter()`:**
- Fra `loadApp()` ([app.js:5168-5177](app/static/js/app.js:5168)), lige efter det eksisterende `fillDispatcherGroupFilter()`-kald, så dropdownen er fyldt inden brugeren første gang besøger fanen.
- Fra det sted i Stamdata → Disponentgrupper hvor `state.dispatcherGroups` genindlæses efter opret/rediger/slet ([app.js:4594-4598](app/static/js/app.js:4594)), lige efter det eksisterende `fillDispatcherGroupFilter()`-kald, så nye/omdøbte/slettede grupper afspejles uden sideopdatering.

**Ny event-listener**, ved siden af de eksisterende `#show-inactive`/`#employee-search`-listeners ([app.js:5205-5206](app/static/js/app.js:5205)):

```js
document.getElementById("employee-filter-dispatcher-group")?.addEventListener("change", renderEmployeeList);
```

Ingen ny fetch ved skift – ren klient-side re-filtrering, ligesom søgefeltet.

## Ikke i scope

- Ingen multi-select.
- Ingen ændring af `#filter-dispatcher-group` (Aktiviteter) eller Vagtplans gruppefilter.
- Ingen serverside-filtrering eller nyt API-parameter.
- Ingen ændring af `#show-inactive`-adfærd – de to filtre kombineres blot (AND) med det eksisterende søgefilter i `renderEmployeeList()`.

## Test-dækning (til implementeringsplan)

- Dropdown indeholder "Alle afdelinger", "Ingen gruppe" og alle disponentgrupper (inkl. dem med `visible_in_activity_overview = false`), alfabetisk sorteret.
- Valg af en specifik afdeling viser kun medarbejdere med den `dispatcher_group.id`.
- Valg af "Ingen gruppe" viser kun medarbejdere uden `dispatcher_group`.
- Kombination af afdelingsfilter + søgefelt + "Vis inaktive" virker sammen (AND-logik) – fx søgning på navn inden for en valgt afdeling.
- Oprettelse/omdøbning/sletning af en disponentgruppe i Stamdata opdaterer dropdownens indhold uden sideopdatering, uden at nulstille et allerede valgt filter (medmindre den valgte gruppe selv blev slettet).
- Sideopdatering (F5) nulstiller filteret til "Alle afdelinger", ligesom søgefeltet nulstilles.
