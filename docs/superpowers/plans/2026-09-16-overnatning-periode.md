# Overnatning over en periode – Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gør det muligt at oprette overnatning/DOB overnatning over en periode (fra/til dato) i "Tilføj aktivitet"-modalen, med én aktivitet pr. kalenderdag (inkl. weekend/helligdage), uden at ændre enkeltdags-adfærden.

**Architecture:** Overnatning får sin egen isolerede periode-gren (adskilt fra den generelle `_RANGE_TYPES`-mekanisme, som ferie/sygdom/barsel bruger), fordi overnatning hverken kræver køretøj eller timeberegning. Backend-siden genbruger den eksisterende `absence_group_id`-gruppe-mekanisme og periode-redigeringsendpointet, udvidet til at kende "alle kalenderdage"-varianten og til at oprette midnat-aktiviteter i stedet for timebaserede.

**Tech Stack:** Python/FastAPI + SQLAlchemy (backend, `app/routers/activities.py`), vanilla JS (frontend, `app/static/js/app.js`), pytest (backend-tests, ingen automatiseret frontend-testsuite i dette projekt).

**Spec:** `docs/superpowers/specs/2026-09-16-overnatning-periode-design.md`

## Global Constraints

- Enkeltdags-oprettelse af overnatning/DOB overnatning ("Til dato" tom) skal forblive **100% uændret** — ingen regression.
- Perioden skal inkludere ALLE kalenderdage (weekend + helligdage), ikke kun hverdage.
- DOB-flaget gælder for hele perioden på én gang (ét afkrydsningsfelt, ingen blanding pr. dag).
- Ingen ændringer i lønkørsel, PDF-timeseddel, CSV-eksport eller prøvekørsel — de tæller allerede pr. `Activity`-række.
- Registreringsnummer/køretøj kræves fortsat IKKE for overnatning, hverken enkeltdag eller periode.
- **Git:** Claude committer/stager/pusher ALDRIG selv i dette projekt — brugeren håndterer git i VS Code. Hver task slutter derfor med en verifikations-step, ikke en commit-step.
- Der findes ingen automatiseret frontend-testsuite i dette projekt — frontend-tasks verificeres manuelt i browseren (dev-server), ikke med en test-runner.

---

## Fil-oversigt

| Fil | Ændring |
|---|---|
| `app/routers/activities.py` | Ny `_all_dates()` + `_COUNT_BASED_RANGE_TYPES`; `update_absence_group_dates()` udvides til at håndtere overnatning/DOB overnatning |
| `tests/test_absence_group_helpers.py` | Nye tests for `_all_dates()` |
| `tests/test_absence_group_patch.py` | Nye tests for periode-redigering af overnatnings-grupper |
| `app/static/js/app.js` | Ny `getAllDates()`; `updateManualTypeVisibility()` viser "Til dato" for overnatning; `confirmManualActivity()`s overnatnings-gren udvides med periode-underforgrening; `saveAbsencePeriodDates()` bliver type-bevidst |
| `CODEREF.md` | Ny dateret sektion, samme mønster som eksisterende ændringslog-afsnit |

---

### Task 1: Backend — `_all_dates()`-hjælpefunktion

**Files:**
- Modify: `app/routers/activities.py` (lige efter `_weekday_dates()`, omkring linje 423-431)
- Test: `tests/test_absence_group_helpers.py`

**Interfaces:**
- Produces: `_all_dates(start: date, end: date) -> list[date]` — alle kalenderdage i `[start, end]` inkl. weekend, brugt af Task 2.
- Produces: `_COUNT_BASED_RANGE_TYPES: set[str]` — `{"overnatning", "dob_overnatning"}`, brugt af Task 2.

- [ ] **Step 1: Skriv de fejlende tests**

Tilføj nederst i `tests/test_absence_group_helpers.py`:

