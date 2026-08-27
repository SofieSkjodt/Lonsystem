# "Al pause til andet arbejde" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a button "Al pause til andet arbejde" above the "Detaljeret information om dagen" segment table in the activity detail modal, which converts all not-yet-corrected pause segments of that activity to "Andet arbejde" in one click — equivalent to clicking "Ret linje" on every pause row — while leaving the per-row "Gendan" (revert) mechanism fully intact.

**Architecture:** One new FastAPI endpoint `POST /api/activities/{id}/correct-all-segments` in `app/routers/activities.py` reuses the exact same segment-transformation rule as the existing single-row `correct-segment` endpoint, extracted into a small pure helper function so it can be verified without a running server or database. One new button + JS handler in `app/static/js/app.js` calls the endpoint and re-renders the activity detail, mirroring the existing `correctSegment()` pattern.

**Tech Stack:** FastAPI + SQLAlchemy (Python backend), vanilla JS (frontend), SQLite dev DB.

## Global Constraints

- Button label must be exactly "Al pause til andet arbejde".
- Button is placed immediately above the "Detaljeret information om dagen" label, inside the container returned by `renderSegmentTable()`.
- Button is shown **only** when the activity has at least one segment with `seg[2] === "rest"` and `seg.length < 4` (not already corrected) — hidden entirely otherwise (no disabled state, no empty-click toast).
- The bulk transformation must be byte-for-byte identical per segment to what the existing single-row `correct-segment` endpoint produces: `seg[:2] + ["work", seg[2]]` (original type preserved as 4th element).
- The whole bulk operation is one atomic DB transaction — either all eligible segments are corrected, or (on error) none are.
- No new permission is introduced — same access level as the existing `correct-segment`/`resize-segment` endpoints (`get_current_user` only).
- Exactly one `log_action` call for the whole bulk operation (not one per segment), action name `"correct_all_segments"`, details include the corrected count.
- Per-row "Ret linje"/"Gendan"/"Tilpas" buttons and their endpoints are not modified — after a bulk correction, every affected row must still show a working "Gendan" button that reverts only that row.
- Manual activities without `segments` (only `pause_intervals`) never show this button.

---

### Task 1: Backend endpoint `correct-all-segments`

**Files:**
- Create: `app/_test_correct_all_segments.py`
- Modify: `app/routers/activities.py:758` (insert new helper + endpoint immediately after the end of `correct_segment`, before `resize_segment`)

**Interfaces:**
- Produces: `_correct_all_segments_list(segments: list) -> tuple[list, int]` — pure function, importable from `routers.activities`. Returns `(new_segments, corrected_count)`.
- Produces: `POST /api/activities/{activity_id}/correct-all-segments` → `ActivityResponse` (same shape as `correct-segment`/`resize-segment` responses). 404 if activity not found, 400 `"Ingen pauselinjer at rette"` if there are zero eligible segments.

- [ ] **Step 1: Write the failing standalone test script**

Create `app/_test_correct_all_segments.py` (leading underscore matches the existing `_test_overtime.py` convention — these scripts are run manually with `python`, not collected by pytest):

