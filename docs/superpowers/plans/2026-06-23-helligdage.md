# Helligdagskalender Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tilføj en helligdagskalender der auto-genererer danske helligdage for 5 løbende år, vises i Stamdata (kun `manage_holidays`), og markerer helligdage med farven `#adc730` i aktivitetskalenderen.

**Architecture:** En ny `Holiday` SQLAlchemy-model gemmer alle helligdage (auto-genererede og manuelle). `app/calculators/holidays.py` beregner påskedato via Computus og returnerer årets 14 helligdage. `_seed_holidays()` i `session.py` sikrer altid 5 år er seeded ved serveropstart. Frontend: fane + CRUD kun synlig for `manage_holidays`; aktivitetskalenderens dag-headers markeres med `#adc730` og "½"-badge for halvdagshelligdage.

**Tech Stack:** Python 3.11, SQLAlchemy 2, FastAPI, SQLite (WAL), Vanilla JS (ES2020)

## Global Constraints

- Farvekode helligdagsmarkering: `#adc730` (baggrundsfarve på `<th>`-header i aktivitetskalender)
- Halvdagshelligdage: samme farve + badge-tekst `½ fra 12:00`
- Permission-navn: `manage_holidays` — label `"Administrér helligdage"`
- `admin`-rollen har `is_system=True` og omgår alle permission-checks automatisk
- Store Bededag medtages ikke (afskaffet fra 2024)
- Ingen ændringer til lønberegner i dette scope (lønregler implementeres i separat fase)
- Alle eksisterende mønstre følges: `jq()` i onclick-attributter, `h()` til XSS-escaping i innerHTML

---

### Task 1: Holiday-model

**Files:**
- Modify: `app/database/models.py` — tilføj `Holiday`-klasse

**Interfaces:**
- Produces: `Holiday` model med `id`, `date`, `name`, `half_day_from`, `is_auto_generated`

- [ ] **Step 1: Tilføj `Holiday`-klasse til `app/database/models.py`**

Åbn filen. Find klassen `MasterAbsenceType` (sidst i filen). Tilføj følgende **efter** den:

```python
class Holiday(Base):
    __tablename__ = "holidays"

    id                = Column(Integer, primary_key=True)
    date              = Column(Date, unique=True, nullable=False)
    name              = Column(String(200), nullable=False)
    half_day_from     = Column(String(5), nullable=True)    # "12:00" = fri fra middag; NULL = heldagshelligdag
    is_auto_generated = Column(Boolean, default=True, nullable=False)
```

- [ ] **Step 2: Verificér model**

Genstart preview-server. Ingen fejl i loggen = OK. `Base.metadata.create_all` opretter tabellen automatisk ved opstart — ingen ALTER-migration nødvendig da det er en helt ny tabel.

---

### Task 2: Holiday-beregner

**Files:**
- Create: `app/calculators/holidays.py`

**Interfaces:**
- Produces:
  - `easter_date(year: int) -> date` — returnerer påskedato for `year`
  - `get_holidays_for_year(year: int) -> list[dict]` — hvert element er `{"date": date, "name": str, "half_day_from": str|None, "is_auto_generated": True}`

- [ ] **Step 1: Opret `app/calculators/holidays.py`**

```python
from datetime import date, timedelta


def easter_date(year: int) -> date:
    """Beregn påskedag via anonym Gregoriansk Computus."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_holidays_for_year(year: int) -> list:
    """Returnér liste af helligdage for ét år (14 rækker)."""
    easter = easter_date(year)

    fixed = [
        (date(year,  1,  1), "Nytårsdag",            None),
        (date(year,  5,  1), "1. maj",                "12:00"),
        (date(year,  6,  5), "Grundlovsdag",          "12:00"),
        (date(year, 12, 24), "Juleaftensdag",         None),
        (date(year, 12, 25), "1. juledag",            None),
        (date(year, 12, 26), "2. juledag",            None),
        (date(year, 12, 31), "Nytårsaftensdag",       None),
    ]

    moving = [
        (easter - timedelta(days=3),  "Skærtorsdag",           None),
        (easter - timedelta(days=2),  "Langfredag",             None),
        (easter,                      "Påskedag",               None),
        (easter + timedelta(days=1),  "2. påskedag",            None),
        (easter + timedelta(days=39), "Kristi Himmelfartsdag",  None),
        (easter + timedelta(days=49), "Pinsedag",               None),
        (easter + timedelta(days=50), "2. pinsedag",            None),
    ]

    return [
        {"date": d, "name": n, "half_day_from": hf, "is_auto_generated": True}
        for d, n, hf in fixed + moving
    ]
```

