# AI Agent Context – Lønsystem

Dette dokument er til brug for AI-agenter der arbejder på lønsystemet. Det giver et hurtigt overblik over systemet, regler og kodebasen.

---

## Hvad er systemet?

Et webbaseret lønsystem til behandling af tachografdata (.ddd-filer) og lønberegning for lastbilchauffører under **Transport- og Logistikoverenskomsten 2025-2028** (DIO I (ATL) / 3F).

**CVR-nummer:** 13246505

---

## Teknologistack

| Komponent | Teknologi |
|-----------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Database | SQLite (WAL-mode) |
| Frontend | HTML + Vanilla JS + CSS / Jinja2 |
| .ddd-parsing | Python (bibliotek TBD) |
| Excel-output | openpyxl |
| CSV-output | Python stdlib |

---

## Vigtige regler

### Lønperioder
- Altid præcis **14 dage**
- Starter ikke nødvendigvis d. 1. i måneden
- Næste periode starter på **næste hverdag** efter forrige periods slutdag
- Systemet udleder automatisk lønperiode fra valgt dato

### Effektiv arbejdstid
- **Total tid fra start til slut** (sluttid minus starttid)
- Inkluderer rådighedstid, hvil, kørsel, andet arbejde
- Inkluderer manuelt tastede pålæsnings-/aflæsningstider

### Minimum 4-timer regel
- Vagter under 4 timer → automatisk 🔴 Rød, kræver manuel godkendelse
- Godkendelse kræver initialer og begrundelse

### Overtime (se `OVERTIME_RULES.md` – opdateret 2026-07-02)
- Tidlig overarbejde: kl. 05:00–06:00 → +44,54 kr./time (fortærer IKKE normaltids-loftet)
- Normalt overarbejde (op til 3 t i kl. 06-18/18-21): +44,54 kr./time
- Ekstra overarbejde (nat 21-05, samt over 3 t): +109,40 kr./time
- Registreret normaltid (7/7,5/8 t) kan kun forbruges i tidsrummet 06-18; loftet deles pr. dag på tværs af flere aktiviteter, og hører til vagten (kan krydse midnat) medmindre vagten starter på en søndag/helligdag
- Søndage/helligdage: al kørt tid → kode 1 + kode 9, uanset tidspunkt. Lørdag har INGEN særregel – regnes altid som en normal hverdag med lørdagens eget (typisk 0) loft

### Ubekvem tid
- Kl. 18:00–23:00: +46,93 kr./time
- Kl. 23:00–06:00: +52,65 kr./time

### Anciennitet
- Automatisk tæller fra ansættelsesdato
- 9 måneder → pop-up ved programopstart hvis løngruppe ikke opdateret

---

## Farvestatus for aktiviteter (bjælker)

| Farve | Status | Bedeutning |
|-------|--------|------------|
| 🔴 Rød | `deactivated` | Kræver handling (split eller deaktivering) |
| 🟢 Grøn | `approved` | Godkendt af medarbejder med initialer |
| 🔵 Blå | `pending` | Ikke godkendt endnu, men data OK |

Alle bjælker skal være 🟢 grønne før "Kør løn" er aktiv.

---

## Aktivitet (bjælke) – vigtige felter

- `source`: `tachograph` eller `manual` – manuelle vises med `(K)` prefix
- `parent_activity_id` + `split_part`: bruges ved split af aktivitet
- Split del 1 = deaktiveret, del 2 = kan godkendes

---

## CSV til Danløn

Kolonner: A=CVR (13246505), B=medarbejdernr, C=Danløn-kode, D=timer, E=sats, F=afspadsering

**Danløn-koder: midlertidigt alle sat til "1"** – opdateres når koderne kendes.

---

## Medarbejdertyper

| Kode | Beskrivelse | Timeløn |
|------|-------------|---------|
| `trainee` | Under oplæring | 159,65 kr. |
| `driver` | Nyansættelse | 174,15 kr. |
| `driver_senior` | Efter 9 måneder | 182,30 kr. |
| `driver_qualified` | Faglært | 186,30 kr. |
| + `qualification_allowance` | Kvalifikationstillæg | +3,80 kr. |

---

## Filstruktur

```
lønsystem/
├── AGENTS.md               ← dette dokument
├── REQUIREMENTS.md         ← fuld kravspecifikation
├── ARCHITECTURE.md         ← teknisk arkitektur
├── DATA_MODEL.md           ← databasemodel
├── PAYROLL_RULES.md        ← lønberegningsregler
├── OVERTIME_RULES.md       ← overtidsregler
├── DDD_FORMAT.md           ← .ddd filformat
├── main.py                 ← FastAPI app
├── database/
├── parsers/
├── calculators/
├── exporters/
├── routers/
├── static/
└── templates/
```

---

## Åbne spørgsmål (spørg bruger – gæt aldrig)

- Sti til .ddd inputmappe
- Sti til disponentgrupper Excel-fil
- Output-mapper for CSV og Excel
- Danløn-koder (sættes til "1" indtil de kendes)
- Python-bibliotek til .ddd-parsing
- Overtid: beregnes dagligt eller ugentligt?
- Afspadsering (CSV kolonne F): hvad skal stå?
- Serverens IP/hostname og port
