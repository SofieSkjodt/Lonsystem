# Design: DOB-overnatning (løntypekode 43)

**Dato:** 2026-08-19
**Status:** Godkendt

---

## Oversigt

I dag registreres alle overnatninger i CSV'en under løntypekode 14 ("Overnatning"). Der skal nu kunne
skelnes mellem almindelig overnatning (kode 14) og DOB-overnatning (kode 43), styret af et
afkrydsningsfelt "DOB" i opret-aktivitet-modalen for Overnatning.

Løntypekoden `DOB_overnatning` (kode 43, kvantitetstype "antal", sats-kilde peger allerede på
tillægget "DOB_overnatning" á 597 kr) og selve tillægssatsen er allerede oprettet i databasen via
Stamdata → Løntypekoder / Stamdata → Tillæg. Denne opgave omfatter kun aktivitetsoprettelsen og de
steder i beregning/visning der i dag kun kender til `"overnatning"`.

---

## Kernevalg: ny `activity_type`-værdi, ikke et boolean-felt

DOB-flaget repræsenteres som en ny `activity_type`-værdi, `"dob_overnatning"`, i stedet for et
boolean-felt (fx `is_dob`) på den eksisterende `"overnatning"`-type.

Begrundelse: Systemets generiske CSV-motor for brugeroprettede løntypekoder
(`_user_pay_type_rows()` i `app/routers/payroll_router.py`) matcher aktiviteter på
`Activity.activity_type == MasterPayType.code_key`. Løntypekoden `dob_overnatning` findes allerede
med `code_key="dob_overnatning"`. Ved at bruge denne streng som `activity_type` får kode 43
**automatisk** korrekt antal og sats i CSV-eksporten — ingen ændring nødvendig i selve
CSV-eksportfunktionerne (`export_csv`/`export_csv_post`).

Et boolean-flag ville i stedet kræve to nye hardcodede CSV-linjer (én pr. eksportfunktion) og en ny
databasemigration. Det er unødvendigt når mekanismen allerede findes.

---

## Modal "Tilføj aktivitet" (`app/templates/index.html`, `app/static/js/app.js`)

- Nyt afkrydsningsfelt "DOB" vises kun når type = Overnatning (samme betingelse som
  `isOvernatning` i `updateManualTypeVisibility()`).
- Ved bekræftelse (`confirmManualActivity()`, overnatnings-grenen): hvis krydset, sendes
  `activity_type: "dob_overnatning"` i stedet for `"overnatning"`. Start-/sluttid forbliver
  midnat-placeholder som i dag — uændret for begge varianter.
- Feltet nulstilles ved modal-åbning, ligesom `manual-salt` gør i dag.
- **Ingen redigering efter oprettelse** — flaget kan kun sættes ved oprettelse. Skal det ændres,
  slettes aktiviteten og oprettes på ny (bekræftet valg).
- `"dob_overnatning"` tilføjes **ikke** som selvstændig valgmulighed i `#manual-type`-dropdownet —
  den tilgås udelukkende via afkrydsningsfeltet.

---

## Backend — validering (`app/database/schemas.py`)

`ActivityCreate.end_after_start`-validatoren (linje ~159) springer i dag kun slut-efter-start-tjekket
over for `activity_type == "overnatning"` (fordi start_time == end_time == midnat for denne type).
Udvides til også at gælde `"dob_overnatning"` — ellers afvises oprettelsen med "Sluttid skal være
efter starttid".

Ingen ændring nødvendig i `routers/activities.py` (`create_manual_activity`): `is_absence`-logikken
(`activity_type != "normal"`) og `_BACKEND_ONLY_TYPES`-tjekket rammer allerede `"dob_overnatning"`
korrekt uden kodeændring — aktiviteten godkendes automatisk, ligesom almindelig overnatning gør i
dag.

---

## Backend — beregning (`app/routers/payroll_router.py`, `_calculate_employee()`)

Tre steder tjekker i dag udelukkende `activity_type == "overnatning"` og skal udvides til også at
matche `"dob_overnatning"`, så DOB-overnatning behandles identisk mht. IKKE at tælle som arbejdstid
og vises korrekt som "overnight"-kolonne pr. dag:

1. **Linje ~378** — dag-gruppering (`acts_by_date`): overnatning håndteres som kolonne, ikke som
   fraværsrække med tidsopdeling.
2. **Linje ~405** — `overnight_dates`: bruges til det binære "overnight"-flag pr. dag i
   dag-for-dag-oversigten (frontend-preview, prøvekørsel-Excel). Begge typer skal vise
   overnatnings-markering på deres dag.
3. **Linje ~425** — `acts_today`-filtrering: overnatningsaktiviteter (begge typer) skal fortsat
   udelukkes fra den almindelige arbejdstids-/dagtype-beregning.

**Kode-14-optællingen (linje ~406, `totals["overnight_count"]`) ændres IKKE** — den matcher kun
`"overnatning"` og udelukker dermed automatisk DOB-aktiviteter, uden yderligere logik.

