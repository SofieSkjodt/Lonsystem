/* ── Lønsystem frontend ── */
"use strict";

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
const h = escapeHtml;

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  currentView: "activities",
  currentPeriodStart: null,
  periodInfo: null,
  activities: [],
  employees: [],
  vehicles: [],
  agreementTypes: [],
  absenceTypes: [],
  selectedActivityId: null,
  currentUser: null,       // { id, name, initials, role, email, permissions }
  roles: [],               // { id, name, display_name, is_system, permissions[] }
  usersAdminTab: "users",  // aktiv fane i users-admin view
  holidays: [],            // { date: "YYYY-MM-DD", name: string, half_day_from: string|null }
  dispatcherGroups: [],    // { id, name, description }
};

const PERMISSION_LABELS = {
  payroll:             "Lønkørsel",
  absence_overview:    "Fraværsoversigt",
  import_ddd:          "Importer .ddd",
  user_management:     "Brugerstyring",
  reopen_period:       "Åbn låst lønperiode",
  stamdata:            "Stamdata",
  view_employees:      "Se medarbejdere",
  manage_employees:    "Tilføj medarbejdere",
  view_vehicles:       "Se vognpark",
  manage_vehicles:     "Tilføj vogn",
  manage_holidays:     "Administrér helligdage",
  anciennitet_alert:   "Anciennitetsvarsel",
  approve_activities:  "Godkend aktiviteter",
  view_calendar:       "Se aktivitetskalender",
};

let manualPauses = [];
let _resizeSegState = null;
let _absenceConflictConfirmed = false;

const WEEKDAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"];
const TYPE_LABELS = { normal: "Normal tid" };
const ABSENCE_LABELS = {};  // value → UPPERCASE label for grid badges
const ABSENCE_TYPES = new Set();

// ── API helpers ────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (res.status === 401) {
    showLoginOverlay();
    throw new Error("Ikke logget ind");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}