```python
def test_all_dates_includes_weekend():
    from routers.activities import _all_dates
    dates = _all_dates(date(2026, 1, 5), date(2026, 1, 11))  # man 5/1 - søn 11/1
    assert dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                     date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 10),
                     date(2026, 1, 11)]


def test_all_dates_single_day():
    from routers.activities import _all_dates
    assert _all_dates(date(2026, 1, 7), date(2026, 1, 7)) == [date(2026, 1, 7)]


def test_count_based_range_types_contains_overnatning_and_dob():
    from routers.activities import _COUNT_BASED_RANGE_TYPES
    assert _COUNT_BASED_RANGE_TYPES == {"overnatning", "dob_overnatning"}
```

- [ ] **Step 2: Kør testene og bekræft at de fejler**

Run: `python -m pytest tests/test_absence_group_helpers.py -v`
Expected: 3 nye FAIL med `ImportError: cannot import name '_all_dates'` (og tilsvarende for `_COUNT_BASED_RANGE_TYPES`).

- [ ] **Step 3: Implementér i `app/routers/activities.py`**

Find den eksisterende `_weekday_dates()`-funktion:

```python
def _weekday_dates(start: date, end: date) -> list[date]:
    """Alle hverdage (mandag-fredag) i [start, end] – mirror af getWeekdayDates() i app.js."""
    dates = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    return dates
```

Indsæt lige efter den:

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

- [ ] **Step 4: Kør testene igen og bekræft at de består**

Run: `python -m pytest tests/test_absence_group_helpers.py -v`
Expected: Alle tests PASS (både de nye og de eksisterende `_weekday_dates`/`_range_day_defaults`-tests).

- [ ] **Step 5: Verificér ingen regression i resten af testsuiten**

Run: `python -m pytest tests/ -v`
Expected: Alle tests PASS (ingen nye fejl introduceret).

---

### Task 2: Backend — `update_absence_group_dates()` håndterer overnatning/DOB overnatning

**Files:**
- Modify: `app/routers/activities.py` (funktionen `update_absence_group_dates`, omkring linje 555-650)
- Test: `tests/test_absence_group_patch.py`

**Interfaces:**
- Consumes: `_all_dates(start, end) -> list[date]` og `_COUNT_BASED_RANGE_TYPES` fra Task 1.
- Consumes (uændret): `_weekday_dates(start, end) -> list[date]`, `_range_day_defaults(activity_type, d, employee) -> Optional[float]`.
- Produces: `update_absence_group_dates()` opretter nu midnat-til-midnat-aktiviteter (uden timeberegning) for grupper med `activity_type in _COUNT_BASED_RANGE_TYPES`, og bruger `_all_dates()` i stedet for `_weekday_dates()` til at udregne det nye datointerval for disse grupper.

- [ ] **Step 1: Skriv de fejlende tests**

Tilføj nederst i `tests/test_absence_group_patch.py`:

```python
def test_growing_overnatning_range_includes_weekend_with_midnight_times(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6)]  # man+tir
    _make_group(db, employee, dates, activity_type="overnatning")

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 11))  # +weekend
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                               date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 10),
                               date(2026, 1, 11)]
    saturday = next(a for a in result.activities if a.start_time.date() == date(2026, 1, 10))
    assert saturday.start_time.strftime("%H:%M") == "00:00"
    assert saturday.end_time == saturday.start_time
    assert saturday.activity_type == "overnatning"
    assert saturday.status == ActivityStatus.approved
    assert result.skipped == []


def test_growing_dob_overnatning_range_includes_weekend(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5)]
    _make_group(db, employee, dates, activity_type="dob_overnatning")

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6)]
    for a in result.activities:
        assert a.activity_type == "dob_overnatning"
        assert a.start_time == a.end_time


def test_shrinking_overnatning_range_deletes_pending_days_outside_new_range(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    _make_group(db, employee, dates, activity_type="overnatning", status=ActivityStatus.pending)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6)]
    assert db.query(Activity).filter(Activity.absence_group_id == "grp-1").count() == 2


def test_ferie_range_still_uses_weekday_dates_not_all_dates(db, employee):
    """Regression: almindelige fraværstyper må IKKE pludselig få weekend-dage med."""
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5)]
    _make_group(db, employee, dates, activity_type="ferie")

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 11))  # +weekend
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert date(2026, 1, 10) not in remaining_dates  # lørdag
    assert date(2026, 1, 11) not in remaining_dates  # søndag
```

