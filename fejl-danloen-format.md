# Fejl i danløn-CSV filen og generelle rettelser

Formål: beskrive de gentagne strukturelle fejl, der er fundet i danløn-eksporter, og hvad der generelt skal ændres, så filerne matcher Tacholøn-formatet.

## Fundne fejl

### 1. Manglende afsluttende semikolon på linjerne

De fleste linjer i danløn-filen slutter **uden** semikolon efter sidste felt:

```
medarbejder-id;løn-id;kode;beløb;lønart
```

I Tacholøn-filen slutter linjerne konsekvent **med** semikolon:

```
medarbejder-id;løn-id;kode;beløb;lønart;
```

Kun ganske få linjer i danløn-filen har den afsluttende semikolon — det er derfor en systematisk fejl i eksporten, ikke en enkeltstående afvigelse.

### 2. Linjer med for få felter

Nogle linjer mangler et felt (typisk det sidste, lønart), fordi et tomt felt i slutningen af linjen bliver **droppet** i stedet for skrevet som et tomt felt:

```
medarbejder-id;løn-id;kode;beløb;
```

Der er kun 4 felter her i stedet for 5. Det korrekte ville være at bevare det tomme felt eksplicit:

```
medarbejder-id;løn-id;kode;beløb;;
```

## Root cause

Begge fejl peger på samme underliggende problem: eksportlogikken **trimmer/dropper afsluttende tomme værdier**, i stedet for at skrive dem ud som tomme felter og altid afslutte linjen med semikolon. Tacholøn-filen viser, at det korrekte mønster er at bevare tomme felter som `;;` og altid have en afsluttende `;` for hver linje.

## Hvad der generelt skal ændres

- [ ] Eksportlogikken skal **altid** skrive det fulde antal felter (5) pr. linje, uanset om en værdi er tom
- [ ] En tom værdi skal skrives som et tomt felt mellem semikoloner (`;;`), aldrig udelades
- [ ] Hver linje skal **altid** afsluttes med et semikolon efter sidste felt
- [ ] Encoding (uden BOM) og linjeskift (CRLF) skal bibeholdes, som de allerede fungerer korrekt

## Verifikation efter rettelse

For at kontrollere at en fremtidig eksport er korrekt, bør man tjekke:
- At alle linjer har præcis 5 datafelter (ingen linjer med færre)
- At alle linjer ender med et afsluttende semikolon
- At filen ikke indeholder en UTF-8 BOM
- At linjeskift er CRLF
