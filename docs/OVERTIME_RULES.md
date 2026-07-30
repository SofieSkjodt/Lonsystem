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
- **Loftet deles pr. dag, ikke pr. aktivitet (2026-07-02):** har en dag flere godkendte
  aktiviteter (fx efter en opdeling), deler de normaltids-/OT13-loftet i stedet for at hver
  aktivitet får sit eget friske loft. `calculate_overtime()` tager imod og videresender det
  resterende loft via `normal_remaining`/`ot13_remaining`.

## Vagter der krydser midnat, lørdag/søndag/helligdag

- **Loftet hører til vagten** (den dag den startede), ikke til kalenderdagen. En vagt der
  starter fredag aften og fortsætter ind i lørdag bruger fredagens loft, indtil det er brugt
  op – `calculate_overtime()`s kronologiske gennemløb håndterer det automatisk uden at vagten
  splittes.
- **Søndage/helligdage er undtagelsen:** de har en loft-uafhængig regel ("alle kørte timer →
  kode 9, uanset tidspunkt"). En vagt der STARTER på en søndag/helligdag splittes derfor altid
  ved midnat (`_split_into_day_pieces()` i `payroll_router.py`) – søndagsdelen får søndagens
  regel, resten falder tilbage til den følgende dags egne regler.
- **Lørdag har ingen særregel** (fjernet 2026-07-02): lørdag regnes altid som en normal
  hverdag via `calculate_overtime()`, med lørdagens egne garanterede timer (typisk 0) som loft.
  Er loftet 0, giver den almindelige tidsvindues-logik automatisk "første op til 3 dagtimer →
  kode 8, resten → kode 9" uden særkode. Se `calculators/day_type.py` og
  `memory/project_lonsystem_midnight_split.md` for den fulde baggrund og verifikation.

## Lønperioder

Faste 14-dages perioder, mandag–søndag, anker 1/6-2026
(dokumentets eksempel: 3/6-2026 → periode 1/6–14/6). Bekræftet af bruger 10/6-2026.

## Fraværstyper (opdateret 2026-07-30)

Aktiviteter kan have type: normal, ferie, sygdom (+ sygdom u. 8 uger), §56 syg, barn 1./2-3.
sygedag (+ u. 8 uger), barsel (+ u. løn), feriefri, graviditetsbetinget sygdom, skole/kursus,
selvbetalt fridag, afspadsering, overnatning. Den fulde liste konfigureres i
Stamdata → Fraværstyper (`master_absence_types`).

- **Normal**: indgår i timeberegningen (normal + additive OT-tillæg som ovenfor).
- **Afspadsering**: timer summeres til `afspadsering_hours`. En **periode** (flere
  kalenderdage) tæller 7,4 t/skemalagte timer pr. hverdag, ikke rå klokketid – se
  `_afspadsering_hours()` i `payroll_router.py`. En enkeltdags-registrering bruger den
  faktiske varighed.
- **Sygdom, §56 syg, barsel, barn 1.sygedag, feriefri, skole/kursus**: timer summeres hver for
  sig i `_calculate_employee()`s result-dict og indgår i Danløn CSV'en, hvis den enkelte
  løntype har `include_in_csv=true` i Stamdata.
- **Ferie**: registreres og tælles (i timer), men er som default IKKE med i Danløn CSV'en
  (`include_in_csv=false` for løntypen `ferie`, kode 60) – ferie afregnes uden om dette system,
  indtil det evt. slås til.
- **Sygdom u. 8 uger, barn 2-3.sygedag, selvbetalt fridag, barsel u. løn**: registreres, men
  regnes ikke med i nogen timetotal og kommer aldrig med i CSV'en.

## Danløn CSV (Kør løn)

Kolonner: A=CVR, B=medarbejdernummer, C=Danløn-kode, D=antal (timer eller antal, afhængig af
løntypen), E=sats (hvis `csv_include_rate`), F=totalbeløb (hvis `csv_include_total`). Én række
pr. løntype med antal > 0 og `include_in_csv=true`, pr. medarbejder. Kode, enhed og hvilke af
E/F der vises konfigureres pr. løntype i Stamdata → Løntypekoder (`master_pay_types`) – se
CODEREF.md-afsnittet "Danløn CSV-struktur" for den fulde kodeliste.