```python
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from routers.activities import _correct_all_segments_list


def check(name, segments, expected_segments, expected_count):
    result, count = _correct_all_segments_list(segments)
    ok = result == expected_segments and count == expected_count
    status = "OK" if ok else "FEJL"
    print(f"{name}: {status} - fik {result}, {count} (forventet {expected_segments}, {expected_count})")


# Blandede segmenter: kun de to 'rest'-segmenter rettes, driving/work urørt
check(
    "Blandede segmenter",
    [
        ["2026-06-08T06:00:00", "2026-06-08T06:45:00", "driving"],
        ["2026-06-08T06:45:00", "2026-06-08T07:15:00", "rest"],
        ["2026-06-08T07:15:00", "2026-06-08T08:00:00", "work"],
        ["2026-06-08T08:00:00", "2026-06-08T08:30:00", "rest"],
    ],
    [
        ["2026-06-08T06:00:00", "2026-06-08T06:45:00", "driving"],
        ["2026-06-08T06:45:00", "2026-06-08T07:15:00", "work", "rest"],
        ["2026-06-08T07:15:00", "2026-06-08T08:00:00", "work"],
        ["2026-06-08T08:00:00", "2026-06-08T08:30:00", "work", "rest"],
    ],
    2,
)

# Et segment er allerede rettet (len==4) -> springes over, kun det andet rettes
check(
    "Allerede rettet segment springes over",
    [
        ["2026-06-08T06:00:00", "2026-06-08T06:30:00", "work", "rest"],
        ["2026-06-08T06:30:00", "2026-06-08T07:00:00", "rest"],
    ],
    [
        ["2026-06-08T06:00:00", "2026-06-08T06:30:00", "work", "rest"],
        ["2026-06-08T06:30:00", "2026-06-08T07:00:00", "work", "rest"],
    ],
    1,
)

# Ingen pause-segmenter overhovedet -> 0 rettet, listen uændret
check(
    "Ingen pauser",
    [["2026-06-08T06:00:00", "2026-06-08T06:45:00", "driving"]],
    [["2026-06-08T06:00:00", "2026-06-08T06:45:00", "driving"]],
    0,
)

# Tom liste -> 0 rettet, tom liste tilbage
check("Tom liste", [], [], 0)
```

- [ ] **Step 2: Run the script and verify it fails**

Run from the `app/` directory:

```bash
python _test_correct_all_segments.py
```