const GET   = (p)    => api("GET",    p);
const POST  = (p, b) => api("POST",   p, b);
const PATCH = (p, b) => api("PATCH",  p, b);
const DEL   = (p)    => api("DELETE", p);
// jq: JSON.stringify der er sikker til brug i onclick="..." HTML-attributter
const jq = x => JSON.stringify(x).replace(/"/g, "&quot;");

// ── UI helpers ─────────────────────────────────────────────────────────────
function toast(msg, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
function setLoading(on) {
  document.getElementById("loading-overlay").classList.toggle("open", on);
}
function openModal(id) {
  const modal = document.getElementById(id);
  modal.classList.add("open");
  modal.querySelector(".modal-body")?.scrollTo(0, 0);
}
function closeModal(id) { document.getElementById(id).classList.remove("open"); }
function closeAllModals() {
  document.querySelectorAll(".modal-overlay").forEach(m => m.classList.remove("open"));
}

// ── Navigation ─────────────────────────────────────────────────────────────
function setView(view) {
  state.currentView = view;
  document.querySelectorAll(".sidebar-item").forEach(el =>
    el.classList.toggle("active", el.dataset.view === view));
  document.querySelectorAll(".view").forEach(el =>
    el.classList.toggle("hidden", el.dataset.view !== view));

  if (view === "activities")        loadActivities();
  if (view === "employees")         loadEmployees();
  if (view === "payroll")           loadPayrollPreview();
  if (view === "absence-overview")  loadAbsenceOverview();
  if (view === "vehicles")          loadVehicles();
  if (view === "users-admin")       loadUsersAdminView();
  if (view === "stamdata")          loadStamdata();
}

// ── Period navigation ──────────────────────────────────────────────────────
async function loadPeriodInfo(periodStart = null) {
  const qs = periodStart ? `?period_start=${periodStart}` : "";
  const data = await GET(`/api/activities/period-info${qs}`);
  state.periodInfo = data;
  state.currentPeriodStart = data.period.start_date;
  renderPeriodBar();
}

function renderPeriodBar() {
  const p = state.periodInfo;
  if (!p) return;
  const fmt = iso => new Date(iso + "T00:00:00")
    .toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
  document.getElementById("period-label").textContent =
    `${fmt(p.period.start_date)} – ${fmt(p.period.end_date)}`;
  document.getElementById("stat-pending").textContent  = `${p.period.pending} afventer`;
  document.getElementById("stat-approved").textContent = `${p.period.approved} godkendt`;
  document.getElementById("stat-deact").textContent    = `${p.period.deactivated} deaktiveret`;
  setDatePicker("period-date-picker", p.period.start_date);
  updateStatChipActive();
}

function updateStatChipActive() {
  const cur = document.getElementById("filter-status")?.value || "all";
  const map = { "stat-pending": "pending", "stat-approved": "approved", "stat-deact": "deactivated" };
  Object.entries(map).forEach(([id, val]) => {
    document.getElementById(id)?.classList.toggle("active", cur === val);
  });
}

function toggleStatFilter(status) {
  const sel = document.getElementById("filter-status");
  if (!sel) return;
  sel.value = (sel.value === status) ? "all" : status;
  updateStatChipActive();
  renderActivitiesTable();
}


async function navigatePeriod(direction) {
  const p = state.periodInfo;
  if (!p) return;
  const iso = direction === "prev" ? p.prev_period_start : p.next_period_start;
  await loadPeriodInfo(iso);
  await loadActivities();
}

async function jumpToDate(iso) {
  if (!iso) return;
  await loadPeriodInfo(iso);
  await loadActivities();
}

// ── Activities view ────────────────────────────────────────────────────────
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

const DAY_NAMES = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"];

function renderActivitiesTable() {
  const p = state.periodInfo?.period;
  if (!p) return;

  const statusFilter = document.getElementById("filter-status")?.value || "all";
  const empFilter = document.getElementById("filter-employee")?.value || "";
  const groupFilter = document.getElementById("filter-dispatcher-group")?.value || "";

  const activities = state.activities.filter(a => {
    if (statusFilter !== "all" && a.status !== statusFilter) return false;
    if (empFilter && a.employee_id !== parseInt(empFilter)) return false;
    if (groupFilter) {
      const emp = state.employees.find(e => e.id === a.employee_id);
      if (!emp || !_empInGroup(emp, groupFilter)) return false;
    }
    return true;
  });

  // Periodens 14 dage
  const days = [];
  const start = new Date(p.start_date + "T00:00:00");
  for (let i = 0; i < 14; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    days.push(d);
  }
  const todayIso = new Date().toISOString().slice(0, 10);
  const isoOf = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

  // Header
  const head = document.getElementById("grid-head");
  head.innerHTML = `<tr>
    <th>Chauffør</th>
    ${days.map(d => {
      const iso  = isoOf(d);
      const hol  = state.holidays.find(x => x.date === iso);
      const cls  = iso === todayIso ? "today" : "";
      const bg   = hol ? (cls === "today" ? `background:#056a10;border-bottom:3px solid var(--accent);` : `background:#056a10;`) : "";
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

  // Helper: er datoen søndag eller helligdag? (bestemmer om aktivitet splittes)
  const _isAbsDay = iso => {
    const d = new Date(iso + "T00:00:00");
    if (d.getDay() === 0) return true;
    return (state.holidays || []).some(h => h.date === iso);
  };
  const _fmtLocal = dt => {
    const p = n => String(n).padStart(2, "0");
    return `${dt.getFullYear()}-${p(dt.getMonth()+1)}-${p(dt.getDate())}T${p(dt.getHours())}:${p(dt.getMinutes())}:${p(dt.getSeconds())}`;
  };

  // Gruppér aktiviteter: employee_id -> dato-ISO -> [{a, role}]
  // Kørsels-aktiviteter der starter på søn/helligdag splittes ved midnat
  // (afspejler lønberegningens _split_into_day_pieces-logik)
  const byEmpDay = {};
  for (const a of activities) {
    const startDate = a.start_time.slice(0, 10);
    const endDate   = a.end_time.slice(0, 10);
    (byEmpDay[a.employee_id] ??= {})[startDate] ??= [];
    if (endDate !== startDate && a.activity_type === "normal" && _isAbsDay(startDate)) {
      let cur = new Date(a.start_time);
      const endDt = new Date(a.end_time);
      while (cur < endDt) {
        const midnight = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 1);
        const pieceEnd = endDt < midnight ? endDt : midnight;
        const piece = { ...a, start_time: _fmtLocal(cur), end_time: _fmtLocal(pieceEnd), _orig_id: a.id };
        const pieceDate = _fmtLocal(cur).slice(0, 10);
        (byEmpDay[a.employee_id][pieceDate] ??= []).push({a: piece, role: "piece"});
        cur = midnight;
      }
    } else if (endDate !== startDate) {
      byEmpDay[a.employee_id][startDate].push({a, role: "start"});
      (byEmpDay[a.employee_id][endDate] ??= []).push({a, role: "end"});
    } else {
      byEmpDay[a.employee_id][startDate].push({a, role: "full"});
    }
  }

  // Rækker: medarbejdere (filtreret hvis valgt), sorteret efter navn
  let emps = state.employees.filter(e => e.active);
  if (groupFilter) emps = emps.filter(e => _empInGroup(e, groupFilter));
  if (empFilter) emps = emps.filter(e => e.id === parseInt(empFilter));
  emps.sort((x, y) => x.name.localeCompare(y.name, "da"));

  const body = document.getElementById("grid-body");
  body.innerHTML = "";

  if (emps.length === 0) {
    body.innerHTML = `<tr><td colspan="15" class="empty-state"><div class="icon">📋</div><h3>Ingen medarbejdere</h3></td></tr>`;
    return;
  }

  for (const emp of emps) {
    const tr = document.createElement("tr");
    let cells = `<td class="emp-cell" title="${h(emp.name)}">${h(emp.name)}</td>`;
    for (const d of days) {
      const iso = isoOf(d);
      const acts = (byEmpDay[emp.id]?.[iso] || [])
        .sort((x, y) => {
          const tx = x.role === "end" ? x.a.end_time : x.a.start_time;
          const ty = y.role === "end" ? y.a.end_time : y.a.start_time;
          return tx.localeCompare(ty);
        });
      const weekend = d.getDay() === 0 || d.getDay() === 6;
      cells += `<td class="${weekend ? "weekend" : ""}" data-emp-id="${emp.id}" data-date="${iso}">${acts.map(({a, role}) => renderCellActivity(a, role)).join("")}</td>`;
    }
    tr.innerHTML = cells;
    body.appendChild(tr);
  }

  // Klik på badge -> detalje
  body.querySelectorAll(".time-badge").forEach(el => {
    el.addEventListener("click", () => openActivityDetail(parseInt(el.dataset.id)));
  });

  // Enkelt klik på celle -> opret aktivitet for medarbejder + dag
  body.querySelectorAll("td[data-emp-id]").forEach(td => {
    td.addEventListener("click", e => {
      if (e.target.closest(".time-badge")) return;
      openManualActivityModal(parseInt(td.dataset.empId), td.dataset.date);
    });
  });
}

function renderCellActivity(a, role = "full") {
  const k = a.is_manual ? "(K) " : "";
  const warn = a.status === "approved" ? "" : (a.is_under_4h ? " ❗" : (a.is_over_12h ? " ⚠️" : ""));
  const incomplete = a.is_likely_incomplete
    ? `<span class="incomplete-mark" title="Filen ser ud til at være hentet midt i vagten (0 km registreret og dagen slutter ikke i hvil) – resten af dagen mangler formentlig. Hent en ny fil senere og importér igen.">✕</span>`
    : "";
  if (a.activity_type !== "normal") {
    return `<div class="badge-group">
      <span class="time-badge absence ${a.status}" data-id="${a.id}" title="${TYPE_LABELS[a.activity_type]} – ${statusLabel(a.status)}">${ABSENCE_LABELS[a.activity_type] || a.activity_type}</span>
    </div>`;
  }
  const title = `${a.employee_name}: ${formatTime(a.start_time)}–${formatTime(a.end_time)} (${formatDuration(a.duration_minutes)}) – ${statusLabel(a.status)}${a.is_manual ? " – manuel" : ""}`;
  const autoCls = (a.status === "approved" && a.auto_approved) ? " auto-approved" : "";
  const autoSuffix = (a.status === "approved" && a.auto_approved) ? `<span class="auto-dot" title="Auto-godkendt"></span>` : "";
  if (role === "start") {
    return `<div class="badge-group">
      <span class="time-badge ${a.status}${autoCls}" data-id="${a.id}" title="${title}">${k}${formatTime(a.start_time)}${warn}${autoSuffix}${incomplete}</span>
    </div>`;
  }
  if (role === "end") {
    return `<div class="badge-group">
      <span class="time-badge ${a.status}${autoCls}" data-id="${a.id}" title="${title}">${k}${formatTime(a.end_time)}${autoSuffix}${incomplete}</span>
    </div>`;
  }
  if (role === "piece") {
    const id = a._orig_id ?? a.id;
    return `<div class="badge-group">
      <span class="time-badge ${a.status}${autoCls}" data-id="${id}" title="${title}">${k}${formatTime(a.start_time)}–${formatTime(a.end_time)}${warn}${autoSuffix}${incomplete}</span>
    </div>`;
  }
  return `<div class="badge-group">
    <span class="time-badge time-badge-stacked ${a.status}${autoCls}" data-id="${a.id}" title="${title}">
      <span class="time-line">${k}${formatTime(a.start_time)}${warn}</span>
      <span class="time-line">${formatTime(a.end_time)}${autoSuffix}${incomplete}</span>
    </span>
  </div>`;
}

function renderPctBar(a) {
  const d = pct(a.driving_pct), w = pct(a.other_work_pct), av = pct(a.availability_time_pct);
  const r = Math.max(0, 100 - d - w - av);
  return `<div class="pct-bar" title="Kørsel ${fmtPct(d)}% / Arbejde ${fmtPct(w)}% / Rådighed ${fmtPct(av)}% / Hvil ${fmtPct(r)}%">
    <div class="pct-driving" style="width:${d}%"></div>
    <div class="pct-work" style="width:${w}%"></div>
    <div class="pct-avail" style="width:${av}%"></div>
    <div class="pct-rest" style="width:${r}%"></div>
  </div>`;
}
function pct(v) { return v ? parseFloat(v) : 0; }
function fmtPct(v) { return v.toFixed(2); }

function renderActionBtns(a) {
  const btns = [];
  if (a.status === "pending") {
    btns.push(`<button class="btn btn-success btn-sm" onclick="quickApprove(${a.id})">✓ Godkend</button>`);
    btns.push(`<button class="btn btn-danger btn-sm" onclick="quickDeactivate(${a.id})">✗</button>`);
  } else {
    btns.push(`<button class="btn btn-secondary btn-sm" onclick="quickReopen(${a.id})">↩ Genåbn</button>`);
  }
  return btns.join("");
}

async function quickApprove(id) {
  state.selectedActivityId = id;
  openApproveModal();
}
async function quickDeactivate(id) {
  state.selectedActivityId = id;
  openDeactivateModal();
}
async function quickReopen(id) {
  try {
    await POST(`/api/activities/${id}/reopen`);
    toast("Aktivitet genåbnet");
    await refreshActivities();
  } catch (e) { toast(e.message, "error"); }
}
async function bulkAutoApprove() {
  const params = state.currentPeriodStart ? `?period_start=${state.currentPeriodStart}` : '';
  const res = await POST(`/api/activities/auto-approve-pending${params}`, {});
  if (res) {
    toast(`Auto-godkendt: ${res.approved} aktiviteter. Flagget til gennemgang: ${res.flagged}.`);
    const btn = document.getElementById("btn-auto-approve");
    if (btn) btn.innerHTML = '<span class="auto-dot"></span>Autogodkendte';
    await refreshActivities();
  }
}
async function refreshActivities() {
  state.activities = await GET(`/api/activities?period_start=${state.currentPeriodStart}`);
  await loadPeriodInfo(state.currentPeriodStart);
  renderActivitiesTable();
}

// Opdaterer én aktivitet i state og gentegner med det samme, uden at vente på
// en fuld genindlæsning fra serveren (undgår synlig forsinkelse efter godkend/deaktiver/genåbn).
function applyActivityLocally(updated) {
  if (!updated) return;
  const idx = state.activities.findIndex(x => x.id === updated.id);
  if (idx !== -1) state.activities[idx] = updated;
  else state.activities.push(updated);
  renderActivitiesTable();
}

// ── Activity detail modal ──────────────────────────────────────────────────
function openActivityDetail(id) {
  state.selectedActivityId = id;
  const a = state.activities.find(x => x.id === id);
  if (!a) return;

  document.getElementById("modal-activity-title").textContent =
    `${a.employee_name} – ${formatDate(a.start_time)}`;

  let d = pct(a.driving_pct), w = pct(a.other_work_pct), av = pct(a.availability_time_pct);
  let r, effektivLabel = "Kørsel";
  const hasSegmentData = d > 0 || w > 0 || av > 0;
  if (!hasSegmentData && a.pause_intervals && a.pause_intervals.length) {
    const totalMs = new Date(a.end_time) - new Date(a.start_time);
    let pauseMs = 0;
    for (const [ps, pe] of a.pause_intervals) {
      const s = Math.max(new Date(a.start_time).getTime(), new Date(ps).getTime());
      const e = Math.min(new Date(a.end_time).getTime(), new Date(pe).getTime());
      if (e > s) pauseMs += (e - s);
    }
    r = totalMs > 0 ? (pauseMs / totalMs) * 100 : 0;
    d = Math.max(0, 100 - r);
    effektivLabel = "Effektiv tid";
  } else {
    r = Math.max(0, 100 - d - w - av);
  }

  document.getElementById("modal-activity-body").innerHTML = `
    <div class="detail-grid">
      <div class="detail-item"><label>Vogn nr.</label><span>${a.vehicle_number || "–"}</span></div>
      <div class="detail-item"><label>KM start</label><span>${a.km_start != null ? a.km_start + " km" : "–"}</span></div>
      <div class="detail-item"><label>KM slut</label><span>${a.km_end != null ? a.km_end + " km" : "–"}</span></div>
      <div class="detail-item"><label>Salttillæg</label><span>${a.salt_supplement ? "Ja" : "Nej"}</span></div>
      <div class="detail-item"><label>Status</label><span class="badge badge-${a.status}">${statusLabel(a.status)}</span></div>
      <div class="detail-item"><label>Kort</label><span>${a.employee_number}</span></div>
      <div class="detail-item"><label>Type</label><span>${TYPE_LABELS[a.activity_type] || a.activity_type}</span></div>
      <div class="detail-item"><label>Start</label><span>${formatDateTime(a.start_time)}</span></div>
      <div class="detail-item"><label>Slut</label><span>${formatDateTime(a.end_time)}</span></div>
      <div class="detail-item"><label>Sum, effektiv tid</label><span>${formatDuration(a.duration_minutes)}</span></div>
      <div class="detail-item"><label>Oprettet af</label><span>${a.is_manual ? (a.created_by || "Manuelt") : "System"}</span></div>
      ${(a.auto_approval_flags && a.auto_approval_flags.length > 0) ? `<div class="auto-approval-flags"><strong>Afvigelser registreret (ikke auto-godkendt):</strong><ul>${a.auto_approval_flags.map(f => `<li>${h(f)}</li>`).join('')}</ul></div>` : ""}
      ${a.status === "approved" && a.approved_by ? `<div class="detail-item"><label>Godkendt af</label><span>${h(a.approved_by)}</span></div>` : ""}
      ${a.status === "deactivated" && (a.deactivated_by || a.approved_by) ? `<div class="detail-item"><label>Deaktiveret af</label><span>${h(a.deactivated_by || a.approved_by)}</span></div>` : ""}
    </div>

    <div class="form-row" style="margin-bottom:14px">
      <div class="form-group" style="min-width:0">
        <label>Ret starttid</label>
        <div class="dt-picker" id="edit-start"></div>
      </div>
      <div class="form-group" style="min-width:0">
        <label>Ret sluttid</label>
        <div class="dt-picker" id="edit-end"></div>
      </div>
    </div>
    <div class="form-group" style="margin-bottom:14px">
      <label>Vogn nr.</label>
      <select id="edit-vehicle">
        <option value="">– Ingen –</option>
        ${state.vehicles.slice().sort((va,vb) => va.vehicle_number.localeCompare(vb.vehicle_number,"da",{numeric:true})).map(v => `<option value="${v.vehicle_number}" ${a.vehicle_number === v.vehicle_number ? "selected" : ""}>${v.vehicle_number} (${v.registration_number})</option>`).join("")}
      </select>
    </div>
    <div class="form-row" style="margin-bottom:14px">
      <div class="form-group" style="min-width:0">
        <label>KM start</label>
        <input type="number" id="edit-km-start" min="0" value="${a.km_start != null ? a.km_start : ""}">
      </div>
      <div class="form-group" style="min-width:0">
        <label>KM slut</label>
        <input type="number" id="edit-km-end" min="0" value="${a.km_end != null ? a.km_end : ""}">
      </div>
    </div>
    <div class="form-group" style="margin-bottom:14px">
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
        <input type="checkbox" id="edit-salt" ${a.salt_supplement ? "checked" : ""} ${a.status !== "pending" ? "disabled" : ""} style="width:16px;height:16px;cursor:${a.status !== 'pending' ? 'not-allowed' : 'pointer'}">
        Salttillæg
      </label>
    </div>

    <div>
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light);margin-bottom:6px;display:block">Aktivitetsfordeling</label>
      <div class="pct-bar" style="height:16px">
        <div class="pct-driving" style="width:${d}%"></div>
        <div class="pct-work" style="width:${w}%"></div>
        <div class="pct-avail" style="width:${av}%"></div>
        <div class="pct-rest" style="width:${r}%"></div>
      </div>
      <div class="pct-legend">
        <div class="pct-legend-item"><span class="pct-dot" style="background:#2563eb"></span>${effektivLabel} ${fmtPct(d)}%</div>
        ${!hasSegmentData ? "" : `<div class="pct-legend-item"><span class="pct-dot" style="background:#059669"></span>Andet arbejde ${fmtPct(w)}%</div>
        <div class="pct-legend-item"><span class="pct-dot" style="background:#d97706"></span>Rådighedstid ${fmtPct(av)}%</div>`}
        <div class="pct-legend-item"><span class="pct-dot" style="background:#9ca3af"></span>Hvil/pause ${fmtPct(r)}%</div>
      </div>
    </div>

    ${renderSegmentTable(a)}
    ${(!a.segments || !a.segments.length) && (a.pause_intervals && a.pause_intervals.length) ? `
    <div class="form-group mt-16">
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light)">Pauser (fratrækkes i tidsrummet de afholdes)</label>
      <div style="font-size:13px;padding:8px;background:var(--bg);border-radius:4px">
        ${a.pause_intervals.map(p => `${formatTime(p[0])} – ${formatTime(p[1])}`).join(" · ")}
      </div>
    </div>` : ""}
    ${a.is_under_4h ? `<div class="alert-banner mt-16"><span class="icon">⚠️</span><div class="text"><h4>Under 4 timer</h4>Angiv begrundelse ved godkendelse (overenskomst: minimum 4 timer medmindre andet er aftalt).</div></div>` : ""}
    ${a.is_over_12h ? `<div class="alert-banner mt-16" style="background:#fef2f2;border-color:#fca5a5"><span class="icon">🔴</span><div class="text"><h4>Over 12 timer</h4>Usædvanlig lang aktivitet – kontroller om korrekt.</div></div>` : ""}
    ${a.comment ? `<div class="form-group mt-16"><label>Kommentar</label><div style="padding:8px;background:var(--bg);border-radius:4px;font-size:13px">${h(a.comment)}</div></div>` : ""}
  `;

  // Byg datetime-pickers efter innerHTML er sat
  buildDatetimePicker("edit-start", a.start_time.slice(0, 16));
  buildDatetimePicker("edit-end",   a.end_time.slice(0, 16));

  const footer = document.getElementById("modal-activity-footer");
  footer.innerHTML = "";
  // Fortryd-knapper
  if (a.is_edited) {
    footer.innerHTML += `<button class="btn btn-warning" onclick="undoEdit()" title="Gendan de oprindelige tider">↩ Fortryd tidsændring</button>`;
  }
  if (a.has_split_children || a.parent_activity_id) {
    footer.innerHTML += `<button class="btn btn-warning" onclick="undoSplit()" title="Slet delene og gendan den originale aktivitet">↩ Fortryd split</button>`;
  }
  footer.innerHTML += `<button class="btn btn-secondary" onclick="saveActivityTimes()">💾 Gem ændringer</button>`;
  if (a.status === "pending") {
    footer.innerHTML += `<button class="btn btn-warning" onclick="openSplitModal()">✂️ Split</button>`;
    footer.innerHTML += `<button class="btn btn-danger" onclick="modalDeactivate()">✗ Deaktiver</button>`;
    footer.innerHTML += `<button class="btn btn-success" onclick="openApproveModal()">✓ Godkend</button>`;
  } else {
    if (a.status === "deactivated") footer.innerHTML += `<button class="btn btn-warning" onclick="openSplitModal()">✂️ Split</button>`;
    footer.innerHTML += `<button class="btn btn-secondary" onclick="modalReopen()">↩ Genåbn</button>`;
  }
  footer.innerHTML += `<button class="btn btn-secondary" onclick="closeModal('modal-activity')">Luk</button>`;

  // Saks-knapper i hændelsestabellen
  document.querySelectorAll("#modal-activity-body .seg-split-btn").forEach(btn => {
    btn.addEventListener("click", () => splitAtSegment(btn.dataset.splitAt));
  });
  document.querySelectorAll("#modal-activity-body .seg-correct-btn").forEach(btn => {
    btn.addEventListener("click", () => correctSegment(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });
  document.querySelectorAll("#modal-activity-body .seg-revert-btn").forEach(btn => {
    btn.addEventListener("click", () => correctSegment(parseInt(btn.dataset.id), parseInt(btn.dataset.idx), true));
  });
  document.querySelectorAll("#modal-activity-body .seg-resize-btn").forEach(btn => {
    btn.addEventListener("click", () => openResizeSegment(parseInt(btn.dataset.id), parseInt(btn.dataset.idx)));
  });

  openModal("modal-activity");
  document.getElementById("modal-activity-body").scrollTop = 0;
}

const SEGMENT_LABELS = {
  rest: "Pause", availability: "Rådighed", work: "Andet arbejde", driving: "Kørsel",
};
const SEGMENT_ICONS = {
  rest: "☕", availability: "⏳", work: "📦", driving: "🚚",
};

function renderSegmentTable(a) {
  if (!a.segments || a.segments.length === 0) return "";
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

async function correctSegment(activityId, segIdx, revert = false) {
  try {
    const updated = await POST(`/api/activities/${activityId}/correct-segment`, { segment_index: segIdx, revert });
    state.activities = state.activities.map(a => a.id === updated.id ? updated : a);
    const body = document.getElementById("modal-activity-body");
    const scrollTop = body ? body.scrollTop : 0;
    openActivityDetail(activityId);
    if (body) body.scrollTop = scrollTop;
    renderActivitiesTable();
    toast(revert ? "Segment gendannet" : "Linje rettet til 'Andet arbejde'", "success");
  } catch (e) { toast(e.message, "error"); }
}

function openResizeSegment(activityId, segIdx) {
  const a = state.activities.find(x => x.id === activityId);
  if (!a) return;
  const seg = a.segments[segIdx];
  if (!seg) return;

  _resizeSegState = {
    activityId,
    segIdx,
    segStart: seg[0],
    segEnd: seg[1],
    nextSeg: a.segments[segIdx + 1] || null,
  };

  const segLabel = SEGMENT_LABELS[seg[2]] || seg[2];
  const next = _resizeSegState.nextSeg;
  const nextInfo = next
    ? `Næste: ${SEGMENT_LABELS[next[2]] || next[2]} (${next[0].slice(11, 16)}–${next[1].slice(11, 16)})`
    : "Ingen næste segment";
  document.getElementById("resize-seg-info").innerHTML =
    `<strong>${segLabel}</strong> &nbsp; ${_resizeSegState.segStart.slice(11, 16)}–${_resizeSegState.segEnd.slice(11, 16)}<br>` +
    `<span style="color:var(--text-light);font-size:12px">${nextInfo}</span>`;

  buildDatetimePicker("resize-seg-end", seg[1].slice(0, 16));
  _stackDatetimePicker("resize-seg-end");
  document.getElementById("resize-seg-preview").innerHTML = "";

  document.getElementById("resize-seg-end").querySelectorAll("input").forEach(inp => {
    inp.addEventListener("input", updateResizePreview);
    inp.addEventListener("change", updateResizePreview);
  });

  openModal("modal-resize-segment");
}

function updateResizePreview() {
  if (!_resizeSegState) return;
  const preview = document.getElementById("resize-seg-preview");
  const newEndIso = readDatetimePicker("resize-seg-end");
  if (!newEndIso) { preview.innerHTML = ""; return; }

  const newEnd = newEndIso + ":00";
  const { segStart, segEnd, nextSeg } = _resizeSegState;

  if (newEnd <= segStart) {
    preview.style.color = "var(--danger)";
    preview.textContent = `Sluttid skal være efter starttid (${segStart.slice(11, 16)})`;
    return;
  }
  if (newEnd === segEnd) {
    preview.style.color = "var(--text-light)";
    preview.textContent = "Ingen ændring";
    return;
  }

  const diffMs = new Date(newEnd) - new Date(segEnd);
  const absDiffMin = Math.round(Math.abs(diffMs) / 60000);

  if (diffMs < 0) {
    preview.style.color = "var(--primary)";
    preview.textContent =
      `Pausen forkortes med ${absDiffMin} min. ` +
      `De resterende ${absDiffMin} min tilføjes som 'Andet arbejde' (${newEnd.slice(11, 16)}–${segEnd.slice(11, 16)}).`;
  } else {
    if (!nextSeg) {
      preview.style.color = "var(--danger)";
      preview.textContent = "Der er intet næste segment – pausen kan ikke forlænges.";
      return;
    }
    const nextEnd = nextSeg[1];
    if (newEnd >= nextEnd) {
      preview.style.color = "var(--danger)";
      preview.textContent =
        `Ny sluttid (${newEnd.slice(11, 16)}) overstiger næste segments sluttid (${nextEnd.slice(11, 16)}).`;
      return;
    }
    preview.style.color = "";
    const nextLabel = SEGMENT_LABELS[nextSeg[2]] || nextSeg[2];
    preview.textContent =
      `Pausen forlænges med ${absDiffMin} min. ` +
      `Næste segment (${nextLabel}) forkortes: ${nextSeg[0].slice(11, 16)}–${nextSeg[1].slice(11, 16)} → ${newEnd.slice(11, 16)}–${nextEnd.slice(11, 16)}.`;
  }
}

async function confirmResizeSegment() {
  if (!_resizeSegState) return;
  const newEndIso = readDatetimePicker("resize-seg-end");
  if (!newEndIso) { toast("Angiv ny sluttid", "error"); return; }

  const newEnd = newEndIso + ":00";
  const { activityId, segIdx, segStart, segEnd } = _resizeSegState;
  if (newEnd <= segStart) { toast("Sluttid skal være efter starttid", "error"); return; }
  if (newEnd === segEnd) { toast("Ingen ændring", "error"); return; }

  try {
    const updated = await POST(`/api/activities/${activityId}/resize-segment`, {
      segment_index: segIdx,
      new_end_iso: newEndIso,
    });
    state.activities = state.activities.map(a => a.id === updated.id ? updated : a);
    closeModal("modal-resize-segment");
    const body = document.getElementById("modal-activity-body");
    const scrollTop = body ? body.scrollTop : 0;
    openActivityDetail(activityId);
    if (body) body.scrollTop = scrollTop;
    renderActivitiesTable();
    toast("Pauselængde tilpasset", "success");
  } catch (e) { toast(e.message, "error"); }
}

function splitAtSegment(isoTime) {
  openSplitModal();
  setDatetimePicker("split-at", isoTime.slice(0, 16));
}

async function undoEdit() {
  if (!confirm("Fortryd tidsændringer og gendan de oprindelige tider?")) return;
  try {
    const updated = await POST(`/api/activities/${state.selectedActivityId}/undo-edit`);
    toast("Tidsændringer fortrudt – originale tider gendannet", "success");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}

async function undoSplit() {
  if (!confirm("Fortryd split? Delene slettes, og den originale aktivitet gendannes som afventende.")) return;
  try {
    await POST(`/api/activities/${state.selectedActivityId}/undo-split`);
    toast("Split fortrudt – original aktivitet gendannet", "success");
    closeAllModals();
    await refreshActivities();
  } catch (e) { toast(e.message, "error"); }
}

async function saveActivityTimes() {
  const start = readDatetimePicker("edit-start");
  const end   = readDatetimePicker("edit-end");
  if (!start || !end) { toast("Angiv start- og sluttid", "error"); return; }
  if (new Date(end) <= new Date(start)) { toast("Sluttid skal være efter starttid", "error"); return; }
  const vehicleNum = document.getElementById("edit-vehicle")?.value || null;
  const kmStartVal = document.getElementById("edit-km-start")?.value;
  const kmEndVal   = document.getElementById("edit-km-end")?.value;
  const saltVal    = document.getElementById("edit-salt")?.checked ?? false;
  try {
    const updated = await PATCH(`/api/activities/${state.selectedActivityId}`, {
      start_time: start + ":00",
      end_time: end + ":00",
      vehicle_number: vehicleNum || null,
      km_start: kmStartVal !== "" && kmStartVal != null ? parseInt(kmStartVal) : null,
      km_end:   kmEndVal   !== "" && kmEndVal   != null ? parseInt(kmEndVal)   : null,
      salt_supplement: saltVal,
    });
    toast("Ændringer gemt", "success");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}

function openApproveModal() {
  const a = state.activities.find(x => x.id === state.selectedActivityId);
  if (!a) return;
  document.getElementById("approve-comment").value = "";
  document.getElementById("approve-comment-required").classList.toggle("hidden", !a.is_under_4h);
  const lbl = document.getElementById("approve-user-label");
  if (lbl) lbl.textContent = state.currentUser ? `Godkendes af: ${state.currentUser.name} (${state.currentUser.initials})` : "";
  openModal("modal-approve");
}

async function confirmApprove() {
  const comment = document.getElementById("approve-comment").value.trim();
  const a = state.activities.find(x => x.id === state.selectedActivityId);
  if (a?.is_under_4h && !comment) { toast("Angiv begrundelse for aktivitet under 4 timer", "error"); return; }

  try {
    // Gem vognnummer, km og salttillæg inden godkendelse
    const vehicleNum = document.getElementById("edit-vehicle")?.value;
    const kmStartVal = document.getElementById("edit-km-start")?.value;
    const kmEndVal   = document.getElementById("edit-km-end")?.value;
    const saltVal    = document.getElementById("edit-salt")?.checked ?? false;
    if (vehicleNum !== undefined) {
      await PATCH(`/api/activities/${state.selectedActivityId}`, {
        vehicle_number: vehicleNum || null,
        km_start: kmStartVal !== "" && kmStartVal != null ? parseInt(kmStartVal) : null,
        km_end:   kmEndVal   !== "" && kmEndVal   != null ? parseInt(kmEndVal)   : null,
        salt_supplement: saltVal,
      });
    }
    const updated = await POST(`/api/activities/${state.selectedActivityId}/approve`,
      { comment: comment || null });
    toast("Aktivitet godkendt", "success");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}

async function modalDeactivate() {
  openDeactivateModal();
}

function openDeactivateModal() {
  document.getElementById("deactivate-comment").value = "";
  const lbl = document.getElementById("deactivate-user-label");
  if (lbl) lbl.textContent = state.currentUser ? `Deaktiveres af: ${state.currentUser.name} (${state.currentUser.initials})` : "";
  openModal("modal-deactivate");
}

async function confirmDeactivate() {
  const comment = document.getElementById("deactivate-comment").value.trim();
  try {
    const updated = await POST(`/api/activities/${state.selectedActivityId}/deactivate`,
      { comment: comment || null });
    toast("Aktivitet deaktiveret");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}
async function modalReopen() {
  try {
    const updated = await POST(`/api/activities/${state.selectedActivityId}/reopen`);
    toast("Aktivitet genåbnet");
    closeAllModals();
    applyActivityLocally(updated);
    refreshActivities().catch(() => {});
  } catch (e) { toast(e.message, "error"); }
}

// ── Split modal ────────────────────────────────────────────────────────────
function openSplitModal() {
  const a = state.activities.find(x => x.id === state.selectedActivityId);
  if (!a) return;
  document.getElementById("split-activity-info").textContent =
    `${a.employee_name}: ${formatDateTime(a.start_time)} – ${formatDateTime(a.end_time)}`;
  const midMs = (new Date(a.start_time).getTime() + new Date(a.end_time).getTime()) / 2;
  const mid = new Date(midMs);
  const midIso = mid.getFullYear() + "-" +
    String(mid.getMonth()+1).padStart(2,"0") + "-" +
    String(mid.getDate()).padStart(2,"0") + "T" +
    String(mid.getHours()).padStart(2,"0") + ":" +
    String(mid.getMinutes()).padStart(2,"0");
  buildDatetimePicker("split-at", midIso);
  state.splitMin = a.start_time.slice(0, 16);
  state.splitMax = a.end_time.slice(0, 16);
  openModal("modal-split");
}

async function confirmSplit() {
  const splitAt = readDatetimePicker("split-at");
  if (!splitAt) { toast("Angiv splitpunkt", "error"); return; }
  if (splitAt <= state.splitMin || splitAt >= state.splitMax) {
    toast("Splitpunktet skal ligge mellem start- og sluttid", "error"); return;
  }
  try {
    await POST(`/api/activities/${state.selectedActivityId}/split`, { split_at: splitAt + ":00" });
    toast("Aktivitet splittet", "success");
    closeAllModals();
    await refreshActivities();
  } catch (e) { toast(e.message, "error"); }
}

// ── Datetime picker helpers ────────────────────────────────────────────────
function _dtOptions(max) {
  return Array.from({length: max}, (_, i) => {
    const v = String(i).padStart(2, "0");
    return `<option value="${v}">${v}</option>`;
  }).join("");
}

function _stackDatetimePicker(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const dateEl = el.querySelector(".dt-date");
  const hourEl = el.querySelector(".dt-hour");
  const sepEl  = el.querySelector(".dt-sep");
  const minEl  = el.querySelector(".dt-min");
  if (!dateEl || !hourEl || !sepEl || !minEl) return;
  el.style.cssText = "display:flex;flex-direction:column;gap:6px;";
  dateEl.style.width = "100%";
  const timeRow = document.createElement("div");
  timeRow.style.cssText = "display:flex;align-items:center;gap:6px;";
  timeRow.append(hourEl, sepEl, minEl);
  el.append(timeRow);
}

function buildDatetimePicker(id, isoValue) {
  const el = document.getElementById(id);
  if (!el) return;
  const date = isoValue ? isoValue.slice(0, 10) : "";
  const hh   = isoValue ? isoValue.slice(11, 13) : "06";
  const mm   = isoValue ? isoValue.slice(14, 16) : "00";
  const S = "padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;background:var(--surface);color:var(--text);box-sizing:border-box;";
  const N = `${S}width:62px;flex:0 0 62px;text-align:center;`;
  el.style.cssText = "display:flex;align-items:center;gap:6px;flex-wrap:nowrap;";
  el.innerHTML = `
    <input type="date"   class="dt-date" value="${date}" style="${S}flex:1 1 0;min-width:0;">
    <input type="text" inputmode="numeric" class="dt-hour" maxlength="2" value="${hh}" style="${N}" placeholder="tt">
    <span  class="dt-sep" style="font-weight:600;color:var(--text-light);flex-shrink:0;">:</span>
    <input type="text" inputmode="numeric" class="dt-min"  maxlength="2" value="${mm}" style="${N}" placeholder="mm">
  `;
}

function readDatetimePicker(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const date = el.querySelector(".dt-date")?.value;
  const hRaw = el.querySelector(".dt-hour")?.value;
  const mRaw = el.querySelector(".dt-min")?.value;
  const hh = String(Math.min(23, Math.max(0, parseInt(hRaw, 10) || 0))).padStart(2, "0");
  const mm = String(Math.min(59, Math.max(0, parseInt(mRaw, 10) || 0))).padStart(2, "0");
  return date ? `${date}T${hh}:${mm}` : null;
}

function setDatetimePicker(id, isoValue) {
  const el = document.getElementById(id);
  if (!el || !isoValue) return;
  el.querySelector(".dt-date").value  = isoValue.slice(0, 10);
  el.querySelector(".dt-hour").value  = isoValue.slice(11, 13);
  el.querySelector(".dt-min").value   = isoValue.slice(14, 16);
}

// ── Date picker (årstal-dropdown + kalender) ───────────────────────────────
const _DP_MONTHS = ["Januar","Februar","Marts","April","Maj","Juni",
                    "Juli","August","September","Oktober","November","December"];
const _DP_DAYS   = ["Ma","Ti","On","To","Fr","Lø","Sø"];

function buildDatePicker(containerId, initialValue) {
  const wrap = document.getElementById(containerId);
  if (!wrap) return;

  const iso = initialValue || "";
  let selY = null, selM = null, selD = null;
  if (iso.length >= 10) {
    selY = parseInt(iso.slice(0, 4), 10);
    selM = parseInt(iso.slice(5, 7), 10) - 1;
    selD = parseInt(iso.slice(8, 10), 10);
  }
  const today  = new Date();
  const viewY  = (selY && selY <= 2100) ? selY : today.getFullYear();
  const viewM  = (selM !== null && selY && selY <= 2100) ? selM : today.getMonth();

  const yearOpts = Array.from({length: 151}, (_, i) => 1950 + i).map(y =>
    `<option value="${y}"${y === viewY ? " selected" : ""}>${y}</option>`).join("");
  const monthOpts = _DP_MONTHS.map((m, i) =>
    `<option value="${i}"${i === viewM ? " selected" : ""}>${m}</option>`).join("");

  let displayVal = "";
  if (iso === "9999-12-31") displayVal = "31-12-9999";
  else if (iso.length >= 10)
    displayVal = `${iso.slice(8,10)}-${iso.slice(5,7)}-${iso.slice(0,4)}`;

  const S = "padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;background:var(--surface);color:var(--text);";
  const BTN = "border:none;background:var(--bg);border-radius:4px;padding:4px 9px;cursor:pointer;font-size:13px;color:var(--text);";

  wrap.style.cssText = "position:relative;display:block;";
  wrap.innerHTML = `
    <input type="text" class="dp-display" readonly placeholder="Vælg dato"
      value="${displayVal}"
      style="${S}width:100%;box-sizing:border-box;cursor:pointer;">
    <input type="hidden" class="dp-val" value="${iso}">
    <div class="dp-popup" style="display:none;position:fixed;z-index:10000;
      background:white;border:1px solid var(--border);border-radius:8px;
      box-shadow:0 6px 24px rgba(0,0,0,0.18);padding:12px;width:264px;">
      <div style="display:flex;align-items:center;gap:4px;margin-bottom:10px;">
        <button type="button" class="dp-prev" style="${BTN}">&#9664;</button>
        <select class="dp-month-sel" style="${S}flex:1;padding:4px 6px;">${monthOpts}</select>
        <select class="dp-year-sel"  style="${S}flex:0 0 72px;padding:4px 6px;">${yearOpts}</select>
        <button type="button" class="dp-next" style="${BTN}">&#9654;</button>
      </div>
      <div class="dp-grid"></div>
    </div>`;

  _dpRenderGrid(wrap, viewY, viewM, selY, selM, selD);
  _dpBindEvents(wrap);
}

function _dpRenderGrid(wrap, viewY, viewM, selY, selM, selD) {
  const grid  = wrap.querySelector(".dp-grid");
  const today = new Date(); today.setHours(0,0,0,0);
  let html = `<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:1px;text-align:center;">`;
  _DP_DAYS.forEach(d => {
    html += `<div style="font-size:11px;color:#888;font-weight:600;padding:3px 0;">${d}</div>`;
  });
  const firstDay = new Date(viewY, viewM, 1).getDay();
  const offset   = firstDay === 0 ? 6 : firstDay - 1;
  for (let i = 0; i < offset; i++) html += `<div></div>`;
  const dim = new Date(viewY, viewM + 1, 0).getDate();
  for (let d = 1; d <= dim; d++) {
    const dt  = new Date(viewY, viewM, d);
    const iso = `${viewY}-${String(viewM+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const isSel  = (selY===viewY && selM===viewM && selD===d);
    const isTod  = (dt.getTime()===today.getTime());
    const isWEnd = (dt.getDay()===0 || dt.getDay()===6);
    let bg = "transparent", fg = isWEnd ? "#999" : "var(--text)", fw = "normal";
    if (isTod && !isSel) { bg="#EBF4FF"; fg="#1a6fbf"; }
    if (isSel)           { bg="#1a6fbf"; fg="white"; fw="600"; }
    html += `<button type="button" data-iso="${iso}"
      style="border:none;background:${bg};color:${fg};font-weight:${fw};
        border-radius:4px;padding:5px 0;cursor:pointer;font-size:13px;width:100%;">${d}</button>`;
  }
  html += `</div>`;
  grid.innerHTML = html;
}

function _dpBindEvents(wrap) {
  const display  = wrap.querySelector(".dp-display");
  const popup    = wrap.querySelector(".dp-popup");
  const valInput = wrap.querySelector(".dp-val");
  const yearSel  = wrap.querySelector(".dp-year-sel");
  const monthSel = wrap.querySelector(".dp-month-sel");

  function selParts() {
    const v = valInput.value;
    if (!v || v.length < 10) return [null, null, null];
    return [parseInt(v.slice(0,4),10), parseInt(v.slice(5,7),10)-1, parseInt(v.slice(8,10),10)];
  }
  function rerender() {
    const [sy,sm,sd] = selParts();
    _dpRenderGrid(wrap, parseInt(yearSel.value,10), parseInt(monthSel.value,10), sy, sm, sd);
  }

  display.addEventListener("click", e => {
    e.stopPropagation();
    const isOpen = popup.style.display !== "none";
    document.querySelectorAll(".dp-popup").forEach(p => p.style.display = "none");
    if (!isOpen) {
      const rect = wrap.getBoundingClientRect();
      const popW = 264;
      let left = rect.left;
      if (left + popW > window.innerWidth - 8) left = window.innerWidth - popW - 8;
      popup.style.left = left + "px";
      popup.style.top   = "-9999px";
      popup.style.display = "block";
      const popH = popup.offsetHeight;
      const fitsBelow = rect.bottom + 4 + popH <= window.innerHeight - 8;
      const top = fitsBelow
        ? rect.bottom + 4
        : Math.max(8, rect.top - popH - 4);
      popup.style.top = top + "px";
    }
  });

  popup.addEventListener("click",  e => e.stopPropagation());
  yearSel.addEventListener("change",  rerender);
  monthSel.addEventListener("change", rerender);

  wrap.querySelector(".dp-prev").addEventListener("click", e => {
    e.stopPropagation();
    let m = parseInt(monthSel.value,10)-1, y = parseInt(yearSel.value,10);
    if (m < 0) { m=11; y--; }
    monthSel.value=m; yearSel.value=y; rerender();
  });
  wrap.querySelector(".dp-next").addEventListener("click", e => {
    e.stopPropagation();
    let m = parseInt(monthSel.value,10)+1, y = parseInt(yearSel.value,10);
    if (m>11) { m=0; y++; }
    monthSel.value=m; yearSel.value=y; rerender();
  });

  wrap.querySelector(".dp-grid").addEventListener("click", e => {
    const btn = e.target.closest("button[data-iso]");
    if (!btn) return;
    const iso = btn.dataset.iso;
    valInput.value = iso;
    const [y,m,d] = [parseInt(iso.slice(0,4),10), parseInt(iso.slice(5,7),10)-1, parseInt(iso.slice(8,10),10)];
    display.value = `${String(d).padStart(2,"0")}-${String(m+1).padStart(2,"0")}-${y}`;
    popup.style.display = "none";
    rerender();
    valInput.dispatchEvent(new Event("change"));
  });
}

document.addEventListener("click", () =>
  document.querySelectorAll(".dp-popup").forEach(p => p.style.display = "none"));

function readDatePicker(id) {
  return document.getElementById(id)?.querySelector(".dp-val")?.value || "";
}

function setDatePicker(id, iso) {
  const wrap = document.getElementById(id);
  if (!wrap) return;
  const valInput = wrap.querySelector(".dp-val");
  const display  = wrap.querySelector(".dp-display");
  if (!valInput || !display) return;
  valInput.value = iso || "";
  if (!iso || iso.length < 10) { display.value = ""; return; }
  if (iso === "9999-12-31") { display.value = "31-12-9999"; return; }
  display.value = `${iso.slice(8,10)}-${iso.slice(5,7)}-${iso.slice(0,4)}`;
  const y = parseInt(iso.slice(0,4),10);
  const m = parseInt(iso.slice(5,7),10)-1;
  const d = parseInt(iso.slice(8,10),10);
  const yearSel  = wrap.querySelector(".dp-year-sel");
  const monthSel = wrap.querySelector(".dp-month-sel");
  if (yearSel && y <= 2100) { yearSel.value = y; monthSel.value = m; _dpRenderGrid(wrap, y, m, y, m, d); }
}

// ── Manual activity ────────────────────────────────────────────────────────
function badgeLabel(label) {
  const s = label.toUpperCase();
  if (s.length <= 9) return s;
  return s.slice(0, 7).replace(/[\s.\-]+$/, '') + '..';
}

async function loadAbsenceTypes() {
  try {
    const types = await GET("/api/activities/absence-types");
    state.absenceTypes = types;
    ABSENCE_TYPES.clear();
    const sel = document.getElementById("manual-type");
    sel.innerHTML = "";
    const allTypes = [{ value: "normal", label: "Normal tid" }, { value: "overnatning", label: "Overnatning" }, ...types];
    allTypes.sort((a, b) => a.label.localeCompare(b.label, "da")).forEach(t => {
      TYPE_LABELS[t.value] = t.label;
      if (t.value !== "normal") {
        ABSENCE_LABELS[t.value] = badgeLabel(t.label);
        ABSENCE_TYPES.add(t.value);
      }
      const opt = document.createElement("option");
      opt.value = t.value;
      opt.textContent = t.label;
      sel.appendChild(opt);
    });
  } catch (e) { console.error("loadAbsenceTypes fejlede:", e); }
}

function isoWeekNumber(d) {
  const jan4 = new Date(d.getFullYear(), 0, 4);
  const startOfWeek1 = new Date(jan4);
  startOfWeek1.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
  const diff = d - startOfWeek1;
  return Math.floor(diff / 604800000) + 1;
}

function updateManualTypeVisibility() {
  const type = document.getElementById("manual-type").value;
  const isFerie        = (type === "ferie" || type === "selvbetalt_fridag");
  const isSygdom       = (type === "sygdom" || type === "barn_1sygedag" || type === "paragraf_56_syg" || type === "graviditetsbetinget_sygdom" || type === "skole_kursus");
  const isAfspadsering = (type === "afspadsering");
  const isFeriefri     = (type === "feriefri");
  const isBarsel       = (type === "barsel");
  const isOvernatning  = (type === "overnatning");
  const isDateOnly     = isFerie || isSygdom || isFeriefri || isBarsel || isOvernatning;
  const isAbsence      = ABSENCE_TYPES.has(type);
  const isRangeType    = type === "ferie" || isFeriefri || isBarsel || type === "paragraf_56_syg" || type === "graviditetsbetinget_sygdom";

  document.getElementById("manual-normal-fields").style.display = isAbsence ? "none" : "";
  document.getElementById("manual-end-group").style.display     = isDateOnly ? "none" : "";
  document.getElementById("manual-barsel-group").style.display  = isBarsel ? "" : "none";

  // Skjul/vis tidsfelterne i startpickeren (kun dato for ferie og sygdom)
  const startEl = document.getElementById("manual-start");
  if (startEl) {
    [".dt-hour", ".dt-sep", ".dt-min"].forEach(sel => {
      const el = startEl.querySelector(sel);
      if (el) el.style.display = isDateOnly ? "none" : "";
    });
    startEl.style.maxWidth = isDateOnly ? "220px" : "";
  }

  // Skift label Starttid ↔ Fra dato / Dato
  const lbl = document.querySelector("#manual-start-group label");
  if (lbl) lbl.innerHTML = isRangeType
    ? `Fra dato <span style="color:var(--danger)">*</span>`
    : isDateOnly
      ? `Dato <span style="color:var(--danger)">*</span>`
      : `Starttid <span style="color:var(--danger)">*</span>`;

  if (isAbsence) {
    ["manual-loading", "manual-unloading", "manual-km-start", "manual-km-end", "manual-reg"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("manual-reg-hint").textContent = "";
    document.getElementById("manual-salt").checked = false;
  }
  document.getElementById("manual-til-dato-group").style.display = isRangeType ? "" : "none";
  if (!isRangeType) document.getElementById("manual-til-dato").value = "";
  const pauseSection = document.getElementById("manual-pause-section");
  if (pauseSection) pauseSection.style.display = isDateOnly ? "none" : "";

  if (isFerie)        applyFerieDefaults();
  if (isSygdom)       applySygdomDefaults();
  if (isAfspadsering) applyAfspadseringDefaults();
  if (isFeriefri)     applyFeriefriDefaults();
  if (isBarsel)       applySygdomDefaults();
}

function applyFerieDefaults() {
  const empId = parseInt(document.getElementById("manual-employee").value);
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!empId || !dateStr) return;

  const emp = state.employees.find(e => e.id === empId);
  if (!emp || !emp.work_schedule) return;

  const d = new Date(dateStr + "T12:00:00");
  const weekNum = isoWeekNumber(d);
  const key = weekNum % 2 === 0 ? "even" : "odd";
  const weekdayIdx = (d.getDay() + 6) % 7;
  const hours = emp.work_schedule[key]?.[weekdayIdx] ?? 0;

  // Fallback til 7,4 timer hvis ingen normaltid på dagen
  const effectiveHours = hours > 0 ? hours : 7.4;
  const totalMinutes = Math.round(effectiveHours * 60);
  const endH = 6 + Math.floor(totalMinutes / 60);
  const endM = totalMinutes % 60;
  const endHH = String(endH).padStart(2, "0") + ":" + String(endM).padStart(2, "0");

  setDatetimePicker("manual-start", dateStr + "T06:00");
  setDatetimePicker("manual-end",   dateStr + "T" + endHH);
}

function applySygdomDefaults() {
  const empId = parseInt(document.getElementById("manual-employee").value);
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!empId || !dateStr) return;

  const emp = state.employees.find(e => e.id === empId);
  if (!emp || !emp.work_schedule) return;

  const d = new Date(dateStr + "T12:00:00");
  const weekNum = isoWeekNumber(d);
  const key = weekNum % 2 === 0 ? "even" : "odd";
  const weekdayIdx = (d.getDay() + 6) % 7;
  const hours = emp.work_schedule[key]?.[weekdayIdx] ?? 0;

  const effectiveHours = hours > 0 ? hours : 7.4;
  const totalMinutes = Math.round(effectiveHours * 60);
  const endH = 6 + Math.floor(totalMinutes / 60);
  const endM = totalMinutes % 60;
  const endHH = String(endH).padStart(2, "0") + ":" + String(endM).padStart(2, "0");

  setDatetimePicker("manual-start", dateStr + "T06:00");
  setDatetimePicker("manual-end",   dateStr + "T" + endHH);
}

function applyAfspadseringDefaults() {
  const empId = parseInt(document.getElementById("manual-employee").value);
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!empId || !dateStr) return;

  const emp = state.employees.find(e => e.id === empId);
  if (!emp || !emp.work_schedule) return;

  const d = new Date(dateStr + "T12:00:00");
  const weekNum = isoWeekNumber(d);
  const key = weekNum % 2 === 0 ? "even" : "odd";
  const weekdayIdx = (d.getDay() + 6) % 7;
  const hours = emp.work_schedule[key]?.[weekdayIdx] ?? 0;

  // Fallback til 7,4 timer hvis ingen normaltid på dagen
  const effectiveHours = hours > 0 ? hours : 7.4;
  const totalMinutes = Math.round(effectiveHours * 60);
  const endH = 6 + Math.floor(totalMinutes / 60);
  const endM = totalMinutes % 60;
  const endHH = String(endH).padStart(2, "0") + ":" + String(endM).padStart(2, "0");

  setDatetimePicker("manual-start", dateStr + "T06:00");
  setDatetimePicker("manual-end",   dateStr + "T" + endHH);
}

function applyFeriefriDefaults() {
  const dateStr = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
  if (!dateStr) return;
  // Altid 7,4 timer fra 06:00 – uanset medarbejderens normale tid
  const totalEndMin = 6 * 60 + Math.round(7.4 * 60);  // 06:00 + 7h24m = 13:24
  const endH = String(Math.floor(totalEndMin / 60)).padStart(2, "0");
  const endM = String(totalEndMin % 60).padStart(2, "0");
  setDatetimePicker("manual-start", dateStr + "T06:00");
  setDatetimePicker("manual-end",   dateStr + "T" + endH + ":" + endM);
}

function renderManualPauses() {
  const list = document.getElementById("manual-pauses-list");
  if (!list) return;
  if (!manualPauses.length) { list.innerHTML = ""; return; }
  list.innerHTML = manualPauses.map((p, i) => `
    <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg);border-radius:4px;margin-bottom:4px;font-size:13px">
      <span style="font-weight:600;min-width:56px;color:var(--primary)">Pause ${i + 1}</span>
      <span>${p[0].slice(8,10)}.${p[0].slice(5,7)} ${p[0].slice(11,16)} – ${p[1].slice(8,10)}.${p[1].slice(5,7)} ${p[1].slice(11,16)}</span>
      <button type="button" onclick="deleteManualPause(${i})" style="margin-left:auto;background:none;border:none;color:var(--danger);cursor:pointer;font-size:18px;line-height:1;padding:0">&times;</button>
    </div>
  `).join("");
}

function addManualPause() {
  const startIso = readDatetimePicker("manual-start");
  if (!startIso) { toast("Angiv starttidspunkt for aktiviteten først", "error"); return; }
  const n = manualPauses.length + 1;
  document.getElementById("pause-modal-title").textContent = "Pause " + n;
  const dateStr = startIso.slice(0, 10);
  buildDatetimePicker("pause-start", dateStr + "T00:00");
  buildDatetimePicker("pause-end",   dateStr + "T00:00");
  _stackDatetimePicker("pause-start");
  _stackDatetimePicker("pause-end");
  openModal("modal-pause");
}

function confirmPause() {
  const startIso = readDatetimePicker("pause-start");
  const endIso   = readDatetimePicker("pause-end");
  if (!startIso || !endIso) { toast("Angiv både start- og sluttidspunkt for pausen", "error"); return; }
  if (endIso <= startIso) { toast("Sluttidspunkt skal være efter starttidspunkt", "error"); return; }
  manualPauses.push([startIso + ":00", endIso + ":00"]);
  renderManualPauses();
  closeModal("modal-pause");
}

function deleteManualPause(idx) {
  manualPauses.splice(idx, 1);
  renderManualPauses();
}

function openManualActivityModal(empId = null, dateIso = null) {
  document.getElementById("manual-employee").innerHTML =
    state.employees.filter(e => e.active)
      .slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  buildDatetimePicker("manual-start", null);
  buildDatetimePicker("manual-end",   null);
  ["manual-loading", "manual-unloading", "manual-comment", "manual-km-start", "manual-km-end"]
    .forEach(id => document.getElementById(id).value = "");
  document.getElementById("manual-reg").value = "";
  document.getElementById("manual-reg-hint").textContent = "";
  document.getElementById("manual-salt").checked = false;
  document.getElementById("manual-reg").oninput = function () {
    const reg = this.value.trim().toUpperCase();
    this.value = reg;
    const hint = document.getElementById("manual-reg-hint");
    if (!reg) { hint.textContent = ""; return; }
    const v = state.vehicles.find(x =>
      x.registration_number.toUpperCase() === reg ||
      x.vehicle_number.toUpperCase() === reg
    );
    if (v) {
      hint.textContent = `Vogn nr. ${v.vehicle_number} – reg. ${v.registration_number} fundet`;
      hint.style.color = "var(--success, #059669)";
    } else {
      hint.textContent = "Registreringsnummer/vognnummer ikke fundet i Vognpark";
      hint.style.color = "var(--danger, #dc2626)";
    }
  };
  document.getElementById("manual-type").value = "normal";
  document.getElementById("manual-terminsdato").value = "";
  document.getElementById("manual-til-dato").value = "";
  manualPauses = [];
  renderManualPauses();
  updateManualTypeVisibility();

  document.getElementById("manual-type").onchange = updateManualTypeVisibility;
  document.getElementById("manual-employee").onchange = () => {
    const t = document.getElementById("manual-type").value;
    if (t === "ferie" || t === "selvbetalt_fridag") applyFerieDefaults();
    if (t === "sygdom" || t === "barn_1sygedag" || t === "paragraf_56_syg" || t === "barsel") applySygdomDefaults();
    if (t === "afspadsering")                       applyAfspadseringDefaults();
    if (t === "feriefri")                           applyFeriefriDefaults();
  };
  // Lyt på dato-ændring inde i dt-picker containeren
  document.getElementById("manual-start").addEventListener("change", () => {
    const t = document.getElementById("manual-type").value;
    if (t === "ferie" || t === "selvbetalt_fridag") applyFerieDefaults();
    if (t === "sygdom" || t === "barn_1sygedag" || t === "paragraf_56_syg" || t === "barsel") applySygdomDefaults();
    if (t === "afspadsering")                       applyAfspadseringDefaults();
    if (t === "feriefri")                           applyFeriefriDefaults();
    if (t === "normal") {
      const startDate = document.getElementById("manual-start")?.querySelector(".dt-date")?.value;
      const endDateEl = document.getElementById("manual-end")?.querySelector(".dt-date");
      if (startDate && endDateEl) endDateEl.value = startDate;
    }
  });

  if (empId) document.getElementById("manual-employee").value = empId;
  if (dateIso) {
    setDatetimePicker("manual-start", dateIso + "T06:00");
    setDatetimePicker("manual-end",   dateIso + "T06:00");
  }
  openModal("modal-manual-activity");
}

function confirmAbsenceConflict() {
  _absenceConflictConfirmed = true;
  closeModal("modal-absence-conflict");
  confirmManualActivity();
}

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

async function confirmManualActivity() {
  const start   = readDatetimePicker("manual-start");
  const end     = readDatetimePicker("manual-end");
  const actType = document.getElementById("manual-type").value;
  const tilDato = document.getElementById("manual-til-dato").value;
  const empId   = parseInt(document.getElementById("manual-employee").value);

  if (actType === "overnatning") {
    if (!start) { toast("Angiv dato for overnatningen", "error"); return; }
    const dateStr = start.slice(0, 10);
    const timeStr = dateStr + "T00:00:00";
    try {
      await POST("/api/activities", {
        employee_id: empId,
        activity_type: "overnatning",
        start_time: timeStr,
        end_time:   timeStr,
      });
      toast("Overnatning oprettet", "success");
      closeModal("modal-manual-activity");
      await refreshActivities();
    } catch (e) { toast(e.message, "error"); }
    return;
  }

  const _RANGE_TYPES = ["ferie", "feriefri", "barsel", "paragraf_56_syg", "graviditetsbetinget_sygdom"];
  const isRange = _RANGE_TYPES.includes(actType) && !!tilDato;

  if (!start || (!isRange && !end)) {
    const msg = (actType === "ferie" || actType === "selvbetalt_fridag" || actType === "feriefri" || actType === "barsel") ? "Angiv dato for fraværsdagen"
              : (actType === "sygdom" || actType === "barn_1sygedag" || actType === "paragraf_56_syg") ? "Angiv dato for sygedagen"
              : "Angiv start- og sluttid";
    toast(msg, "error");
    return;
  }
  if (!isRange && new Date(end) <= new Date(start)) { toast("Sluttid skal være efter starttid", "error"); return; }

  const terminsdato = document.getElementById("manual-terminsdato").value || null;
  if (actType === "barsel" && !terminsdato) {
    toast("Angiv terminsdato for barsel", "error");
    return;
  }

  const regInput = document.getElementById("manual-reg").value.trim().toUpperCase();
  const foundVehicle = regInput ? state.vehicles.find(x =>
    x.registration_number.toUpperCase() === regInput ||
    x.vehicle_number.toUpperCase() === regInput
  ) : null;
  if (regInput && !foundVehicle) {
    openModal("modal-reg-error");
    return;
  }

  // ── Advarsel: fravær på dag med kørsel ───────────────────────────────────
  if (ABSENCE_TYPES.has(actType) && !_absenceConflictConfirmed) {
    const datesToCheck = isRange
      ? getWeekdayDates(start.slice(0, 10), tilDato)
      : [start.slice(0, 10)];
    const conflicts = datesToCheck.filter(date =>
      state.activities.some(a =>
        a.employee_id === empId &&
        a.activity_type === "normal" &&
        a.start_time.slice(0, 10) === date &&
        a.status !== "deactivated"
      )
    );
    if (conflicts.length > 0) {
      const dateList = conflicts.map(d => {
        const [y, m, day] = d.split("-");
        return `${day}-${m}-${y}`;
      }).join(", ");
      document.getElementById("absence-conflict-msg").innerHTML =
        `Der er allerede registreret kørsel på følgende dag${conflicts.length > 1 ? "e" : ""}:<br><strong>${dateList}</strong><br><br>Vil du alligevel registrere fraværet?`;
      openModal("modal-absence-conflict");
      return;
    }
  }
  _absenceConflictConfirmed = false;

  // ── Periodetilstand: opret én aktivitet per hverdag ──────────────────────
  if (isRange) {
    const fra = start.slice(0, 10);
    if (tilDato < fra) { toast("Til dato skal være på eller efter fra dato", "error"); return; }
    const dates = getWeekdayDates(fra, tilDato);
    if (dates.length === 0) { toast("Ingen hverdage i den valgte periode", "error"); return; }

    // Overlapscheck for alle dage i perioden
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
      if (!window.confirm(`Advarsel: ${allOverlaps.length} overlappende aktiviteter i perioden:\n\n${lines.join("\n")}\n\nVil du stadig oprette alle aktiviteter?`)) return;
    }

    const emp = state.employees.find(e => e.id === empId);
    let created = 0;
    try {
      for (const iso of dates) {
        let hours = 7.4;
        if (actType !== "feriefri" && emp?.work_schedule) {
          const d = new Date(iso + "T12:00:00");
          const key = isoWeekNumber(d) % 2 === 0 ? "even" : "odd";
          const idx = (d.getDay() + 6) % 7;
          const sched = emp.work_schedule[key]?.[idx] ?? 0;
          hours = sched > 0 ? sched : 7.4;
        }
        const mins = Math.round(hours * 60);
        const endH = String(6 + Math.floor(mins / 60)).padStart(2, "0");
        const endM = String(mins % 60).padStart(2, "0");
        await POST("/api/activities", {
          employee_id: empId,
          activity_type: actType,
          start_time:   iso + "T06:00:00",
          end_time:     iso + "T" + endH + ":" + endM + ":00",
          terminsdato:  terminsdato,
        });
        created++;
      }
      toast(`${created} ${created === 1 ? "aktivitet oprettet" : "aktiviteter oprettet"}`, "success");
      closeModal("modal-manual-activity");
      await refreshActivities();
    } catch (e) { toast(e.message, "error"); }
    return;
  }

  // ── Enkeltdag: eksisterende overlapscheck + POST ─────────────────────────
  const newStart = new Date(start + ":00");
  const newEnd   = new Date(end   + ":00");
  const overlapping = state.activities.filter(a => {
    if (a.employee_id !== empId) return false;
    if (a.status === "deactivated") return false;
    return newStart < new Date(a.end_time) && newEnd > new Date(a.start_time);
  });
  if (overlapping.length > 0) {
    const lines = overlapping.map(a =>
      `• ${TYPE_LABELS[a.activity_type] || a.activity_type}: ${formatTime(a.start_time)}–${formatTime(a.end_time)}`
    ).join("\n");
    const noun = overlapping.length === 1 ? "en eksisterende aktivitet" : `${overlapping.length} eksisterende aktiviteter`;
    if (!window.confirm(`Advarsel: Der er ${noun} der overlapper med det valgte tidsrum:\n\n${lines}\n\nVil du stadig oprette aktiviteten?`)) return;
  }

  try {
    await POST("/api/activities", {
      employee_id: empId,
      activity_type: actType,
      start_time: start + ":00",
      end_time: end + ":00",
      terminsdato: terminsdato,
      loading_minutes: parseInt(document.getElementById("manual-loading").value) || null,
      unloading_minutes: parseInt(document.getElementById("manual-unloading").value) || null,
      comment: document.getElementById("manual-comment").value || null,
      vehicle_number: foundVehicle?.vehicle_number || null,
      km_start: parseInt(document.getElementById("manual-km-start").value) || null,
      km_end:   parseInt(document.getElementById("manual-km-end").value)   || null,
      salt_supplement: document.getElementById("manual-salt").checked,
      pause_intervals: manualPauses,
    });
    toast("Aktivitet oprettet", "success");
    closeModal("modal-manual-activity");
    await refreshActivities();
  } catch (e) { toast(e.message, "error"); }
}

// ── Employees ──────────────────────────────────────────────────────────────
async function loadEmployees() {
  setLoading(true);
  try {
    const showInactive = document.getElementById("show-inactive")?.checked;
    state.employees = await GET(`/api/employees?active_only=${!showInactive}`);
    renderEmployeeList();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function renderEmployeeList() {
  const query = (document.getElementById("employee-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("employee-list");
  container.innerHTML = "";
  let emps = state.employees;
  if (query) {
    emps = emps.filter(e =>
      e.name.toLowerCase().includes(query) ||
      String(e.employee_number).toLowerCase().includes(query)
    );
  }
  emps = emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"));
  if (emps.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">👤</div><h3>Ingen medarbejdere</h3></div>`;
    return;
  }
  for (const e of emps) {
    const initials = `${e.first_name[0] || ""}${e.last_name[0] || ""}`.toUpperCase();
    const div = document.createElement("div");
    div.className = "emp-card";
    div.style.cursor = "pointer";
    div.innerHTML = `
      <div class="emp-avatar">${h(initials)}</div>
      <div class="emp-info">
        <div class="emp-name">${h(e.name)}</div>
        <div class="emp-sub">Lønnr. ${h(e.employee_number)} · ${h(e.agreement_type)}${e.hourly_rate ? ` · ${e.hourly_rate.toFixed(2)} kr/t` : ""} · Ansat ${formatDateShort(e.hire_date)} (${e.months_employed} mdr.)</div>
      </div>
      ${e.active ? "" : `<span class="badge" style="background:#fee2e2;color:#dc2626">Inaktiv</span>`}
      ${state.currentUser?.permissions?.includes("manage_employees") ? `<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openEditEmployee(${e.id})">Rediger</button>` : ""}
    `;
    div.addEventListener("click", () => {
      if (state.currentUser?.permissions?.includes("manage_employees")) openEditEmployee(e.id);
    });
    container.appendChild(div);
  }
}

const DEFAULT_SCHEDULE = [7.5, 7.5, 7.5, 7.5, 7, 0, 0]; // man-tor, fre, lør, søn

function _hoursFromTimes(startVal, endVal) {
  if (!startVal || !endVal) return null;
  const [sh, sm] = startVal.split(":").map(Number);
  const [eh, em] = endVal.split(":").map(Number);
  let mins = (eh * 60 + em) - (sh * 60 + sm);
  if (mins < 0) mins += 24 * 60; // arbejdstid over midnat
  return Math.round((mins / 60) * 100) / 100;
}

function _scheduleRowCell(prefix, day, hours) {
  return `
    <td>
      <div style="display:flex;align-items:center;gap:6px">
        <input type="number" step="0.1" min="0" max="24" class="sched-${prefix}" data-day="${day}" value="${hours}" style="width:70px"> t
      </div>
      <div style="display:flex;align-items:center;gap:4px;margin-top:4px;font-size:12px;color:var(--text-light)">
        <input type="time" class="sched-${prefix}-start" data-day="${day}" style="width:88px">
        –
        <input type="time" class="sched-${prefix}-end" data-day="${day}" style="width:88px">
      </div>
    </td>`;
}

function buildScheduleTable(schedule) {
  const tbody = document.querySelector("#schedule-table tbody");
  tbody.innerHTML = "";
  for (let i = 0; i < 7; i++) {
    const def = DEFAULT_SCHEDULE[i];
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${WEEKDAYS[i]}</td>
      ${_scheduleRowCell("even", i, schedule?.even?.[i] ?? def)}
      ${_scheduleRowCell("odd", i, schedule?.odd?.[i] ?? def)}
    `;
    tbody.appendChild(tr);
  }
  document.querySelectorAll("#schedule-table .sched-even, #schedule-table .sched-odd").forEach(el =>
    el.addEventListener("input", _updateScheduleTotals));
  ["even", "odd"].forEach(prefix => {
    document.querySelectorAll(`#schedule-table .sched-${prefix}-start, #schedule-table .sched-${prefix}-end`).forEach(el => {
      el.addEventListener("input", () => {
        const day = el.dataset.day;
        const startEl = document.querySelector(`.sched-${prefix}-start[data-day="${day}"]`);
        const endEl   = document.querySelector(`.sched-${prefix}-end[data-day="${day}"]`);
        const hours = _hoursFromTimes(startEl.value, endEl.value);
        if (hours !== null) {
          document.querySelector(`.sched-${prefix}[data-day="${day}"]`).value = hours;
          _updateScheduleTotals();
        }
      });
    });
  });
  _updateScheduleTotals();
}

function _updateScheduleTotals() {
  const sum = cls => [...document.querySelectorAll(cls)].reduce((s, el) => s + (parseFloat(el.value) || 0), 0);
  document.getElementById("sched-even-total").textContent = fmtHours(sum(".sched-even"));
  document.getElementById("sched-odd-total").textContent  = fmtHours(sum(".sched-odd"));
}

function readScheduleTable() {
  const even = [], odd = [];
  ["even", "odd"].forEach(prefix => {
    const target = prefix === "even" ? even : odd;
    for (let day = 0; day < 7; day++) {
      const startEl = document.querySelector(`.sched-${prefix}-start[data-day="${day}"]`);
      const endEl   = document.querySelector(`.sched-${prefix}-end[data-day="${day}"]`);
      const fromTimes = _hoursFromTimes(startEl.value, endEl.value);
      const numEl = document.querySelector(`.sched-${prefix}[data-day="${day}"]`);
      target.push(fromTimes !== null ? fromTimes : (parseFloat(numEl.value) || 0));
    }
  });
  return { even, odd };
}

async function loadAgreementTypes() {
  if (state.agreementTypes.length) return;
  state.agreementTypes = await GET("/api/employees/agreement-types");
}

function fillAgreementTypeSelect(selected = null) {
  const sel = document.getElementById("emp-agreement-type");
  const placeholder = selected ? "" : `<option value="">[Vælg overenskomsttype]</option>`;
  sel.innerHTML = placeholder + state.agreementTypes
    .map(t => `<option value="${t.name}" ${t.name === selected ? "selected" : ""}>${t.name} (${t.hourly_rate.toFixed(2)} kr)</option>`)
    .join("");
}

async function _loadEmpCvrDropdown(selectedCvr) {
  const group = document.getElementById("emp-cvr-group");
  const sel   = document.getElementById("emp-cvr");
  try {
    const rows = await GET("/api/stamdata/cvr-numbers");
    if (rows.length < 2) { group.style.display = "none"; return; }
    const defaultRow = rows.find(r => r.is_default);
    const current = selectedCvr || (defaultRow ? defaultRow.cvr_number : rows[0].cvr_number);
    sel.innerHTML = rows.map(r =>
      `<option value="${h(r.cvr_number)}" ${r.cvr_number === current ? "selected" : ""}>${h(r.cvr_number)}${r.company_name ? " – " + h(r.company_name) : ""}</option>`
    ).join("");
    group.style.display = "";
  } catch (_) { group.style.display = "none"; }
}

function _renderDispatcherGroupCheckboxes(selectedIds) {
  const container = document.getElementById("emp-dispatcher-groups");
  if (!state.dispatcherGroups.length) {
    container.innerHTML = `<p style="font-size:13px;color:var(--text-light);margin:0">Ingen disponentgrupper oprettet endnu</p>`;
    return;
  }
  container.innerHTML = state.dispatcherGroups.map(g => `
    <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:14px">
      <input type="checkbox" value="${g.id}" ${selectedIds.includes(g.id) ? "checked" : ""}
             style="width:15px;height:15px;accent-color:var(--primary);cursor:pointer">
      ${h(g.name)}
    </label>`).join("");
}

async function openNewEmployeeModal() {
  await loadAgreementTypes();
  document.getElementById("emp-modal-title").textContent = "Opret medarbejder";
  document.getElementById("emp-save-btn").textContent = "Opret";
  document.getElementById("emp-id").value = "";
  ["emp-number","emp-card","emp-firstname","emp-lastname","emp-address","emp-postal",
   "emp-email","emp-phone","emp-mobile"].forEach(id => document.getElementById(id).value = "");
  document.getElementById("emp-agreement-kind").value = "";
  fillAgreementTypeSelect();
  _renderDispatcherGroupCheckboxes([]);
  buildDatePicker("emp-hire", "");
  buildDatePicker("emp-termination", "9999-12-31");
  document.getElementById("emp-active").checked = true;
  document.getElementById("emp-fuldloennet").checked = true;
  buildScheduleTable(null);
  await _loadEmpCvrDropdown(null);
  openModal("modal-employee");
}

async function openEditEmployee(id) {
  await loadAgreementTypes();
  const e = state.employees.find(x => x.id === id);
  if (!e) return;
  document.getElementById("emp-modal-title").textContent = "Rediger medarbejder";
  document.getElementById("emp-save-btn").textContent = "Opdater";
  document.getElementById("emp-id").value = e.id;
  document.getElementById("emp-number").value = e.employee_number;
  document.getElementById("emp-card").value = e.tachograph_card_number || "";
  document.getElementById("emp-firstname").value = e.first_name;
  document.getElementById("emp-lastname").value = e.last_name;
  document.getElementById("emp-address").value = e.address || "";
  document.getElementById("emp-postal").value = e.postal_code || "";
  document.getElementById("emp-email").value = e.email || "";
  document.getElementById("emp-phone").value = e.phone || "";
  document.getElementById("emp-mobile").value = e.mobile || "";
  document.getElementById("emp-agreement-kind").value = e.agreement_kind;
  fillAgreementTypeSelect(e.agreement_type);
  _renderDispatcherGroupCheckboxes((e.dispatcher_groups || []).map(g => g.id));
  buildDatePicker("emp-hire", e.hire_date);
  buildDatePicker("emp-termination", e.termination_date);
  document.getElementById("emp-active").checked = e.active;
  document.getElementById("emp-fuldloennet").checked = e.fuldloennet;
  buildScheduleTable(e.work_schedule);
  await _loadEmpCvrDropdown(e.cvr_number || null);
  openModal("modal-employee");
}

async function confirmEmployee() {
  const id = document.getElementById("emp-id").value;
  const body = {
    employee_number: document.getElementById("emp-number").value.trim(),
    tachograph_card_number: document.getElementById("emp-card").value.trim() || null,
    first_name: document.getElementById("emp-firstname").value.trim(),
    last_name: document.getElementById("emp-lastname").value.trim(),
    address: document.getElementById("emp-address").value.trim() || null,
    postal_code: document.getElementById("emp-postal").value.trim() || null,
    email: document.getElementById("emp-email").value.trim() || null,
    phone: document.getElementById("emp-phone").value.trim() || null,
    mobile: document.getElementById("emp-mobile").value.trim() || null,
    agreement_kind: document.getElementById("emp-agreement-kind").value,
    agreement_type: document.getElementById("emp-agreement-type").value,
    dispatcher_group_ids: [...document.querySelectorAll("#emp-dispatcher-groups input:checked")].map(cb => parseInt(cb.value)),
    cvr_number: document.getElementById("emp-cvr-group").style.display !== "none"
      ? (document.getElementById("emp-cvr").value || null)
      : null,
    fuldloennet: document.getElementById("emp-fuldloennet").checked,
    active: document.getElementById("emp-active").checked,
    hire_date: readDatePicker("emp-hire"),
    termination_date: readDatePicker("emp-termination") || "9999-12-31",
    work_schedule: readScheduleTable(),
  };
  if (!body.employee_number || !body.first_name || !body.last_name || !body.hire_date) {
    toast("Udfyld lønnummer, navn og ansættelsesdato", "error");
    return;
  }

  if (!id) {
    try {
      const all = await GET("/api/employees?active_only=false");
      const nameMatches = all.filter(e =>
        e.first_name.trim().toLowerCase() === body.first_name.toLowerCase() &&
        e.last_name.trim().toLowerCase() === body.last_name.toLowerCase());
      const cardMatches = body.tachograph_card_number
        ? all.filter(e => (e.tachograph_card_number || "").trim().toLowerCase() === body.tachograph_card_number.toLowerCase())
        : [];
      if (nameMatches.length || cardMatches.length) {
        _showEmployeeDuplicateWarning(body, nameMatches, cardMatches);
        return;
      }
    } catch (_) { /* duplikat-tjek må ikke blokere oprettelse hvis den fejler */ }
  }
  await _saveEmployee(id, body);
}

async function _saveEmployee(id, body) {
  try {
    if (id) {
      await PATCH(`/api/employees/${id}`, body);
      toast("Medarbejder opdateret", "success");
    } else {
      await POST("/api/employees", body);
      toast("Medarbejder oprettet", "success");
    }
    closeModal("modal-employee");
    await loadEmployees();
    fillEmployeeFilter();
  } catch (e) { toast(e.message, "error"); }
}

let _pendingEmployeeBody = null;

function _showEmployeeDuplicateWarning(body, nameMatches, cardMatches) {
  _pendingEmployeeBody = body;
  const parts = [];
  if (cardMatches.length) {
    parts.push(`<p>Førerkortnummeret <b>${h(body.tachograph_card_number)}</b> er allerede registreret på: <b>${cardMatches.map(e => h(e.name)).join(", ")}</b>. Det kan ikke bruges igen.</p>`);
  }
  if (nameMatches.length) {
    parts.push(`<p>Der findes allerede en medarbejder med navnet <b>${h(body.first_name)} ${h(body.last_name)}</b>: <b>${nameMatches.map(e => h(e.name + " (" + e.employee_number + ")")).join(", ")}</b>.</p>`);
  }
  document.getElementById("emp-duplicate-warning-body").innerHTML = parts.join("");
  document.getElementById("btn-emp-duplicate-ok").style.display = cardMatches.length ? "none" : "";
  openModal("modal-emp-duplicate-warning");
}

function empDuplicateChange() {
  closeModal("modal-emp-duplicate-warning");
  _pendingEmployeeBody = null;
}

async function empDuplicateIgnore() {
  const body = _pendingEmployeeBody;
  closeModal("modal-emp-duplicate-warning");
  _pendingEmployeeBody = null;
  if (body) await _saveEmployee("", body);
}

// ── Anciennitet popup ──────────────────────────────────────────────────────
async function dismissAnciennitetsAlert(employeeId) {
  try {
    await POST(`/api/employees/${employeeId}/dismiss-anciennitet`, {});
  } catch (e) {
    console.error("Kunne ikke gemme afvisning af anciennitetsadvarsel:", e);
  }
  closeModal("modal-anciennitet");
}

async function checkAnciennitetsAlerts() {
  if (!state.currentUser?.permissions?.includes("anciennitet_alert")) return;
  try {
    const all = await GET("/api/employees/anciennitet-alerts");
    const dismissed = _getDismissedAlerts();
    const alerts = all.filter(a => !dismissed.has(a.employee_id));
    if (alerts.length === 0) return;
    const a = alerts[0];
    document.getElementById("anciennitet-body").innerHTML = `
      <p style="font-size:14px;margin-bottom:8px">
        Medarbejder <strong>${h(a.employee_name)} (${h(a.employee_number)})</strong> har ny anciennitetsstatus.
      </p>
      <p style="font-size:13px;color:var(--text-light)">
        Ansat ${formatDateShort(a.hire_date)} – ${a.months_employed} måneder.
        ${a.suggested_agreement_type ? `Foreslået overenskomsttype: <strong>${a.suggested_agreement_type}</strong>` : ""}
      </p>
      ${alerts.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${alerts.length - 1} flere medarbejdere med ny anciennitetsstatus.</p>` : ""}
    `;
    document.getElementById("btn-goto-employee").onclick = async () => {
      closeModal("modal-anciennitet");
      setView("employees");
      await loadEmployees();
      openEditEmployee(a.employee_id);
    };
    document.getElementById("btn-anciennitet-done").onclick = () => dismissAnciennitetsAlert(a.employee_id);
    openModal("modal-anciennitet");
  } catch (e) {
    console.error("Anciennitet check fejlede:", e);
  }
}

// ── Vehicles ────────────────────────────────────────────────────────────────
let _editingVehicleId = null;

async function loadVehicles() {
  setLoading(true);
  try {
    state.vehicles = await GET("/api/vehicles");
    renderVehicleList();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function renderVehicleList() {
  const query = (document.getElementById("vehicle-search")?.value || "").toLowerCase().trim();
  const container = document.getElementById("vehicle-list");
  container.innerHTML = "";
  let vehicles = state.vehicles;
  if (query) {
    vehicles = vehicles.filter(v =>
      v.registration_number.toLowerCase().includes(query) ||
      String(v.vehicle_number).toLowerCase().includes(query)
    );
  }
  if (vehicles.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">🚛</div><h3>Ingen vogne</h3></div>`;
    return;
  }
  for (const v of vehicles) {
    const initials = v.registration_number.slice(0, 2).toUpperCase();
    const div = document.createElement("div");
    div.className = "emp-card";
    div.style.cursor = "pointer";
    div.innerHTML = `
      <div class="emp-avatar">${initials}</div>
      <div class="emp-info">
        <div class="emp-name">${v.registration_number}</div>
        <div class="emp-sub">Vognnr. ${v.vehicle_number}</div>
      </div>
      ${state.currentUser?.permissions?.includes("manage_vehicles") ? `<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openEditVehicle(${v.id})">Rediger</button>` : ""}
    `;
    div.addEventListener("click", () => {
      if (state.currentUser?.permissions?.includes("manage_vehicles")) openEditVehicle(v.id);
    });
    container.appendChild(div);
  }
}

function openNewVehicleModal() {
  _editingVehicleId = null;
  document.getElementById("vehicle-modal-title").textContent = "Opret vogn";
  document.getElementById("vehicle-reg").value = "";
  document.getElementById("vehicle-num").value = "";
  document.getElementById("vehicle-delete-btn").classList.add("hidden");
  openModal("modal-vehicle");
}

function openEditVehicle(id) {
  const v = state.vehicles.find(x => x.id === id);
  if (!v) return;
  _editingVehicleId = id;
  document.getElementById("vehicle-modal-title").textContent = "Rediger vogn";
  document.getElementById("vehicle-reg").value = v.registration_number;
  document.getElementById("vehicle-num").value = v.vehicle_number;
  document.getElementById("vehicle-delete-btn").classList.remove("hidden");
  openModal("modal-vehicle");
}

async function saveVehicle() {
  const reg = document.getElementById("vehicle-reg").value.trim();
  const num = document.getElementById("vehicle-num").value.trim();
  if (!reg || !num) { toast("Udfyld begge felter", "error"); return; }
  try {
    if (_editingVehicleId) {
      await PATCH(`/api/vehicles/${_editingVehicleId}`, { registration_number: reg, vehicle_number: num });
      toast("Vogn opdateret", "success");
    } else {
      await POST("/api/vehicles", { registration_number: reg, vehicle_number: num });
      toast("Vogn oprettet", "success");
    }
    closeModal("modal-vehicle");
    await loadVehicles();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteVehicle() {
  if (!_editingVehicleId) return;
  const v = state.vehicles.find(x => x.id === _editingVehicleId);
  if (!confirm(`Slet vogn ${v?.registration_number}?`)) return;
  try {
    await api("DELETE", `/api/vehicles/${_editingVehicleId}`);
    toast("Vogn slettet", "success");
    closeModal("modal-vehicle");
    await loadVehicles();
  } catch (e) { toast(e.message, "error"); }
}


// ── Import ─────────────────────────────────────────────────────────────────
function _setImportBtnsDisabled(on) {
  ["btn-import-files", "btn-import-folder"].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.disabled = on;
  });
}

function _showImportResult(result) {
  const msg = `Importeret: ${result.imported} aktivitet${result.imported !== 1 ? "er" : ""}.` +
    (result.skipped ? ` Sprunget over: ${result.skipped}.` : "") +
    (result.files_processed !== undefined ? ` Filer behandlet: ${result.files_processed}.` : "") +
    (result.errors?.length ? ` Fejl: ${result.errors.join("; ")}` : "");
  document.getElementById("import-result").textContent = msg;

  const allClean = !result.skipped && !result.errors?.length && !result.zero_activity_files?.length;
  const body = document.getElementById("import-result-modal-body");

  if (allClean) {
    body.innerHTML = `
      <div style="text-align:center;padding:16px 0">
        <div style="font-size:40px;line-height:1;margin-bottom:10px">&#9989;</div>
        <div style="font-size:16px;font-weight:600;color:var(--primary)">Importering succesfuld</div>
        <div style="color:var(--text-light);margin-top:6px">
          ${result.imported} aktivitet${result.imported !== 1 ? "er" : ""} importeret fra
          ${result.files_processed} fil${result.files_processed !== 1 ? "er" : ""}.
        </div>
      </div>`;
  } else {
    const rowStyle = "margin-bottom:12px;font-size:13px;line-height:1.5";
    const rows = [];
    rows.push(`<div style="${rowStyle}"><b>Filer behandlet:</b> ${result.files_processed}</div>`);
    rows.push(`<div style="${rowStyle}"><b>Importeret:</b> ${result.imported}</div>`);
    if (result.updated) {
      rows.push(`<div style="${rowStyle}"><b>Opdateret (km-data udfyldt):</b> ${result.updated}</div>`);
    }
    if (result.skipped_unknown_card) {
      rows.push(`<div style="${rowStyle};color:var(--danger)">
        <b>Sprunget over – ukendt førerkortnummer (${result.skipped_unknown_card}):</b><br>
        ${(result.unknown_cards || []).map(h).join(", ")}<br>
        <span style="font-weight:400">Kontrollér at kortnummeret er registreret korrekt på medarbejderen i Stamdata (de første 14 tegn, uden udskiftnings-/fornyelsescifre).</span>
      </div>`);
    }
    if (result.skipped_duplicate) {
      rows.push(`<div style="${rowStyle}"><b>Sprunget over – allerede importeret:</b> ${result.skipped_duplicate}</div>`);
    }
    if (result.zero_activity_files?.length) {
      rows.push(`<div style="${rowStyle}">
        <b>Fil(er) uden aktiviteter (${result.zero_activity_files.length}):</b><br>
        ${result.zero_activity_files.map(h).join(", ")}
      </div>`);
    }
    if (result.errors?.length) {
      rows.push(`<div style="${rowStyle};color:var(--danger)">
        <b>Fejl (${result.errors.length}):</b>
        <ul style="margin:4px 0 0 18px">${result.errors.map(e => `<li>${h(e)}</li>`).join("")}</ul>
      </div>`);
    }
    body.innerHTML = rows.join("");
  }
  openModal("modal-import-result");
}

async function importDddPickFiles() {
  const btn = document.getElementById("btn-import-files");
  btn.disabled = true;
  btn.textContent = "Venter...";
  let paths;
  try {
    const res = await GET("/api/browse-ddd-files");
    if (!res.paths?.length) { return; }
    paths = res.paths;
  } catch (e) {
    toast("Kunne ikke åbne filvælger", "error"); return;
  } finally {
    btn.disabled = false;
    btn.innerHTML = "&#128229; Vælg filer";
  }

  _setImportBtnsDisabled(true);
  document.getElementById("import-result").textContent = `Importerer ${paths.length} fil(er)...`;
  try {
    const result = await POST("/api/import-ddd-from", { source_files: paths });
    _showImportResult(result);
  } catch (e) {
    toast(e.message, "error");
    document.getElementById("import-result").textContent = "Fejl: " + e.message;
  } finally { _setImportBtnsDisabled(false); }
}

async function importDddPickFolder() {
  const btn = document.getElementById("btn-import-folder");
  btn.disabled = true;
  btn.textContent = "Venter...";
  let folder;
  try {
    const res = await GET("/api/browse-ddd-folder");
    if (!res.path) { return; }
    folder = res.path;
  } catch (e) {
    toast("Kunne ikke åbne mappevælger", "error"); return;
  } finally {
    btn.disabled = false;
    btn.innerHTML = "&#128193; Vælg mappe";
  }

  _setImportBtnsDisabled(true);
  document.getElementById("import-result").textContent = `Importerer fra ${folder}...`;
  try {
    const result = await POST("/api/import-ddd-from", { source_folder: folder });
    _showImportResult(result);
  } catch (e) {
    toast(e.message, "error");
    document.getElementById("import-result").textContent = "Fejl: " + e.message;
  } finally { _setImportBtnsDisabled(false); }
}

// ── Payroll ────────────────────────────────────────────────────────────────
async function loadPayrollPreview() {
  setLoading(true);
  try {
    const qs = state.currentPeriodStart ? `?period_start=${state.currentPeriodStart}` : "";
    const data = await GET(`/api/payroll/preview${qs}`);
    renderPayrollPreview(data);
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function renderPayrollPreview(data) {
  const container = document.getElementById("payroll-preview-container");
  container.innerHTML = "";
  state.hasUnresolvedPending = !!data.has_unresolved_pending;
  state.periodClosed = data.period_status === "closed";
  document.getElementById("payroll-period-label").textContent =
    `${formatDateShort(data.period_start)} – ${formatDateShort(data.period_end)}`;
  const koerLoenBtn = document.getElementById("btn-koer-loen");
  if (koerLoenBtn) koerLoenBtn.classList.toggle("btn-muted", state.hasUnresolvedPending || state.periodClosed);

  if (data.period_status === "closed") {
    const closedWarn = document.createElement("div");
    closedWarn.className = "alert-banner mb-16";
    closedWarn.innerHTML = `<span class="icon">🔒</span><div class="text"><h4>Perioden er låst</h4>Lønnen er allerede kørt for denne periode. Åbn perioden igen under Administration, hvis der skal foretages ændringer.</div>`;
    container.appendChild(closedWarn);
  }

  if (data.has_unresolved_pending) {
    const warn = document.createElement("div");
    warn.className = "alert-banner mb-16";
    warn.innerHTML = `<span class="icon">⚠️</span><div class="text"><h4>Afventende aktiviteter</h4>Der er aktiviteter, der afventer handling. Før lønnen kan køres, skal alle aktiviteter enten godkendes eller deaktiveres. Kun godkendte aktiviteter tæller med i lønnen.</div>`;
    container.appendChild(warn);
  }

  data.employees.sort((a, b) => (a.employee_name || "").localeCompare(b.employee_name || "", "da"));
  let any = false;
  for (const emp of data.employees) {
    if (emp.activity_count === 0 && emp.afspadsering_hours === 0) continue;
    any = true;
    const el = document.createElement("div");
    el.className = "payroll-employee";
    el.innerHTML = `
      <div class="payroll-emp-header">
        <div class="emp-avatar" style="width:34px;height:34px;font-size:13px">${h(emp.employee_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase())}</div>
        <div class="payroll-emp-info">
          <h3>${h(emp.employee_name)}</h3>
          <div class="emp-meta">${h(emp.employee_number)} · ${h(emp.agreement_type)}</div>
        </div>
        <button class="btn btn-sm payroll-proeve-btn" onclick="proevekoersel(${emp.employee_id})">📊 Prøvekørsel</button>
        <button class="btn btn-sm btn-secondary" onclick="downloadTimeseddel(${emp.employee_id})" title="Download PDF-timeseddel" style="padding:5px 10px">⬇ PDF</button>
        <button class="btn btn-sm btn-primary" onclick="sendTimeseddel(${emp.employee_id})" title="Send timeseddel til medarbejder" style="padding:5px 10px;background:#317423;border-color:#317423">✉ Send</button>
      </div>
      <div class="payroll-col-header">
        <div></div>
        <div>Antal</div>
        <div>Sats</div>
        <div>DKK</div>
      </div>
      <div class="payroll-rows">
        ${payrollRow("Normal tid", emp.normal_hours, emp.hourly_rate)}
        ${payrollRow("Overtid 1 time før", emp.ot_before_hours, emp.ot_rates?.["Overtid 1 time før"])}
        ${payrollRow("Overtid 1-3 timer efter", (emp.ot_13_hours || 0) + (emp.sh_kode8_hours || 0), emp.ot_rates?.["Overtid 1-3 timer efter"])}
        ${payrollRow("Øvrig overtid", (emp.ot_extra_hours || 0) + (emp.sh_kode9_hours || 0), emp.ot_rates?.["Øvrigt overtid"])}
        ${payrollRow("Søgnehelligdag", emp.sh_fuldloennet_hours, emp.hourly_rate)}
        ${payrollRow("SH-Udbetaling", emp.sh_timeloennet_hours, emp.hourly_rate)}
        ${payrollRowSalt("Salttillæg", emp.salt_hours, emp.salt_rate, emp.salt_kr)}
        ${payrollRowOvernight("Overnatning", emp.overnight_count, emp.overnight_rate, emp.overnight_kr)}
        ${payrollRow("Afspadsering", emp.afspadsering_hours)}
        ${payrollRow("Sygdom med løn", emp.sygdom_hours, emp.hourly_rate)}
        ${payrollRow("§56 syg", emp.paragraf_56_syg_hours, emp.dagpenge_sats)}
        ${payrollRow("Barn 1.sygedag", emp.barn_1sygedag_u_loen_hours, emp.dagpenge_sats)}
        ${payrollRow("Feriefri", emp.feriefri_hours, emp.hourly_rate)}
        ${payrollRow("Barsel", emp.barsel_hours, emp.hourly_rate)}
        ${payrollRow("Kursus/Skole", emp.skole_kursus_hours, emp.hourly_rate)}
        <div class="payroll-row total">
          <div>I alt</div>
          <div>${fmtHours(emp.total_hours)}</div>
          <div></div>
          <div class="text-right">${fmtKr(emp.total_kr)}</div>
        </div>
      </div>`;
    container.appendChild(el);
  }
  if (!any) {
    container.innerHTML += `<div class="empty-state"><div class="icon">💰</div><h3>Ingen godkendte aktiviteter i perioden</h3></div>`;
  }
}

function payrollRow(label, hours, rate = null) {
  if (!hours || hours < 0.001) return "";
  const kr = rate != null ? hours * rate : null;
  return `<div class="payroll-row">
    <div class="label">${label}</div>
    <div>${fmtHours(hours)}</div>
    <div style="color:var(--text-light);font-size:12px">${rate != null ? rate.toFixed(2) + " kr/t" : ""}</div>
    <div class="text-right">${kr != null ? fmtKr(kr) : ""}</div>
  </div>`;
}

function payrollRowSalt(label, hours, rate, kr) {
  if (!hours || hours < 0.001) return "";
  return `<div class="payroll-row">
    <div class="label">${label}</div>
    <div>${fmtHours(hours)}</div>
    <div style="color:var(--text-light);font-size:12px">${rate != null ? rate.toFixed(2) + " kr/t" : ""}</div>
    <div class="text-right">${fmtKr(kr)}</div>
  </div>`;
}

function payrollRowOvernight(label, count, rate, kr) {
  if (!count || count < 1) return "";
  return `<div class="payroll-row">
    <div class="label">${label}</div>
    <div>${count} gang${count !== 1 ? "e" : ""}</div>
    <div style="color:var(--text-light);font-size:12px">${rate != null ? rate.toFixed(2) + " kr/gang" : ""}</div>
    <div class="text-right">${fmtKr(kr)}</div>
  </div>`;
}

function downloadTimeseddel(employeeId) {
  const periodStart = state.currentPeriodStart;
  if (!periodStart) { toast("Vælg en lønperiode først", "error"); return; }
  const url = `/api/timeseddel/${employeeId}/pdf?period_start=${periodStart}`;
  window.open(url, "_blank");
}

async function sendTimeseddel(employeeId) {
  const periodStart = state.currentPeriodStart;
  if (!periodStart) { toast("Vælg en lønperiode først", "error"); return; }
  const empData = (state.payrollData?.employees || []).find(e => e.employee_id === employeeId);
  const employeeName = empData?.employee_name || `medarbejder ${employeeId}`;
  if (!confirm(`Send timeseddel til ${employeeName}?`)) return;
  setLoading(true);
  try {
    const res = await POST(`/api/timeseddel/${employeeId}/send?period_start=${periodStart}`, {});
    toast(`Timeseddel sendt til ${res.sent_to}`, "success");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

async function proevekoersel(employeeId = null) {
  state.proevekoerselEmployeeId = employeeId;
  document.getElementById("proeve-result").textContent = "";
  try {
    const res = await GET("/api/payroll/downloads-folder");
    document.getElementById("proeve-folder").value = res.path;
  } catch { /* lad feltet være tomt */ }
  openModal("modal-proevekoersel");
}

async function browseProeveFolder() {
  const btn = document.getElementById("proeve-browse-btn");
  btn.disabled = true;
  btn.textContent = "Venter...";
  try {
    const current = document.getElementById("proeve-folder").value.trim();
    const res = await GET(`/api/payroll/browse-folder?initial=${encodeURIComponent(current)}`);
    if (res.path) document.getElementById("proeve-folder").value = res.path;
  } catch (e) { toast("Kunne ikke åbne mappevælger", "error"); }
  finally { btn.disabled = false; btn.textContent = "Gennemse"; }
}

async function confirmProevekoersel() {
  const folder = document.getElementById("proeve-folder").value.trim();
  if (!folder) { toast("Angiv en mappe at gemme filen i", "error"); return; }
  setLoading(true);
  try {
    const result = await POST("/api/payroll/proevekoersel-gem", {
      period_start: state.currentPeriodStart || null,
      employee_id: state.proevekoerselEmployeeId || null,
      output_folder: folder,
    });
    toast(`Prøvekørsel gemt: ${result.filename}`, "success");
    closeModal("modal-proevekoersel");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

async function exportCsv() {
  if (state.periodClosed) {
    toast("Lønperioden er allerede låst – lønnen er allerede kørt for denne periode.", "error");
    return;
  }
  if (state.hasUnresolvedPending) {
    toast("Lønnen kan ikke køres – der er aktiviteter, der afventer handling. Godkend eller deaktiver dem først.", "error");
    return;
  }
  const p = state.periodInfo?.period;
  const fmt = iso => new Date(iso + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "long", year: "numeric" });
  const periodTxt = p ? `${fmt(p.start_date)} – ${fmt(p.end_date)}` : "den aktuelle periode";
  document.getElementById("csv-confirm-text").innerHTML =
    `Er du sikker på, at du vil låse lønperioden <strong>${periodTxt}</strong>?<br><br>` +
    `Når perioden er låst, kan der ikke foretages flere ændringer i den. CSV-filen til Danløn gemmes i den valgte mappe.`;
  try {
    const res = await GET("/api/payroll/downloads-folder");
    document.getElementById("csv-folder").value = res.path;
  } catch { /* lad feltet stå tomt */ }
  document.getElementById("csv-result").textContent = "";
  openModal("modal-csv");
}

async function browseCsvFolder() {
  const btn = document.getElementById("csv-browse-btn");
  btn.disabled = true; btn.textContent = "Venter...";
  try {
    const current = document.getElementById("csv-folder").value.trim();
    const res = await GET(`/api/payroll/browse-folder?initial=${encodeURIComponent(current)}`);
    if (res.path) document.getElementById("csv-folder").value = res.path;
  } catch { toast("Kunne ikke åbne mappevælger", "error"); }
  finally { btn.disabled = false; btn.textContent = "Gennemse"; }
}

async function confirmExportCsv() {
  const folder = document.getElementById("csv-folder").value.trim();
  if (!folder) { toast("Angiv en mappe at gemme CSV-filen i", "error"); return; }
  setLoading(true);
  try {
    const result = await POST("/api/payroll/export-csv", {
      period_start: state.currentPeriodStart || null,
      output_folder: folder,
    });
    toast(`Danløn CSV gemt: ${result.filename}`, "success");
    closeModal("modal-csv");
    await loadPeriodInfo(state.currentPeriodStart);
    await loadActivities();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

// ── Absence Overview ──────────────────────────────────────────────────────
async function loadAbsenceOverview() {
  if (!readDatePicker("absence-from-dp") && state.periodInfo) {
    setDatePicker("absence-from-dp", state.periodInfo.period.start_date);
    setDatePicker("absence-to-dp",   state.periodInfo.period.end_date);
  }
  setLoading(true);
  try {
    const from = readDatePicker("absence-from-dp");
    const to   = readDatePicker("absence-to-dp");
    const qs   = (from && to) ? `?date_from=${from}&date_to=${to}` : "";
    const data = await GET(`/api/absence-overview/data${qs}`);
    window._absenceOverviewData = data;
    renderAbsenceOverview(data);
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function renderAbsenceOverview(data) {
  const container = document.getElementById("absence-overview-container");
  container.innerHTML = "";

  const emps = (data.employees || []).slice().sort(
    (a, b) => (a.employee_name || "").localeCompare(b.employee_name || "", "da")
  );

  if (emps.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">📅</div><h3>Ingen fravær i valgt periode</h3></div>`;
    return;
  }

  for (const emp of emps) {
    const absences = Object.entries(emp.absences || {});
    if (absences.length === 0) continue;
    absences.sort((a, b) => a[1].label.localeCompare(b[1].label, "da"));

    const totalHours = absences.reduce((s, [, v]) => s + v.hours, 0);
    const totalDays  = absences.reduce((s, [, v]) => s + v.days,  0);

    const rows = absences.map(([, ainfo]) => `
      <div class="payroll-row">
        <div class="label">${ainfo.label}</div>
        <div>${ainfo.days} dag${ainfo.days !== 1 ? "e" : ""}</div>
        <div>${(ainfo.rate || 0) > 0 ? fmtKr(ainfo.rate) + "/t" : ""}</div>
        <div class="text-right">${fmtHours(ainfo.hours)}</div>
      </div>`).join("");

    const initials = emp.employee_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
    const el = document.createElement("div");
    el.className = "payroll-employee";
    el.innerHTML = `
      <div class="payroll-emp-header">
        <div class="emp-avatar" style="width:34px;height:34px;font-size:13px">${initials}</div>
        <div class="payroll-emp-info">
          <h3>${h(emp.employee_name)}</h3>
          <div class="emp-meta">${h(emp.employee_number)}</div>
        </div>
      </div>
      <div class="payroll-col-header">
        <div>Fraværstype</div>
        <div>Dage</div>
        <div></div>
        <div>Timer</div>
      </div>
      <div class="payroll-rows">
        ${rows}
        <div class="payroll-row total">
          <div>I alt</div>
          <div>${totalDays} dag${totalDays !== 1 ? "e" : ""}</div>
          <div></div>
          <div class="text-right">${fmtHours(totalHours)}</div>
        </div>
      </div>`;
    container.appendChild(el);
  }
}

async function exportAbsencePerEmployee() {
  // Reset modal
  document.querySelector('input[name="emp-export-scope"][value="all"]').checked = true;
  empExportScopeChanged();

  // Fetch options and populate dropdowns
  try {
    const opts = await GET("/api/absence-overview/employee-options");

    const grpSel = document.getElementById("emp-export-group-select");
    grpSel.innerHTML = "";
    (opts.dispatcher_groups || []).forEach(g => {
      const o = document.createElement("option");
      o.value = g.id; o.textContent = g.name;
      grpSel.appendChild(o);
    });

    const empSel = document.getElementById("emp-export-employee-select");
    empSel.innerHTML = "";
    (opts.employees || []).forEach(e => {
      const o = document.createElement("option");
      o.value = e.id; o.textContent = e.name;
      empSel.appendChild(o);
    });
  } catch (err) { toast("Kunne ikke hente medarbejdere: " + err.message, "error"); return; }

  openModal("modal-export-per-employee");
}

function empExportScopeChanged() {
  const scope = document.querySelector('input[name="emp-export-scope"]:checked').value;
  document.getElementById("emp-export-group-row").style.display    = scope === "group"    ? "" : "none";
  document.getElementById("emp-export-employee-row").style.display = scope === "employee" ? "" : "none";
}

function doExportPerEmployee() {
  const from  = readDatePicker("absence-from-dp");
  const to    = readDatePicker("absence-to-dp");
  const scope = document.querySelector('input[name="emp-export-scope"]:checked').value;
  const p = new URLSearchParams();
  if (from && to) { p.set("date_from", from); p.set("date_to", to); }
  if (scope === "group") {
    p.set("dispatcher_group_id", document.getElementById("emp-export-group-select").value);
  } else if (scope === "employee") {
    p.set("employee_id", document.getElementById("emp-export-employee-select").value);
  }
  const qs = p.toString() ? "?" + p.toString() : "";
  window.location.href = `/api/absence-overview/export-per-employee${qs}`;
  closeModal("modal-export-per-employee");
}

function exportAbsencePerType() {
  const list = document.getElementById("export-type-list");
  list.innerHTML = "";
  const allCb = document.getElementById("export-type-all");
  allCb.checked = true;

  const types = (window._absenceOverviewData || {}).absence_types || [];
  types.forEach(t => {
    const lbl = document.createElement("label");
    lbl.style.cssText = "display:flex;align-items:center;gap:8px;cursor:pointer";
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.value = t.value; cb.checked = true;
    cb.style.cssText = "width:15px;height:15px;cursor:pointer";
    cb.addEventListener("change", exportTypeCbChanged);
    lbl.appendChild(cb);
    lbl.appendChild(document.createTextNode(t.label));
    list.appendChild(lbl);
  });
  openModal("modal-export-per-type");
}

function exportTypeAllChanged() {
  const checked = document.getElementById("export-type-all").checked;
  document.querySelectorAll("#export-type-list input[type=checkbox]")
    .forEach(cb => { cb.checked = checked; });
}

function exportTypeCbChanged() {
  const all = [...document.querySelectorAll("#export-type-list input[type=checkbox]")];
  document.getElementById("export-type-all").checked = all.every(cb => cb.checked);
}

function doExportPerType() {
  const from   = readDatePicker("absence-from-dp");
  const to     = readDatePicker("absence-to-dp");
  const allCb  = document.getElementById("export-type-all");
  const selected = [...document.querySelectorAll("#export-type-list input[type=checkbox]:checked")]
    .map(cb => cb.value);

  const p = new URLSearchParams();
  if (from && to) { p.set("date_from", from); p.set("date_to", to); }
  if (!allCb.checked && selected.length > 0) {
    selected.forEach(v => p.append("absence_type", v));
  }
  const qs = p.toString() ? "?" + p.toString() : "";
  window.location.href = `/api/absence-overview/export-per-type${qs}`;
  closeModal("modal-export-per-type");
}

// ── Auth ───────────────────────────────────────────────────────────────────
function showLoginOverlay() {
  const el = document.getElementById("login-overlay");
  el.style.display = "flex";
  document.getElementById("login-error").style.display = "none";
  document.getElementById("login-initials").value = "";
  document.getElementById("login-password").value = "";
  setTimeout(() => document.getElementById("login-initials").focus(), 50);
}

function hideLoginOverlay() {
  document.getElementById("login-overlay").style.display = "none";
}

async function doLogin() {
  const initials = document.getElementById("login-initials").value.trim().toUpperCase();
  const password = document.getElementById("login-password").value;
  if (!initials || !password) {
    showLoginError("Angiv initialer og adgangskode");
    return;
  }
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initials, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg = typeof err.detail === "string" ? err.detail : "Login mislykkedes";
      showLoginError(msg);
      return;
    }
    const user = await res.json();
    state.currentUser = user;
    hideLoginOverlay();
    applyRoleVisibility();
    updateHeaderUser();
    await loadApp();
  } catch (e) {
    showLoginError("Netværksfejl – prøv igen");
  }
}

function showLoginError(msg) {
  const el = document.getElementById("login-error");
  el.textContent = msg;
  el.style.display = "block";
  const card = document.getElementById("login-card");
  card.classList.remove("login-shake");
  void card.offsetWidth; // reflow for at genstartte animationen
  card.classList.add("login-shake");
  card.addEventListener("animationend", () => card.classList.remove("login-shake"), { once: true });
}

async function doLogout() {
  const userName = state.currentUser?.name || "";
  try { await api("POST", "/api/auth/logout", {}); } catch {}

  const farewell = document.createElement("div");
  farewell.style.cssText = "position:fixed;inset:0;background:#317423;z-index:10000;display:flex;align-items:center;justify-content:center;transition:opacity .35s";
  farewell.innerHTML = `<p style="color:#fff;font-size:30px;font-weight:700;margin:0;letter-spacing:.5px">På gensyn${userName ? ", " + h(userName) : ""}!</p>`;
  document.body.appendChild(farewell);

  await new Promise(r => setTimeout(r, 2000));

  // Nulstil state og vis login mens farewell-overlay stadig dækker (z-index 10000)
  state.currentUser = null;
  showLoginOverlay();
  document.getElementById("header-user").style.display = "none";
  document.getElementById("btn-logout").style.display = "none";

  // Fade det grønne overlay ud – afslører login-skærmen, ikke appen
  farewell.style.opacity = "0";
  await new Promise(r => setTimeout(r, 350));
  farewell.remove();
}

function applyRoleVisibility() {
  const perms = state.currentUser?.permissions || [];
  document.querySelectorAll("[data-perm-require]").forEach(el => {
    el.style.display = perms.includes(el.dataset.permRequire) ? "" : "none";
  });
}

function _roleDisplayName(roleName) {
  const r = state.roles.find(r => r.name === roleName);
  return r ? r.display_name : roleName;
}

function updateHeaderUser() {
  const u = state.currentUser;
  if (!u) return;
  const label = _roleDisplayName(u.role);
  document.getElementById("header-user").textContent = `${u.name} (${label})`;
  document.getElementById("header-user").style.display = "";
  document.getElementById("btn-logout").style.display = "";
}

async function doSSOLogin() {
  if (!window.msal || !ENTRA_TENANT_ID || !ENTRA_CLIENT_ID) return;
  const btn = document.getElementById("btn-sso-login");
  if (btn) { btn.disabled = true; btn.style.opacity = "0.6"; }
  try {
    const msalInstance = new msal.PublicClientApplication({
      auth: {
        clientId: ENTRA_CLIENT_ID,
        authority: `https://login.microsoftonline.com/${ENTRA_TENANT_ID}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    const result = await msalInstance.loginPopup({
      scopes: ["openid", "profile", "email"],
    });
    const res = await fetch("/api/auth/sso", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: result.idToken }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showLoginError(typeof err.detail === "string" ? err.detail : "SSO fejlede – er din Entra-konto tilknyttet en bruger i systemet?");
      return;
    }
    const user = await res.json();
    state.currentUser = user;
    hideLoginOverlay();
    applyRoleVisibility();
    updateHeaderUser();
    await loadApp();
  } catch (e) {
    const code = String(e?.errorCode || e?.message || "");
    if (!code.includes("user_cancelled") && !code.includes("interaction_in_progress")) {
      showLoginError("Microsoft-login fejlede – prøv igen");
    }
  } finally {
    if (btn) { btn.disabled = false; btn.style.opacity = "1"; }
  }
}

async function attemptSSO() {
  if (!window.msal || !ENTRA_TENANT_ID || !ENTRA_CLIENT_ID) return false;
  try {
    const msalInstance = new msal.PublicClientApplication({
      auth: {
        clientId: ENTRA_CLIENT_ID,
        authority: `https://login.microsoftonline.com/${ENTRA_TENANT_ID}`,
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    });
    let result;
    const accounts = msalInstance.getAllAccounts();
    if (accounts.length > 0) {
      result = await msalInstance.acquireTokenSilent({
        account: accounts[0],
        scopes: ["openid", "profile", "email"],
      });
    } else {
      result = await msalInstance.ssoSilent({
        scopes: ["openid", "profile", "email"],
      });
    }
    const res = await fetch("/api/auth/sso", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: result.idToken }),
    });
    if (!res.ok) return false;
    const user = await res.json();
    state.currentUser = user;
    hideLoginOverlay();
    updateHeaderUser();
    applyRoleVisibility();
    return true;
  } catch {
    return false;
  }
}

async function initAuth() {
  try {
    const user = await fetch("/api/auth/me").then(r => r.ok ? r.json() : null);
    if (user) {
      state.currentUser = user;
      hideLoginOverlay();
      applyRoleVisibility();
      updateHeaderUser();
      return true;
    }
  } catch {}
  const ssoOk = await attemptSSO();
  if (ssoOk) return true;
  showLoginOverlay();
  return false;
}

// ── Administration ─────────────────────────────────────────────────────────
function switchAdminTab(tab) {
  ["users", "period", "log"].forEach(t => {
    document.getElementById(`admin-pane-${t}`).style.display = t === tab ? "" : "none";
    const btn = document.getElementById(`admin-tab-${t}`);
    btn.style.background = t === tab ? "var(--primary)" : "var(--bg)";
    btn.style.color = t === tab ? "#fff" : "var(--text)";
  });
  if (tab === "users") loadUsersTable();
  if (tab === "log") loadAuditLog();
}

async function openAdminModal() {
  const p = state.periodInfo?.period;
  const fmt = iso => new Date(iso + "T00:00:00").toLocaleDateString("da-DK", { day: "numeric", month: "long", year: "numeric" });
  const periodTxt = p ? `${fmt(p.start_date)} – ${fmt(p.end_date)}` : "den aktuelle periode";
  document.getElementById("admin-period-text").innerHTML =
    `Vil du åbne lønperioden <strong>${periodTxt}</strong> igen?`;
  document.getElementById("admin-result").textContent = "";
  switchAdminTab("period");
  openModal("modal-admin");
}

async function loadUsersTable() {
  if (!state.roles.length) {
    try { state.roles = await GET("/api/roles"); } catch {}
  }
  try {
    const users = await GET("/api/users");
    const tbody = document.getElementById("users-table-body");
    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text-light)">Ingen brugere</td></tr>`;
      return;
    }
    tbody.innerHTML = users.map(u => `
      <tr style="border-bottom:1px solid var(--border);${!u.active ? "opacity:.55" : ""}">
        <td style="padding:8px 10px">${h(u.name)}</td>
        <td style="padding:8px 10px;font-weight:600">${h(u.initials)}</td>
        <td style="padding:8px 10px">${h(u.email || "")}</td>
        <td style="padding:8px 10px">${_roleDisplayName(u.role)}</td>
        <td style="padding:8px 10px">
          <span style="padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;
            background:${u.active ? "#d4edcc" : "#eee"};color:${u.active ? "#317423" : "#888"}">
            ${u.active ? "Aktiv" : "Inaktiv"}
          </span>
        </td>
        <td style="padding:8px 10px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" onclick="openEditUserModal(${u.id})" style="font-size:12px;padding:4px 8px">Rediger</button>
          ${u.id !== state.currentUser?.id ? `
          <button class="btn btn-${u.active ? "danger" : "primary"}" onclick="toggleUserActive(${u.id},${u.active})"
                  style="font-size:12px;padding:4px 8px;margin-left:4px">
            ${u.active ? "Deaktiver" : "Aktiver"}
          </button>` : ""}
        </td>
      </tr>`).join("");
  } catch (e) { toast(e.message, "error"); }
}

async function loadAuditLog() {
  try {
    const entries = await GET("/api/users/audit-log");
    const actionLabels = {
      approve: "Godkendt", deactivate: "Deaktiveret", reopen: "Genåbnet",
      split: "Splittet", create_activity: "Oprettet aktivitet", update_activity: "Opdateret aktivitet",
      payroll_run: "Løn kørt", create_user: "Bruger oprettet", update_user: "Bruger opdateret",
      delete_user: "Bruger slettet",
    };
    const tbody = document.getElementById("audit-log-body");
    if (!entries.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--text-light)">Ingen hændelser</td></tr>`;
      return;
    }
    tbody.innerHTML = entries.map(e => {
      const ts = e.timestamp ? new Date(e.timestamp).toLocaleString("da-DK") : "";
      return `<tr style="border-bottom:1px solid var(--border)">
        <td style="padding:6px 10px">${ts}</td>
        <td style="padding:6px 10px;font-weight:600">${h(e.user_initials || "")}</td>
        <td style="padding:6px 10px">${h(actionLabels[e.action] || e.action)}</td>
        <td style="padding:6px 10px;color:var(--text-light)">${h(e.details || "")}</td>
      </tr>`;
    }).join("");
  } catch (e) { toast(e.message, "error"); }
}