- [ ] **Step 2: Verificér beregner i Python**

Åbn en terminal i `app/`-mappen og kør:

```python
python -c "
from calculators.holidays import easter_date, get_holidays_for_year
print('Påske 2026:', easter_date(2026))   # Forventet: 2026-04-05
print('Påske 2025:', easter_date(2025))   # Forventet: 2025-04-20
print('Påske 2024:', easter_date(2024))   # Forventet: 2024-03-31
for hol in sorted(get_holidays_for_year(2026), key=lambda x: x['date']):
    print(hol['date'], hol['name'], hol['half_day_from'] or '')
"
```

Forventet output for 2026 (14 linjer, sorteret efter dato):
```
2026-01-01 Nytårsdag
2026-04-02 Skærtorsdag
2026-04-03 Langfredag
2026-04-05 Påskedag
2026-04-06 2. påskedag
2026-05-01 1. maj 12:00
2026-05-14 Kristi Himmelfartsdag
2026-05-24 Pinsedag
2026-05-25 2. pinsedag
2026-06-05 Grundlovsdag 12:00
2026-12-24 Juleaftensdag
2026-12-25 1. juledag
2026-12-26 2. juledag
2026-12-31 Nytårsaftensdag
```

---

### Task 3: Seed helligdage ved serveropstart

**Files:**
- Modify: `app/database/session.py`

**Interfaces:**
- Consumes: `get_holidays_for_year(year)` fra `app/calculators/holidays.py`; `Holiday` fra `app/database/models.py`
- Produces: `_seed_holidays()` funktion tilgængelig og kaldt fra `init_db()`

- [ ] **Step 1: Tilføj `_seed_holidays()` til `app/database/session.py`**

Find `_seed_cvr()`-funktionen. Tilføj `_seed_holidays()` **direkte efter** den:

```python
def _seed_holidays():
    from database.models import Holiday
    from calculators.holidays import get_holidays_for_year
    from datetime import date
    db = SessionLocal()
    try:
        current_year = date.today().year
        for year in range(current_year, current_year + 5):
            for h in get_holidays_for_year(year):
                if not db.query(Holiday).filter(Holiday.date == h["date"]).first():
                    db.add(Holiday(
                        date=h["date"],
                        name=h["name"],
                        half_day_from=h["half_day_from"],
                        is_auto_generated=True,
                    ))
        db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved seeding af helligdage: {e}")
    finally:
        db.close()
```

- [ ] **Step 2: Kald `_seed_holidays()` fra `init_db()`**

Find `init_db()`-funktionen. Den ender nu med `_seed_cvr()`. Tilføj kaldet:

```python
def init_db():
    from database.models import Base
    Base.metadata.create_all(bind=engine)
    _migrate()
    _seed_roles()
    _seed_admin()
    _seed_master_data()
    _seed_cvr()
    _seed_holidays()    # ← tilføj denne linje
```

- [ ] **Step 3: Verificér seeding**

Genstart preview-server og tjek loggen — ingen fejl. Verificér via preview_eval i browser:

```javascript
fetch("/api/stamdata/holidays").then(r=>r.json()).then(d=>console.log(d.length, d[0]))
```

Forventet: tallet 70 (14 helligdage × 5 år) og første objekt som `{id:1, date:"2026-01-01", name:"Nytårsdag", ...}`.

*Bemærk: GET /api/stamdata/holidays eksisterer endnu ikke — step 3 udføres efter Task 4.*

---

### Task 4: Permission + API-endpoints

