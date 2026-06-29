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
- **Alle** arbejdstimer tæller med i forbruget af normaltid – også timer kl. 21-05 og 05-06
  (jf. dokumentets eksempel 1: arbejde kl. 4-14 med normaltid 7 → 1 øvrig + 1 før + 5 normal + 3 OT 1-3).

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
