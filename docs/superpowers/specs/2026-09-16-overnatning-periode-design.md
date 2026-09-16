# Design: Overnatning over en periode

**Dato:** 2026-09-16
**Status:** Afventer brugergodkendelse

---

## Oversigt

I dag kan overnatning (og DOB overnatning) kun oprettes for én dag ad gangen via "Tilføj
aktivitet"-modalen (`confirmManualActivity()`, `app/static/js/app.js:2765-2783`). Hvis en medarbejder
er væk flere dage i træk, skal brugeren gentage oprettelsen manuelt for hver enkelt dag.

Der skal nu kunne udfyldes en "Til dato" for overnatning/DOB overnatning, ligesom for ferie, sygdom
m.fl. i dag — hver kalenderdag i intervallet får sin egen overnatnings-aktivitet, så optællingen
(`overnight_count`/`dob_overnight_count` i `payroll_router.py`) automatisk giver præcis 1 pr. dag,
uden ny tælle-logik.

**Hvis "Til dato" ikke udfyldes, er adfærden 100% uændret** — samme enkelt-dags-opførsel som i dag.

---

## Beslutninger (bekræftet med bruger)

1. **Alle kalenderdage inkl. weekend** medtages i perioden — IKKE kun hverdage. Dette adskiller sig
   bevidst fra ferie/sygdom/barsel, som i dag springer lørdag/søndag over
   (`getWeekdayDates()`/`_weekday_dates()`).
2. **Helligdage medtages også** — ingen opslag mod helligdagskalenderen, konsistent med at ferie i dag
   heller ikke udelader helligdage.
3. **DOB-flaget gælder for hele perioden på én gang** — ét afkrydsningsfelt, som i dag; alle dage i
   intervallet bliver enten alle `"overnatning"` eller alle `"dob_overnatning"`. Ingen mulighed for at
   blande pr. dag i samme opret-kald.
4. **Periode-redigering understøttes bagefter** — en oprettet overnatningsperiode kan forlænges/
   afkortes via den eksisterende "Gem periodedatoer"-funktion (`saveAbsencePeriodDates()`,
   `app.js:1643-1697`, backend `update_absence_group_dates()`, `activities.py:555-650`), på samme måde
   som ferie-perioder kan i dag.
5. **Dublet-/overlapskontrol**: hvis en dag i perioden allerede har en anden aktivitet (overnatning
   eller andet), vises en advarsel med liste over konflikterne, og brugeren skal aktivt bekræfte for at
   fortsætte — samme mønster som den generelle periode-overlapskontrol, der allerede findes for
   ferie/sygdom/barsel m.fl. (`app.js:2851-2868`).

---

## Kernevalg: genbrug periode-mekanismen, men som en isoleret gren

Overnatning indgår **ikke** i den eksisterende `_RANGE_TYPES`-liste (`app.js:2785`) eller
`isRangeType`-beregningen i `updateManualTypeVisibility()`, fordi den generelle periode-gren i
`confirmManualActivity()` (linje 2785-2917):

- kræver et udfyldt registreringsnummer (`regInput`, linje 2803-2816) — overnatning kræver i dag
  **intet** køretøj, og det skal den fortsat ikke,
- beregner "garanterede timer" pr. dag ud fra medarbejderens skema (linje 2876-2889) — irrelevant for
  overnatning, som er en fast sats pr. forekomst uden tidsberegning,
- bruger `getWeekdayDates()` — overnatning skal bruge ALLE kalenderdage.

I stedet udvides den eksisterende, allerede isolerede overnatnings-gren (linje 2765-2783) til selv at
håndtere periodetilfældet, uden at røre den generelle periode-gren eller `_RANGE_TYPES`. Det holder
ændringen lille og undgår at påvirke ferie/sygdom/barsel/afspadsering.

---

## Frontend — `updateManualTypeVisibility()` (`app.js:2161-2230`)

Kun én ændring: `isOvernatning` tilføjes til `isRangeType`-beregningen (linje 2175), så:
- "Til dato"-feltet vises for overnatning (`tilDatoFieldVisible = isRangeType || isAfspadsering`,
  linje 2176 — uændret, arver automatisk værdien via `isRangeType`),
- Label på start-feltet skifter til "Fra dato" i stedet for "Dato" (linje 2203-2207), konsistent med
  hvordan ferie allerede altid viser "Fra dato", uanset om en periode reelt er valgt.

`isDateOnly` (linje 2173) inkluderer allerede `isOvernatning` — ingen ændring nødvendig der, da
overnatning aldrig har brugerredigerbar tid, hverken i enkelt-dags- eller periodetilstand.

---

## Frontend — ny hjælpefunktion `getAllDates()` (ved siden af `getWeekdayDates()`, `app.js:2691-2700`)

```js
function getAllDates(from, to) {
  const dates = [];
  const d = new Date(from + "T12:00:00");
  const end = new Date(to  + "T12:00:00");
  while (d <= end) {
    dates.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }
  return dates;
}
```

Samme mønster som `getWeekdayDates()`, men uden weekend-filtreringen.

---

