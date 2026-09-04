# Bevar ugemte formularrettelser i aktivitets-detaljevisningen – Design

**Dato:** 2026-09-04
**Status:** Godkendt af bruger

## Baggrund

I aktivitets-detaljevisningen (`openActivityDetail()` i `app.js`) kan flere felter rettes samlet (starttid, sluttid, vognnummer, km start/slut, salttillæg, DOB) og gemmes med ét klik på "💾 Gem ændringer" (`saveActivityTimes()`).

Segment-korrektion (`correctSegment()`, `correctAllSegments()`), segment-tilpasning (`resize-segment`, i `confirmResizeSegment()`) og pause-redigering/-sletning (`_confirmActivityPauseEdit()`, `deleteActivityPause()`) gemmer derimod **med det samme** til serveren og genindlæser derefter hele detaljevisningen via `openActivityDetail(activityId)` for at vise resultatet. Denne genindlæsning bygger `edit-start`/`edit-end`/`edit-vehicle`/`edit-km-start`/`edit-km-end`/`edit-salt`/`edit-dob` på ny fra serverens (friske) data – hvilket overskriver enhver rettelse i de felter, brugeren har indtastet, men endnu ikke gemt via "Gem ændringer".

**Konkret oplevet fejl:** Retter man sluttidspunktet manuelt og derefter retter en pauselinje til "Andet arbejde" (segment-korrektion), nulstilles det indtastede sluttidspunkt til den oprindelige værdi.

## Løsning

`openActivityDetail(id)` udvides til at bevare ugemte formularværdier, når den kaldes igen for **samme** aktivitet, mens detaljemodalen allerede er åben for den (hvilket kun sker via de nævnte "gem med det samme og genindlæs"-handlinger – et almindeligt nyt klik på en aktivitet i oversigten åbner altid en frisk visning, uændret).

Ved funktionens start, før noget genopbygges, tjekkes om modalen allerede er åben for samme `id`. Hvis ja, læses de aktuelle værdier fra `edit-start`, `edit-end`, `edit-vehicle`, `edit-km-start`, `edit-km-end`, `edit-salt`, `edit-dob`. Efter formularen er genopbygget med serverens (opdaterede) data, genindsættes disse gemte værdier i de samme felter – uden at skelne mellem om værdien reelt er "ændret" eller ej, for enkelthedens skyld og forudsigelighedens skyld.

Dette retter automatisk alle fem eksisterende steder, der følger "gem med det samme + genindlæs"-mønsteret, uden at de skal ændres hver for sig:
- `correctSegment()` (Ret linje / Gendan)
- `correctAllSegments()` (Al pause til andet arbejde)
- `confirmResizeSegment()` (Tilpas pauselængde)
- `_confirmActivityPauseEdit()` (Ret pause)
- `deleteActivityPause()` (Slet pause)

## Ikke i scope

- Ingen ændring af selve gem-mekanismen for segment-korrektion, pause-redigering eller pause-sletning – de forbliver umiddelbare, separate server-kald (kun visningen efter kaldet ændres).
- Ingen ændring af `saveActivityTimes()`s eksisterende batchede felter.
- Ingen ændring af hvordan en helt frisk åbning af detaljevisningen (fra aktivitetsoversigten) fungerer.

## Test-dækning (til implementeringsplan)

- Ret sluttid i formularen (ikke gemt endnu) → udløs en segment-korrektion (`correctSegment()`) → bekræft at sluttidsfeltet stadig viser den indtastede, ugemte værdi bagefter.
- Samme scenarie for `correctAllSegments()`, segment-tilpasning, pause-redigering og pause-sletning.
- En helt frisk åbning af detaljevisningen (anden aktivitet, eller samme aktivitet men modalen var lukket) viser fortsat serverens aktuelle værdier, uændret.
- Efter en bevaret rettelse: klik "Gem ændringer" gemmer korrekt den bevarede værdi sammen med den øvrige batch.
