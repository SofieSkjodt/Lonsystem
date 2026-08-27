# "Sum, pause"-felt i aktivitets-detaljevisningen – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Aktivitets-detaljevisningen (`openActivityDetail()` i `app.js`, den modal der åbnes ved klik på en aktivitet i Aktivitetsoversigten) viser i dag et felt "Sum, effektiv tid" (`a.duration_minutes`, formateret via `formatDuration()` som fx "2t 00m"). Dette felt vises for enhver aktivitet, uanset om den er oprettet manuelt eller er hentet ind via DDD-import (systemet) – det er én fælles visning.

**Ønsket ændring:** Et nyt felt "Sum, pause" skal tilføjes i samme detalje-gitter, lige under "Sum, effektiv tid", der viser den summerede pausetid for vagten.

## Løsning

### Beregning
`a.duration_minutes` er allerede – server-side, i `_duration_minutes()` i `app/routers/activities.py` – totaltiden (slut − start) med pauser fratrukket. Pauserne hentes derfra enten fra `segments` (type `"rest"`) for DDD-importerede aktiviteter, eller fra `pause_intervals` for manuelle aktiviteter. Da dette allerede er den autoritative kilde for, hvad der tæller som pause for enhver aktivitet, beregnes "Sum, pause" som komplementet, uden nogen backend-ændring:

```js
const totalMinutes = Math.round((new Date(a.end_time) - new Date(a.start_time)) / 60000);
const pauseMinutes = totalMinutes - a.duration_minutes;
```

Dette er garanteret matematisk konsistent med "Sum, effektiv tid" – de to felter summer altid til den fulde varighed, uanset om aktiviteten stammer fra manuel oprettelse eller systemet.

### Placering
Ny `<div class="detail-item">` i `openActivityDetail()`'s `modal-activity-body`-gitter (`app/static/js/app.js`), umiddelbart efter den eksisterende "Sum, effektiv tid"-linje, i samme øverste detalje-område som start/sluttid, type, salttillæg, km, oprettet af, godkendt af osv.

### Format
Genbruger den eksisterende `formatDuration(minutes)`-funktion (samme "Xt YYm"-format som "Sum, effektiv tid" allerede bruger), for visuel konsistens mellem de to felter.

## Ikke i scope

- Ingen ændring af selve pauseberegningen i `_duration_minutes()` eller andre backend-beregninger.
- Ingen ændring af opret-aktivitet-modalen (feltet vises kun i detaljevisningen for en allerede oprettet/hentet aktivitet).
- Ingen ændring af `ActivityResponse`-schemaet eller API'et – beregningen sker rent i frontend ud fra allerede tilgængelige felter.

## Test-dækning (til implementeringsplan)

- En manuel aktivitet med kendte `pause_intervals` viser korrekt summeret pausetid i "Xt YYm"-format.
- En DDD-importeret aktivitet med `segments` af type `"rest"` viser korrekt summeret pausetid.
- En aktivitet uden nogen pause viser "0t 00m".
- Feltet vises i samme detalje-gitter som de øvrige felter (start/sluttid, type, salttillæg, km, oprettet af, godkendt af), lige under "Sum, effektiv tid".