- [ ] **Step 2: Kør testene og bekræft at de fejler**

Run: `python -m pytest tests/test_absence_group_patch.py -v`
Expected: De 3 nye overnatnings-tests FEJLER (fx `saturday`/`AssertionError` fordi lørdag/søndag mangler, da `update_absence_group_dates` i dag altid bruger `_weekday_dates`). `test_ferie_range_still_uses_weekday_dates_not_all_dates` BESTÅR allerede (ren regressionstest af eksisterende adfærd — bekræft at den også kører grønt før ændringen).

- [ ] **Step 3: Implementér ændringen i `update_absence_group_dates()`**

Find denne linje i `app/routers/activities.py`:

```python
    new_dates = set(_weekday_dates(body.new_start_date, body.new_end_date))
```

Erstat med:

```python
    date_fn = _all_dates if activity_type in _COUNT_BASED_RANGE_TYPES else _weekday_dates
    new_dates = set(date_fn(body.new_start_date, body.new_end_date))
```

Find derefter tilføjelses-loopet:

```python
    # Trin 3: tilføj
    skipped: list[str] = []
    for d in to_add_dates:
        hours = _range_day_defaults(activity_type, d, employee)
        if hours is None:
            skipped.append(d.isoformat())
            continue
        start_dt = datetime.combine(d, time(6, 0))
        end_dt = start_dt + timedelta(minutes=round(hours * 60))
        period = get_billing_period(d, db)
```

Erstat med:

```python
    # Trin 3: tilføj
    skipped: list[str] = []
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
```

(Resten af `Activity(...)`-konstruktøren efter denne blok forbliver uændret.)

- [ ] **Step 4: Kør testene igen og bekræft at de består**

Run: `python -m pytest tests/test_absence_group_patch.py -v`
Expected: Alle tests PASS, inkl. de 4 nye og alle eksisterende (ferie/afspadsering/vagtplan-tests uændret).

- [ ] **Step 5: Verificér ingen regression i resten af testsuiten**

Run: `python -m pytest tests/ -v`
Expected: Alle tests PASS.

---

### Task 3: Frontend — `getAllDates()` + "Til dato" synlig for overnatning

**Files:**
- Modify: `app/static/js/app.js` (ny funktion ved siden af `getWeekdayDates()`, omkring linje 2691-2700; `updateManualTypeVisibility()`, omkring linje 2161-2230)

**Interfaces:**
- Produces: `getAllDates(from: string, to: string) -> string[]` (ISO-datoer) — bruges af Task 4 og Task 5.
- Consumes: ingen nye backend-ændringer (ren frontend-visning).

- [ ] **Step 1: Tilføj `getAllDates()`**

Find `getWeekdayDates()`:

```js
function getWeekdayDates(from, to) {
  const dates = [];
  const d = new Date(from + "T12:00:00");
  const end = new Date(to  + "T12:00:00");
  while (d <= end) {
    if (d.getDay() !== 0 && d.getDay() !== 6) dates.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }
  return dates;
}
```

Indsæt lige efter:

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

- [ ] **Step 2: Vis "Til dato" og "Fra dato"-label for overnatning**

I `updateManualTypeVisibility()`, find:

```js
  const isRangeType    = type === "ferie" || isFeriefri || isBarsel || type === "sygdom" || type === "paragraf_56_syg" || type === "graviditetsbetinget_sygdom" || type === "skole_kursus" || isAfspadseringPeriode;
```

Erstat med:

```js
  const isRangeType    = type === "ferie" || isFeriefri || isBarsel || type === "sygdom" || type === "paragraf_56_syg" || type === "graviditetsbetinget_sygdom" || type === "skole_kursus" || isAfspadseringPeriode || isOvernatning;
```