**Files:**
- Modify: `app/auth.py` — tilføj `manage_holidays` til `ALL_PERMISSIONS`
- Modify: `app/routers/stamdata.py` — tilføj `Holiday`-import + 4 endpoints

**Interfaces:**
- Consumes: `Holiday` model, `_access` (stamdata-permission), `require_permission("manage_holidays")`
- Produces:
  - `GET /api/stamdata/holidays?year=YYYY`
  - `POST /api/stamdata/holidays` — body: `{date, name, half_day_from}`
  - `DELETE /api/stamdata/holidays/{id}`
  - `POST /api/stamdata/holidays/generate/{year}`

- [ ] **Step 1: Tilføj `manage_holidays` til `ALL_PERMISSIONS` i `app/auth.py`**

Find `ALL_PERMISSIONS`-dict og tilføj ét nyt entry:

```python
"manage_holidays": "Administrér helligdage",
```

- [ ] **Step 2: Tilføj `Holiday` til import i `app/routers/stamdata.py`**

Find import-linjen med `from database.models import (` og tilføj `Holiday`:

```python
from database.models import (
    AppUser, Employee,
    MasterAgreementType, MasterOvertimeRate,
    MasterSupplementRate, MasterPayType, MasterAbsenceType, MasterCvrNumber,
    Holiday,
)
```

- [ ] **Step 3: Tilføj helligdags-endpoints til slutningen af `app/routers/stamdata.py`**

Tilføj hele denne blok efter de eksisterende CVR-endpoints:

```python
# ── Helligdage ───────────────────────────────────────────────────────────────

_holidays_mgmt = require_permission("manage_holidays")


def _holiday_row(r) -> dict:
    return {
        "id":               r.id,
        "date":             r.date.isoformat(),
        "name":             r.name,
        "half_day_from":    r.half_day_from,
        "is_auto_generated": r.is_auto_generated,
    }


class HolidayBody(BaseModel):
    date:          str
    name:          str
    half_day_from: Optional[str] = None


@router.get("/holidays")
def list_holidays(
    year: Optional[int] = None,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    from datetime import date as _date
    q = db.query(Holiday).order_by(Holiday.date)
    if year:
        q = q.filter(
            Holiday.date >= _date(year, 1, 1),
            Holiday.date <= _date(year, 12, 31),
        )
    return [_holiday_row(r) for r in q.all()]


@router.post("/holidays", status_code=201)
def create_holiday(
    body: HolidayBody,
    current_user: AppUser = Depends(_holidays_mgmt),
    db: Session = Depends(get_db),
):
    from datetime import date as _date
    try:
        d = _date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(400, "Ugyldig dato — brug YYYY-MM-DD format")
    if db.query(Holiday).filter(Holiday.date == d).first():
        raise HTTPException(400, "Der er allerede en helligdag på denne dato")
    if body.half_day_from and body.half_day_from not in ("12:00",):
        raise HTTPException(400, "half_day_from skal være '12:00' eller tom")
    row = Holiday(
        date=d,
        name=body.name.strip(),
        half_day_from=body.half_day_from or None,
        is_auto_generated=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "holiday", row.id,
               f"Oprettet helligdag: {row.date} {row.name}")
    db.commit()
    return _holiday_row(row)


@router.delete("/holidays/{holiday_id}", status_code=204)
def delete_holiday(
    holiday_id: int,
    current_user: AppUser = Depends(_holidays_mgmt),
    db: Session = Depends(get_db),
):
    row = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not row:
        raise HTTPException(404, "Helligdag ikke fundet")
    log_action(db, current_user, "stamdata_delete", "holiday", row.id,
               f"Slettet helligdag: {row.date} {row.name}")
    db.delete(row)
    db.commit()


@router.post("/holidays/generate/{year}", status_code=200)
def generate_holidays_for_year(
    year: int,
    current_user: AppUser = Depends(_holidays_mgmt),
    db: Session = Depends(get_db),
):
    from calculators.holidays import get_holidays_for_year
    if year < 2020 or year > 2100:
        raise HTTPException(400, "Årstal skal være mellem 2020 og 2100")
    added = 0
    for h in get_holidays_for_year(year):
        if not db.query(Holiday).filter(Holiday.date == h["date"]).first():
            db.add(Holiday(
                date=h["date"],
                name=h["name"],
                half_day_from=h["half_day_from"],
                is_auto_generated=True,
            ))
            added += 1
    db.commit()
    log_action(db, current_user, "stamdata_create", "holiday", None,
               f"Genereret {added} helligdage for {year}")
    db.commit()
    return {"year": year, "added": added}
```

