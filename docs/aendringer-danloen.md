# Formatkrav til danløn-CSV filer (matcher Tacholøn-formatet)

Formål: beskrive hvordan en danløn-CSV skal være opbygget, så den strukturelt og encoding-mæssigt matcher Tacholøn-filerne.

## 1. Encoding uden BOM

- **Krav:** filen skal gemmes som ren ASCII/UTF-8 **uden** BOM (byte order mark).
- **Fejl at undgå:** hvis filen gemmes som "UTF-8 med BOM", vil de tre bytes `EF BB BF` blive indsat forrest i filen, hvilket kan gøre at det første tegn i filen fejltolkes af systemer, der ikke fjerner BOM automatisk.
- **Handling ved konvertering:** gem/eksportér filen med encoding "UTF-8" (uden BOM) eller "ANSI" i stedet for "UTF-8 med BOM".

## 2. Afsluttende semikolon på hver linje – KUN når totalkolonnen er tom

- **Opdateret 2026-09 efter bekræftelse fra bruger: dette er IKKE et fast krav.** Den nuværende, korrekte eksport (`app/routers/payroll_router.py`) skriver et afsluttende `;` kun når linjens sidste felt (total-kolonnen) er tomt for den pågældende løntype – ellers slutter linjen direkte efter beløbet, uden ekstra semikolon. Eksporten skal IKKE ændres til altid at tilføje et afsluttende semikolon.
- **Eksempel, total tom** (fx type der kun viser sats, ikke total):
  ```
  cvr;medarbejdernr;kode;antal;sats;
  ```
- **Eksempel, total udfyldt:**
  ```
  cvr;medarbejdernr;kode;antal;sats;25000
  ```

## 3. Antal felter pr. linje – 6, ikke 5

- **Opdateret 2026-09:** den nuværende, korrekte eksport skriver altid 6 felter pr. linje: CVR-nummer, medarbejdernummer, Danløn-kode, antal/timer, sats (tom streng hvis løntypen ikke skal vise sats) og total (tom streng hvis løntypen ikke skal vise total). Om sats/total er udfyldt eller tomt styres pr. løntype i Stamdata → Løntypekoder (`csv_include_rate`/`csv_include_total`) – det er tilsigtet, ikke en fejl, og skal ikke rettes til 5 felter.

## 4. Linjeskift

- **Krav:** filen skal bruge CRLF som linjeskift (Windows-format), ligesom Tacholøn-filerne.
- **Handling ved konvertering:** ingen ændring nødvendig, hvis filen allerede er gemt med CRLF (standard ved eksport fra Windows/Excel).

## Tjekliste ved konvertering af en danløn-fil

- [ ] Gem filen uden UTF-8 BOM
- [ ] Kontroller at hver linje har 6 felter (afsluttende `;` er kun til stede når totalkolonnen er tom – ikke et generelt krav)
- [ ] Kontroller at linjeskift er CRLF