## Frontend — `confirmManualActivity()`, overnatnings-grenen (`app.js:2765-2783`)

Erstattes af en gren, der forgrener på om `tilDato` er udfyldt:

```js
if (actType === "overnatning") {
  if (!start) { toast("Angiv dato for overnatningen", "error"); return; }
  const isDob = document.getElementById("manual-dob").checked;
  const fra = start.slice(0, 10);

  if (!tilDato) {
    // ── Enkeltdag: uændret adfærd ──────────────────────────────────────────
    const timeStr = fra + "T00:00:00";
    try {
      await POST("/api/activities", {
        employee_id: empId,
        activity_type: isDob ? "dob_overnatning" : "overnatning",
        start_time: timeStr,
        end_time:   timeStr,
        source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
      });
      toast(isDob ? "DOB-overnatning oprettet" : "Overnatning oprettet", "success");
      closeModal("modal-manual-activity");
      await _afterManualActivitySaved(empId, fra);
    } catch (e) { toast(e.message, "error"); }
    return;
  }

  // ── Periode: én aktivitet pr. kalenderdag ────────────────────────────────
  if (tilDato < fra) { toast("Til dato skal være på eller efter fra dato", "error"); return; }
  const dates = getAllDates(fra, tilDato);

  const allOverlaps = [];
  for (const iso of dates) {
    const hits = state.activities.filter(a => {
      if (a.employee_id !== empId) return false;
      if (a.status === "deactivated") return false;
      return new Date(iso + "T00:00:00") < new Date(a.end_time) &&
             new Date(iso + "T23:59:59") > new Date(a.start_time);
    });
    allOverlaps.push(...hits.map(h => ({ iso, act: h })));
  }
  if (allOverlaps.length > 0) {
    const lines = allOverlaps.slice(0, 5).map(o =>
      `• ${o.iso}: ${TYPE_LABELS[o.act.activity_type] || o.act.activity_type} ${formatTime(o.act.start_time)}–${formatTime(o.act.end_time)}`
    );
    if (allOverlaps.length > 5) lines.push(`  … og ${allOverlaps.length - 5} mere`);
    if (!window.confirm(`Advarsel: ${allOverlaps.length} overlappende aktiviteter i perioden:\n\n${lines.join("\n")}\n\nVil du stadig oprette alle overnatninger?`)) return;
  }

  const absenceGroupId = _genGroupId();
  let created = 0;
  try {
    for (const iso of dates) {
      const timeStr = iso + "T00:00:00";
      await POST("/api/activities", {
        employee_id: empId,
        activity_type: isDob ? "dob_overnatning" : "overnatning",
        start_time: timeStr,
        end_time:   timeStr,
        absence_group_id: absenceGroupId,
        source: _manualActivityContext.vagtplan ? "vagtplan" : undefined,
      });
      created++;
    }
    toast(`${created} ${isDob ? "DOB-overnatning" : "overnatning"}${created === 1 ? "" : "er"} oprettet`, "success");
    closeModal("modal-manual-activity");
    await _afterManualActivitySaved(empId, dates[dates.length - 1]);
  } catch (e) { toast(e.message, "error"); }
  return;
}
```

Bemærk: overlapskontrollen genbruger nøjagtig samme kode/logik som den generelle periode-gren
(linje 2851-2868) — kopieres ind lokalt i stedet for at dele funktion, for at holde overnatnings-grenen
selvstændig og ikke skabe en afhængighed til/fra den generelle `isRange`-gren.

---

## Frontend — periode-redigering (`saveAbsencePeriodDates()`, `app.js:1643-1697`)

Funktionen bruger i dag hardcodet `getWeekdayDates(newStart, newEnd)` (linje 1656) og tjekker kun
konflikt mod `activity_type === "normal"` (linje 1666). Begge dele generaliseres til at kende
gruppens aktivitetstype:

```js
const groupType = group[0].activity_type;
const isCountBased = groupType === "overnatning" || groupType === "dob_overnatning";
const newDates = isCountBased ? getAllDates(newStart, newEnd) : getWeekdayDates(newStart, newEnd);
```

Konflikt-tjekket ved tilføjelse af nye dage (linje 1662-1674) udvides for `isCountBased`-grupper til at
tjekke mod **enhver** overlappende aktivitet (samme bredere logik som oprettelsens overlapskontrol),
ikke kun `activity_type === "normal"` — konsistent med beslutning 5 ovenfor. For de øvrige typer
(ferie, sygdom, barsel osv.) forbliver den eksisterende `"normal"`-specifikke kørsels-advarsel
uændret.

---

## Backend — ny hjælpefunktion `_all_dates()` (ved siden af `_weekday_dates()`, `activities.py:423-431`)

```python
def _all_dates(start: date, end: date) -> list[date]:
    """Alle kalenderdage i [start, end] inkl. weekend/helligdage – mirror af getAllDates() i app.js."""
    dates = []
    d = start
    while d <= end:
        dates.append(d)
        d += timedelta(days=1)
    return dates


_COUNT_BASED_RANGE_TYPES = {"overnatning", "dob_overnatning"}
```