(`isOvernatning` er allerede defineret tidligere i samme funktion, linje 2171: `const isOvernatning = (type === "overnatning");` — ingen ny variabel nødvendig.)

- [ ] **Step 3: Manuel verifikation i browser**

Start dev-serveren (`preview_start`) og åbn "Tilføj aktivitet"-modalen:
1. Vælg medarbejder, vælg type "Overnatning".
2. Bekræft at et "Til dato"-felt nu vises (var skjult før ændringen).
3. Bekræft at DOB-afkrydsningsfeltet stadig vises som før.
4. Bekræft at start-feltets label siger "Fra dato".
5. Skift type til "Normal tid" og bekræft at "Til dato"-feltet forsvinder igen (ingen regression for andre typer).

---

### Task 4: Frontend — periode-oprettelse i `confirmManualActivity()`

**Files:**
- Modify: `app/static/js/app.js` (overnatnings-grenen i `confirmManualActivity()`, omkring linje 2765-2783)

**Interfaces:**
- Consumes: `getAllDates(from, to)` fra Task 3, `_genGroupId()` (eksisterende, linje 2677-2689), `TYPE_LABELS`, `formatTime()`, `state.activities` (alle eksisterende globale hjælpefunktioner/state).
- Produces: POST `/api/activities` kaldes med `absence_group_id` sat, én gang pr. dag i perioden, når "Til dato" er udfyldt for overnatning.

- [ ] **Step 1: Erstat overnatnings-grenen**

Find i `confirmManualActivity()`:

```js
  if (actType === "overnatning") {
    if (!start) { toast("Angiv dato for overnatningen", "error"); return; }
    const isDob = document.getElementById("manual-dob").checked;
    const dateStr = start.slice(0, 10);
    const timeStr = dateStr + "T00:00:00";
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
      await _afterManualActivitySaved(empId, dateStr);
    } catch (e) { toast(e.message, "error"); }
    return;
  }
```

Erstat hele blokken med:

```js
  if (actType === "overnatning") {
    if (!start) { toast("Angiv dato for overnatningen", "error"); return; }
    const isDob = document.getElementById("manual-dob").checked;
    const fra = start.slice(0, 10);

    if (!tilDato) {
      // ── Enkeltdag: uændret adfærd ────────────────────────────────────────
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

    // ── Periode: én aktivitet pr. kalenderdag ──────────────────────────────
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

- [ ] **Step 2: Manuel verifikation i browser — enkeltdag (ingen regression)**

1. Åbn "Tilføj aktivitet", vælg en medarbejder, type "Overnatning", udfyld kun "Fra dato" (lad "Til dato" stå tom).
2. Opret. Bekræft toast "Overnatning oprettet" og at præcis 1 ny aktivitet vises i aktivitetsoversigten den valgte dag, status godkendt.
3. Gentag med DOB afkrydset — bekræft toast "DOB-overnatning oprettet" og korrekt type på den nye aktivitet.

- [ ] **Step 3: Manuel verifikation i browser — periode**

1. Åbn "Tilføj aktivitet", vælg medarbejder, type "Overnatning", udfyld "Fra dato" = en fredag og "Til dato" = den efterfølgende mandag (4 dage, inkl. weekend).
2. Opret. Bekræft toast "4 overnatninger oprettet".
3. Bekræft i aktivitetsoversigten at der nu findes 4 separate, godkendte overnatnings-aktiviteter — fredag, lørdag, søndag, mandag.
4. Gentag med DOB afkrydset for en anden periode — bekræft at alle oprettede dage har typen DOB Overnatning.

- [ ] **Step 4: Manuel verifikation i browser — dublet-advarsel**

1. Opret én enkelt overnatning for en bestemt dag (fx onsdag).
2. Opret derefter en periode, der inkluderer samme onsdag.
3. Bekræft at der vises en advarsel med onsdagens dato og den eksisterende aktivitet.
4. Annuller advarslen — bekræft at INGEN nye aktiviteter blev oprettet.
5. Gentag og bekræft advarslen — bekræft at alle dage i perioden nu er oprettet, inkl. den dag der allerede havde en aktivitet (der findes nu to overnatninger den dag, som forventet efter bekræftelse).

---

### Task 5: Frontend — periode-redigering bliver type-bevidst

**Files:**
- Modify: `app/static/js/app.js` (`saveAbsencePeriodDates()`, omkring linje 1643-1697)

**Interfaces:**
- Consumes: `getAllDates(from, to)` fra Task 3, `getWeekdayDates(from, to)` (eksisterende).
- Produces: `saveAbsencePeriodDates()` udleder selv om gruppen er overnatning/DOB overnatning og bruger korrekt datoliste + bredere overlapskontrol for disse.

- [ ] **Step 1: Erstat dato-udregningen og konflikt-tjekket**

Find:

```js
  const empId = group[0].employee_id;
  const existingDates = group.map(g => g.start_time.slice(0, 10));
  const newDates = getWeekdayDates(newStart, newEnd);
  const toRemove = existingDates.filter(d => !newDates.includes(d));
  const toAdd    = newDates.filter(d => !existingDates.includes(d));

  if (toRemove.length === 0 && toAdd.length === 0) { toast("Ingen ændringer i perioden", "warning"); return; }

  if (toAdd.length > 0) {
    const conflicts = toAdd.filter(iso =>
      state.activities.some(a =>
        a.employee_id === empId &&
        a.activity_type === "normal" &&
        a.start_time.slice(0, 10) === iso &&
        a.status !== "deactivated"
      )
    );
    if (conflicts.length > 0) {
      const dateList = conflicts.map(d => { const [y,m,day]=d.split("-"); return `${day}-${m}-${y}`; }).join(", ");
      if (!window.confirm(`Der er allerede registreret kørsel på følgende dag${conflicts.length>1?"e":""}:\n${dateList}\n\nVil du alligevel udvide fraværsperioden til at inkludere den/dem?`)) return;
    }
  }
```

Erstat med:

```js
  const empId = group[0].employee_id;
  const groupType = group[0].activity_type;
  const isCountBased = groupType === "overnatning" || groupType === "dob_overnatning";
  const existingDates = group.map(g => g.start_time.slice(0, 10));
  const newDates = isCountBased ? getAllDates(newStart, newEnd) : getWeekdayDates(newStart, newEnd);
  const toRemove = existingDates.filter(d => !newDates.includes(d));
  const toAdd    = newDates.filter(d => !existingDates.includes(d));

  if (toRemove.length === 0 && toAdd.length === 0) { toast("Ingen ændringer i perioden", "warning"); return; }

  if (toAdd.length > 0) {
    const conflicts = isCountBased
      ? toAdd.filter(iso =>
          state.activities.some(a =>
            a.employee_id === empId &&
            a.status !== "deactivated" &&
            new Date(iso + "T00:00:00") < new Date(a.end_time) &&
            new Date(iso + "T23:59:59") > new Date(a.start_time)
          )
        )
      : toAdd.filter(iso =>
          state.activities.some(a =>
            a.employee_id === empId &&
            a.activity_type === "normal" &&
            a.start_time.slice(0, 10) === iso &&
            a.status !== "deactivated"
          )
        );
    if (conflicts.length > 0) {
      const dateList = conflicts.map(d => { const [y,m,day]=d.split("-"); return `${day}-${m}-${y}`; }).join(", ");
      const msg = isCountBased
        ? `Der er allerede registreret ${conflicts.length > 1 ? "aktiviteter" : "en aktivitet"} følgende dag${conflicts.length>1?"e":""}:\n${dateList}\n\nVil du alligevel udvide perioden til at inkludere den/dem?`
        : `Der er allerede registreret kørsel på følgende dag${conflicts.length>1?"e":""}:\n${dateList}\n\nVil du alligevel udvide fraværsperioden til at inkludere den/dem?`;
      if (!window.confirm(msg)) return;
    }
  }
