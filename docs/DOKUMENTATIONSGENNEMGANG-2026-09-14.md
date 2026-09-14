# Gennemgang af Brugervejledning.docx og Teknisk dokumentation.docx

**Dato:** 2026-09-14
**Metode:** Hele kodebasen (routers, calculators, parsers, frontend), alle `docs/*.md`, alle `docs/superpowers/plans` og `specs` (37 features, 2026-06-22 → 2026-09-11) samt hele `docs/build_docs.py` (kilden til de to `.docx`-filer) er læst igennem og sammenholdt.

De to dokumenter genereres af `docs/build_docs.py`. Begge har et hardkodet forsidedatostempel **"Juni 2026"**, men indeholder faktisk indhold helt frem til 2026-09-10 (`ot_extra_alle_timer`) — så selve datostemplet er misvisende, men ikke i sig selv en indholdsmangel. Det seneste kapitel i begge dokumenter er **Dagsplan** (dateret specs 2026-09-09). Alt implementeret **efter** det (dvs. 2026-09-10 og 2026-09-11) mangler strukturelt, bortset fra `ot_extra_alle_timer` som blev indsat retroaktivt i §5.6/§9.6.

---

## A. Kritiske mangler — features der slet ikke er dokumenteret

Disse findes i koden (og er brugerfacing/produktionsklare), men optræder intetsteds i de to dokumenters kapitler — kun evt. som et enkelt ord i en menu-liste.

1. **Vagtplan-fanen (helt kapitel mangler)** — implementeret 2026-08-21, er et fuldt 4-ugers rostergrid med fravær/kommentarer pr. medarbejder/dag, egen tilladelsesmodel (`vagtplan_view`/`vagtplan_edit_own`/`vagtplan_edit_all`), en hel router (`vagtplan_comments.py`), "Fravær i morgen"-oversigt, afdelingsfilter osv. Den nævnes kun som ét ord i navigationslisten (Bruger §2.1). Dagsplan (yngre feature) fik til sammenligning et helt kapitel (Bruger §13, Teknisk §14). Vagtplan bør have et tilsvarende kapitel i begge dokumenter.

2. **Fraværsoversigt (helt kapitel mangler)** — egen sidebar-side, egen router (`absence_overview_router.py`), egen tilladelse (`absence_overview`), to forskellige eksportformater (pr. medarbejder / pr. fraværstype med typevalg). Nævnes kun som ét ord i navigationslisten. Ingen forklaring af hvordan man bruger filtrene eller hvad de to eksporttyper indeholder.

3. **Vognpark/Vehicle-administration (helt kapitel mangler)** — vogn-CRUD nævnes kun i navigationslisten og i sammenhæng med Dagsplan. Selve opret/rediger/slet-vogn-workflowet (inkl. den helt nye Vognpark/Alle-underfane-opdeling, se punkt 6) er ikke beskrevet noget sted.

4. **Vognpark/Alle-underfaner (nyeste feature, 2026-09-11)** — vogn-checkboksen "Vognpark" og de to underfaner på vognsiden ligger dateret *efter* dokumenternes seneste indhold og er slet ikke med. Dette er reelt uundgåeligt givet hvornår dokumentet sidst blev genereret, men bør være det næste, der tilføjes.

5. **"Rediger fraværsperiode" (2026-09-07)** — mulighed for at ændre fra/til-dato på en hel flerdages fraværsperiode i ét hug (i stedet for dag for dag), inkl. automatisk sletning/oprettelse af dage og spærring hvis en berørt dag ligger i en lukket lønperiode. Et ret indgribende, let-at-misforstå feature, som ikke nævnes noget sted.

6. **Afløser-feltet (`afloeser`, 2026-08-27)** — et medarbejderflag der slår SH-søgnehelligdagstillæg (kode 4/63) fra, medmindre der er en godkendt kørselsaktivitet den dag; farvekodes særskilt i flere visninger. Optræder ikke i medarbejder-felt-tabellen i Bruger §7.2, og ikke i SH-reglerne i Teknisk §5.4/Bruger §9.5 — på trods af at det direkte ændrer SH-udregningen for en hel personalegruppe.

7. **Microsoft Entra ID / SSO-login** — en hel, alternativ login-metode (`POST /api/auth/sso`, MSAL i frontend) er slet ikke nævnt i noget kapitel, hverken teknisk eller for brugere (hvordan logger man ind med SSO, hvad kræver det af opsætning).

8. **Ugentlig kontra daglig overarbejdsloft (`hourly_fixed` vs. `hourly_flexible`)** — dette er den mest væsentlige *tekniske* mangel: `hourly_fixed`-medarbejdere har et **dagligt** loft for normaltid/OT-13 (nulstilles hver dag), mens `hourly_flexible`-medarbejdere har et **ugentligt, fælles** loft (37 t normal + 5 t OT-1-3, mandag–søndag, nulstilles hver mandag), delt på tværs af alle vagter i ugen. Teknisk dokumentation §5 beskriver kun det daglige forbrug af loftet — den fundamentale forskel mellem de to aftaletyper i selve loft-logikken nævnes ingen steder, kun at de "begge" bruger `calculate_overtime()`.