async function _populateRoleDropdown(selectId, selectedValue) {
  try {
    if (!state.roles.length) state.roles = await GET("/api/roles");
    const sel = document.getElementById(selectId);
    sel.innerHTML = state.roles.map(r =>
      `<option value="${r.name}"${r.name === selectedValue ? " selected" : ""}>${r.display_name}</option>`
    ).join("");
  } catch {
    const sel = document.getElementById(selectId);
    if (sel) sel.innerHTML = `<option value="${selectedValue || ""}">${selectedValue || "Fejl"}</option>`;
  }
}

let _editUserId = null;
async function openCreateUserModal() {
  _editUserId = null;
  document.getElementById("user-form-title").textContent = "Opret bruger";
  document.getElementById("user-form-id").value = "";
  document.getElementById("user-form-name").value = "";
  document.getElementById("user-form-initials").value = "";
  document.getElementById("user-form-email").value = "";
  document.getElementById("user-form-password").value = "";
  document.getElementById("user-form-password-label").innerHTML = "Adgangskode <span style='color:var(--danger)'>*</span>";
  document.getElementById("user-form-password-hint").style.display = "none";
  await _populateRoleDropdown("user-form-role", "lonbogholder");
  openModal("modal-user-form");
}

async function openEditUserModal(userId) {
  try {
    const users = await GET("/api/users");
    const u = users.find(x => x.id === userId);
    if (!u) return;
    _editUserId = userId;
    document.getElementById("user-form-title").textContent = "Rediger bruger";
    document.getElementById("user-form-id").value = u.id;
    document.getElementById("user-form-name").value = u.name;
    document.getElementById("user-form-initials").value = u.initials;
    document.getElementById("user-form-email").value = u.email || "";
    document.getElementById("user-form-password").value = "";
    document.getElementById("user-form-password-label").textContent = "Ny adgangskode";
    document.getElementById("user-form-password-hint").style.display = "";
    await _populateRoleDropdown("user-form-role", u.role);
    openModal("modal-user-form");
  } catch (e) { toast(e.message, "error"); }
}

