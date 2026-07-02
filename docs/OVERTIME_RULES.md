# Overtidsregler (opdateret 10/6-2026 efter revideret kravdokument)

Kilde: "Ønsker til opsætning+funktioner" (afsnit Overtidstillæg) + brugerafklaring 10/6-2026.

## Tre tillægstyper

Satserne vedligeholdes i Excel-arket **"Overtid satser.xlsx"** i rodmappen
og genindlæses ved hvert kald:

| Tillægstype | Tidsrum / betingelse | Sats (pt.) |
|---|---|---|
| Overtid 1 time før | Arbejde kl. 05–06 | 44,54 kr |
| Overtid 1-3 timer efter | Arbejde kl. 18–21, samt timer ud over normaltid i kl. 06–18 | 44,54 kr |
| Øvrigt overtid | Arbejde kl. 21–05, samt overtidstimer ud over de første 3 | 109,40 kr |

**Bekræftet af bruger 10/6-2026:**
- De tre tillæg **erstatter fuldstændigt** de tidligere ubekvemstillæg (18-23, 23-06, lørdag/søndag/helligdag).
- Overtidstimer ud over de første 3 → "Øvrigt overtid".

## Normaltid

- Normaltid pr. dag kommer fra medarbejderens **timefordeling** (lige/ulige uger, indtastet ved oprettelse).
- **Alle** arbejdstimer tæller med i normal_hours (kode 1, alle giver normal løn), men det
  **registrerede** normaltids-loft (7/7,5/8 t) kan kun forbruges i tidsrummet **kl. 06-18**.
  Arbejde uden for dette vindue (nat 21-05, "1 time før" 05-06, aften 18-21) er altid rent
  tillæg og fortærer ikke loftet – ellers "blot overarbejde" oveni.
  **Rettet 2026-07-02:** den oprindelige gengivelse af dokumentets eksempel 1 herunder
  (5 normal + 3 OT 1-3) var en fejlfortolkning af kravdokumentet, bekræftet af bruger.
  Korrekt for kl. 4-14 med normaltid 7: nat (04-05) og før (05-06) giver hver 1 tillægstime
  uden at røre loftet; af de 8 timer i 06-14 dækker loftet de første 7 (ren normaltid), og
  den sidste time overskrider loftet → 1 OT 1-3. Total kode 1 (alle arbejdstimer) = 10 t;
  fordelt som 1 øvrig + 1 før + 1 OT 1-3 tillæg oveni.

## Beregning

- Daglig (pr. aktivitet). Implementeret i `calculators/overtime.py`.
- Alle timer betales med medarbejderens timesats (fra "Overenskomsttyper og timesatser.xlsx");
  tillægget lægges **oveni** for overtidstimer.
- Verificeret mod dokumentets 3 eksempler i `_test_overtime.py` (alle OK).

## Lønperioder

Faste 14-dages perioder, mandag–søndag, anker 1/6-2026
(dokumentets eksempel: 3/6-2026 → periode 1/6–14/6). Bekræftet af bruger 10/6-2026.

## Fraværstyper

Aktiviteter kan have type: normal, ferie, fri, afspadsering, skole/kursus.
- **Normal**: indgår i timeberegningen.
- **Afspadsering**: timer summeres og skrives i Danløn-CSV kolonne F.
- **Ferie/fri/skole-kursus**: registreres, men indgår ikke i timeberegningen (afregning AFKLARES).

## Danløn CSV (Kør løn)

Kolonner: A=CVR (13246505), B=medarbejdernummer, C=Danløn-kode (placeholder "1" – rigtige koder mangler),
D=antal timer, E=time-/tillægssats, F=afspadsering. Én række pr. tillægstype pr. medarbejder.
