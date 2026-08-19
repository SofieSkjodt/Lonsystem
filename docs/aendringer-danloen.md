# Formatkrav til danløn-CSV filer (matcher Tacholøn-formatet)

Formål: beskrive hvordan en danløn-CSV skal være opbygget, så den strukturelt og encoding-mæssigt matcher Tacholøn-filerne.

## 1. Encoding uden BOM

- **Krav:** filen skal gemmes som ren ASCII/UTF-8 **uden** BOM (byte order mark).
- **Fejl at undgå:** hvis filen gemmes som "UTF-8 med BOM", vil de tre bytes `EF BB BF` blive indsat forrest i filen, hvilket kan gøre at det første tegn i filen fejltolkes af systemer, der ikke fjerner BOM automatisk.
- **Handling ved konvertering:** gem/eksportér filen med encoding "UTF-8" (uden BOM) eller "ANSI" i stedet for "UTF-8 med BOM".

## 2. Afsluttende semikolon på hver linje

- **Krav:** hver linje skal ende med et afsluttende `;` efter det sidste felt, før linjeskift.
- **Format:**
  ```
  medarbejder-id;løn-id;kode;beløb;lønart;
  ```
- **Fejl at undgå:** linjer uden afsluttende semikolon, f.eks.:
  ```
  medarbejder-id;løn-id;kode;beløb;lønart
  ```
- **Handling ved konvertering:** tilføj `;` til slutningen af hver linje, hvis den ikke allerede er der.

## 3. Fast antal felter pr. linje

- **Krav:** hver linje skal indeholde de samme 5 datafelter (medarbejder-id, løn-id, kode, beløb, lønart) — ingen linjer må have færre felter.
- **Fejl at undgå:** linjer hvor et felt er tomt, f.eks. `...;kode;beløb;;` (manglende lønart) eller hvor der er sat semikolon direkte efter et felt, uden at værdien er udfyldt.
- **Handling ved konvertering:** valider at alle 5 felter er udfyldte på hver linje, inden filen bruges. Linjer med manglende feltværdier skal rettes manuelt, da værdien ikke kan udledes automatisk fra resten af rækken.

## 4. Linjeskift

- **Krav:** filen skal bruge CRLF som linjeskift (Windows-format), ligesom Tacholøn-filerne.
- **Handling ved konvertering:** ingen ændring nødvendig, hvis filen allerede er gemt med CRLF (standard ved eksport fra Windows/Excel).

## Tjekliste ved konvertering af en danløn-fil

- [ ] Gem filen uden UTF-8 BOM
- [ ] Tilføj afsluttende `;` på alle linjer
- [ ] Kontroller at alle linjer har 5 udfyldte datafelter
- [ ] Kontroller at linjeskift er CRLF