- [ ] **Step 4: Verificér endpoints**

Genstart server. Test i browser-konsol (F12):

```javascript
// GET — hent 2026
fetch("/api/stamdata/holidays?year=2026").then(r=>r.json()).then(d=>console.log(d.length, d))
// Forventet: 14, array med helligdage

// POST generate — tilføj 2031
fetch("/api/stamdata/holidays/generate/2031",{method:"POST"}).then(r=>r.json()).then(console.log)
// Forventet: {"year":2031,"added":14}
```

---

### Task 5: Frontend — Stamdata Helligdage-fane

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`

**Interfaces:**
- Consumes: alle 4 endpoints fra Task 4; `buildDatePicker()`, `readDatePicker()`, `openModal()`, `closeModal()`, `toast()`, `GET()`, `POST()`, `DEL()`, `h()`, `jq()` (alle allerede defineret i app.js)
- Produces: `loadStamdataHolidays()`, `openNewHolidayModal()`, `confirmNewHoliday()`, `deleteHoliday(id, label)`, `generateHolidaysForYear()`

- [ ] **Step 1: Tilføj `manage_holidays` til `PERMISSION_LABELS` i `app.js`**

Find `PERMISSION_LABELS`-objektet og tilføj ét entry:

```javascript
manage_holidays: "Administrér helligdage",
```

- [ ] **Step 2: Tilføj toolbar-knap i `app/templates/index.html`**

Find blokken med Stamdata-toolbar-knapper (alle `btn-stamdata-add-*`). Tilføj som den sidste:

```html
<button id="btn-stamdata-add-holiday" class="btn btn-primary" style="display:none" onclick="openNewHolidayModal()">+ Tilføj</button>
```

- [ ] **Step 3: Tilføj tab-knap i `app/templates/index.html`**

Find tab-knap-blokken i Stamdata-view. Tilføj **efter** "CVR nummer"-knappen:

```html
<button id="sd-tab-holiday" onclick="switchStamdataTab('holiday')"
        style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer"
        data-perm-require="manage_holidays">
  Helligdage
</button>
```

- [ ] **Step 4: Tilføj Helligdage-pane i `app/templates/index.html`**

Find `<div id="sd-pane-paytype"...>` pane-blokken. Tilføj følgende **før** den (dvs. inden Løntypekoder):

```html
<!-- Helligdage -->
<div id="sd-pane-holiday" style="display:none">
  <table style="width:100%;border-collapse:collapse;font-size:14px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
    <thead>
      <tr style="background:var(--primary);color:#fff">
        <th style="padding:10px 14px;text-align:left;font-weight:600">Dato</th>
        <th style="padding:10px 14px;text-align:left;font-weight:600">Navn</th>
        <th style="padding:10px 14px;text-align:center;font-weight:600">Halvdag fra</th>
        <th style="padding:10px 14px;text-align:center;font-weight:600">Type</th>
        <th style="padding:10px 14px;text-align:center;font-weight:600">Handlinger</th>
      </tr>
    </thead>
    <tbody id="stamdata-holiday-tbody">
      <tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>
    </tbody>
  </table>
  <div style="margin-top:12px;display:flex;gap:8px;align-items:center">
    <span style="font-size:13px;color:var(--text-light)">Generer helligdage for år:</span>
    <input type="number" id="holiday-gen-year" style="width:90px;padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px" placeholder="2031" min="2020" max="2100">
    <button class="btn btn-secondary" style="font-size:13px" onclick="generateHolidaysForYear()">Generer</button>
  </div>
