# Lønsystem – Kravspecifikation

## Formål
Nyt lønsystem til behandling af tachografdata (.ddd-filer) og lønberegning for lastbilchauffører under Transport- og Logistikoverenskomsten 2025-2028 (DIO I (ATL) / 3F).

---

## Overordnet flow

1. **Import** – .ddd-filer indlæses automatisk og omdannes til aktiviteter (bjælker)
2. **Oversigt (Startside)** – Vis lønperiode med aktiviteter per chauffør, farvekodet status
3. **Godkendelse** – Sagsbehandler godkender, redigerer eller splitter aktiviteter
4. **Prøvekørsel** – Generer Excel-udkast til kontrol
5. **Lønkørsel** – Generer endelig CSV til Danløn

---

## Startside (TO-BE)

- Viser tabel over alle chaufførers aktiviteter for den aktuelle lønperiode
- **Default dato**: dagens dato → udleder automatisk lønperiode
- **Lønperioder**: Antageligt 1.-14. og 15.-ultimo hver måned (AFKLARES)
- Kan skifte dato frem/tilbage
- **Farvestatus**:
  - 🔴 Rød = deaktiveret (kræver manuel handling: split eller redigering)
  - 🟢 Grøn = godkendt
  - 🔵 Blå = ikke godkendt, men data opfylder krav
- Manuel indtastning vises med `(K) HH:MM` prefix
- **Filtre**: Dato + Disponentgruppe
- Disponentgrupper vedligeholdes i Excel-fil (lokal sti – AFKLARES)
- Knap: **"Lav prøvekørsel"** (for alle eller én chauffør)
- Knap: **"Kør løn"** (genererer CSV til Danløn)
- Alle bjælker skal være grønne før "Kør løn" er aktiv

---

## Aktivitetsvisning (klik på aktivitet)

Felter der vises og kan redigeres:

| Felt | Type |
|------|------|
| TurNR (6 cifre) | Tekst |
| Status (Godkendt / Deaktiveret) | Dropdown |
| Tachografkortnr | Tekst (read-only) |
| Start (tidspunkt) | Dato/tid, redigerbar |
| Slut (tidspunkt) | Dato/tid, redigerbar |
| Rådighedstid | d.t.m (%) |
| Hvil/pause | d.t.m (%) |
| Andet arbejde | d.t.m (%) |
| Kørsel | d.t.m (%) |
| Godkendt af | Initialer (fri tekst ved godkendelse) |
| Oprettet af | System / Manuelt (auto) |
| Kommentar | Fri tekst |
| Sum, effektiv tid | d.t.m (%) – beregnet |

---

## Medarbejderoprettelse (TO-BE)

- Knap til at oprette ny medarbejder i "database"
- Felter (AFKLARES endeligt):
  - Navn
  - Medarbejdernummer
  - Tachografkortnummer
  - Ansættelsesdato
  - Løngruppe / tillægstype
  - Faglært (Ja/Nej)
  - Anciennitet (automatisk tæller fra ansættelsesdato; 0 eller 9 måneder)
- **Pop-up-advarsel** når medarbejder har været ansat i 9 måneder, hvis:
  - ikke faglært, OG
  - ikke allerede tildelt anciennitetstillæg fra start

---

## Lønberegning

### Overenskomstgrundlag
Transport- og Logistikoverenskomsten 2025-2028, satser pr. 1. marts 2026:

| Type | Timeløn ved nyansættelse | Timeløn efter 9 mdr. | Timeløn faglært |
|------|--------------------------|----------------------|-----------------|
| Chauffør under oplæring | 159,65 kr. | – | – |
| Chauffør | 174,15 kr. | 182,30 kr. | 186,30 kr. |
| Chauffør m. kvalifikationstillæg | 177,95 kr. | 186,10 kr. | 190,10 kr. |

**Overtidstillæg (pr. time ud over grundløn):**
- Timen før + 1.-3. time efter normal arbejdstid: +44,54 kr.
- Derefter samt søn- og helligdage: +109,40 kr.

**Tillæg ubekvem arbejdstid – UDGÅET (erstattet 10/6-2026):**
Dette var det oprindelige krav (18-23: +46,93 kr./time, 23-06: +52,65 kr./time), men er
bekræftet af bruger og fuldstændigt erstattet af de tre overtidstillæg ovenfor
(se `docs/PAYROLL_RULES.md`, afsnit "Ubekvem arbejdstid – UDGÅET"). Findes IKKE i den
nuværende kode og skal ikke lægges til oveni overtidstillæggene.

### Minimum 4-timer regel
Ifølge overenskomsten (§ 5 afløser / Chaufføroverenskomstens § 3, stk. 1):
- Timelønnede chauffører kan ikke aflønnes for færre timer end pågældende dags normale arbejdstid.
- Ved antagelse efter normal arbejdstids begyndelse: minimum 4 timer.
- Vagter under 4 timer markeres – AFKLARES: automatisk oprundes eller blot markeres til godkendelse.

---

## Slutprodukt – CSV til Danløn

Kolonnestruktur:

| Kolonne | Indhold |
|---------|---------|
| A | CVR-nummer |
| B | Medarbejdernummer |
| C | Danløn-kode (konfigureres pr. løntype i Stamdata → Løntypekoder – seedet med placeholder "1" for de fleste typer indtil lønafdelingen oplyser de rigtige koder på hver installation) |
| D | Antal timer |
| E | Timesats / tillægssats |
| F | Afspadsering |

---

## Prøvekørsel – Excel-udkast

