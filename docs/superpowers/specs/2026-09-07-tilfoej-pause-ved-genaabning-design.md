# Tilføj pause ved genåbning af aktivitet – Design

**Dato:** 2026-09-07
**Status:** Godkendt af bruger

## Baggrund

I aktivitetens detaljevisning (`openActivityDetail()` i `app.js`) vises "Pauser"-sektionen i dag kun, hvis aktiviteten allerede har mindst én pause (`(a.pause_intervals && a.pause_intervals.length)`). Findes der ingen pauser, vises sektionen slet ikke – der er ingen måde at tilføje en pause til en allerede oprettet aktivitet. De eksisterende "Ret"/×-knapper (`openActivityPauseEdit()`, `deleteActivityPause()`) kan kun redigere/slette pauser der allerede findes.

**Ønsket ændring:** Har man oprettet en manuel aktivitet uden pause, skal man ved genåbning af den kunne tilføje en pause.

**Afgrænsning (bekræftet af bruger):** Gælder **kun** manuelt oprettede aktiviteter (aktiviteter uden `segments` – uændret fra den eksisterende afgrænsning) **og kun** når aktivitetens status er `pending` (afventer – dvs. en genåbnet eller endnu ikke godkendt aktivitet). De eksisterende "Ret"/×-knapper på allerede oprettede pauser er uændrede og har ingen status-begrænsning i dag – det ændres ikke.

## Løsning

### Visning
Betingelsen for at vise "Pauser"-sektionen ændres fra "kun hvis der allerede er mindst én pause" til "altid for aktiviteter uden `segments`". Er listen tom, vises ingen rækker, men de nye knapper er der (kun når `a.status === "pending"`).

### Nye knapper (kun når `a.status === "pending"`)
"+ Tilføj pause", "12:00–12:30" og "12:00–12:45" – samme tekst/stil som de tilsvarende knapper i opret-aktivitet-modalen.

### Kode-genbrug
- **"+ Tilføj pause"**: ny funktion `openActivityPauseAdd(actId)` sætter `_pauseEditState = { mode: "activity", activityId: actId, idx: null }` og åbner den eksisterende pause-modal (samme modal som "Ret"-knappen bruger), forudfyldt med aktivitetens startdato.
- **De to hurtig-knapper**: ny funktion `addActivityPauseSuggestion(actId, startHHMM, endHHMM)` sætter samme `idx: null`-tilstand og gemmer direkte, uden at åbne modalen.
- **`_confirmActivityPauseEdit()`** udvides: når `idx` er `null`, **tilføjes** den nye pause til listen (`[...a.pause_intervals, [start, end]]`) i stedet for at erstatte et eksisterende indeks (`a.pause_intervals.map(...)`). Samme validering som i dag (pausen skal ligge inden for vagtens tidsrum) gælder uændret for begge veje – både "Ret" af en eksisterende og "Tilføj" af en ny pause.

## Ikke i scope

- Ingen ændring af opret-aktivitet-modalens egen pausefunktion (`addManualPause()`, `addPauseSuggestion()`).
- Ingen ændring af hvordan takograf-aktiviteters segment-baserede pauser håndteres.
- Ingen ny status-begrænsning på de eksisterende "Ret"/×-knapper for allerede oprettede pauser – de forbliver tilgængelige uanset status, som i dag.

## Test-dækning (til implementeringsplan)

- En manuel aktivitet med status `pending` og ingen pauser: "Pauser"-sektionen vises med de tre knapper, ingen rækker.
- Klik på "12:00–12:30" tilføjer pausen med det samme, uden at åbne modalen.
- "+ Tilføj pause" åbner modalen forudfyldt med aktivitetens dato; bekræftelse tilføjer pausen (i stedet for at erstatte en eksisterende).
- Samme validering som ved "Ret" af en eksisterende pause: en pause uden for vagtens tidsrum afvises med samme fejlbesked.
- En manuel aktivitet med status `approved` eller `deactivated`: "+ Tilføj pause"/hurtig-knapperne vises IKKE, men eksisterende "Ret"/×-knapper er uændret tilgængelige (hvis der er pauser).
- En takograf-importeret aktivitet (med `segments`): "Pauser"-sektionen og de nye knapper vises fortsat ikke, uanset status.