**Nye felter i retur-dictet**, til brug i lønkørsel-oversigt og prøvekørsel (se nedenfor):
- `dob_overnight_count` — antal `"dob_overnatning"`-aktiviteter i perioden (samme mønster som
  `overnight_count`).
- `dob_overnight_rate` — hentes via ny funktion `load_dob_overnight_rate_from_db()`.
- `dob_overnight_kr` — `dob_overnight_count × dob_overnight_rate`, afrundet som `overnight_kr`.

## Ny loader (`app/calculators/rates_loader.py`)

```python
def load_dob_overnight_rate_from_db(db) -> Decimal:
    from database.models import MasterSupplementRate
    row = db.query(MasterSupplementRate).filter(MasterSupplementRate.label == "DOB_overnatning").first()
    return Decimal(str(row.rate)) if row else Decimal("0")
```

Samme mønster som `load_overnight_rate_from_db()`, men uden Excel-fallback (tillægget er
brugeroprettet via Stamdata, ikke Excel-seedet).

---

## CSV-eksport (`export_csv`, `export_csv_post`)

**Ingen kodeændring.** Den eksisterende `_user_pay_type_rows()`-loop henter alle
`MasterPayType`-rækker med `is_user_created=True`, tæller matchende aktiviteter
(`activity_type == code_key`) og slår sats op via `_resolve_rate(csv_rate_source, calc)`. Løntypekoden
`dob_overnatning` (kode 43, `csv_rate_source="supplement:5"`) fanges automatisk af denne mekanisme,
så snart aktiviteter med `activity_type="dob_overnatning"` findes i perioden.

---

## Lønkørsel-oversigt (frontend, `app/static/js/app.js`)

Ny linje tilføjes lige efter den eksisterende Overnatnings-linje (omkring linje 2562):

```js
${payrollRowOvernight("DOB Overnatning", emp.dob_overnight_count, emp.dob_overnight_rate, emp.dob_overnight_kr)}
```

`payrollRowOvernight()` returnerer allerede tom streng hvis antal < 1 — linjen vises kun når der er
DOB-overnatninger i perioden.

---

## Prøvekørsel-Excel (`_build_proevekoersel_workbook`, `app/routers/payroll_router.py`)

Ny betinget totalrække, mirrorende den eksisterende "Overnatning (kr.)"-række (omkring linje 762):

```python
dob_on_kr = calc.get("dob_overnight_kr", 0.0)
if dob_on_kr > 0:
    ws.append([calc["employee_name"], calc["employee_number"], "", "DOB Overnatning (kr.)",
               "", "", "", "", "", "", "", "", "", "", round(dob_on_kr, 2)])
    for cell in ws[ws.max_row]:
        cell.font = bold
```

---

## Frontend — labels (`app/static/js/app.js`)

`"dob_overnatning"` registreres statisk (ikke via den dynamiske `absence-types`-liste eller
dropdown-loopet) så aktivitetslisten/detaljevisningen viser et pænt navn i stedet for den rå
type-streng:

```js
TYPE_LABELS["dob_overnatning"] = "DOB Overnatning";
ABSENCE_LABELS["dob_overnatning"] = badgeLabel("DOB Overnatning");
ABSENCE_TYPES.add("dob_overnatning");
```

Tilføjes i `loadAbsenceTypes()` efter den eksisterende `forEach`-loop.

---

## Ikke inkluderet (bevidst fravalgt)

- DOB-flaget kan ikke rettes efter oprettelse (hverken i "Rediger aktivitet"-modalen eller andre
  steder) — bekræftet valg.
- Ingen selvstændig visuel badge-styling ud over den almindelige type-label.
- Ingen ændring af `dob_overnatning`-løntypekodens sats-kilde — allerede rettet manuelt til
  `supplement:5`.

---

## Test/verifikation

- **Oprettelse:** afkryds DOB i Overnatning-modalen → aktivitet oprettes med
  `activity_type="dob_overnatning"`, status `approved` med det samme (som almindelig overnatning).
- **Uden kryds:** aktivitet oprettes fortsat med `activity_type="overnatning"` — ingen regression.
- **Lønkørsel-oversigt:** en medarbejder med både almindelig og DOB-overnatning i perioden viser to
  separate linjer ("Overnatning" og "DOB Overnatning") med korrekte antal/sats/total.
- **CSV-eksport:** samme medarbejder giver to linjer i Danløn-CSV'en — kode 14 med
  overnatnings-satsen, kode 43 med 597 kr — uden at `export_csv`/`export_csv_post` er ændret.
- **Prøvekørsel-Excel:** viser "DOB Overnatning (kr.)"-totalrække når relevant.
- **Dag-for-dag-oversigt:** en dag med DOB-overnatning viser overnatnings-markering, og timerne den
  dag tælles ikke som normal arbejdstid.
- **Validering:** oprettelse med `activity_type="dob_overnatning"` og `start_time == end_time`
  fejler IKKE (validator-udvidelsen virker).

## Åbne punkter

Ingen.