9. **Timeseddel-udsendelse pr. mail ("Send"/"Send timesedler")** — funktionen der mailer PDF-timesedler direkte til medarbejderens registrerede mailadresse (enkeltvis og i bulk, med fejlhåndtering hærdet 2026-08-29) er ikke beskrevet som selvstændigt workflow — kun PDF-download nævnes (Bruger §9.2).

10. **§56-oversigtsknappen og sygdoms-konflikt-modalen** — "§56"-knappen på Medarbejdere-siden (read-only liste over aktive §56-aftaler) og forced-choice-dialogen der dukker op, når man opretter "Sygdom" på en medarbejder med aktiv §56, er ikke beskrevet — kun selve §56-feltet og 30-dages-advarslen (Bruger §7.6) er med.

---

## B. Vigtige mangler — dokumenteret, men væsentligt ufuldstændigt

1. **DDD-genimport/dedup-logikken er forældet i Teknisk §4.1** — dokumentet beskriver 2026-07-02-rettelsen (udvidelse i stedet for skip ved senere sluttid), men *ikke* de langt nyere og mere komplekse regler fra `import_ddd.py`: præference for en ventende rettelseslinje frem for en godkendt/deaktiveret linje ved overlap (rettet efter en fejl der skabte **1.273 dubletlinjer**, fundet 2026-09-11), sammenligning mod `original_*`-felter i stedet for evt. manuelt rettede værdier, SAVEPOINT-arbejdsomgåelsen for en SQLAlchemy/pysqlite-fejl, og fuld session-rollback ved fejl i én aktivitet under en batch-import. Dette er den mest bug-historik-tunge del af hele kodebasen og fortjener en opdatering.

2. **Springertillæg er kun sporadisk nævnt** — selve fluebenet i aktivitetsoversigten (der styrer om en medarbejder får springertillæg i den aktuelle periode, og at det nulstilles automatisk hver ny periode) er ikke forklaret som brugerworkflow — kun en bisætning om "springer-suffix" i prøvekørsel-Excel'en (Bruger §9.1) og at det vises særskilt i Lønafregning (§12.2).

3. **Brugeroprettede overtids-/tillægssatser kan være uden effekt** — Stamdata-modalen for at oprette en ny overtids-/tillægssats advarer eksplicit brugeren om, at "beregningsmotoren ikke kender reglen for hvornår den anvendes endnu" — dvs. en ny sats gemmes, men bruges reelt kun hvis den efterfølgende også kobles på via en Løntypekodes "Sats-kilde" til CSV-eksport; den påvirker **ikke** selve lønberegningen/visningen i øvrigt. Denne meget vigtige begrænsning nævnes i UI'et men ikke i Bruger §6.2/§10.2 eller Teknisk §6.

4. **Danløn-kodernes placeholder-status er utydelig i hoveddokumenterne** — de fleste `DANLOEN_CODE_*`-konstanter er stadig litterally `"1"` (jf. `pay_rates.py`s egen kommentar "kravdokument: disse findes pt. ikke"). Teknisk §7.4 henviser til at koder "konfigureres i Stamdata", hvilket er korrekt for allerede-seedede rækker, men gør ikke opmærksom på at ret mange af standardkoderne stadig er midlertidige placeholders indtil lønafdelingen oplyser de rigtige Danløn-koder.

5. **Ingen automatisk overtidsberegning for nye "Aftale"-typer** — dette er allerede eksplicit indrømmet i selve scriptet (se C.2 nedenfor), men værd at fremhæve: hvis en admin opretter en ny aftaletype i Stamdata → Aftale, får medarbejdere med den type **ingen** overtidstillæg og **ingen** søn-/helligdagstillæg overhovedet — kun flad normaltid. Dette er reelt en fælde for en admin, der ikke har læst den tekniske note.

6. **Genåbning af lønperiode sveje "forvildede" aktiviteter** — når en lukket periode genåbnes, flyttes aktiviteter der i mellemtiden er blevet oprettet i den *efterfølgende* periode (fordi de skulle placeres et andet sted, jf. `get_billing_period()`) automatisk tilbage. Denne automatik er ikke nævnt i Bruger §9.3/§11 (Administration → Lønperiode).

---

## C. Selv-indrømmede huller (allerede markeret som ufærdige i `build_docs.py`)

Disse er *ikke* mangler i dokumentationen som sådan — scriptet er ærligt om dem — men bør fremhæves, fordi de er reelle funktionelle begrænsninger en bruger/udvikler bør kende:

1. **Teknisk §2.6 (Holidays):** `half_day_from`-feltet er kun forberedt til fremtidig brug — der er **ingen** faktisk helligdagstillæg-beregning baseret på halvdags-feltet endnu, kun UI-visning.
2. **Teknisk §5.5 / Bruger §8 (Aftale-typer):** eksplicit indrømmet "midlertidig afgrænsning" — se punkt B.5 ovenfor.

---

## D. Modsigelser og forældet indhold i de øvrige `docs/*.md`-filer