```

- [ ] **Step 2: Manuel verifikation i browser — forlæng periode**

1. Opret en overnatningsperiode på 2 dage (man-tir).
2. Åbn den første dags aktivitet i redigeringsmodalen, brug periode-sektionen til at ændre "Til dato" til søndag (4 dage mere, inkl. weekend).
3. Gem periodedatoer. Bekræft at der nu findes 6 overnatnings-aktiviteter i alt, inkl. weekenddagene, alle godkendt.

- [ ] **Step 3: Manuel verifikation i browser — afkort periode**

1. Fra samme periode, åbn redigeringsmodalen igen og sæt "Til dato" tilbage til tirsdag.
2. Gem. Bekræft at de 4 tilføjede dage nu er slettet igen, og kun de oprindelige 2 dage (man-tir) er tilbage.

- [ ] **Step 4: Manuel verifikation i browser — ferie-periode uændret (regression)**

1. Opret en ferieperiode på 3 hverdage.
2. Åbn redigeringsmodalen, forlæng perioden hen over en weekend.
3. Bekræft at lørdag/søndag IKKE får en ferie-aktivitet (uændret adfærd for ferie).

---

### Task 6: CODEREF.md — dokumentér ændringen

**Files:**
- Modify: `CODEREF.md`

- [ ] **Step 1: Tilføj en ny dateret sektion**

Find det seneste daterede ændringslog-afsnit (fx `## "Ændret af"-felt på aktiviteter (2026-09-10, ...)` omkring linje 631) og tilføj en ny sektion i samme stil, umiddelbart efter det sidste eksisterende afsnit i den dele af filen:

```markdown
## Overnatning over en periode (2026-09-16, activities.py + app.js)
- `_all_dates(start, end)` (activities.py, ved siden af `_weekday_dates`) – alle kalenderdage inkl.
  weekend/helligdage. `_COUNT_BASED_RANGE_TYPES = {"overnatning", "dob_overnatning"}`.
- `update_absence_group_dates()` bruger `_all_dates()` i stedet for `_weekday_dates()` for disse to
  typer, og opretter tilføjede dage med `start_time == end_time == midnat` (ingen timeberegning) i
  stedet for at kalde `_range_day_defaults()`.
- Frontend: overnatnings-grenen i `confirmManualActivity()` (app.js) har nu sin egen periode-gren
  (adskilt fra `_RANGE_TYPES`/`isRange`-mekanismen ferie m.fl. bruger) – ingen krav om
  registreringsnummer, alle kalenderdage medtages, ét DOB-flueben gælder hele perioden.
  `getAllDates(from, to)` ved siden af `getWeekdayDates()`.
- `saveAbsencePeriodDates()` genkender nu gruppens `activity_type` og bruger `getAllDates` +
  bredere overlapskontrol for overnatnings-grupper ved efterfølgende periode-redigering.
- Se `docs/superpowers/specs/2026-09-16-overnatning-periode-design.md` for fulde designbeslutninger.
```

- [ ] **Step 2: Verificér**

Læs det opdaterede `CODEREF.md` igennem og bekræft at den nye sektion er konsistent med de øvrige
daterede afsnits format (overskrift, filhenvisning, punktopstilling).

---

## Afsluttende verifikation (efter alle tasks)

- [ ] Kør hele backend-testsuiten: `python -m pytest tests/ -v` — alle tests PASS.
- [ ] Gennemfør Task 4 Step 2-4 og Task 5 Step 2-4's manuelle browser-scenarier i sammenhæng, på en test-medarbejder, for at bekræfte hele flowet fungerer end-to-end (oprettelse, dublet-advarsel, periode-forlængelse, periode-afkortning).
- [ ] Bekræft i Lønkørsel-fanen at en medarbejder med en periode-oprettet overnatningsperiode på fx 3 dage viser `overnight_count = 3` (eller tilsvarende for DOB), uden yderligere kodeændringer.