</div>
```

- [ ] **Step 5: Tilføj modal i `app/templates/index.html`**

Find den første `<!-- ──` modal-kommentar i modal-sektionen. Tilføj denne modal **øverst** i modal-sektionen:

```html
<!-- ── Stamdata: Opret helligdag ── -->
<div id="modal-stamdata-holiday" class="modal-overlay">
  <div class="modal" style="width:420px">
    <div class="modal-header">
      <h2>Opret helligdag</h2>
      <button class="modal-close" onclick="closeModal('modal-stamdata-holiday')">&#215;</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label>Dato <span style="color:var(--danger)">*</span></label>
        <div id="holiday-date-picker"></div>
      </div>
      <div class="form-group">
        <label>Navn <span style="color:var(--danger)">*</span></label>
        <input type="text" id="holiday-name" placeholder="fx Særlig fridag">
      </div>
      <div class="form-group" style="display:flex;align-items:center;gap:10px">
        <input type="checkbox" id="holiday-halfday-check" style="width:16px;height:16px;cursor:pointer"
               onchange="document.getElementById('holiday-halfday-group').style.display=this.checked?'':'none'">
        <label for="holiday-halfday-check" style="margin:0;cursor:pointer">Halvdagshelligdag</label>
      </div>
      <div class="form-group" id="holiday-halfday-group" style="display:none">
        <label>Fri fra kl.</label>
        <input type="text" id="holiday-halfday-from" value="12:00" placeholder="12:00" maxlength="5"
               style="width:80px">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-stamdata-holiday')">Annuller</button>
      <button class="btn btn-primary" onclick="confirmNewHoliday()">Opret</button>
    </div>
  </div>
