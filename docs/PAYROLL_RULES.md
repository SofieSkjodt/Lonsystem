# Lønberegningsregler – Lønsystem

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

## Ubekvem arbejdstid

Beregnes **time-for-time** baseret på hvornår arbejdet falder:

| Tidsrum | Tillæg |
|---------|--------|
| Kl. 18:00–23:00 (hverdage) | +46,93 kr./time |
| Kl. 23:00–06:00 | +52,65 kr./time |
| Lørdag kl. 14:00+ og søn-/helligdage | +102,71 kr./time |

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
| A | CVR-nummer | 13246505 |
| B | Medarbejdernummer | [medarbejdernr] |
| C | Danløn-kode | 1 (midlertidig) |
| D | Antal timer | 7.40 |
| E | Timesats / tillægssats | 174.15 |
| F | Afspadsering | [TBD] |

CVR-nummer: **13246505**

---

## Prøvekørsel – Excel-markering

Følgende markeres i prøvekørsels-Excel:
- 🟡 Dage med **under 4 timer** (kræver manuel godkendelse)
- 🟠 Dage med **over 12 timer** (ualmindeligt lang vagt – til kontrol)

---

## Åbne punkter

- [ ] Præcis beregning af overtid: dagligt vs. ugentligt
- [ ] Bekræftelse af om ubekvem tid og overtidstillæg kan kombineres på samme time
- [ ] Danløn-koder (sættes til "1" indtil videre)
- [ ] Afspadsering (kolonne F) – hvad skal stå her?
- [ ] Disponentgrupper Excel-sti
- [ ] Output-mappe stier (CSV, Excel)
