# Pauseforslag ved oprettelse af aktivitet – Design

**Dato:** 2026-08-26
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

I opret-aktivitet-modalen (`modal-manual-activity`) kan brugeren i dag tilføje en pause via "+ Tilføj pause"-knappen i "Pauser"-sektionen. Det åbner `modal-pause`, hvor brugeren manuelt skal indstille start- og sluttidspunkt for pausen og derefter klikke "Tilføj" (`confirmPause()` i `app.js`).

**Ønsket ændring:** De to mest almindelige pauselængder (12:00–12:30 og 12:00–12:45) skal kunne tilføjes med ét klik, uden at åbne pause-modalen.

## Løsning

### UI
To nye knapper — **"12:00–12:30"** og **"12:00–12:45"** — tilføjes i `manual-pause-section` i `app/templates/index.html`, ved siden af den eksisterende "+ Tilføj pause"-knap. Samme `btn btn-secondary`-styling og skriftstørrelse som "+ Tilføj pause".

Tidsformatet i knapperne bruger kolon (`HH:MM`), i tråd med resten af appens tidsvisning (fx pauselisten i `renderManualPauses()`), ikke punktum.

### Adfærd
Klik på en forslagsknap tilføjer pausen **med det samme** – ingen modal, ingen ekstra bekræftelsesklik. Pausens dato er aktivitetens startdato (samme som `addManualPause()` bruger i dag).

Samme validering som den eksisterende pause-modal genbruges 1:1:
- Er aktivitetens starttidspunkt ikke udfyldt endnu → samme fejl som i dag: "Angiv starttidspunkt for aktiviteten først".
- Ligger den foreslåede pause uden for aktivitetens tidsrum (starter før vagten begynder, eller slutter efter vagten er slut) → samme fejlbeskeder som `confirmPause()` bruger i dag ("Pausen starter (HH:MM) før vagten begynder (HH:MM)" / "Pausen slutter (HH:MM) efter vagten er slut (HH:MM)").

Forslagsknapperne vises **altid**, uanset aktivitetens tidsrum – der er ingen dynamisk vis/skjul-logik baseret på om 12:00 ligger inden for vagten. Rammer klikket uden for tidsrummet, vises blot fejlbeskeden i stedet for at pausen tilføjes.

### Kode-genbrug
`confirmPause()`'s "opret"-gren (linje ~1772-1789 i `app.js`) indeholder i dag: valider mod aktivitetens start/slut → byg `entry` → indsæt/opdater i `manualPauses` → `renderManualPauses()`. Denne logik udtrækkes til en ny delt hjælpefunktion, f.eks.:

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
```

`confirmPause()`'s opret-gren kalder denne funktion i stedet for at duplikere logikken. De to nye genvejsknapper kalder en ny funktion, f.eks. `addPauseSuggestion(startHHMM, endHHMM)`, som:
1. Læser aktivitetens starttidspunkt (`readDatetimePicker("manual-start")`) for at finde datoen. Er det tomt, vises "Angiv starttidspunkt for aktiviteten først" (samme som `addManualPause()`), og der returneres uden at tilføje noget.
2. Bygger `startIso`/`endIso` af `dateStr + "T" + startHHMM` / `dateStr + "T" + endHHMM`.
3. Sætter `_pauseEditState = { mode: "create", idx: null }` (så det altid tilføjer en ny pause, aldrig overskriver en eksisterende ved en fejl).
4. Kalder `_validateAndStoreManualPause(startIso, endIso)`.

### Afgrænsning
Kun opret-aktivitet-modalens pause-flow (`manualPauses`-arrayet) berøres. Redigering af pauser på en allerede oprettet aktivitet (`_pauseEditState.mode === "activity"`, kaldt fra aktivitetsdetalje-visningen) ændres ikke.

## Test-dækning (til implementeringsplan)

- Klik på "12:00–12:30" på en aktivitet 06:00–14:00 → pause `[dato+"T12:00:00", dato+"T12:30:00"]` tilføjes til `manualPauses`, listen re-renderes med "Pause 1".
- Klik på "12:00–12:45" derefter → endnu en pause tilføjes (nu "Pause 2") – begge bevares, ingen automatisk fjernelse af den første.
- Klik på et forslag uden at aktivitetens starttidspunkt er udfyldt → fejltoast, ingen pause tilføjes.
- Klik på "12:00–12:30" på en aktivitet 18:00–02:00 (nattevagt, dækker ikke kl. 12) → fejltoast om at pausen ligger uden for vagten, ingen pause tilføjes.
- Den eksisterende "+ Tilføj pause"-modal virker uændret (opret og redigér af brugerdefinerede pausetider).
