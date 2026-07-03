# Auto-godkendelse af aktiviteter

Implementeret 29/6-2026.

---

## Hvad er auto-godkendelse?

Systemet kan automatisk godkende tachograf-registreringer der ligner chaufførens normale arbejdsmønster. En aktivitet auto-godkendes kun, når den er statistisk konsistent med chaufførens historiske data for den givne ugedag.

Auto-godkendelse gælder **udelukkende** for:
- Kilden `tachograph` (ikke manuelle aktiviteter)
- Aktivitetstypen `normal` (ikke ferie, afspadsering, overnatning osv.)

---

## Betingelser for auto-godkendelse

En aktivitet auto-godkendes, hvis alle fire betingelser er opfyldt:

| Betingelse | Grænse |
|---|---|
| Minimum datagrundlag | ≥ 5 registreringer for den pågældende ugedag |
| Varighed – afvigelse | Maks. ±2,5 × std (eller ±30 % af mean, hvis std er lille) |
| Starttidspunkt – afvigelse | Maks. ±1,5 time fra gennemsnitlig starttid |
| Aktivitetstype | Kun `normal` tachograf |

Hvis én betingelse ikke er opfyldt, sættes aktiviteten til `pending` og flagges med en eller flere årsager til manuel gennemgang.

---

## Baseline – den statistiske model

Systemet vedligeholder en **EmployeeBaseline** pr. medarbejder pr. ugedag (mandag = 0, søndag = 6).

Hvert baseline-record indeholder:

| Felt | Indhold |
|---|---|
| `sample_count` | Antal godkendte aktiviteter der indgår |
| `duration_mean_minutes` | Gennemsnitlig varighed (minutter) |
| `duration_m2_minutes` | Welford M2 (bruges til std-beregning) |
| `start_hour_mean` | Gennemsnitlig starttid (decimal timer, fx 7,5 = 07:30) |
| `start_hour_m2` | Welford M2 for starttid |
| `salt_count` | Antal aktiviteter med salt-tillæg |
| `last_updated` | Tidspunkt for seneste opdatering |

### Welford's online-algoritme

Baseline opdateres **inkrementelt** uden at gemme rådata. Algoritmen opdaterer mean og M2 i én gennemgang pr. ny observation. Standardafvigelse beregnes som populationsstd: `sqrt(M2 / n)`.

Baseline opdateres automatisk, når en aktivitet godkendes (manuelt eller automatisk).

---

## Re-godkendelse og baseline-integritet

For at undgå forfejlede statistikker ved genåbning + re-godkendelse gælder følgende regler:

| Scenarie | Opførsel |
|---|---|
| Aktivitet godkendes **første gang** | Tilføjes til baseline; de bidragede værdier gemmes på aktiviteten (`baseline_duration_minutes`, `baseline_start_hour`) |
| Aktivitet genåbnes og godkendes **uden ændringer** (< 30 sek forskel) | Springes over – tæller ikke dobbelt i baseline |
| Aktivitet genåbnes og godkendes med **ændret tidsrum** | Welford **downdate** fjerner det gamle bidrag; det nye tilføjes. Altid præcis ét bidrag pr. aktivitet |

`rebuild_baselines_for_employee` nulstiller markørerne på alle aktiviteter inden genopbygning, så en ren rekonstruktion aldrig dobbelt-tæller.

---

## Sekvens ved import

```
DDD-import
    └─ _import_activity()
           ├─ Gemmer aktivitet som `pending`
           └─ should_auto_approve()
                  ├─ Ikke nok data → forbliver `pending`
                  └─ Inden for tolerance → status = `approved`, approved_by = "AUTO"
```

---

## Sådan kommer du i gang (første gang)

1. **Importer 4 ugers .ddd-filer** via normal DDD-import.
2. **Godkend manuelt** – baseline akkumuleres for hver godkendelse.
3. **Kald rebuild-baselines** (kræver `manage_baselines`-tilladelse):
   `POST /api/auto-approval/rebuild-baselines`
   Dette genberegner baseline fra alle allerede godkendte aktiviteter.
4. Fra og med næste DDD-import auto-godkendes aktiviteter der matcher mønsteret.

**Anbefalet minimumsdata:** 4 ugers registreringer giver data nok til at starte, men forventet auto-godkendelsesrate er lav de første måneder. Robustheden stiger markant efter 3+ måneders data og er fuldt moden efter >1 år (ferie, helligdage m.m. er da repræsenteret).

### Forventet auto-godkendelsesrate over tid

| Periode | Forventet rate |
|---|---|
| Uge 1–4 | 0 % (baseline bygges op) |
| Uge 5–8 | ~50 % |
| Måned 3+ | ~60–75 % |
| År 1+ | ~80–90 % |

---

## Bulk-godkendelse

I kalender-visningen: knap **"Auto-godkend egnede"** kører `POST /api/activities/auto-approve-pending` og godkender alle ventende aktiviteter der i øjeblikket opfylder kriterierne. Returnerer `{ "approved": N, "flagged": N }`.

---

## Visning i UI

- Auto-godkendte aktiviteter vises med en **gul prik (●)** foran aktivitetsbadget i kalendervisningen.
- Knappen skifter til "● Autogodkendte" efter vellykket kørsels.
- Aktiviteter med flags (dvs. afviste auto-godkendelser) vises med et gult advarselsfelt i detaljevisningen med årsag(erne) til afvisning.

---

## API-endpoints

| Metode | URL | Beskrivelse | Tilladelse |
|---|---|---|---|
| `POST` | `/api/activities/auto-approve-pending` | Kør auto-godkendelse på alle pending | Enhver godkendt bruger |
| `POST` | `/api/auto-approval/rebuild-baselines` | Genberegn baseline (alle eller én medarbejder) | `manage_baselines` |
| `GET` | `/api/auto-approval/baseline-summary` | Oversigt over baseline-status pr. medarbejder | `manage_baselines` |

---

## Tilladelse

`manage_baselines` gives til admin-rollen ved installation. Kan tildeles andre roller via Brugeradmin → Roller.

---

## Kendte begrænsninger

**Natskiftsarbejde (midnight-wraparound)**
Starttids-baseline beregnes som decimaltal. Chaufføre der konsekvent starter tæt på midnat (fx 23:30) vil have en mean-starttid der ikke giver mening, og aktiviteterne auto-godkendes aldrig. De sættes til `pending` med en forklarende besked.

**Natskiftsarbejde (midnight-wraparound)**
Starttids-baseline beregnes som decimaltal. Chaufføre der konsekvent starter tæt på midnat vil have en mean-starttid der ikke giver mening. Disse aktiviteter sættes til `pending` med en forklarende besked og skal godkendes manuelt.

---

## Filer

| Fil | Indhold |
|---|---|
| `app/calculators/auto_approval.py` | `should_auto_approve()` – selve beslutningslogikken |
| `app/calculators/baseline_updater.py` | Welford-opdatering og rebuild-funktion |
| `app/routers/auto_approval_router.py` | Admin-endpoints (rebuild, summary) |
| `app/database/models.py` | `EmployeeBaseline`-model; `Activity.auto_approved`, `.auto_approval_flags`, `.baseline_duration_minutes`, `.baseline_start_hour` |
| `tests/test_auto_approval.py` | Funktionstest for should_auto_approve |
| `tests/test_baseline_updater.py` | Funktionstest for Welford-opdatering |