async function submitUserForm() {
  const name = document.getElementById("user-form-name").value.trim();
  const initials = document.getElementById("user-form-initials").value.trim().toUpperCase();
  const email = document.getElementById("user-form-email").value.trim();
  const role = document.getElementById("user-form-role").value;
  const password = document.getElementById("user-form-password").value;

  if (!name || !initials) { toast("Navn og initialer er påkrævet", "error"); return; }
  if (!_editUserId && !password) { toast("Adgangskode er påkrævet", "error"); return; }

  try {
    if (_editUserId) {
      const body = { name, initials, email, role };
      if (password) body.password = password;
      await api("PATCH", `/api/users/${_editUserId}`, body);
      toast("Bruger opdateret");
    } else {
      await api("POST", "/api/users", { name, initials, email, role, password });
      toast("Bruger oprettet", "success");
    }
    closeModal("modal-user-form");
    refreshUserViews();
  } catch (e) { toast(e.message, "error"); }
}

async function toggleUserActive(userId, currentlyActive) {
  try {
    await api("PATCH", `/api/users/${userId}`, { active: !currentlyActive });
    toast(currentlyActive ? "Bruger deaktiveret" : "Bruger aktiveret");
    refreshUserViews();
  } catch (e) { toast(e.message, "error"); }
}

