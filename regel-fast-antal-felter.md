# Regelændring: alle linjer skal altid have det korrekte antal felter (HISTORISK – LØST)

> **OBS:** Denne fil beskrev oprindeligt et formodet krav om altid 5 felter + en obligatorisk
> afsluttende semikolon. Det er siden afklaret at være forkert — se
> **[aendringer-danloen.md](aendringer-danloen.md)**, som er den autoritative kilde: den
> korrekte, tilsigtede opførsel er **6 felter**, og den afsluttende semikolon er **betinget**
> (kun når total-kolonnen er tom). Denne fil bevares kun som historik.

## Oprindeligt antaget problem

Det blev oprindeligt antaget at et tomt felt i slutningen af en linje blev droppet i stedet for skrevet ud, og at hver linje altid skulle ende med semikolon.

## Hvorfor det ikke er en fejl

Den nuværende eksportlogik (`app/routers/payroll_router.py`) skriver bevidst 6 felter pr. linje (CVR, medarbejdernr, kode, antal, sats, total), hvor sats/total kan være tomme strenge afhængigt af løntypens opsætning i Stamdata → Løntypekoder. Den afsluttende semikolon optræder kun når total-feltet er tomt. Dette er bekræftet som tilsigtet, ikke en fejl (se `aendringer-danloen.md`, opdateret 2026-09).

## Handling

Ingen — eksportlogikken skal IKKE ændres på baggrund af dette dokument. Referér til `aendringer-danloen.md` ved fremtidige spørgsmål om CSV-formatet.
