# "Gem ændringer" skal ikke lukke modalen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Efter klik på "💾 Gem ændringer" i aktivitets-detaljevisningen forbliver modalen åben og viser de nu gemte, opdaterede værdier, i stedet for at lukke automatisk.

**Architecture:** Ren frontend-ændring i `saveActivityTimes()` i `app/static/js/app.js`: erstat `closeAllModals()` med et gen-render af samme aktivitet (`openActivityDetail()`), samme mønster som de øvrige "gem med det samme"-handlinger i modalen allerede bruger.

**Tech Stack:** Vanilla JavaScript, intet build-trin, intet JS-testframework i projektet – verifikation sker manuelt i browseren.

## Global Constraints

- Ingen ændring af gem-payload eller validering
- Ingen ændring af de øvrige footer-knapper (Godkend, Deaktiver, Split, Genåbn, Luk)
- **Denne session committer/pusher IKKE selv** – kun filredigering og verifikation
- Spec: `docs/superpowers/specs/2026-09-04-gem-aendringer-lukker-ikke-design.md`

---

## Task 1: Modalen forbliver åben efter "Gem ændringer"

**Files:**
- Modify: `app/static/js/app.js:1236-1242`

**Interfaces:**
- Consumes: `openActivityDetail(id)`, `applyActivityLocally(updated)` (begge allerede eksisterende)

- [ ] **Step 1: Opdater success-grenen i `saveActivityTimes()`**

Find (linje 1236-1242):

```js
  try {
    const updated = await PATCH(`/api/activities/${state.selectedActivityId}`, payload);
    toast("Ændringer gemt", "success");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}
```

Erstat med:

```js
  try {
    const updated = await PATCH(`/api/activities/${state.selectedActivityId}`, payload);
    toast("Ændringer gemt", "success");
    applyActivityLocally(updated);
    openActivityDetail(state.selectedActivityId);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 2: Manuel browser-verifikation**

Forudsætning: dev-serveren kører, og der er logget ind i browser-panelet.

1. Åbn en aktivitets detaljevisning, ret sluttidsfeltet, klik "Gem ændringer".
2. Bekræft at modalen **forbliver åben** (ikke lukker), og at "Sum, effektiv tid" er opdateret til at afspejle den nye sluttid.
3. Bekræft at "Luk"-knappen stadig lukker modalen normalt.
4. Ryd op efter enhver midlertidig ændring du laver på en rigtig aktivitet under testen (gendan oprindelig værdi bagefter), som i tidligere sessioners praksis.

- [ ] **Step 3: Kør fuld test-suite som slutkontrol**

```bash
cd app && python -m pytest ../tests/ -q
```

Forventet: alle tests `PASSED` (ren frontend-ændring, ingen backend-berøring forventes at påvirke resultatet).

---

## Self-Review

**Spec coverage:** ✅ Modalen forbliver åben og viser opdaterede værdier; ✅ øvrige knapper uændrede.

**Placeholder-scan:** Ingen TBD/TODO.

**Type-konsistens:** `openActivityDetail(state.selectedActivityId)` matcher signaturen `openActivityDetail(id)` allerede brugt andre steder i filen (fx i `correctSegment()`).
