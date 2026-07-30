# Lønberegningsregler – Lønsystem

**Bemærk:** Stamdata (databasen) er den autoritative kilde til satser og løntypekoder –
denne fil er en menneskelæsbar reference, som kan komme bagud af ændringer gjort direkte i
Stamdata-UI'en. Tjek altid Stamdata → Overenskomsttyper / Løntypekoder ved tvivl. Sidst
gennemgået mod koden 2026-07-30.

## Timesatser pr. 1. marts 2026

| Medarbejdertype | Grundtimeløn | Tillæg | Samlet timeløn |
|----------------|--------------|--------|----------------|
| Chauffør under oplæring | 159,65 kr. | – | 159,65 kr. |
| Chauffør (nyansættelse) | 159,65 kr. | Chaufførtillæg 14,50 kr. | 174,15 kr. |
| Chauffør (efter 9 mdr.) | 159,65 kr. | 14,50 + anciennitet 8,15 kr. | 182,30 kr. |
| Faglært chauffør | 159,65 kr. | 14,50 + anciennitet 8,15 + faglært 4,00 kr. | 186,30 kr. |
| + Kvalifikationstillæg (hænger+kran) | +3,80 kr. | tillæg oveni | +3,80 kr. |

---

## Effektiv arbejdstid

**Effektiv tid = sluttid − starttid** (total varighed fra stempelind til stempelud)

Der sondres IKKE internt mellem rådighedstid, hvil, kørsel etc. i lønberegningen. Hele perioden tæller.

Undtagelse: Pålæsning og aflæsning (manuelt tastet fra dagssedler) medregnes i effektiv tid.

---

## Minimum 4-timer regel

Kilde: Chaufføroverenskomst §3, stk. 1 / §5 afløser

- En vagt må **ikke** aflønnes for **under 4 timer** uden særlig begrundelse
- Systemet markerer automatisk vagter under 4 timer med rød status
- Kræver **manuel godkendelse** med initialer og begrundelse
- Ved godkendelse under 4 timer: den faktiske tid bruges i lønberegningen

---

## Overtid

Se `OVERTIME_RULES.md` for detaljerede regler.

**Opsummering:**
- Tidlig tid (05:00–06:00): +44,54 kr./time
- Normal overarbejde (time 7,4–10,4): +44,54 kr./time
- Ekstra overarbejde (over 10,4 timer): +109,40 kr./time
- Søn- og helligdage: +109,40 kr./time (al arbejde)

---

## Ubekvem arbejdstid – UDGÅET (erstattet 10/6-2026)

De tre overtidstillæg herover **erstatter fuldstændigt** den tidligere separate
ubekvemstillæg-model (18-23, 23-06, lørdag 14+/søn-/helligdage), som er bekræftet af bruger og
fjernet fra beregningen. Denne sektion stod tidligere med de gamle satser (46,93 / 52,65 /
102,71 kr./time) – de tillæg findes IKKE i den nuværende kode og skal ikke lægges til oveni
overtidstillæggene. Se `docs/OVERTIME_RULES.md` for den fulde, aktuelle model.

---

## Anciennitet

- Beregnes automatisk fra `hire_date`
- 0–8 måneder og 29 dage: nyansættelses-sats
- Fra og med 9 måneder: anciennitetstillæg (+8,15 kr./time)
- Pop-up ved opstart: hvis medarbejder har nået 9 måneder og er i forkert løngruppe
- Pop-up-knapper: "Luk" eller "Gå til medarbejder for at ændre timesats"

---

## Særlig opsparing og pension

| Element | Sats |
|---------|------|
| Særlig opsparing | 10% af grundlønnen |
| Særligt løntillæg (timelønnet) | 8,40% |
| Pension – arbejdsgiver | 11% |
| Pension – lønmodtager | 2% |
| Pension i alt | 13% |

---

## CSV-format til Danløn

| Kolonne | Felt | Eksempel |
|---------|------|---------|
| A | CVR-nummer | fra Stamdata → CVR-nummer (medarbejderens eget, ellers standard) |
| B | Medarbejdernummer (lønnummer) | [medarbejdernr] |
| C | Danløn-kode | 1=Normal, 7=OT før, 8=OT 1-3t, 9=Øvrig OT, 6=Salt, 14=Overnatning, 71=Afspadsering, 51=Sygdom/§56/Barsel, 15=Barn 1.sygedag, 81=Feriefri, 2=Skole/kursus, 4/63=Søgnehelligdag, 60=Ferie (default ekskluderet fra CSV) |
| D | Antal (timer eller antal, afhænger af løntypen) | 7.40 |
| E | Timesats / tillægssats (hvis konfigureret til at vises) | 174.15 |
| F | Totalbeløb (hvis konfigureret til at vises i stedet for/ud over sats) | – |

Én række pr. løntype med antal > 0 og "Medtag i CSV" slået til i Stamdata → Løntypekoder.
Koder, enhed og hvilke af E/F der vises er alt sammen konfigurérbart pr. løntype der – se
`CODEREF.md` for den fulde tabel og implementeringsdetaljer.

---

## Prøvekørsel – Excel-markering

Følgende markeres i prøvekørsels-Excel:
- 🟡 Dage med **under 4 timer** (kræver manuel godkendelse)
- 🟠 Dage med **over 12 timer** (ualmindeligt lang vagt – til kontrol)

---

## Åbne punkter

- [x] Præcis beregning af overtid: dagligt (pr. vagt/kalenderdag) – se OVERTIME_RULES.md
- [x] Ubekvem tid og overtidstillæg kombineres IKKE – ubekvem-modellen er udgået, se ovenfor
- [x] Danløn-koder – konfigureres nu pr. løntype i Stamdata → Løntypekoder (ikke længere fast "1")
- [x] Afspadsering – egen kode (71), timer summeres (periode = skemalagte timer/hverdag)
- [x] Disponentgrupper og output-mappe stier – konfigureres i Stamdata / ved eksport
- [ ] Verificér om "Øvrigt overtid" (nat/aften) altid stemmer med Danløns egen beregning for
      medarbejdere med meget tidligt/sent arbejde – mindre afvigelser observeret 2026-07-30
      ved sammenligning med det gamle Tacho-baserede system, uden en entydig fælles årsag