---

## Backend — `update_absence_group_dates()` (`activities.py:555-650`)

To ændringer:

1. **Datointerval-udregning** (linje 575) skal bruge `_all_dates()` for de to nye typer:
   ```python
   new_dates = set(
       _all_dates(body.new_start_date, body.new_end_date)
       if activity_type in _COUNT_BASED_RANGE_TYPES
       else _weekday_dates(body.new_start_date, body.new_end_date)
   )
   ```

2. **Tilføjelse af nye dage** (linje 607-632): for `overnatning`/`dob_overnatning` skal der IKKE
   beregnes timer via `_range_day_defaults()` — i stedet oprettes en aktivitet med `start_time ==
   end_time == midnat`, som ved almindelig oprettelse:
   ```python
   for d in to_add_dates:
       if activity_type in _COUNT_BASED_RANGE_TYPES:
           start_dt = end_dt = datetime.combine(d, time(0, 0))
       else:
           hours = _range_day_defaults(activity_type, d, employee)
           if hours is None:
               skipped.append(d.isoformat())
               continue
           start_dt = datetime.combine(d, time(6, 0))
           end_dt = start_dt + timedelta(minutes=round(hours * 60))
       period = get_billing_period(d, db)
       db.add(Activity(
           ...  # uændret i øvrigt
       ))
   ```

`create_manual_activity()` (linje 452-536) og valideringen i `schemas.py` (`ActivityCreate.end_after_start`,
linje ~190-196) kræver ingen ændring — de håndterer allerede `"overnatning"`/`"dob_overnatning"` med
`start_time == end_time` korrekt, uanset om aktiviteten kommer fra enkelt-dags- eller
periode-oprettelse.

---

## Ikke berørt (bevidst)

- **`create_manual_activity()`**: ingen ændring — modtager blot N separate kald fra frontend, præcis
  som ferie/sygdom gør i dag.
- **Lønkørsel, PDF-timeseddel, CSV-eksport (Danløn), Prøvekørsel-Excel**: ingen ændring nødvendig.
  De tæller allerede `overnight_count`/`dob_overnight_count` som antal `Activity`-rækker af typen i
  perioden (`payroll_router.py`) — periode-oprettede overnatninger tælles derfor automatisk korrekt,
  præcis 1 pr. dag, uden ny logik.
- **Lønafregnings-fanen**: medregner i dag slet ikke overnatningsbeløb i sin total (kendt, separat
  problem, se `project_lonsystem_pdf_timeseddel_dual`-notat) — uændret af denne opgave.
- **Registreringsnummer**: kræves fortsat ikke for overnatning, hverken enkelt-dag eller periode.
- **Blanding af DOB/almindelig i samme periode**: ikke understøttet — kun ét flueben, gælder alle dage.
- **Automatisk udeladelse af weekend/helligdage**: bevidst fravalgt (beslutning 1-2).
- **Den to-trins "kørsel-konflikt"-modal** (`modal-absence-conflict`/`confirmAbsenceConflict()`),
  som de øvrige periodetyper bruger til at advare om kørsel samme dag: overnatning genbruger IKKE
  denne mekanisme. I stedet bruges en simpel `window.confirm()` med overlapsliste, samme som den
  generelle periode-gren allerede bruger til sin bredere overlapskontrol (linje 2862-2868) — enklere
  og uden afhængighed af det globale `_absenceConflictConfirmed`-flag.

---

## Test/verifikation

- **Enkeltdag uændret:** oprettelse af overnatning/DOB overnatning uden "Til dato" udfyldt giver
  nøjagtig samme resultat som før ændringen (ingen regression).
- **Periode, hverdage:** vælg fra fredag til mandag → 4 aktiviteter oprettes (fre, lør, søn, man),
  alle med samme `absence_group_id`, `overnight_count` stiger med 4.
- **Periode, DOB:** samme som ovenfor med DOB afkrydset → alle 4 aktiviteter får
  `activity_type="dob_overnatning"`.
- **Helligdag i periode:** en helligdag midt i intervallet får sin egen overnatnings-aktivitet, som
  enhver anden dag.
- **Dublet-advarsel:** opret en overnatningsperiode, der overlapper en allerede eksisterende aktivitet
  én af dagene → advarselsdialog vises med den overlappende dag/aktivitet; annuller → intet oprettes;
  bekræft → alle dage oprettes inkl. den overlappende.
- **Periode-redigering:** en oprettet overnatningsperiode kan forlænges/afkortes via "Gem
  periodedatoer" i redigeringsmodalen — nye dage tilføjes med korrekt `activity_type` og
  midnat-tider, fjernede dage slettes permanent (samme regler som ferie: kan ikke fjerne dage i
  lukkede lønperioder eller splittede aktiviteter).
- **Lønkørsel/PDF/CSV:** en medarbejder med en periode-oprettet overnatningsperiode på fx 3 dage
  viser `overnight_count = 3` konsekvent i Lønkørsel-fanen, PDF-timesedlen og Danløn-CSV'en, uden
  kodeændringer i disse tre.

## Åbne punkter

Ingen.