</div>
```

- [ ] **Step 6: Opdater `switchStamdataTab()` i `app.js`**

Find `switchStamdataTab(tab)`-funktionen. Den starter med:
```javascript
["agreement", "overtime", "supplement", "paytype", "absence", "cvr"].forEach(t => {
```

Erstat arrayet med:
```javascript
["agreement", "overtime", "supplement", "paytype", "absence", "cvr", "holiday"].forEach(t => {
```

Find blokken med `btn-stamdata-add-*` display-lines og tilføj:
```javascript
document.getElementById("btn-stamdata-add-holiday").style.display = tab === "holiday" ? "" : "none";
```

- [ ] **Step 7: Tilføj `loadStamdataHolidays()` og hjælpefunktioner til `app.js`**

Find blokken `// ── Hændelseslog`. Indsæt følgende **umiddelbart før** den:

```javascript
// ── Helligdage (stamdata) ────────────────────────────────────────────────────

async function loadStamdataHolidays() {
  const tbody = document.getElementById("stamdata-holiday-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/holidays");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-light)">Ingen helligdage oprettet endnu</td></tr>`;
      return;
    }
    const fmtDate = iso => { const [y,m,d] = iso.split("-"); return `${d}-${m}-${y}`; };
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px;font-variant-numeric:tabular-nums">${fmtDate(r.date)}</td>
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;text-align:center">${r.half_day_from ? h(r.half_day_from) : "—"}</td>
        <td style="padding:10px 14px;text-align:center">
          <span style="font-size:12px;padding:2px 8px;border-radius:12px;background:${r.is_auto_generated ? "var(--bg)" : "#d4edcc"};color:var(--text-light)">
            ${r.is_auto_generated ? "Auto" : "Manuel"}
          </span>
        </td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger)"
                  onclick="deleteHoliday(${r.id}, ${jq(r.date)})">Slet</button>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function openNewHolidayModal() {
  buildDatePicker("holiday-date-picker", "");
  document.getElementById("holiday-name").value = "";
  document.getElementById("holiday-halfday-check").checked = false;
  document.getElementById("holiday-halfday-group").style.display = "none";
  document.getElementById("holiday-halfday-from").value = "12:00";
  openModal("modal-stamdata-holiday");
}

async function confirmNewHoliday() {
  const dateVal  = readDatePicker("holiday-date-picker");
  const name     = document.getElementById("holiday-name").value.trim();
  const isHalf   = document.getElementById("holiday-halfday-check").checked;
  const halfFrom = isHalf ? document.getElementById("holiday-halfday-from").value.trim() : null;
  if (!dateVal || !name) { toast("Udfyld dato og navn", "error"); return; }
  try {
    await POST("/api/stamdata/holidays", { date: dateVal, name, half_day_from: halfFrom });
    toast("Helligdag oprettet");
    closeModal("modal-stamdata-holiday");
    await loadStamdataHolidays();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteHoliday(id, label) {
  if (!confirm(`Slet helligdagen "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/holidays/${id}`);
    toast("Helligdag slettet");
    await loadStamdataHolidays();
  } catch (e) { toast(e.message, "error"); }
}

async function generateHolidaysForYear() {
  const year = parseInt(document.getElementById("holiday-gen-year").value);
  if (!year || year < 2020 || year > 2100) { toast("Angiv et gyldigt årstal (2020–2100)", "error"); return; }
  try {
    const res = await POST(`/api/stamdata/holidays/generate/${year}`, {});
    toast(`${res.added} helligdage tilføjet for ${year}`);
    await loadStamdataHolidays();
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 8: Tilføj `loadStamdataHolidays()` til `loadStamdata()` i `app.js`**

Find `loadStamdata()`-funktionen og tilføj `loadStamdataHolidays()` i Promise.all-arrayet:

```javascript
async function loadStamdata() {
  switchStamdataTab("agreement");
  await Promise.all([
    loadStamdataAgreementTypes(),
    loadStamdataOvertimeRates(),
    loadStamdataSupplements(),
    loadStamdataPayTypes(),
    loadStamdataAbsenceTypes(),
    loadStamdataCvrNumbers(),
    loadStamdataHolidays(),
  ]);
}
```

- [ ] **Step 9: Verificér fanen**

Genstart server. Log ind som admin, gå til Stamdata → Helligdage. Tabellen skal vise 70 rækker (14 × 5 år). Prøv:
- Klik "+ Tilføj" → udfyld dato og navn → opret → bekræft ny række
- Klik "Slet" på en auto-genereret helligdag → bekræft sletning
- Skriv `2031` i "Generer år" → klik Generer → `14 helligdage tilføjet for 2031`

---

### Task 6: Aktivitetskalender — helligdagsmarkering

**Files:**
- Modify: `app/static/js/app.js`

**Interfaces:**
- Consumes: `GET /api/stamdata/holidays?year=YYYY`; `state.holidays` (array med `{date, name, half_day_from}`); `renderActivitiesTable()` (line 173); `isoOf(d)` (line 200, lokal i renderActivitiesTable); `loadActivities()` (line 161)
- Produces: `state.holidays` cache; `loadHolidaysForPeriod(startDate, endDate)`; `<th>`-headers med `#adc730`-baggrund og "½"-badge

- [ ] **Step 1: Tilføj `holidays` til `state`-objektet**

Find `state`-objektet (line ~15). Det slutter med `usersAdminTab: "users-admin",` eller lignende. Tilføj:

```javascript
holidays: [],   // { date: "YYYY-MM-DD", name: string, half_day_from: string|null }
```

- [ ] **Step 2: Tilføj `loadHolidaysForPeriod()` til `app.js`**

Find `loadActivities()`-funktionen (line 161). Tilføj følgende **umiddelbart før** den:

```javascript
async function loadHolidaysForPeriod(startDate, endDate) {
  const startYear = parseInt(startDate.substring(0, 4));
  const endYear   = parseInt(endDate.substring(0, 4));
  try {
    if (startYear === endYear) {
      state.holidays = await GET(`/api/stamdata/holidays?year=${startYear}`);
    } else {
      const [a, b] = await Promise.all([
        GET(`/api/stamdata/holidays?year=${startYear}`),
        GET(`/api/stamdata/holidays?year=${endYear}`),
      ]);
      state.holidays = [...a, ...b];
    }
  } catch (_) {
    state.holidays = [];
  }
}
```

- [ ] **Step 3: Kald `loadHolidaysForPeriod` fra `loadActivities()`**

Find `loadActivities()` (line 161). Dens krop ser ud som:

```javascript
async function loadActivities() {
  setLoading(true);
  try {
    if (!state.periodInfo) await loadPeriodInfo();
    state.activities = await GET(`/api/activities?period_start=${state.currentPeriodStart}`);
    renderActivitiesTable();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}
```

Erstat den med:

```javascript
async function loadActivities() {
  setLoading(true);
  try {
    if (!state.periodInfo) await loadPeriodInfo();
    const p = state.periodInfo.period;
    await Promise.all([
      GET(`/api/activities?period_start=${state.currentPeriodStart}`).then(a => { state.activities = a; }),
      loadHolidaysForPeriod(p.start_date, p.end_date),
    ]);
    renderActivitiesTable();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}
```

- [ ] **Step 4: Markér helligdage i `renderActivitiesTable()` kolonne-headers**

Find header-blokken i `renderActivitiesTable()` (line 202-211):

```javascript
// Header
const head = document.getElementById("grid-head");
head.innerHTML = `<tr>
  <th>Chauffør</th>
  ${days.map(d => `
    <th class="${isoOf(d) === todayIso ? "today" : ""}">
      <span class="day-name">${DAY_NAMES[(d.getDay() + 6) % 7]}</span>
      <span class="day-date">${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}</span>
    </th>`).join("")}
</tr>`;
```

Erstat den med:

```javascript
// Header
const head = document.getElementById("grid-head");
head.innerHTML = `<tr>
  <th>Chauffør</th>
  ${days.map(d => {
    const iso  = isoOf(d);
    const hol  = state.holidays.find(x => x.date === iso);
    const cls  = iso === todayIso ? "today" : "";
    const bg   = hol ? `background:#adc730;` : "";
    const half = hol?.half_day_from
      ? `<span style="font-size:10px;display:block;color:#fff;margin-top:1px">½ fra ${hol.half_day_from}</span>`
      : "";
    const tip  = hol ? `title="${hol.name.replace(/"/g, '&quot;')}"` : "";
    return `<th class="${cls}" style="${bg}" ${tip}>
      <span class="day-name">${DAY_NAMES[(d.getDay() + 6) % 7]}</span>
      <span class="day-date">${String(d.getDate()).padStart(2, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}</span>
      ${half}
    </th>`;
  }).join("")}
</tr>`;
```

- [ ] **Step 5: Verificér kalendermarkering**

Genstart server. Navigér til perioden **15. jun – 28. jun 2026** (eller en periode der inkluderer en helligdag). Da ingen af dagene 15–28 juni 2026 er helligdage, navigér til en periode med **1. maj** eller **Grundlovsdag** (5. juni). Kontrolpunkter:

- Kolonnen for 1. maj 2026: grøn baggrund `#adc730` + badge `½ fra 12:00` + tooltip "1. maj"
- Kolonnen for 5. juni 2026: grøn baggrund `#adc730` + badge `½ fra 12:00` + tooltip "Grundlovsdag"
- Kolonnen for 25. december 2026: grøn baggrund, ingen ½-badge, tooltip "1. juledag"
- Normale dage: uændret udseende

---

## Spec-dækning ✓

| Spec-krav | Task |
|-----------|------|
| `holidays`-tabel med `half_day_from` | Task 1 |
| `easter_date()` + `get_holidays_for_year()` | Task 2 |
| `_seed_holidays()` — 5 løbende år | Task 3 |
| `manage_holidays` permission | Task 4, Step 1 |
| GET/POST/DELETE/generate endpoints | Task 4, Step 3 |
| Stamdata-fane med `data-perm-require` | Task 5, Step 3 |
| CRUD i Stamdata (tilføj, slet, generer) | Task 5 |
| `state.holidays` cache | Task 6, Step 1 |
| Kalendermarkering `#adc730` + ½-badge | Task 6, Step 4 |
| Tooltip med helligdagsnavn | Task 6, Step 4 |
