# .ddd Filformat – Tachografdata

## Baggrund

.ddd-filer er binære filer i EU-standardformat defineret af:
- Kommissionens forordning (EF) nr. 1360/2002
- Europa-Parlamentets og Rådets forordning (EF) nr. 561/2006
- Kommissionens gennemførelsesforordning (EU) 2016/799

Der er to typer .ddd-filer:
1. **Førerkortsdata** (driver card data) – indlæst fra chaufførens kort
2. **Fartskriverdata** (vehicle unit data) – indlæst fra bilens fartskriver

## Identifikation af chauffør

- Hver .ddd-fil identificeres med et **chaufførnummer** (tachografkortnummer)
- Chaufførnummeret kobles til en medarbejder i systemets database

## Inputmappe

- Én mappe med filer for **alle chauffører**
- Sti: AFKLARES (oplyses når mappen er oprettet)
- Systemet scanner mappen og indlæser nye filer automatisk

## Indhold der udtrækkes

Fra .ddd-filer udtrækkes følgende til lønberegning:

| Felt | Beskrivelse |
|------|-------------|
| Chaufførnummer | Tachografkortnummer til kobling med medarbejder |
| Start-tidspunkt | Dato og klokkeslæt for aktivitetens start |
| Slut-tidspunkt | Dato og klokkeslæt for aktivitetens slut |
| Rådighedstid (%) | Andel af perioden med rådighedstid |
| Hvil/pause (%) | Andel af perioden med hvil |
| Andet arbejde (%) | Andel af perioden med andet arbejde |
| Kørsel (%) | Andel af perioden med kørsel |

## Ikke i .ddd-filer

Følgende registreres **ikke** af tachografen og skal tastes manuelt:
- Pålæsning
- Aflæsning
- Andre aktiviteter fra dagssedler

## Python-parser

Ingen PyPI-biblioteker til .ddd-parsing eksisterer. Systemet bruger en **custom parser** (`parsers/ddd_parser.py`).

### Bekræftet filstruktur (analyseret fra faktisk fil)

**TLV top-niveau:** 2-byte tag (big-endian) + 2-byte length + value.

**Daglige records** (consecutive array, variable length):
```
prevRecordLength (2 bytes)
recordLength     (2 bytes)  ← total record size incl. this header
date             (4 bytes)  ← Unix timestamp, midnight UTC+1
dailyPresenceCounter (2 bytes)
activityDayDistance  (2 bytes) ← km kørt denne dag
activityChangeInfo   (N × 2 bytes)
```

**ActivityChangeInfo (2 bytes, big-endian):**
```
bit 15:     slot (0=chauffør, 1=medchauffør)
bit 14:     driverStatus (0=enkelt, 1=besætning)
bit 13:     kortStatus
bits 12-11: aktivitet (00=hvil, 01=rådighed, 10=arbejde, 11=kørsel)
bits 10-0:  minutter fra midnat (0–1439)
```

**Kort-nummer:** Plaintext ASCII-streng, mønster `[A-Z]{2}\d{14}` (fx `DK00000178901010`).

**Bekræftet output fra testfil:**
- 81 arbejdsdage korrekt udtrukket
- Start/sluttider minutpræcise
- Aktivitetsprocenter beregnet korrekt

## Fejlhåndtering og split

Fejl i dataindlæsning kan medføre at en aktivitets starttid er fra **dagen forinden**.
I dette tilfælde markeres aktiviteten automatisk som 🔴 Rød (deaktiveret).

**Split-funktionalitet:**
1. Bruger klikker på en aktivitet og vælger "Split"
2. Bruger angiver splitpunktet (dato/tid)
3. Aktiviteten opdeles i to:
   - **Del 1** (før split): sættes til `deactivated` – regnes ikke med
   - **Del 2** (efter split): kan godkendes normalt
4. Begge dele gemmes med reference til den originale aktivitet

## Åbne punkter

- [ ] Bekræft Python-bibliotek til .ddd-parsing
- [ ] Sti til inputmappe
- [ ] Frekvens for automatisk scanning (fx hvert X minut, eller ved knap-tryk)
- [ ] Hvad sker der med .ddd-filer der allerede er indlæst? (duplikat-håndtering)