Expected: `ImportError: cannot import name '_correct_all_segments_list' from 'routers.activities'` (the function doesn't exist yet).

- [ ] **Step 3: Implement the helper and the endpoint**

In `app/routers/activities.py`, insert the following immediately after the `correct_segment` function ends (after line 758, before `@router.post("/{activity_id}/resize-segment"...)` at line 761):

```python
def _correct_all_segments_list(segments: list) -> tuple[list, int]:
    """Ret alle u-rettede pause-segmenter ('rest') til 'work', bevarer original
    type som 4. element (samme transformation som correct_segment, uden revert).
    Returnerer (nye segmenter, antal rettede linjer)."""
    result = []
    corrected = 0
    for seg in segments:
        seg = list(seg)
        if seg[2] == "rest" and len(seg) < 4:
            seg = seg[:2] + ["work", seg[2]]
            corrected += 1
        result.append(seg)
    return result, corrected


@router.post("/{activity_id}/correct-all-segments", response_model=ActivityResponse)
def correct_all_segments(
    activity_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ret alle u-rettede pause-segmenter for aktiviteten til 'Andet arbejde' i én omgang."""
    a = (
        db.query(Activity)
        .options(selectinload(Activity.employee), selectinload(Activity.split_children))
        .filter(Activity.id == activity_id)
        .first()
    )
    if not a:
        raise HTTPException(404, "Aktivitet ikke fundet")

    new_segments, corrected_count = _correct_all_segments_list(a.segments or [])
    if corrected_count == 0:
        raise HTTPException(400, "Ingen pauselinjer at rette")

    a.segments = new_segments
    flag_modified(a, "segments")
    _recalculate_pcts(a)
    db.commit()
    db.refresh(a)
    log_action(db, current_user, "correct_all_segments", "activity", activity_id,
               {"corrected_count": corrected_count})
    return _to_response(a)
```

- [ ] **Step 4: Run the script again and verify it passes**

Run from the `app/` directory:

```bash
python _test_correct_all_segments.py
```

Expected output (4 lines, all `OK`):

```
Blandede segmenter: OK - fik [['2026-06-08T06:00:00', '2026-06-08T06:45:00', 'driving'], ['2026-06-08T06:45:00', '2026-06-08T07:15:00', 'work', 'rest'], ['2026-06-08T07:15:00', '2026-06-08T08:00:00', 'work'], ['2026-06-08T08:00:00', '2026-06-08T08:30:00', 'work', 'rest']], 2 (forventet [...], 2)
Allerede rettet segment springes over: OK - fik [...], 1 (forventet [...], 1)
Ingen pauser: OK - fik [['2026-06-08T06:00:00', '2026-06-08T06:45:00', 'driving']], 0 (forventet [...], 0)
Tom liste: OK - fik [], 0 (forventet [], 0)
```

- [ ] **Step 5: Commit**

```bash
git add app/routers/activities.py app/_test_correct_all_segments.py
git commit -m "feat: tilføj bulk-korrektion af pause-segmenter (correct-all-segments)"
```

---

### Task 2: Frontend button and end-to-end verification

**Files:**
- Modify: `app/static/js/app.js:923-967` (`renderSegmentTable`)
- Modify: `app/static/js/app.js:969-980` (insert new `correctAllSegments` function after `correctSegment`)

**Interfaces:**
- Consumes: `POST /api/activities/{activity_id}/correct-all-segments` from Task 1 (returns full `ActivityResponse` JSON, same shape as the existing `correct-segment` response consumed by `correctSegment()`).
- Consumes: existing `POST(url, body)` helper, `state.activities`, `openActivityDetail(id)`, `renderActivitiesTable()`, `toast(msg, type)` — all already used identically by `correctSegment()` at `app.js:969-980`.

- [ ] **Step 1: Add the button and `hasCorrectable` check to `renderSegmentTable`**

In `app/static/js/app.js`, modify the start and the return statement of `renderSegmentTable` (currently lines 923-967):

```javascript
function renderSegmentTable(a) {
  if (!a.segments || a.segments.length === 0) return "";
  const hasCorrectable = a.segments.some(seg => seg[2] === "rest" && seg.length < 4);
  // Saksen vises ikke på første linje (split ved aktivitetens start giver ingen mening)
  const rows = a.segments.map((seg, idx) => {
    const [s, e, name, correctedFrom] = seg;
    const mins = Math.round((new Date(e) - new Date(s)) / 60000);
    const h = Math.floor(mins / 60), m = mins % 60;
    const canSplit = idx > 0;
    const isCorrected = correctedFrom !== undefined;
    const rowBg = name === "rest" ? `style="background:#d4edcc;"` : "";
    const tilrettet = isCorrected ? "Ja" : (a.is_edited ? "Ja" : "Nej");
    let retBtns = "";
    if (name === "rest" && !isCorrected) {
      retBtns = `<div style="display:flex;flex-direction:column;gap:3px;align-items:flex-start">
        <button class="seg-correct-btn" data-idx="${idx}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer" title="Ret til 'Andet arbejde'">Ret linje</button>
        <button class="seg-resize-btn" data-idx="${idx}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer" title="Tilpas pauselængde">Tilpas</button>
      </div>`;
    } else if (isCorrected) {
      retBtns = `<button class="seg-revert-btn" data-idx="${idx}" data-id="${a.id}" style="font-size:11px;padding:2px 7px;cursor:pointer" title="Gendan til '${SEGMENT_LABELS[correctedFrom] || correctedFrom}'">Gendan</button>`;
    }
    return `<tr ${rowBg}>
      <td>${formatDateTime(s)}</td>
      <td>${SEGMENT_LABELS[name] || name}</td>
      <td>${h} t. ${m} m.</td>
      <td style="text-align:center">${retBtns}</td>
      <td>${tilrettet}</td>
      <td style="text-align:center">${SEGMENT_ICONS[name] || ""}</td>
      <td style="text-align:center">${canSplit
        ? `<button class="seg-split-btn" data-split-at="${s}" title="Split aktiviteten her (kl. ${formatTime(s)})">✂️</button>`
        : ""}</td>
    </tr>`;
  }).join("");
  return `
  <div class="mt-16">
    ${hasCorrectable ? `<button class="btn btn-secondary" onclick="correctAllSegments(${a.id})" style="margin-bottom:8px">Al pause til andet arbejde</button>` : ""}
    <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light);margin-bottom:6px;display:block">Detaljeret information om dagen</label>
    <div style="max-height:260px;overflow-y:auto;border:1px solid var(--border);border-radius:var(--radius)">
      <table style="font-size:12px">
        <thead>
          <tr><th>Dato og tid</th><th>Status</th><th>Forbrugt tid</th><th>Ret</th><th>Tilrettet</th><th>Type</th><th style="width:36px"></th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </div>`;
}
```