function refreshUserViews() {
  if (state.currentView === "users-admin") {
    if (state.usersAdminTab === "users") loadUsersInAdminView();
    else if (state.usersAdminTab === "roles") loadRolesAdminView();
  }
  if (document.getElementById("modal-admin")?.classList.contains("open")) loadUsersTable();
}

function switchUsersAdminTab(tab) {
  state.usersAdminTab = tab;
  ["users", "roles", "log"].forEach(t => {
    const pane = document.getElementById(`ua-pane-${t}`);
    const btn  = document.getElementById(`ua-tab-${t}`);
    if (pane) pane.style.display = t === tab ? "" : "none";
    if (btn) {
      btn.style.borderBottomColor = t === tab ? "var(--primary)" : "transparent";
      btn.style.color = t === tab ? "var(--primary)" : "var(--text-light)";
      btn.style.fontWeight = t === tab ? "700" : "600";
    }
  });
  const btnUsers = document.getElementById("btn-admin-users-create");
  const btnRoles = document.getElementById("btn-admin-roles-create");
  if (btnUsers) btnUsers.style.display = tab === "users" ? "" : "none";
  if (btnRoles) btnRoles.style.display = tab === "roles" ? "" : "none";

  if (tab === "roles") loadRolesAdminView();
  if (tab === "log")   loadAuditLogView();
}

