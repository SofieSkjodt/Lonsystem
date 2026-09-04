# "Gem ændringer" skal ikke lukke modalen – Design

**Dato:** 2026-09-04
**Status:** Godkendt af bruger

## Baggrund

`saveActivityTimes()` (knappen "💾 Gem ændringer" i aktivitets-detaljevisningen) kalder i dag `closeAllModals()` efter et vellykket gem, hvilket lukker hele detaljevisningen. Dette er inkonsistent med de øvrige "gem med det samme"-handlinger i samme modal (segment-korrektion, segment-tilpasning, pause-redigering/-sletning), som allerede genindlæser den samme visning i stedet for at lukke den (jf. `docs/superpowers/specs/2026-09-04-bevar-utgemte-rettelser-design.md`).

**Ønsket ændring:** Efter et klik på "Gem ændringer" skal modalen forblive åben og vise de nu gemte, opdaterede værdier – ikke lukke automatisk.

## Løsning

I `saveActivityTimes()`'s success-gren erstattes `closeAllModals();` med et gen-render af samme aktivitet via `openActivityDetail(state.selectedActivityId)`, efter `applyActivityLocally(updated)` har opdateret den lokale state. Dette matcher nøjagtigt mønsteret de øvrige fem "gem med det samme"-handlinger allerede bruger.

## Ikke i scope

- Ingen ændring af selve gem-payloaden eller valideringen i `saveActivityTimes()`.
- Ingen ændring af de øvrige knapper i modalens footer (Godkend, Deaktiver, Split, Genåbn, Luk), som fortsat lukker/opfører sig som i dag.

## Test-dækning (til implementeringsplan)

- Efter "Gem ændringer" forbliver modalen åben og viser de nye, gemte værdier (fx opdateret "Sum, effektiv tid" ved ændret sluttid).
- "Luk"-knappen lukker fortsat modalen som normalt.
