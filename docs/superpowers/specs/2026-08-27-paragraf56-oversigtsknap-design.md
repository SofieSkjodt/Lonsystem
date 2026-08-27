# §56-oversigtsknap på Medarbejdere-siden – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

På Medarbejdere-siden ([index.html](app/templates/index.html), `data-view="employees"`) skal der tilføjes en knap "§56" i toolbaren. Klik åbner en modal med navn, start- og slutdato for medarbejdere med igangværende §56 – filtreret af den aktuelt valgte afdeling i toolbarens eksisterende afdelingsfilter (se `docs/superpowers/specs/2026-08-27-medarbejdere-afdelingsfilter-design.md`).

Afklaret under brainstorming:
- Ingen ekstra rettighed – knappen er synlig for alle der kan se Medarbejdere-siden.
- Modalen viser ALTID kun aktive medarbejdere, uanset "Vis inaktive"-fluebenets tilstand.
- Kun afdelingsfilteret slår igennem – ikke søgefeltet.

## Løsning

Rent frontend – ingen backend-/API-ændringer. `state.employees` indeholder allerede alle nødvendige felter (`paragraf_56`, `paragraf_56_start_date`, `paragraf_56_end_date`, `active`, `dispatcher_group`), hentet af `loadEmployees()`/`loadApp()` i dag.

**Knap** i toolbaren ([index.html](app/templates/index.html), employees-view), ved siden af "+ Opret medarbejder":
```html
<button class="btn btn-secondary" onclick="openParagraf56ListModal()">§56</button>
```

**Ny modal** `modal-paragraf56-list`: tabel med kolonnerne Navn, Startdato, Slutdato.

**Ny JS-funktion** `openParagraf56ListModal()`:
1. Læser den aktuelle værdi af `#employee-filter-dispatcher-group` (samme værdisemantik som `renderEmployeeList()` allerede bruger: `""` = alle afdelinger, `"none"` = kun uden gruppe, ellers et gruppe-id).
2. Filtrerer `state.employees` på `active === true && paragraf_56 === true`, og herefter samme afdelingslogik.
3. Sorterer alfabetisk på navn (`localeCompare(..., "da")`, matcher `renderEmployeeList()`).
4. Bygger tabelrækker (navn, `formatDateShort(paragraf_56_start_date)`, `formatDateShort(paragraf_56_end_date)`) – eller en tom-tilstandsbesked hvis ingen matcher.
5. Åbner modalen.

## Ikke i scope

- Ingen ny rettighed.
- Ingen ny API-endpoint – genbruger allerede indlæst `state.employees`.
- Søgefeltet påvirker ikke modalens indhold.
- Ingen ændring af den eksisterende §56-advarsel-popup eller dens logik.

## Test-dækning (til implementeringsplan)

- Klik på §56-knappen uden noget afdelingsfilter valgt viser alle aktive medarbejdere med `paragraf_56=true`, uanset afdeling.
- Vælges en specifik afdeling i filteret først, viser modalen kun aktive §56-medarbejdere i netop den afdeling.
- Vælges "Ingen gruppe", viser modalen kun aktive §56-medarbejdere uden en disponentgruppe.
- En inaktiv medarbejder med `paragraf_56=true` optræder ALDRIG i modalen, uanset "Vis inaktive"-fluebenets tilstand.
- Ingen matchende medarbejdere → tom-tilstandsbesked, ikke en tom tabel.
- Søgefeltets indhold påvirker ikke modalens resultat.
