# Regelændring: alle linjer skal altid have det korrekte antal felter

## Problem

Danløn-CSV'en overholder de fleste formatkrav (se [aendringer-danloen.md](aendringer-danloen.md)), men kan indeholde linjer, hvor et felt mangler, fordi et **tomt felt i slutningen af linjen bliver droppet** i stedet for at blive skrevet som et tomt felt.

Eksempel (generisk, uden konkrete data):

```
medarbejder-id;løn-id;kode;beløb
```

I stedet for det korrekte:

```
medarbejder-id;løn-id;kode;beløb;;
```

Når et felt (typisk det sidste, fx lønart) er tomt, skal det stadig repræsenteres som et tomt felt mellem semikoloner — det må ikke bare udelades, så linjen ender med færre felter end de øvrige.

## Root cause

Eksport-/genereringslogikken trimmer tilsyneladende afsluttende tomme felter, i stedet for at bevare dem som tomme placeholders. Det ses allerede i Tacholøn-filen, hvor et tomt felt midt i en linje korrekt bevares som et dobbelt semikolon (`;;`) — samme princip skal gælde for tomme felter i slutningen af en linje.

## Regel (ny/opdateret)

- Hver linje skal **altid** indeholde det faste antal datafelter (5), uanset om en værdi er tom.
- En tom værdi skal skrives som et tomt felt (dvs. to semikoloner ved siden af hinanden, `;;`, eller et tomt felt lige før den afsluttende semikolon), **aldrig** udelades.
- Linjen skal stadig ende med den afsluttende semikolon efter feltet.

**Korrekt eksempel med tom værdi i sidste felt:**
```
medarbejder-id;løn-id;kode;beløb;;
```

**Forkert (nuværende adfærd):**
```
medarbejder-id;løn-id;kode;beløb;
```

## Handling

- [ ] Ret eksport-/genereringslogikken, så tomme felter altid skrives eksplicit i stedet for at blive trimmet væk
- [ ] Verificér efter rettelsen, at hver linje i filen har præcis 5 datafelter + afsluttende semikolon — uanset om nogle værdier er tomme
- [ ] Kør en valideringstjek (fx tælling af semikoloner pr. linje) på fremtidige eksporter for at fange regressioner