Disse filer er ikke selve Brugervejledningen/Teknisk dokumentation, men fungerer som kildemateriale/reference ved siden af, og flere af dem modsiger hinanden eller de to hoveddokumenter:

1. **Danløn CSV-feltantal og afsluttende semikolon — direkte modsigelse.** `docs/aendringer-danloen.md` (opdateret 2026-09, den nyeste) siger: korrekt linje har **6 felter**, og den afsluttende semikolon er **betinget** (kun når totalkolonnen er tom) — "det er tilsigtet, ikke en fejl". De to rodmappe-filer `fejl-danloen-format.md` og `regel-fast-antal-felter.md` siger det modsatte: **5 felter**, afsluttende semikolon **altid** påkrævet, og beskriver dette som en bug der skal rettes. Disse to filer bør enten arkiveres eller rettes, da de kan få en fremtidig udvikler (menneskelig eller AI) til fejlagtigt at "rette" korrekt opførsel til forkert opførsel.
2. **`docs/AGENTS.md` er den mest forældede fil** — den "åbne spørgsmål"-liste hævder stadig at Danløn-koder er sat til `"1"` for alle og at .ddd-parserbiblioteket ikke er afklaret — begge dele er for længst afklaret/implementeret andetsteds (Stamdata → Løntypekoder, hhv. den brugerdefinerede binære parser i `ddd_parser.py`). Filen er beregnet som "cheat sheet" for AI-agenter og risikerer at give forkert vejledning.
3. **`docs/REQUIREMENTS.md`** fremstår som en aldrig-opdateret v1-kravspec: dens "Åbne punkter"-liste nævner stadig midlertidige Danløn-koder og et uafklaret parser-bibliotek, begge løst for længst.
4. **`docs/ARCHITECTURE.md`s "Åbne punkter"** (IP/port/backup/autostart) er alle besvaret i `deploy/PRODUKTION_OPSAETNING.md`, som til gengæld ikke refereres fra ARCHITECTURE.md.
5. **To uafhængige sikkerhedsrapporter** (`docs/SECURITY_RAPPORT.md` og PDF'en genereret af `docs/build_security_report.py`) vedligeholdes hver for sig og er allerede løbet fra hinanden (forskellige findings-lister, forskellige "løst"-datoer). Begges linjenummer-referencer til kildekoden er desuden allerede en smule forskudt af senere redigeringer.
6. **Overtidssatserne (44,54 kr / 109,40 kr) er hardkodet fire steder** (`OVERTIME_RULES.md`, `PAYROLL_RULES.md`, `REQUIREMENTS.md`, `AGENTS.md`) — en fremtidig satsændring kræver at huske alle fire, hvoraf de to sidste allerede har vist sig at blive glemt ved tidligere opdateringer.
7. **`docs/AUTO_APPROVAL.md`** har et rent redaktionelt problem: afsnittet om natskiftsarbejde/midnatsovergang er duplikeret næsten ordret to gange i træk (linje ~137-141).

---

## E. Mindre/kosmetiske observationer

- Begge `.docx`-forsider viser "Juni 2026", selvom indholdet reelt er ajourført til medio september 2026 — bør opdateres til at bruge den faktiske genereringsdato (`datetime.now()`), så det ikke fejlagtigt læses som et 3 måneder gammelt snapshot.
- `docs/SECURITY_RAPPORT.md`s header-dato (21. juni) er tilsvarende ikke opdateret trods indholdsrettelser helt frem til 29. august.
- Flere linjenummer-referencer i `SECURITY_RAPPORT.md` og `build_security_report.py` er allerede en smule forskudt fra den aktuelle kildekode — en påmindelse om at denne slags pinned referencer bør undgås eller løbende valideres.
- `docs/AGENTS.md` linje 65: stavefejl "Bedeutning" (tysk) i stedet for "Betydning".

---

## Anbefalet prioritering

1. **Tilføj de to manglende kapitler "Vagtplan" og "Fraværsoversigt"** til begge dokumenter — de er de eneste hele, aktive hovedfunktioner uden nogen beskrivelse overhovedet.
2. **Tilføj et afsnit om `hourly_fixed` vs. `hourly_flexible`-loftforskellen** i Teknisk §5 — det er den mest forretningskritiske tekniske detalje der mangler.
3. **Opdatér Teknisk §4.1 (DDD-import)** med 2026-09-dedup-reglerne, givet hvor fejlfølsomt dette område historisk har vist sig at være.
4. **Dokumentér afløser-feltet** i medarbejder- og SH-afsnittene.
5. **Ryd op i de tre modstridende Danløn-CSV-formatfiler** (behold kun `aendringer-danloen.md`, eller opdatér/arkivér de to andre).
6. **Opdatér eller fjern `docs/AGENTS.md`s "åbne spørgsmål"** så de ikke modsiger den faktiske, langt mere modne implementering.
7. Tilføj Vognpark/Alle-underfanerne (2026-09-11) og "Rediger fraværsperiode" (2026-09-07) ved næste regenerering — de er blot faldet uden for det seneste snapshot.
