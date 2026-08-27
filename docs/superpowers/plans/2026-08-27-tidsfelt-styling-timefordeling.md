# Konsistent styling af klokkeslæt-felter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Timefordelingens fra/til-klokkeslæt-felter i medarbejder-modalen skal have samme kant/baggrund/rundede hjørner som alle andre klokkeslæt-felter i appen (aktivitet-start/slut, pausetider).

**Architecture:** Ren CSS-ændring i `app/static/css/style.css` – `input[type="time"]` tilføjes til den eksisterende fælles input-styling-regel. Ingen JS- eller HTML-ændringer. Cache-busting-versionsnummeret i `index.html` bumpes manuelt, da `style.css` ikke har automatisk cache-busting.

**Tech Stack:** Ren CSS, ingen build-trin, intet JS-testframework i projektet – verifikation sker manuelt i browseren mod den kørende dev-server.

## Global Constraints

- Kun CSS-ændring – ingen ændring af JS-logik eller HTML-struktur.
- Ingen visuel ændring af eksisterende klokkeslæt-felter (`.dt-time` i aktivitet-/pause-modalerne) – de bruger allerede inline styles med højere specificitet.
- `style.css?v=N` i `index.html` SKAL bumpes manuelt ved denne ændring (kendt faldgrube i projektet, jf. CODEREF.md).
- Spec: `docs/superpowers/specs/2026-08-27-tidsfelt-styling-timefordeling-design.md`

---

## Filstruktur

```
app/
  static/css/style.css     # MODIFY: tilføj input[type="time"] til fælles input-selector (linje 475-480)
  templates/index.html      # MODIFY: bump style.css?v=10 → v=11 (linje 7)
```

---

## Task 1: Tilføj input[type="time"] til fælles CSS-styling

**Files:**
- Modify: `app/static/css/style.css:475-480`
- Modify: `app/templates/index.html:7`

**Interfaces:**
- Consumes: intet (ren CSS-selector-udvidelse af eksisterende regel)
- Produces: intet nyt navngivet API – kun visuel effekt på alle `input[type="time"]`-elementer i appen

- [ ] **Step 1: Tilføj `input[type="time"]` til selector-listen i `app/static/css/style.css`**

Find (linje 475-480):

```css
input[type="text"],
input[type="date"],
input[type="datetime-local"],
input[type="number"],
select,
textarea {
```

Erstat med:

```css
input[type="text"],
input[type="date"],
input[type="datetime-local"],
input[type="number"],
input[type="time"],
select,
textarea {
```

- [ ] **Step 2: Bump cache-busting-versionsnummeret i `app/templates/index.html`**

Find (linje 7):

```html
  <link rel="stylesheet" href="/static/css/style.css?v=10">
```

Erstat med:

```html
  <link rel="stylesheet" href="/static/css/style.css?v=11">
```

- [ ] **Step 3: Manuel browser-verifikation**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet.

1. Åbn Medarbejdere-fanen, klik "Rediger" på en vilkårlig medarbejder (eller "+ Opret medarbejder") for at åbne `modal-employee`.
2. Scroll ned til Timefordelings-tabellen → bekræft at fra/til-klokkeslæt-felterne (under hvert timetal-felt) nu har synlig kant, lys baggrund og runde hjørner – samme udseende som timetal-feltet ved siden af, og ikke længere browserens rå standardudseende.
3. Bekræft at feltbredden ser uændret ud (smal, ca. 88px – ikke fuld bredde).
4. Udfyld et fra/til-par (fx 06:00–14:00) → bekræft at timetal-feltet stadig automatisk opdateres til 8, og at "Ugentligt timeantal" nederst stadig genberegnes – ingen funktionel regression.
5. Åbn "Tilføj aktivitet"-modalen (Aktiviteter-fanen) → bekræft at start-/sluttidspunktets klokkeslæt-felt ser visuelt uændret ud sammenlignet med før ændringen.
6. Opret en manuel aktivitet og tilføj en pause (modal-pause) → bekræft at pausens klokkeslæt-felter også ser visuelt uændrede ud.
7. Genindlæs siden med tømt cache (Ctrl+Shift+R eller tilsvarende) for at udelukke at den gamle CSS er cachet, og gentag punkt 2 for en sikkerheds skyld.

- [ ] **Step 4: Commit**

```bash
git add app/static/css/style.css app/templates/index.html
git commit -m "fix: konsistent styling af klokkeslæt-felter i Timefordelingen"
```

---

## Self-Review

**Spec coverage:**
- ✅ `input[type="time"]` tilføjet til fælles CSS-selector – Step 1
- ✅ Cache-busting-versionsnummer bumpet – Step 2
- ✅ Verifikation af at eksisterende klokkeslæt-felter (aktivitet, pause) er visuelt uændrede – Step 3, punkt 5-6
- ✅ Verifikation af at feltbredde og fra/til→timetal-funktionalitet er upåvirket – Step 3, punkt 3-4

**Placeholder-scan:** Ingen TBD/TODO – al kode er fuldt udskrevet, verifikationstrinnet har konkrete handlinger og forventede resultater.

**Type-konsistens:** Ikke relevant – ren CSS-ændring uden nye funktioner, signaturer eller navngivne værdier.
