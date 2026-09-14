# Fejl i danløn-CSV filen og generelle rettelser (HISTORISK – LØST)

> **OBS:** Dette dokument beskriver en oprindelig fejlobservation. Den gældende, korrekte
> adfærd er siden blevet afklaret og er **modsat** af det, der oprindeligt blev antaget her
> — se **[docs/aendringer-danloen.md](docs/aendringer-danloen.md)**, som er den autoritative
> kilde til CSV-formatkravene. Dette dokument bevares kun som historik og må ikke bruges som
> grundlag for at "rette" den nuværende eksport.

Formål (oprindeligt): beskrive de gentagne strukturelle fejl, der blev fundet i danløn-eksporter, og hvad der dengang blev antaget skulle ændres, så filerne matcher Tacholøn-formatet.

## Hvad der oprindeligt blev observeret

Nogle linjer i danløn-filen så ud til at mangle et afsluttende semikolon eller et sidste felt, sammenlignet med Tacholøn-filens format.

## Hvorfor det IKKE er en fejl

Efter bekræftelse fra bruger (opdateret 2026-09, se `docs/aendringer-danloen.md`) er den nuværende eksport (`app/routers/payroll_router.py`) **tilsigtet**:

- Hver linje har **6 felter** (CVR, medarbejdernr, kode, antal, sats, total) – ikke 5, som antaget her oprindeligt.
- Et afsluttende semikolon skrives **kun** når linjens sidste felt (total-kolonnen) er tomt for den pågældende løntype – ikke altid.
- Om sats/total er udfyldt eller tomt styres pr. løntype i Stamdata → Løntypekoder (`csv_include_rate`/`csv_include_total`).

**Konklusion:** eksportlogikken skal IKKE ændres på baggrund af dette dokument. Se `docs/aendringer-danloen.md` for den gældende beskrivelse.

## Verifikation af den faktiske, korrekte adfærd

For at kontrollere at en eksport er korrekt, tjek i stedet:
- At alle linjer har præcis 6 datafelter.
- At et afsluttende semikolon KUN optræder når total-kolonnen er tom for den løntype.
- At filen ikke indeholder en UTF-8 BOM.
- At linjeskift er CRLF.