Only two changes versus the current code: the new `hasCorrectable` line right after the early-return, and the new button line at the top of the returned template — the rest of the function body is unchanged, copied verbatim to keep the diff easy to review.

- [ ] **Step 2: Add the `correctAllSegments` handler function**

In `app/static/js/app.js`, immediately after the existing `correctSegment` function (currently ends at line 980, right before `openResizeSegment`), add:

```javascript
async function correctAllSegments(activityId) {
  try {
    const updated = await POST(`/api/activities/${activityId}/correct-all-segments`);
    state.activities = state.activities.map(a => a.id === updated.id ? updated : a);
    const body = document.getElementById("modal-activity-body");
    const scrollTop = body ? body.scrollTop : 0;
    openActivityDetail(activityId);
    if (body) body.scrollTop = scrollTop;
    renderActivitiesTable();
    toast("Alle pauselinjer rettet til 'Andet arbejde'", "success");
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 3: Ensure seeded test data exists**

`app.js` has automatic cache-busting, so no server restart is needed for this task's changes — but the server itself (started in Task 1 to pick up the new endpoint) must already be running. If it isn't, start it:

```bash
cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

If the dev database has no tachograph activities with pause segments yet, seed them:

```bash
cd app && python seed_testdata.py
```

This creates employee `002 Allan Redin Nykov` with a pattern that includes approved/pending tachograph activities with `pause_intervals`/`segments` in the period 2026-06-01 to 2026-06-14 (e.g. day index 0, 3, 6, 9 have a 12:00–12:30 pause).

- [ ] **Step 4: Manually verify in the browser**

1. Open `http://localhost:8000`, log in with initials `admin` / password `admin` (or the project's real admin credentials if already changed).
2. Go to "Aktivitetsoversigt", navigate (via the period toolbar's previous/next buttons) to the period covering 1–14 June 2026, and filter by employee "Allan Redin Nykov".
3. Open an activity that has a visible "Ret linje"/"Tilpas" pair in its segment table (a tachograph activity with an un-corrected pause).
4. **Verify:** the "Al pause til andet arbejde" button is visible directly above the "Detaljeret information om dagen" label.
5. Click the button. **Verify:** every row that previously showed "Ret linje"/"Tilpas" now shows "Gendan" instead, the row's "Type" column changed from "Pause" ☕ to "Andet arbejde" 📦, the "Tilrettet" column shows "Ja", and the "Al pause til andet arbejde" button has disappeared (no correctable segments remain).
6. With the same activity still fully corrected (button hidden, so this bypasses the UI deliberately to test the backend's own guard), open the browser dev console and run `fetch('/api/activities/' + <id> + '/correct-all-segments', {method: 'POST'}).then(r => r.json()).then(console.log)`, substituting the activity's id. **Verify:** the logged response is `{"detail": "Ingen pauselinjer at rette"}` (HTTP 400) — the endpoint itself refuses a no-op call even when reached directly, not just via the hidden button.
7. Click "Gendan" on exactly one of the now-corrected rows. **Verify:** only that row reverts to "Pause" ☕ with "Ret linje"/"Tilpas" buttons again; all other rows remain "Andet arbejde" 📦 with "Gendan". **Verify:** the "Al pause til andet arbejde" button reappears (one correctable segment exists again).
8. Open an activity that has no `segments` at all (a manual activity, or one whose pause is stored only in `pause_intervals`). **Verify:** no "Al pause til andet arbejde" button is rendered.
9. Open the browser's network tab or `read_network_requests`, repeat step 5 on a fresh activity with multiple un-corrected pauses, and confirm the request was `POST /api/activities/{id}/correct-all-segments` with a `200` response and no separate request per row (single network call for the whole bulk action).

- [ ] **Step 5: Commit**

```bash
git add app/static/js/app.js
git commit -m "feat: knap til bulk-korrektion af alle pause-linjer i aktivitetsdetaljen"
```
