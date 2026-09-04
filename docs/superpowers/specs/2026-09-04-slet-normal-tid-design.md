# Permanent sletning af manuelt oprettet normal tid – Design

**Dato:** 2026-09-04
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Commit `f16d743` ("Fravær slettes fra både vagtplan og aktivitetsoversigt. Slettes permanent") tilføjede en "Slet aktiviteten helt"-checkbox i deaktiver-modalen samt `DELETE /api/activities/{id}`-endpointet. Funktionen er i dag begrænset til fraværstyper (`activity_type != "normal"`) – checkboksen skjules, og backend afviser eksplicit forsøg på at slette `normal`-tid-aktiviteter.

**Ønsket ændring:** En manuelt oprettet normal-tid-aktivitet (fx en fejloprettet vagt via Aktivitetsoversigten) skal også kunne slettes permanent – ikke kun deaktiveres. Da normal tid aldrig overføres til Vagtplan, er "fjernes fra Vagtplan"-delen af den eksisterende funktion ikke relevant for denne type.

**Vigtig afgrænsning (bekræftet af bruger):** Takograf-importerede (system-oprettede) normal-tid-aktiviteter er **ikke** omfattet – de kan fortsat kun deaktiveres, ikke slettes helt. Kun manuelt oprettede (`source == "manual"`) normal-tid-aktiviteter kan slettes permanent.

## Løsning

### Backend (`app/routers/activities.py`, `delete_activity()`)

Den nuværende ubetingede afvisning af `activity_type == "normal"` erstattes af en kildebetinget afvisning:

```python
if a.activity_type == "normal" and a.source != ActivitySource.manual:
    raise HTTPException(400, "Kun manuelt oprettede aktiviteter med normal tid kan slettes helt")
```

Fraværstyper er fuldstændig uændrede (kan altid slettes, uanset kilde, som i dag). `split_children`-tjekket bevares uændret.

### Frontend (`app/static/js/app.js`, `openDeactivateModal()`)

Checkbox-gruppens synlighedsbetingelse udvides fra "ikke normal tid" til "ikke normal tid, ELLER manuelt oprettet normal tid":

```js
(a && (a.activity_type !== "normal" || a.is_manual)) ? "" : "none"
```

`a.is_manual` er allerede et eksisterende felt på aktivitetsobjektet (`source === "manual"`), så ingen ny data er nødvendig.

**Oversigt over resulterende synlighed:**

| Type | Kilde | Checkbox ved deaktivering |
|---|---|---|
| Fravær (enhver type) | Manuelt/Vagtplan | Vises (uændret) |
| Normal tid | Manuelt (`is_manual: true`) | Vises (nyt) |
| Normal tid | System/takograf (`is_manual: false`) | Vises ikke (uændret) |

### Dynamisk checkbox-tekst (`app/templates/index.html` + `app.js`)

Den beskrivende tekst i checkbox-label'en pakkes ind i et `<span>` med et id, så den kan sættes dynamisk fra JS:

- Fravær: "Slet aktiviteten helt (fjernes permanent fra både Vagtplan og Aktivitetsoversigt)" – uændret.
- Normal tid (manuelt): "Slet aktiviteten helt (fjernes permanent fra Aktivitetsoversigt)" – uden Vagtplan-nævnelse, da normal tid aldrig har været der.

### Tests

Den eksisterende test `test_delete_activity_rejects_normal_activity_type` i `tests/test_vagtplan.py` (som i dag bekræfter at ALT normal tid afvises) erstattes, da den nu er forkert for det manuelle tilfælde. Ny testdækning:

- Manuelt oprettet normal-tid-aktivitet kan slettes permanent (`source == "manual"`).
- Takograf-importeret (`source == "tachograph"`) normal-tid-aktivitet afvises fortsat med 400.

## Ikke i scope

- Ingen ændring af deaktiverings-flowet (`POST /{id}/deactivate`) i sig selv.
- Ingen ændring af hvordan takograf-data importeres eller genimporteres.
- Ingen ændring af fraværstypers eksisterende slette-adfærd.

## Test-dækning (til implementeringsplan)

- `delete_activity()` med manuelt oprettet normal-tid-aktivitet → sletter succesfuldt.
- `delete_activity()` med takograf-importeret normal-tid-aktivitet → 400-fejl med den nye fejlbesked.
- `delete_activity()` med enhver fraværstype, uanset kilde → sletter succesfuldt (uændret, eksisterende test bevares).
- `delete_activity()` med splittet aktivitet → fortsat 400-fejl (uændret, eksisterende test bevares).
- Frontend: `openDeactivateModal()` viser checkbox-gruppen for manuelt oprettet normal tid, skjuler den for takograf-importeret normal tid, og viser fortsat for fravær.
- Frontend: checkbox-tekst er korrekt for hhv. fravær og manuel normal tid.
