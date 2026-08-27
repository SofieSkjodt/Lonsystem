# "Al pause til andet arbejde" – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

I aktivitetsdetalje-modalen viser `renderSegmentTable()` (`app.js`) en tabel "Detaljeret information om dagen" med aktivitetens tachograf-segmenter. Hvert pause-segment (`type === "rest"`) har i dag en "Ret linje"-knap, der retter den enkelte linje til "Andet arbejde" via `POST /api/activities/{id}/correct-segment`.

Har en dag mange pauselinjer der alle skal rettes, kræver det i dag ét klik pr. linje.

**Ønsket ændring:** En ny knap "Al pause til andet arbejde" lige over tabellen, der retter alle u-rettede pauselinjer for dagen på én gang – med samme effekt som at klikke "Ret linje" på hver af dem. Hver linje skal fortsat kunne fortrydes individuelt bagefter via "Gendan".

## Løsning

### Backend

Nyt endpoint i `app/routers/activities.py`, indsat lige efter `correct_segment` (linje ~716-758):

```
POST /api/activities/{activity_id}/correct-all-segments
```

Ingen request body. Adfærd:

1. Hent aktiviteten (404 hvis ikke fundet, samme mønster som øvrige endpoints).
2. Byg `segments = [list(seg) for seg in (a.segments or [])]`.
3. Find kandidater: indeks hvor `seg[2] == "rest" and len(seg) < 4` – samme kriterium som `correct_segment` bruger til at afgøre om en linje kan rettes (ikke allerede rettet).
4. Er der ingen kandidater → `HTTPException(400, "Ingen pauselinjer at rette")`. Rammes ikke fra normal UI-brug (knappen er skjult i det tilfælde, se Frontend), men beskytter mod race conditions (fx to åbne faner, eller et direkte API-kald).
5. For hver kandidat: `segments[idx] = seg[:2] + ["work", seg[2]]` – identisk transformation til den enkelte `correct_segment` (uden revert).
6. `a.segments = segments`, `flag_modified(a, "segments")`, `_recalculate_pcts(a)`.
7. **Én** `db.commit()` for hele operationen (atomisk – enten rettes alle kandidater, eller ingen ved fejl).
8. `log_action(db, current_user, "correct_all_segments", "activity", activity_id, {"corrected_count": len(candidates)})` – én hændelse for hele bulk-handlingen, ikke én pr. linje (samme mønster som `auto_approve_bulk`).
9. Returnér `_to_response(a)` (samme returtype som `correct_segment`/`resize_segment`).

Ingen ny permission – samme adgangsniveau som `correct_segment` i dag (kun `get_current_user`).

### Frontend

`app.js`, i `renderSegmentTable(a)`:

- Beregn `const hasCorrectable = a.segments.some(seg => seg[2] === "rest" && seg.length < 4);` øverst i funktionen.
- Indsæt knappen i den returnerede HTML **lige over** labelen "Detaljeret information om dagen", kun hvis `hasCorrectable` er `true`:
  ```html
  ${hasCorrectable ? `<button class="btn btn-secondary" onclick="correctAllSegments(${a.id})" style="margin-bottom:8px">Al pause til andet arbejde</button>` : ""}
  ```
- Ny funktion `correctAllSegments(activityId)`, samme struktur som `correctSegment()`:
  ```js
  async function correctAllSegments(activityId) {
    try {
      const updated = await POST(`/api/activities/${activityId}/correct-all-segments`);
      state.activities = state.activities.map(a => a.id === updated.id ? updated : a);
      const body = document.getElementById("modal-activity-body");
      const scrollTop = body ? body.scrollTop : 0;
      openActivityDetail(activityId);
      if (body) body.scrollTop = scrollTop;
      renderActivitiesTable();
      toast("Alle pauselinjer rettet til 'Andet arbejde'", "success");
    } catch (e) { toast(e.message, "error"); }
  }
  ```

### Uændret

- Den enkelte linjes "Ret linje"/"Gendan"/"Tilpas"-knapper og deres endpoints (`correct-segment`, `resize-segment`) ændres ikke. Efter et bulk-klik viser hver tidligere pause-linje nu en "Gendan"-knap (fordi `correctedFrom` er sat), og fungerer præcis som når en enkelt linje rettes manuelt – ingen særlig "bulk-gendan"-funktion.
- Manuelle aktiviteter uden `segments` (kun `pause_intervals`) er upåvirkede – de har ingen "Ret linje"-knapper i dag og får derfor heller ikke denne knap (`hasCorrectable` er `false` når `a.segments` er tomt).
- Ingen ændring i hvornår knappen vises ift. aktivitetens status (`pending`/`approved`/`deactivated`) – matcher at de eksisterende "Ret linje"/"Tilpas"-knapper heller ikke er statusbegrænsede i dag.

## Test-dækning (til implementeringsplan)

- Aktivitet med 3 pause-segmenter, ingen rettet endnu → knappen vises. Klik → alle 3 bliver `type: "work"` med `correctedFrom: "rest"`, procentfordelingen genberegnes, knappen forsvinder (ingen `hasCorrectable` tilbage), alle 3 linjer viser nu "Gendan".
- Aktivitet med 3 pause-segmenter hvor 1 allerede er rettet manuelt → knappen vises stadig (2 kandidater tilbage). Klik → kun de 2 u-rettede ændres; den allerede rettede linje er upåvirket.
- Klik "Gendan" på én af de bulk-rettede linjer bagefter → kun den ene linje reverteres til `rest`, resten forbliver `work`.
- Aktivitet uden pause-segmenter (kun kørsel/arbejde/rådighed) → knappen vises ikke.
- Aktivitet hvor alle pause-segmenter allerede er rettet → knappen vises ikke.
- Direkte POST til `/correct-all-segments` på en aktivitet uden kandidater → 400 "Ingen pauselinjer at rette".
