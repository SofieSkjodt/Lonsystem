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

**Tillæg ubekvem arbejdstid:**
- Kl. 18.00–23.00: +46,93 kr./time
- Kl. 23.00–06.00: +52,65 kr./time

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
| C | Danløn-kode (AFKLARES – koder kendes endnu ikke) |
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

- [ ] Sti til disponentgrupper-Excel
- [ ] Sti til .ddd-filer inputmappe
- [ ] Output-mapper til CSV og Excel
- [ ] Danløn-koder (midlertidigt "1" for alle)
- [ ] Afspadsering (CSV kolonne F) – hvad skal stå?
- [ ] Overtid: beregnes dagligt eller ugentligt?
- [ ] Serverens IP/hostname og port til deployment
- [ ] Python-bibliotek til .ddd-parsing (bekræftes)

## Afklarede punkter

- [x] **Platform**: Lokal web-applikation (FastAPI + SQLite + browser)
- [x] **Lønperiode**: Altid 14 dage, starter på næste hverdag efter forrige periodes slutdag
- [x] **CSV generering**: Kun ved klik på "Kør løn" – ingen fast dato
- [x] **Effektiv tid**: Total tid fra start til slut (inkl. alle tachografaktiviteter + pålæsning/aflæsning)
- [x] **Split**: Opdeling af aktivitet i del 1 (deaktiveret) og del 2 (kan godkendes) – bruges ved fejl i starttid
- [x] **Minimum 4 timer**: Markeres rød, kræver manuel godkendelse med initialer og begrundelse
- [x] **Overarbejde**: Håndteres (se OVERTIME_RULES.md) – tidlig (05-06), normal (1-3 t), ekstra (>3 t)
- [x] **Danløn-koder**: Midlertidigt alle "1"
- [x] **CVR-nummer**: 13246505
- [x] **Medarbejdertyper**: Alle typer (trainee, driver, driver_senior, driver_qualified + kvalifikationstillæg)
- [x] **Pop-up anciennitet**: Vises ved programopstart med knapper "Luk" / "Gå til medarbejder for at ændre timesats"
- [x] **Manuelt input**: Dagssedler tastes manuelt – inkl. pålæsning og aflæsning (ikke i .ddd)
- [x] **Output**: Gem lokalt i mappen indtil stier kendes
