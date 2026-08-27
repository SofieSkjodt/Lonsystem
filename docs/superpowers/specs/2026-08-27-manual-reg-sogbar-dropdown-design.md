# Søgbar vogn-dropdown i "Tilføj aktivitet" – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

I disponentgruppe/vognnummer-arbejdet (2026-08-26) blev der bygget en søgbar, brugerdefineret dropdown til vognnummer-feltet i Stamdata → Disponentgrupper-modalen (substring-søgning på tværs af vognnummer og registreringsnummer, klik for at vælge – ikke native `<datalist>`, af hensyn til konsistent søgeadfærd på tværs af browsere).

**Ønsket ændring:** Samme søgbare dropdown skal genbruges på det eksisterende `manual-reg`-felt ("Registreringsnummer \ Vognnummer") i "Tilføj aktivitet"-modalen under Aktivitetsoversigt.

## Løsning

### UI
Et nyt absolut-positioneret resultatpanel `#manual-reg-dropdown` tilføjes under `#manual-reg`-feltet i `app/templates/index.html`, med samme visuelle stil som `#stamdata-dispatcher-vehicle-dropdown` (fast positioneret under feltet, scrollbar ved mange resultater, luk ved klik udenfor).

### Adfærd
- Ved indtastning/fokus filtreres `state.vehicles` på om `vehicle_number` **eller** `registration_number` indeholder den indtastede tekst (case-insensitive, hvor som helst i strengen) – identisk logik med Stamdata-versionen.
- Klik på en række i listen udfylder feltet med vognnummeret og lukker dropdown'en.
- **Ingen** "— Intet —"-mulighed i listen (til forskel fra Stamdata-versionen) – feltet er påkrævet ved oprettelse af en aktivitet, og brugeren kan altid rydde teksten manuelt.
- Den eksisterende hint-tekst under feltet (grøn "Vogn nr. X – reg. Y fundet" / rød "ikke fundet i Vognpark") bevares uændret og skal også opdateres, når et køretøj vælges via dropdown'en – ikke kun ved direkte indtastning som i dag.

### Kode-genbrug
Den nuværende hint-logik er en anonym funktion tildelt `document.getElementById("manual-reg").oninput` hver gang modalen åbnes (i `openManualActivityModal()`). Den udtrækkes til en navngivet funktion, f.eks. `_updateManualRegHint()`, som:
1. Bruges som `oninput`-handler (uændret adfærd ved direkte indtastning).
2. Kaldes eksplicit, når et køretøj vælges fra den nye dropdown.

Selve søge-/render-logikken (filtrering + klikbar liste) genbruges konceptuelt fra `_renderVehicleSearchResults()`/klik-uden-for-lukning i Stamdata-implementeringen, men skrives som en ny, selvstændig funktion for `manual-reg`-feltet (fx `_renderManualRegDropdown()`), da de to felter har forskellig markup-struktur og opdaterer forskellige mål-elementer (`manual-reg` er blot ét tekstfelt uden skjult id-felt, i modsætning til Stamdata-feltets `vehicle_id`-par).

### Ikke i scope
- Ingen ændring af validering, det påkrævede-tjek, eller hvordan feltets værdi (`foundVehicle?.vehicle_number`) sendes til backend ved oprettelse.
- Ingen ændring af Stamdata-implementeringen fra 2026-08-26.

## Test-dækning (til implementeringsplan)

- Indtastning af en delstreng der findes midt i et vognnummer eller registreringsnummer viser det matchende køretøj i dropdown'en.
- Klik på et køretøj i listen udfylder feltet og opdaterer hintet til "fundet"-tilstand.
- Der er ingen "— Intet —"-mulighed i listen.
- Rydning af feltet og indtastning af en ukendt værdi viser fortsat den røde "ikke fundet"-hint, som i dag.
- Den eksisterende validering ("Registreringsnummer / Vognnummer er påkrævet" ved oprettelse) er uændret.