- Genereres fra "Prøvekørsel"-knap
- Viser mellemregninger
- Markerer dage med **under 4 timer** og **over 12 timer**
- Sti til outputfil: AFKLARES

---

---

## Helligdagskalender

Systemet vedligeholder automatisk en kalender over danske helligdage, der bruges til markering i aktivitetsvisningen og som datagrundlag for fremtidig lønberegning ved helligdagsarbejde.

### Auto-generering

Ved serveropstart genereres helligdage automatisk for de næste 5 år (indeværende år + 4 fremover). Følgende helligdage medtages:

**Faste datoer:**
- Nytårsdag (1. januar)
- 1. maj — fri fra kl. 12:00
- Grundlovsdag (5. juni) — fri fra kl. 12:00
- Juleaftensdag (24. december)
- 1. juledag (25. december)
- 2. juledag (26. december)
- Nytårsaftensdag (31. december)

**Påskebaserede (beregnes automatisk):**
Skærtorsdag, Langfredag, Påskedag, 2. påskedag, Kristi Himmelfartsdag, Pinsedag, 2. pinsedag.

Store Bededag medtages ikke (afskaffet fra 2024).

### Manuel administration

Administratorer kan via **Stamdata → Helligdage**:
- Se alle helligdage i kalenderen
- Tilføje manuelle helligdage (fx særlige fridage) med valgfri halvdagstid
- Slette helligdage
- Generere helligdage for et specifikt år (ved behov)

Kun brugere med rettigheden **"Administrér helligdage"** har adgang til denne fane.

### Markering i aktivitetskalenderen

Dage der er helligdage fremhæves med grøn baggrundsfarve (`#056a10`) i aktivitetskalenderens kolonneoverskrifter. Halvdagshelligdage vises med et "½"-badge og tidspunktet (fx "½ fra 12:00"). Ved hover vises helligdagens navn som tooltip.

### Fremtidig integration

`half_day_from`-feltet er forberedt til brug i lønberegningsintegration, når helligdagstillæg skal implementeres (separat fase).

---

## Åbne punkter (AFKLARES)

Kun miljøspecifikke punkter er reelt stadig åbne – se `deploy/PRODUKTION_OPSAETNING.md` for
hvordan de besvares på den konkrete server:

- [ ] Serverens IP/hostname og port til den enkelte installation (default port 8000)
- [ ] Eventuel justering af .ddd-inputmappe/output-mapper væk fra standardplaceringen

Følgende punkter er siden afklaret og flyttet til "Afklarede punkter" nedenfor:
disponentgrupper (nu en databasetabel, ikke en Excel-fil), Danløn-koder (nu
Stamdata-konfigurerede pr. løntype), afspadsering (egen løntypekode i CSV'en), overtidsregel
(dagligt for hourly_fixed, ugentligt for hourly_flexible) og .ddd-parsing (selvskrevet binær
parser, intet eksternt bibliotek).

## Afklarede punkter

- [x] **Platform**: Lokal web-applikation (FastAPI + SQLite + browser)
- [x] **Lønperiode**: Altid 14 dage, faste perioder mandag-søndag beregnet fra et fast anker (mandag 1/6-2026), ikke "næste hverdag efter forrige periode"
- [x] **CSV generering**: Kun ved klik på "Kør løn" – ingen fast dato
- [x] **Effektiv tid**: Total tid fra start til slut (inkl. alle tachografaktiviteter + pålæsning/aflæsning)
- [x] **Split**: Den oprindelige aktivitet deaktiveres; del 1 og del 2 oprettes som nye, begge afventende (skal godkendes hver for sig) – bruges ved fejl i starttid
- [x] **Minimum 4 timer**: Markeres med advarselsikon (forbliver afventende, ikke deaktiveret), kræver manuel godkendelse med initialer og begrundelse
- [x] **Overarbejde**: Håndteres (se OVERTIME_RULES.md) – tidsrumsbaseret (kl. 05-06, 18-21 samt timer ud over normaltidsloftet i kl. 06-18, kl. 21-05), ikke akkumulerede timer
- [x] **Danløn-koder**: Konfigureres pr. løntype i Stamdata → Løntypekoder (DB er authoritative); seedet med placeholder "1" for de fleste typer, skal gennemgås pr. installation
- [x] **.ddd-parsing**: Selvskrevet binær parser (`app/parsers/ddd_parser.py`), intet eksternt bibliotek
- [x] **Disponentgrupper**: Databasetabel (`dispatcher_groups`), administreres i Stamdata – ikke længere en Excel-fil
- [x] **Overtid**: `hourly_fixed`-medarbejdere har et dagligt loft, `hourly_flexible`-medarbejdere et ugentligt, fælles loft (37t normaltid + 5t OT-1-3, mandag–søndag)
- [x] **CVR-nummer**: 13246505
- [x] **Medarbejdertyper**: Der er ikke længere en fast type-enum (trainee/driver/driver_senior/driver_qualified) – i stedet en Stamdata-styret `agreement_kind` (systemnøgler `hourly_fixed`/`hourly_flexible`) + fritekst `agreement_type` fra Excel/Stamdata, med tilhørende timesats
- [x] **Pop-up anciennitet**: Vises ved programopstart med knapper "Luk" / "Gå til medarbejder for at ændre timesats"
- [x] **Manuelt input**: Dagssedler tastes manuelt – inkl. pålæsning og aflæsning (ikke i .ddd)
- [x] **Output**: Gem lokalt i mappen indtil stier kendes
