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
date             (4 bytes)  ← Unix timestamp, midnight UTC (bekræftet ved byte-analyse 2026-07-01)
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
bits 10-0:  minutter fra midnat (0–1439), også relativt til UTC-midnat
```

⚠️ Dato og minutter i filen er **UTC**, ikke dansk lokal tid. `ddd_parser.py` konverterer
start/slut-tider, segmenter og pauseintervaller til Europe/Copenhagen (DST-korrekt via
`zoneinfo`) i `_build_activities`. Kræver `tzdata`-pakken på Windows (tilføjet i
`requirements.txt`), da Windows ikke har sin egen IANA-tidszonedatabase.

**Kort-nummer (CardNumber):** Feltet er ifølge EU-tachografspecifikationen 16 tegn:
`[A-Z]{2}\d{14}` i rå bytes (fx `DK00000012666013`), men kun de **første 14 tegn**
(`driverIdentification`, fx `DK000000126660`) er det stabile kortnummer der bruges til
medarbejder-matching. De sidste 2 cifre er `cardReplacementIndex` + `cardRenewalIndex`,
som ændrer sig hver gang kortet udskiftes/fornys – de gemmes derfor ikke som del af
`tachograph_card_number`. Bekræftet ved byte-analyse: en længde-markør (`0x0e` = 14)
går umiddelbart forud for feltet i filen, og feltet efterfølges direkte af
kortudstederens navn (`RIGSPOLITICHEFEN...`) uden separator.

**Dagsstart og indledende pause:** Hver dags activityChangeInfo-array starter altid
med en "hvil"-post ved minut 0 – det er blot videreført status fra dagen før, ikke en
reel pause. Bekræftet ved analyse af 132 arbejdsdage: i 129 af dem findes en ekstra
hvil-post (typisk 1-11 min) umiddelbart efter minut-0-posten, lige inden den første
rigtige arbejds-/kørselspost. Det er chaufførens faktiske dagsstart (en kort pause
inden arbejdet begynder). `_build_activities()` bruger denne post som visningsstart
(`day_start_minute`), så pausen indgår i den viste arbejdstid og i `pause_intervals`
– men den er stadig ubetalt, da pause_intervals fratrækkes i lønberegningen.

**Bekræftet output fra testfil:**
- 132 arbejdsdage korrekt udtrukket
- Start/sluttider minutpræcise (efter UTC→lokal-konvertering, inkl. indledende pause)
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

- [x] Bekræft Python-bibliotek til .ddd-parsing – ingen PyPI-bibliotek findes; custom parser i `ddd_parser.py` er bekræftet korrekt (kortnummer + UTC→lokal tid rettet 2026-07-01)
- [ ] Sti til inputmappe
- [ ] Frekvens for automatisk scanning (fx hvert X minut, eller ved knap-tryk)
- [ ] Hvad sker der med .ddd-filer der allerede er indlæst? (duplikat-håndtering)