async function loadUsersAdminView() {
  if (!state.roles.length) {
    try { state.roles = await GET("/api/roles"); } catch {}
  }
  if (!state.usersAdminTab) state.usersAdminTab = "users";
  switchUsersAdminTab(state.usersAdminTab);
  if (state.usersAdminTab === "users") await loadUsersInAdminView();
}

async function loadUsersInAdminView() {
  const tbody = document.getElementById("users-admin-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const users = await GET("/api/users");
    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--text-light)">Ingen brugere oprettet endnu</td></tr>`;
      return;
    }
    tbody.innerHTML = users.map((u, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"};${!u.active ? "opacity:.5" : ""}">
        <td style="padding:11px 14px">${h(u.name)}</td>
        <td style="padding:11px 14px;font-weight:600;font-family:monospace">${h(u.initials)}</td>
        <td style="padding:11px 14px;color:var(--text-light)">${h(u.email || "—")}</td>
        <td style="padding:11px 14px">${_roleDisplayName(u.role)}</td>
        <td style="padding:11px 14px">
          <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;
            background:${u.active ? "#d4edcc" : "#eee"};color:${u.active ? "#317423" : "#999"}">
            ${u.active ? "Aktiv" : "Inaktiv"}
          </span>
        </td>
        <td style="padding:11px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" onclick="openEditUserModal(${u.id})"
                  style="font-size:13px;padding:5px 12px">✏️ Rediger</button>
          ${u.id !== state.currentUser?.id ? `
          <button class="btn btn-${u.active ? "danger" : "primary"}"
                  onclick="toggleUserActive(${u.id}, ${u.active})"
                  style="font-size:13px;padding:5px 12px;margin-left:6px">
            ${u.active ? "Deaktiver" : "Aktiver"}
          </button>` : `<span style="font-size:12px;color:var(--text-light);margin-left:8px">(dig selv)</span>`}
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

// ── Roller-admin ────────────────────────────────────────────────────────────
async function loadRolesAdminView() {
  const tbody = document.getElementById("roles-admin-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    state.roles = await GET("/api/roles");
    if (!state.roles.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--text-light)">Ingen roller</td></tr>`;
      return;
    }
    tbody.innerHTML = state.roles.map((r, i) => {
      const effectivePerms = r.is_system ? Object.keys(PERMISSION_LABELS) : (r.permissions || []);
      const chips = effectivePerms.map(p =>
        `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#d4edcc;color:#317423;margin:2px">${PERMISSION_LABELS[p] || p}</span>`
      ).join("") || `<span style="font-size:12px;color:var(--text-light)">Ingen rettigheder</span>`;
      const systemBadge = r.is_system
        ? `<span style="font-size:10px;background:#e0e0e0;color:#555;padding:1px 6px;border-radius:8px;margin-left:6px;font-family:sans-serif">system</span>` : "";
      return `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:11px 14px;font-family:monospace;font-weight:600">${r.name}${systemBadge}</td>
        <td style="padding:11px 14px">${r.display_name}</td>
        <td style="padding:11px 14px">${chips}</td>
        <td style="padding:11px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" onclick="openEditRoleModal(${r.id})"
                  style="font-size:13px;padding:5px 12px">✏️ Rediger</button>
          ${!r.is_system ? `
          <button class="btn btn-danger" onclick="deleteRole(${r.id}, '${r.display_name.replace(/'/g, "\\'")}' )"
                  style="font-size:13px;padding:5px 12px;margin-left:6px">🗑 Slet</button>` : ""}
        </td>
      </tr>`;
    }).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

let _editRoleId = null;

function openCreateRoleModal() {
  _editRoleId = null;
  document.getElementById("role-form-title").textContent = "Opret rolle";
  document.getElementById("role-form-id").value = "";
  document.getElementById("role-form-name").value = "";
  document.getElementById("role-form-name").disabled = false;
  document.getElementById("role-form-name-hint").style.display = "";
  document.getElementById("role-form-display").value = "";
  _renderPermCheckboxes([], false);
  openModal("modal-role-form");
}

function openEditRoleModal(roleId) {
  const role = state.roles.find(r => r.id === roleId);
  if (!role) return;
  _editRoleId = roleId;
  document.getElementById("role-form-title").textContent = `Rediger: ${role.display_name}`;
  document.getElementById("role-form-id").value = role.id;
  document.getElementById("role-form-name").value = role.name;
  document.getElementById("role-form-name").disabled = true;
  document.getElementById("role-form-name-hint").style.display = "none";
  document.getElementById("role-form-display").value = role.display_name;
  _renderPermCheckboxes(role.permissions || [], role.is_system);
  openModal("modal-role-form");
}

function _renderPermCheckboxes(selectedPerms, isSystem) {
  const effectivePerms = isSystem ? Object.keys(PERMISSION_LABELS) : selectedPerms;
  document.getElementById("role-form-permissions").innerHTML =
    Object.entries(PERMISSION_LABELS).map(([key, label]) => `
      <label style="display:flex;align-items:center;gap:10px;cursor:${isSystem ? "default" : "pointer"};font-size:14px">
        <input type="checkbox" value="${key}" ${effectivePerms.includes(key) ? "checked" : ""}
               ${isSystem ? "disabled" : ""}
               style="width:15px;height:15px;accent-color:var(--primary);cursor:${isSystem ? "default" : "pointer"}">
        ${label}
      </label>`).join("") +
    (isSystem ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px;font-style:italic">Systemrollers rettigheder kan ikke ændres</p>` : "");
}

async function submitRoleForm() {
  const display = document.getElementById("role-form-display").value.trim();
  const name    = document.getElementById("role-form-name").value.trim();
  if (!display) { toast("Visningsnavn er påkrævet", "error"); return; }
  if (!_editRoleId && !name) { toast("Rollenavn er påkrævet", "error"); return; }
  if (!_editRoleId && !/^[a-z0-9_]+$/.test(name)) {
    toast("Rollenavn: kun små bogstaver, tal og underscore", "error"); return;
  }
  const permissions = [...document.querySelectorAll("#role-form-permissions input:checked")].map(cb => cb.value);
  try {
    if (_editRoleId) {
      await api("PATCH", `/api/roles/${_editRoleId}`, { display_name: display, permissions });
      toast("Rolle opdateret");
    } else {
      await api("POST", "/api/roles", { name, display_name: display, permissions });
      toast("Rolle oprettet", "success");
    }
    closeModal("modal-role-form");
    state.roles = [];
    loadRolesAdminView();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteRole(roleId, displayName) {
  if (!confirm(`Vil du slette rollen "${displayName}"?\nDette kan ikke fortrydes.`)) return;
  try {
    await api("DELETE", `/api/roles/${roleId}`);
    toast(`Rollen "${displayName}" er slettet`);
    state.roles = [];
    loadRolesAdminView();
  } catch (e) { toast(e.message, "error"); }
}

// ── Stamdata ────────────────────────────────────────────────────────────────

function switchStamdataTab(tab) {
  ["agreement", "overtime", "supplement", "paytype", "absence", "cvr", "holiday", "dispatcher"].forEach(t => {
    const pane = document.getElementById(`sd-pane-${t}`);
    const btn  = document.getElementById(`sd-tab-${t}`);
    if (pane) pane.style.display = t === tab ? "" : "none";
    if (btn) {
      btn.style.borderBottomColor = t === tab ? "var(--primary)" : "transparent";
      btn.style.color             = t === tab ? "var(--primary)" : "var(--text-light)";
      btn.style.fontWeight        = t === tab ? "700" : "600";
    }
  });
  document.getElementById("btn-stamdata-add-agreement").style.display  = tab === "agreement"  ? "" : "none";
  document.getElementById("btn-stamdata-add-overtime").style.display   = tab === "overtime"   ? "" : "none";
  document.getElementById("btn-stamdata-add-supplement").style.display = tab === "supplement" ? "" : "none";
  document.getElementById("btn-stamdata-add-paytype").style.display    = tab === "paytype"    ? "" : "none";
  document.getElementById("btn-stamdata-add-absence").style.display    = tab === "absence"    ? "" : "none";
  document.getElementById("btn-stamdata-add-cvr").style.display        = tab === "cvr"        ? "" : "none";
  document.getElementById("btn-stamdata-add-holiday").style.display    = tab === "holiday"    ? "" : "none";
  document.getElementById("btn-stamdata-add-dispatcher").style.display = tab === "dispatcher" ? "" : "none";
}

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
    loadStamdataDispatcherGroups(),
  ]);
}

async function loadStamdataAgreementTypes() {
  const tbody = document.getElementById("stamdata-agreement-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/agreement-types");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Ingen overenskomsttyper oprettet endnu</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${r.hourly_rate.toFixed(2).replace(".", ",")} kr</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataAgreementModal(${r.id}, ${jq(r.name)}, ${r.hourly_rate})">Rediger</button>
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataAgreement(${r.id}, ${jq(r.name)})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

async function loadStamdataOvertimeRates() {
  const tbody = document.getElementById("stamdata-overtime-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/overtime-rates");
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${r.rate.toFixed(2).replace(".", ",")} kr</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataRateModal(${r.id}, ${jq(r.label)}, ${r.rate}, 'overtime')">Rediger</button>
          ${r.is_user_created ? `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataRate(${r.id}, ${jq(r.label)}, 'overtime')">Slet</button>` : ""}
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

async function loadStamdataSupplements() {
  const tbody = document.getElementById("stamdata-supplement-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/supplements");
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums">${r.rate.toFixed(2).replace(".", ",")} kr</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataRateModal(${r.id}, ${jq(r.label)}, ${r.rate}, 'supplement')">Rediger</button>
          ${r.is_user_created ? `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataRate(${r.id}, ${jq(r.label)}, 'supplement')">Slet</button>` : ""}
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

const _RATE_SRC_LABELS = {
  hourly: "Timesats", ot_before: "OT 1t før", ot_13: "OT 1-3t",
  ot_extra: "Øvrig OT", salt: "Salt", overnight: "Overnatning", dagpenge: "Dagpenge §56",
};

async function loadStamdataPayTypes() {
  const tbody = document.getElementById("stamdata-paytype-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="7" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/pay-types");
    tbody.innerHTML = rows.map((r, i) => {
      const badge = (v, yes, no) => v
        ? `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#d4edcc;color:#317423">${yes}</span>`
        : `<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;background:#fee2e2;color:#b71c1c">${no}</span>`;
      const qtyLabel = r.csv_quantity_type === "count" ? "Antal" : "Timer";
      const rateLabel = _RATE_SRC_LABELS[r.csv_rate_source] || r.csv_rate_source;
      return `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:center;font-family:monospace;font-weight:600">${h(r.danloen_code) || '<span style="color:var(--text-light);font-style:italic;font-weight:400">ikke sat</span>'}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.include_in_csv, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center;font-size:12px">${h(qtyLabel)}</td>
        <td style="padding:10px 14px;text-align:center;font-size:12px">${h(rateLabel)}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.csv_include_rate, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.csv_include_total, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openStamdataPayTypeModal(${r.id}, ${jq(r.label)}, ${jq(r.danloen_code)}, ${r.include_in_csv}, ${jq(r.csv_quantity_type)}, ${jq(r.csv_rate_source)}, ${r.csv_include_rate}, ${r.csv_include_total})">Rediger</button>
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                  onclick="deleteStamdataPayType(${r.id}, ${jq(r.label)})">Slet</button>
        </td>
      </tr>`;
    }).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function openStamdataAgreementModal(id, name, rate) {
  document.getElementById("stamdata-agreement-id").value   = id   || "";
  document.getElementById("stamdata-agreement-name").value = name || "";
  document.getElementById("stamdata-agreement-rate").value = rate !== undefined ? rate : "";
  document.getElementById("stamdata-agreement-title").textContent =
    id ? "Rediger overenskomsttype" : "Tilføj overenskomsttype";
  openModal("modal-stamdata-agreement");
}

async function confirmStamdataAgreement() {
  const id   = document.getElementById("stamdata-agreement-id").value;
  const name = document.getElementById("stamdata-agreement-name").value.trim();
  const rate = parseFloat(document.getElementById("stamdata-agreement-rate").value);
  if (!name || isNaN(rate)) { toast("Udfyld navn og timesats", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/agreement-types/${id}`, { name, hourly_rate: rate });
      toast("Overenskomsttype opdateret");
    } else {
      await POST("/api/stamdata/agreement-types", { name, hourly_rate: rate });
      toast("Overenskomsttype oprettet");
    }
    closeModal("modal-stamdata-agreement");
    await loadStamdataAgreementTypes();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataAgreement(id, name) {
  if (!confirm(`Slet overenskomsttypen "${name}"?`)) return;
  try {
    await DEL(`/api/stamdata/agreement-types/${id}`);
    toast("Overenskomsttype slettet");
    await loadStamdataAgreementTypes();
  } catch (e) { toast(e.message, "error"); }
}

function openStamdataRateModal(id, label, rate, type) {
  document.getElementById("stamdata-rate-id").value = id;
  document.getElementById("stamdata-rate-type").value = type;
  document.getElementById("stamdata-rate-label-display").textContent = label;
  document.getElementById("stamdata-rate-value").value = rate;
  document.getElementById("stamdata-rate-title").textContent =
    type === "overtime" ? "Rediger overtidssats" : "Rediger tillægssats";
  openModal("modal-stamdata-rate");
}

async function confirmStamdataRate() {
  const id   = document.getElementById("stamdata-rate-id").value;
  const type = document.getElementById("stamdata-rate-type").value;
  const rate = parseFloat(document.getElementById("stamdata-rate-value").value);
  if (isNaN(rate)) { toast("Ugyldig sats", "error"); return; }
  const url = type === "overtime"
    ? `/api/stamdata/overtime-rates/${id}`
    : `/api/stamdata/supplements/${id}`;
  try {
    await PATCH(url, { rate });
    toast("Sats opdateret");
    closeModal("modal-stamdata-rate");
    if (type === "overtime") await loadStamdataOvertimeRates();
    else                     await loadStamdataSupplements();
  } catch (e) { toast(e.message, "error"); }
}

function openStamdataPayTypeModal(id, label, code, inCsv, qtyType, rateSrc, incRate, incTotal) {
  document.getElementById("stamdata-paytype-id").value = id;
  document.getElementById("stamdata-paytype-label").value = label || "";
  document.getElementById("stamdata-paytype-code").value = code || "";
  document.getElementById("stamdata-paytype-incsv").checked = !!inCsv;
  document.getElementById("stamdata-paytype-qtytype").value = qtyType || "hours";
  document.getElementById("stamdata-paytype-ratesrc").value = rateSrc || "hourly";
  document.getElementById("stamdata-paytype-incrate").checked = incRate !== false;
  document.getElementById("stamdata-paytype-inctotal").checked = !!incTotal;
  openModal("modal-stamdata-paytype");
}

async function confirmStamdataPayType() {
  const id       = document.getElementById("stamdata-paytype-id").value;
  const label    = document.getElementById("stamdata-paytype-label").value.trim();
  const code     = document.getElementById("stamdata-paytype-code").value.trim();
  const inCsv    = document.getElementById("stamdata-paytype-incsv").checked;
  const qtyType  = document.getElementById("stamdata-paytype-qtytype").value;
  const rateSrc  = document.getElementById("stamdata-paytype-ratesrc").value;
  const incRate  = document.getElementById("stamdata-paytype-incrate").checked;
  const incTotal = document.getElementById("stamdata-paytype-inctotal").checked;
  if (!label) { toast("Type må ikke være tom", "error"); return; }
  try {
    await PATCH(`/api/stamdata/pay-types/${id}`, {
      label, danloen_code: code, include_in_csv: inCsv,
      csv_quantity_type: qtyType, csv_rate_source: rateSrc,
      csv_include_rate: incRate, csv_include_total: incTotal,
    });
    toast("Løntypekode opdateret");
    closeModal("modal-stamdata-paytype");
    await loadStamdataPayTypes();
  } catch (e) { toast(e.message, "error"); }
}

function openNewRateModal(type) {
  document.getElementById("new-rate-type").value = type;
  document.getElementById("new-rate-title").textContent =
    type === "overtime" ? "Opret ny overtidssats" : "Opret nyt tillæg";
  document.getElementById("new-rate-label").value = "";
  document.getElementById("new-rate-value").value = "";
  openModal("modal-stamdata-new-rate");
}

async function confirmNewRate() {
  const type  = document.getElementById("new-rate-type").value;
  const label = document.getElementById("new-rate-label").value.trim();
  const rate  = parseFloat(document.getElementById("new-rate-value").value);
  if (!label) { toast("Betegnelse er påkrævet", "error"); return; }
  if (isNaN(rate) || rate <= 0) { toast("Sats skal være større end 0", "error"); return; }
  const url = type === "overtime" ? "/api/stamdata/overtime-rates" : "/api/stamdata/supplements";
  try {
    await POST(url, { label, rate });
    closeModal("modal-stamdata-new-rate");
    toast("Sats oprettet");
    if (type === "overtime") await loadStamdataOvertimeRates();
    else                     await loadStamdataSupplements();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataRate(id, label, type) {
  if (!confirm(`Slet "${label}"?`)) return;
  const url = type === "overtime"
    ? `/api/stamdata/overtime-rates/${id}`
    : `/api/stamdata/supplements/${id}`;
  try {
    await DEL(url);
    toast("Slettet");
    if (type === "overtime") await loadStamdataOvertimeRates();
    else                     await loadStamdataSupplements();
  } catch (e) { toast(e.message, "error"); }
}

function openNewPayTypeModal() {
  document.getElementById("new-paytype-label").value = "";
  document.getElementById("new-paytype-code").value  = "";
  document.getElementById("new-paytype-incsv").checked = true;
  document.getElementById("new-paytype-qtytype").value = "hours";
  document.getElementById("new-paytype-ratesrc").value = "hourly";
  document.getElementById("new-paytype-incrate").checked = true;
  document.getElementById("new-paytype-inctotal").checked = false;
  openModal("modal-stamdata-new-paytype");
}

async function confirmNewPayType() {
  const label    = document.getElementById("new-paytype-label").value.trim();
  const code     = document.getElementById("new-paytype-code").value.trim();
  const inCsv    = document.getElementById("new-paytype-incsv").checked;
  const qtyType  = document.getElementById("new-paytype-qtytype").value;
  const rateSrc  = document.getElementById("new-paytype-ratesrc").value;
  const incRate  = document.getElementById("new-paytype-incrate").checked;
  const incTotal = document.getElementById("new-paytype-inctotal").checked;
  if (!label) { toast("Betegnelse er påkrævet", "error"); return; }
  try {
    await POST("/api/stamdata/pay-types", {
      label, danloen_code: code, include_in_csv: inCsv,
      csv_quantity_type: qtyType, csv_rate_source: rateSrc,
      csv_include_rate: incRate, csv_include_total: incTotal,
    });
    closeModal("modal-stamdata-new-paytype");
    toast("Løntypekode oprettet");
    await loadStamdataPayTypes();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataPayType(id, label) {
  if (!confirm(`Slet "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/pay-types/${id}`);
    toast("Slettet");
    await loadStamdataPayTypes();
  } catch (e) { toast(e.message, "error"); }
}

// ── Fraværstyper (stamdata) ─────────────────────────────────────────────────

async function loadStamdataAbsenceTypes() {
  const tbody = document.getElementById("stamdata-absence-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/absence-types");
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;font-family:monospace;font-size:12px;color:var(--text-light)">${h(r.normalized_key)}</td>
        <td style="padding:10px 14px;text-align:center">
          <span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;
                       background:${r.is_active ? "var(--light-tint)" : "#f5f5f5"};
                       color:${r.is_active ? "var(--primary)" : "var(--text-light)"}">
            ${r.is_active ? "Aktiv" : "Inaktiv"}
          </span>
        </td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataAbsenceModal(${r.id},${jq(r.label)},${r.is_active},${r.is_user_created})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataAbsence(${r.id},${jq(r.label)})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
}

function openStamdataAbsenceModal(id, label, isActive, isUserCreated) {
  document.getElementById("stamdata-absence-id").value = id || "";
  document.getElementById("stamdata-absence-label").value = label || "";
  document.getElementById("stamdata-absence-active").checked = isActive !== false;
  const keyGroup = document.getElementById("stamdata-absence-key-group");
  if (id) {
    keyGroup.style.display = "none";
  }
  document.getElementById("stamdata-absence-title").textContent = id ? "Rediger fraværstype" : "Ny fraværstype";
  openModal("modal-stamdata-absence");
}

async function confirmStamdataAbsence() {
  const id      = document.getElementById("stamdata-absence-id").value;
  const label   = document.getElementById("stamdata-absence-label").value.trim();
  const active  = document.getElementById("stamdata-absence-active").checked;
  if (!label) { toast("Betegnelse er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/absence-types/${id}`, { label, is_active: active });
      toast("Fraværstype opdateret");
    } else {
      await POST("/api/stamdata/absence-types", { label, is_active: active });
      toast("Fraværstype oprettet");
    }
    closeModal("modal-stamdata-absence");
    await loadStamdataAbsenceTypes();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataAbsence(id, label) {
  if (!confirm(`Slet fraværstypen "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/absence-types/${id}`);
    toast("Fraværstype slettet");
    await loadStamdataAbsenceTypes();
  } catch (e) { toast(e.message, "error"); }
}

// ── Disponentgrupper (stamdata) ──────────────────────────────────────────────

async function loadStamdataDispatcherGroups() {
  const tbody = document.getElementById("stamdata-dispatcher-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/dispatcher-groups");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--text-light)">Ingen disponentgrupper oprettet endnu</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;color:var(--text-light)">${h(r.description || "")}</td>
        <td style="padding:10px 14px;text-align:center">${r.employee_count}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataDispatcherModal(${r.id},${jq(r.name)},${jq(r.description || "")})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataDispatcher(${r.id},${jq(r.name)},${r.employee_count})">Slet</button>
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="4" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
  // Ny/ændret gruppe kan påvirke medarbejder-modal og filtre
  try { state.dispatcherGroups = await GET("/api/employees/dispatcher-groups"); fillDispatcherGroupFilter(); } catch (_) {}
}

function openStamdataDispatcherModal(id, name, description) {
  document.getElementById("stamdata-dispatcher-id").value = id || "";
  document.getElementById("stamdata-dispatcher-name").value = name || "";
  document.getElementById("stamdata-dispatcher-description").value = description || "";
  document.getElementById("stamdata-dispatcher-title").textContent = id ? "Rediger disponentgruppe" : "Ny disponentgruppe";
  openModal("modal-stamdata-dispatcher");
}

async function confirmStamdataDispatcher() {
  const id   = document.getElementById("stamdata-dispatcher-id").value;
  const name = document.getElementById("stamdata-dispatcher-name").value.trim();
  const description = document.getElementById("stamdata-dispatcher-description").value.trim();
  if (!name) { toast("Navn er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/dispatcher-groups/${id}`, { name, description });
      toast("Disponentgruppe opdateret");
    } else {
      await POST("/api/stamdata/dispatcher-groups", { name, description });
      toast("Disponentgruppe oprettet");
    }
    closeModal("modal-stamdata-dispatcher");
    await loadStamdataDispatcherGroups();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataDispatcher(id, name, employeeCount) {
  const warn = employeeCount ? `\n${employeeCount} medarbejder(e) er tilknyttet og vil miste denne gruppe.` : "";
  if (!confirm(`Slet disponentgruppen "${name}"?${warn}`)) return;
  try {
    await DEL(`/api/stamdata/dispatcher-groups/${id}`);
    toast("Disponentgruppe slettet");
    await loadStamdataDispatcherGroups();
    await loadEmployees();
  } catch (e) { toast(e.message, "error"); }
}

// ── CVR-numre (stamdata) ─────────────────────────────────────────────────────

async function loadStamdataCvrNumbers() {
  const tbody = document.getElementById("stamdata-cvr-tbody");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    const rows = await GET("/api/stamdata/cvr-numbers");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--text-light)">Ingen CVR-numre oprettet endnu</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((r, i) => `
      <tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
        <td style="padding:10px 14px;font-family:monospace">${h(r.cvr_number)}</td>
        <td style="padding:10px 14px">${h(r.company_name)}</td>
        <td style="padding:10px 14px;text-align:center">
          ${r.is_default
            ? `<span style="background:var(--primary);color:#fff;padding:2px 10px;border-radius:12px;font-size:12px">Standard</span>`
            : `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                       onclick="setDefaultCvr(${r.id})">Sæt som standard</button>`}
        </td>
        <td style="padding:10px 14px;text-align:center;white-space:nowrap">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px"
                  onclick="openEditCvrModal(${r.id}, ${jq(r.cvr_number)}, ${jq(r.company_name)})">Rediger</button>
          ${!r.is_default
            ? `<button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;color:var(--danger);border-color:var(--danger);margin-left:4px"
                       onclick="deleteStamdataCvr(${r.id}, ${jq(r.cvr_number)})">Slet</button>`
            : ""}
        </td>
      </tr>
    `).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function openNewCvrModal() {
  document.getElementById("stamdata-cvr-id").value      = "";
  document.getElementById("stamdata-cvr-number").value  = "";
  document.getElementById("stamdata-cvr-company").value = "";
  document.getElementById("stamdata-cvr-title").textContent = "Opret CVR nummer";
  openModal("modal-stamdata-cvr");
}

function openEditCvrModal(id, cvrNumber, companyName) {
  document.getElementById("stamdata-cvr-id").value      = id;
  document.getElementById("stamdata-cvr-number").value  = cvrNumber;
  document.getElementById("stamdata-cvr-company").value = companyName;
  document.getElementById("stamdata-cvr-title").textContent = "Rediger CVR nummer";
  openModal("modal-stamdata-cvr");
}

async function confirmStamdataCvr() {
  const id      = document.getElementById("stamdata-cvr-id").value;
  const cvr     = document.getElementById("stamdata-cvr-number").value.trim();
  const company = document.getElementById("stamdata-cvr-company").value.trim();
  if (!cvr) { toast("CVR-nummer er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/cvr-numbers/${id}`, { cvr_number: cvr, company_name: company });
      toast("CVR nummer opdateret");
    } else {
      await POST("/api/stamdata/cvr-numbers", { cvr_number: cvr, company_name: company });
      toast("CVR nummer oprettet");
    }
    closeModal("modal-stamdata-cvr");
    await loadStamdataCvrNumbers();
  } catch (e) { toast(e.message, "error"); }
}

async function setDefaultCvr(id) {
  try {
    await POST(`/api/stamdata/cvr-numbers/${id}/set-default`, {});
    toast("Standard CVR opdateret");
    await loadStamdataCvrNumbers();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataCvr(id, label) {
  if (!confirm(`Slet CVR-nummeret "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/cvr-numbers/${id}`);
    toast("CVR nummer slettet");
    await loadStamdataCvrNumbers();
  } catch (e) { toast(e.message, "error"); }
}

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

// ── Hændelseslog ────────────────────────────────────────────────────────────
const ACTION_LABELS = {
  login:           { label: "Login",                    color: "#317423", bg: "#d4edcc" },
  approve:         { label: "Aktivitet godkendt",       color: "#1565c0", bg: "#dbeafe" },
  deactivate:      { label: "Aktivitet deaktiveret",    color: "#b71c1c", bg: "#fee2e2" },
  reopen_activity: { label: "Aktivitet genåbnet",       color: "#7b1fa2", bg: "#f3e8ff" },
  split:           { label: "Aktivitet splittet",       color: "#e65100", bg: "#fff3e0" },
  create_activity: { label: "Aktivitet oprettet",       color: "#00695c", bg: "#e0f2f1" },
  update_activity: { label: "Aktivitet ændret",         color: "#424242", bg: "#f5f5f5" },
  payroll_run:     { label: "Løn kørt",                 color: "#317423", bg: "#d4edcc" },
  reopen_period:   { label: "Lønperiode genåbnet",      color: "#e65100", bg: "#fff3e0" },
  create_user:     { label: "Bruger oprettet",          color: "#1565c0", bg: "#dbeafe" },
  update_user:     { label: "Bruger opdateret",         color: "#424242", bg: "#f5f5f5" },
  role_change:     { label: "Rolle ændret",             color: "#7b1fa2", bg: "#f3e8ff" },
  delete_user:     { label: "Bruger slettet",           color: "#b71c1c", bg: "#fee2e2" },
  create_role:     { label: "Rolle oprettet",           color: "#1565c0", bg: "#dbeafe" },
  update_role:     { label: "Rolle opdateret",          color: "#424242", bg: "#f5f5f5" },
  delete_role:     { label: "Rolle slettet",            color: "#b71c1c", bg: "#fee2e2" },
  stamdata_create: { label: "Stamdata oprettet",        color: "#00695c", bg: "#e0f2f1" },
  stamdata_update: { label: "Stamdata opdateret",       color: "#424242", bg: "#f5f5f5" },
  stamdata_delete: { label: "Stamdata slettet",         color: "#b71c1c", bg: "#fee2e2" },
  ddd_import:      { label: "DDD-import",               color: "#317423", bg: "#d4edcc" },
};

let _auditLogEntries = [];

async function loadAuditLogView() {
  const tbody = document.getElementById("audit-log-view-body");
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="4" style="padding:30px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>`;
  try {
    _auditLogEntries = await GET("/api/users/audit-log?limit=500");
    _renderAuditLog(_auditLogEntries);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="4" style="padding:30px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`;
  }
}

function filterAuditLog() {
  const q = (document.getElementById("log-filter-input")?.value || "").toLowerCase();
  const filtered = q ? _auditLogEntries.filter(e =>
    (e.user_initials || "").toLowerCase().includes(q) ||
    (ACTION_LABELS[e.action]?.label || e.action || "").toLowerCase().includes(q) ||
    (e.details || "").toLowerCase().includes(q)
  ) : _auditLogEntries;
  _renderAuditLog(filtered);
}

function _renderAuditLog(entries) {
  const tbody = document.getElementById("audit-log-view-body");
  if (!tbody) return;
  if (!entries.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="padding:30px;text-align:center;color:var(--text-light)">Ingen hændelser fundet</td></tr>`;
    return;
  }
  tbody.innerHTML = entries.map((e, i) => {
    const ts   = e.timestamp ? new Date(e.timestamp).toLocaleString("da-DK") : "—";
    const meta = ACTION_LABELS[e.action] || { label: e.action, color: "#555", bg: "#eee" };
    return `<tr style="border-bottom:1px solid var(--border);background:${i % 2 === 0 ? "#fff" : "var(--bg)"}">
      <td style="padding:10px 12px;white-space:nowrap;color:var(--text-light);font-size:12px">${ts}</td>
      <td style="padding:10px 12px;font-weight:700;font-family:monospace">${h(e.user_initials || "—")}</td>
      <td style="padding:10px 12px">
        <span style="display:inline-block;padding:3px 10px;border-radius:10px;font-size:12px;font-weight:600;
                     color:${meta.color};background:${meta.bg}">${h(meta.label)}</span>
      </td>
      <td style="padding:10px 12px;color:var(--text-light);font-size:13px">${h(e.details || "—")}</td>
    </tr>`;
  }).join("");
}

async function confirmReopenPeriod() {
  setLoading(true);
  try {
    await POST(`/api/payroll/reopen-period?period_start=${state.currentPeriodStart || ""}`, {});
    toast("Lønperioden er åbnet igen.", "success");
    closeModal("modal-admin");
    await loadPeriodInfo(state.currentPeriodStart);
    await loadActivities();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

// ── PDF timesedler ─────────────────────────────────────────────────────────
async function openPdfModal() {
  const p = state.periodInfo?.period;
  // Hent Downloads-mappe fra backend som forslag
  try {
    const res = await GET("/api/payroll/downloads-folder");
    document.getElementById("pdf-folder").value = res.path;
  } catch { /* lad feltet være tomt ved fejl */ }
  if (p) {
    document.getElementById("pdf-from").value = p.start_date;
    document.getElementById("pdf-to").value = p.end_date;
  }
  const sel = document.getElementById("pdf-employee");
  sel.innerHTML = `<option value="">Alle medarbejdere</option>` +
    state.employees.filter(e => e.active)
      .slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  document.getElementById("pdf-result").textContent = "";
  openModal("modal-pdf");
}

async function browsePdfFolder() {
  const btn = document.getElementById("pdf-browse-btn");
  btn.disabled = true;
  btn.textContent = "Venter...";
  try {
    const current = document.getElementById("pdf-folder").value.trim();
    const res = await GET(`/api/payroll/browse-folder?initial=${encodeURIComponent(current)}`);
    if (res.path) document.getElementById("pdf-folder").value = res.path;
  } catch (e) { toast("Kunne ikke åbne mappevælger", "error"); }
  finally { btn.disabled = false; btn.textContent = "Gennemse"; }
}

async function generatePdfs() {
  const from = document.getElementById("pdf-from").value;
  const to = document.getElementById("pdf-to").value;
  const folder = document.getElementById("pdf-folder").value.trim();
  if (!from || !to) { toast("Angiv fra- og til-dato", "error"); return; }
  if (!folder) { toast("Angiv en mappe at gemme PDF'erne i", "error"); return; }
  const empId = document.getElementById("pdf-employee").value;
  setLoading(true);
  try {
    const result = await POST("/api/payroll/pdf-timesedler", {
      from_date: from, to_date: to,
      employee_id: empId ? parseInt(empId) : null,
      output_folder: folder,
    });
    const msg = `${result.created.length} PDF'er dannet i ${result.folder}` +
      (result.skipped.length ? ` (${result.skipped.length} sprunget over uden aktiviteter)` : "");
    toast(msg, "success");
    closeModal("modal-pdf");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

async function sendAllTimesedler() {
  const from = document.getElementById("pdf-from").value;
  const to   = document.getElementById("pdf-to").value;
  const empId = document.getElementById("pdf-employee").value;
  if (!from || !to) { toast("Angiv fra- og til-dato", "error"); return; }

  const empName = empId
    ? (state.employees.find(e => e.id === parseInt(empId))?.name || "den valgte medarbejder")
    : "alle medarbejdere";
  if (!confirm(`Send timesedler til ${empName} for perioden ${from} – ${to}?`)) return;

  setLoading(true);
  try {
    const result = await POST("/api/timeseddel/send-all", {
      from_date: from,
      to_date: to,
      employee_id: empId ? parseInt(empId) : null,
    });
    let msg = `${result.sent.length} timeseddel${result.sent.length !== 1 ? "er" : ""} sendt`;
    if (result.skipped_no_email.length)       msg += `, ${result.skipped_no_email.length} uden e-mail`;
    if (result.skipped_no_activities.length)  msg += `, ${result.skipped_no_activities.length} uden aktiviteter`;
    if (result.failed.length)                 msg += `, ${result.failed.length} fejlede`;
    toast(msg, result.failed.length ? "error" : "success");
    if (!result.failed.length) closeModal("modal-pdf");
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString("da-DK", { day: "2-digit", month: "2-digit", year: "numeric" }) : "–";
}
function formatDateShort(iso) {
  if (!iso) return "–";
  const d = new Date(iso + (iso.length <= 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString("da-DK", { day: "numeric", month: "short", year: "numeric" });
}
function formatTime(iso) {
  return iso ? new Date(iso).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }) : "–";
}
function formatDateTime(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleDateString("da-DK", { day: "2-digit", month: "2-digit" }) + " " +
         d.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
}
function formatDuration(minutes) {
  return `${Math.floor(minutes / 60)}t ${(minutes % 60).toString().padStart(2, "0")}m`;
}
function fmtHours(h) { return `${h.toFixed(2)} t`; }
function fmtKr(v) {
  return v.toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " kr";
}
function statusLabel(s) {
  return { pending: "Afventer", approved: "Godkendt", deactivated: "Deaktiveret" }[s] || s;
}

function _empInGroup(emp, groupId) {
  return (emp.dispatcher_groups || []).some(g => String(g.id) === String(groupId));
}

function fillDispatcherGroupFilter() {
  const sel = document.getElementById("filter-dispatcher-group");
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = `<option value="">Alle afdelinger</option>` +
    state.dispatcherGroups.map(g => `<option value="${g.id}">${h(g.name)}</option>`).join("");
  if (state.dispatcherGroups.find(g => String(g.id) === cur)) sel.value = cur;
}

function fillEmployeeFilter() {
  const sel = document.getElementById("filter-employee");
  const cur = sel.value;
  const groupFilter = document.getElementById("filter-dispatcher-group")?.value || "";
  const visible = groupFilter
    ? state.employees.filter(e => _empInGroup(e, groupFilter))
    : state.employees;
  const placeholder = groupFilter ? "Alle i afdelingen" : "Alle medarbejdere";
  sel.innerHTML = `<option value="">${placeholder}</option>` +
    visible.slice().sort((a, b) => a.name.localeCompare(b.name, "da"))
      .map(e => `<option value="${e.id}">${h(e.name)} (${h(e.employee_number)})</option>`).join("");
  if (visible.find(e => String(e.id) === cur)) sel.value = cur;
}

// ── Startup ────────────────────────────────────────────────────────────────
async function loadApp() {
  try {
    [state.employees, state.vehicles, state.dispatcherGroups] = await Promise.all([
      GET("/api/employees"),
      GET("/api/vehicles"),
      GET("/api/employees/dispatcher-groups"),
    ]);
    fillDispatcherGroupFilter();
    fillEmployeeFilter();
  } catch (e) { console.error(e); }

  await loadAbsenceTypes();
  await setView("activities");
  await checkAnciennitetsAlerts();
}

async function init() {
  document.querySelectorAll(".sidebar-item").forEach(el =>
    el.addEventListener("click", () => setView(el.dataset.view)));

  document.getElementById("btn-prev-period").addEventListener("click", () => navigatePeriod("prev"));
  document.getElementById("btn-next-period").addEventListener("click", () => navigatePeriod("next"));
  buildDatePicker("period-date-picker", "");
  document.getElementById("period-date-picker").style.width = "150px";
  document.getElementById("period-date-picker").querySelector(".dp-val").addEventListener("change", e => jumpToDate(e.target.value));
  buildDatePicker("absence-from-dp", "");
  buildDatePicker("absence-to-dp", "");
  document.getElementById("filter-status").addEventListener("change", () => { updateStatChipActive(); renderActivitiesTable(); });
  document.getElementById("filter-employee").addEventListener("change", renderActivitiesTable);
  document.getElementById("filter-dispatcher-group").addEventListener("change", () => { fillEmployeeFilter(); renderActivitiesTable(); });
  document.getElementById("stat-pending") ?.addEventListener("click", () => toggleStatFilter("pending"));
  document.getElementById("stat-approved")?.addEventListener("click", () => toggleStatFilter("approved"));
  document.getElementById("stat-deact")   ?.addEventListener("click", () => toggleStatFilter("deactivated"));
  document.getElementById("show-inactive")?.addEventListener("change", loadEmployees);
  document.getElementById("employee-search")?.addEventListener("input", renderEmployeeList);
  document.getElementById("vehicle-search")?.addEventListener("input", renderVehicleList);

  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", e => {
      if (e.target === overlay) overlay.classList.remove("open");
    });
  });

  const loggedIn = await initAuth();
  if (loggedIn) await loadApp();
}

document.addEventListener("DOMContentLoaded", init);
