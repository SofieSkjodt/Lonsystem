"""
Lønkørsel:
- /api/payroll/preview           – JSON-mellemregninger til forsiden
- /api/payroll/proevekoersel     – Excel-fil (alle eller én medarbejder)
- /api/payroll/export-csv        – "Kør løn": Danløn CSV
- /api/payroll/pdf-timesedler    – dan PDF-timesedler pr. medarbejder (gemmes
                                   lokalt i output/timesedler; e-mail-afsendelse
                                   tilføjes senere, jf. aftale 10/6-2026)
"""
import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user, log_action, require_permission
from database.models import AppUser

from calculators.overtime import (
    OT_13_KEY,
    OT_13_MAX,
    OT_BEFORE_KEY,
    OT_EXTRA_KEY,
    calculate_overtime,
)
from calculators.day_type import (
    DayType,
    classify_day,
    compute_sh_hours,
    calculate_special_day_overtime,
)
from calculators.pay_period import get_or_create_period_for_date, is_even_week
import logging as _logging
from calculators.rates_loader import (
    load_agreement_types_from_db,
    load_overtime_rates_from_db,
    load_salt_supplement_rate_from_db,
    load_overnight_rate_from_db,
    load_dagpenge_rate_from_db,
    load_springer_rate_from_db,
    get_active_supplement_for_period,
)
from database.models import Activity, ActivityStatus, Employee, EmployeeSpringerFlag, Holiday, MasterCvrNumber, PayPeriod, PayPeriodStatus
from database.session import get_db

router = APIRouter(prefix="/api/payroll", tags=["payroll"])

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

_payroll_access = require_permission("payroll")
_reopen_access = require_permission("reopen_period")

_ALLOWED_SAVE_ROOTS = [Path.home(), Path("C:/"), Path("D:/")]


def _safe_save_dir(raw_path: str) -> Path:
    """Valider at den bruger-angivne sti ikke forsøger path traversal til systemkritiske steder."""
    save_dir = Path(raw_path).resolve()
    app_dir = BASE_DIR.resolve()
    # Tillad stier under brugerens hjemmemappe eller under rod-drev (Windows)
    # Afvis stier inde i selve applikationsmappen (undgår overskrivning af kildekode)
    try:
        save_dir.relative_to(app_dir)
        raise HTTPException(400, "Ugyldig gemmemappe – kan ikke gemme i applikationsmappen")
    except ValueError:
        pass  # Stien er IKKE inde i app-mappen – det er ønsket
    return save_dir

TWO = Decimal("0.01")


def _round2(v: Decimal) -> Decimal:
    return v.quantize(TWO, rounding=ROUND_HALF_UP)


def _get_employee_cvr(emp: Employee, db: Session) -> str:
    """Returnerer CVR-nummeret for medarbejderen (eget hvis sat, ellers standard fra Stamdata)."""
    if emp.cvr_number:
        return emp.cvr_number
    default = db.query(MasterCvrNumber).filter(MasterCvrNumber.is_default == True).first()
    if default:
        return default.cvr_number
    raise HTTPException(500, "Intet standard-CVR fundet – tilføj et CVR-nummer i Stamdata → CVR-nummer")


def _get_pay_type_data(db: Session) -> dict:
    """Returnerer {code_key: {code, in_csv, qty_type, rate_src, inc_total}} fra stamdata-tabellen."""
    from database.models import MasterPayType
    rows = db.query(MasterPayType).all()
    return {r.code_key.upper(): {
        "code": r.danloen_code,
        "in_csv": r.include_in_csv,
        "qty_type": r.csv_quantity_type or "hours",
        "rate_src": r.csv_rate_source or "hourly",
        "inc_rate": r.csv_include_rate if r.csv_include_rate is not None else True,
        "inc_total": r.csv_include_total or False,
    } for r in rows}


def _resolve_rate(rate_src: str, calc: dict) -> float:
    """Opslår en sats fra calc-dict baseret på rate_src-streng."""
    if rate_src == "ot_before":
        return float(calc["ot_rates"][OT_BEFORE_KEY])
    if rate_src == "ot_13":
        return float(calc["ot_rates"][OT_13_KEY])
    if rate_src == "ot_extra":
        return float(calc["ot_rates"][OT_EXTRA_KEY])
    if rate_src == "salt":
        return float(calc.get("salt_rate", 0))
    if rate_src == "overnight":
        return float(calc.get("overnight_rate", 0))
    if rate_src == "dagpenge":
        return float(calc.get("dagpenge_sats", 137.43))
    if rate_src == "springer":
        return float(calc.get("springer_rate", 0))
    return float(calc["hourly_rate"])


def _user_pay_type_rows(emp_id: int, start: date, end: date, calc: dict, db: Session) -> list:
    """Beregner antal/timer pr. brugerdefineret løntypekode for én medarbejder i perioden."""
    from database.models import MasterPayType
    user_types = db.query(MasterPayType).filter(MasterPayType.is_user_created == True).all()
    result = []
    start_str = start.isoformat()
    end_str = (end + timedelta(days=1)).isoformat()
    for upt in user_types:
        acts = db.query(Activity).filter(
            Activity.employee_id == emp_id,
            Activity.activity_type == upt.code_key,
            Activity.status == ActivityStatus.approved,
            Activity.start_time >= start_str,
            Activity.start_time < end_str,
        ).all()
        qty_type = upt.csv_quantity_type or "hours"
        if qty_type == "count":
            qty = float(len(acts))
        else:
            qty = sum((a.end_time - a.start_time).total_seconds() / 3600 for a in acts)
        if qty > 0:
            rate = _resolve_rate(upt.csv_rate_source or "hourly", calc)
            result.append((upt.code_key.upper(), qty, rate))
    return result


def _springer_row(calc: dict) -> tuple:
    """CSV-tuple for springertillæg: samme timetal som løntypekode 1 (Normal tid),
    men kun hvis flaget er sat for medarbejderens periode (calc['springer_enabled'])."""
    qty = calc["normal_hours"] if calc.get("springer_enabled") else 0
    return ("SPRINGERTILLAEG", qty, calc.get("springer_rate", 0))


def _builtin_absence_qty(pt: dict, key: str, activity_type: str, hours_value: float,
                          emp_id: int, start: date, end: date, db: Session) -> float:
    """Antal for en indbygget fraværs-løntype – bruger stamdatas csv_quantity_type
    (fx 'count' for antal dage) i stedet for altid at bruge det akkumulerede
    timeantal fra _calculate_employee."""
    qty_type = pt.get(key, {}).get("qty_type", "hours")
    if qty_type != "count":
        return hours_value
    start_str = start.isoformat()
    end_str = (end + timedelta(days=1)).isoformat()
    return float(db.query(Activity).filter(
        Activity.employee_id == emp_id,
        Activity.activity_type == activity_type,
        Activity.status == ActivityStatus.approved,
        Activity.start_time >= start_str,
        Activity.start_time < end_str,
    ).count())


def _normal_hours_for_day(emp: Employee, d: date) -> Decimal:
    """Normaltid for en given dag fra medarbejderens timefordeling."""
    schedule = emp.work_schedule or {"even": [0] * 7, "odd": [0] * 7}
    key = "even" if is_even_week(d) else "odd"
    return Decimal(str(schedule[key][d.weekday()]))


def _afspadsering_hours(emp: Employee, act: Activity) -> Decimal:
    """Timer for en afspadsering-aktivitet. En periode (aktiviteten strækker sig
    over flere kalenderdage, jf. 'Til dato' i oprettelsesmodalen) tæller 7,4 t
    (eller medarbejderens skemalagte timer) pr. hverdag i perioden – uanset de
    faktiske klokketider på aktiviteten. En enkeltdags-aktivitet bruger stadig
    den reelle varighed, så en delvis fridag kan registreres korrekt."""
    start_d = act.start_time.date()
    end_d = act.end_time.date()
    if start_d == end_d:
        return Decimal(str((act.end_time - act.start_time).total_seconds())) / 3600
    total = Decimal("0")
    cur_d = start_d
    while cur_d <= end_d:
        if cur_d.weekday() < 5:
            day_h = _normal_hours_for_day(emp, cur_d)
            total += day_h if day_h > 0 else Decimal("7.4")
        cur_d += timedelta(days=1)
    return total


@dataclass
class _DayPiece:
    """Et stykke af en aktivitet der falder inden for én kalenderdag."""
    start_time: datetime
    end_time: datetime
    pause_intervals: list
    activity_type: str
    salt_supplement: bool
    vehicle_number: Optional[str]


def _split_into_day_pieces(act: Activity) -> list[_DayPiece]:
    """Splitter en aktivitet, der strækker sig over midnat, i ét stykke pr.
    kalenderdag – hvert stykke skal beregnes under SIN EGEN dags dag-type og
    normaltids-loft (fx en søndag-til-mandag-vagt: søndagsdelen får
    søndagsregler, mandagsdelen får mandagens normale tidsvindues-beregning).
    Pauseintervaller der overlapper døgnskellet klippes tilsvarende.

    Kaldes KUN når aktiviteten starter på en søndag/helligdag (se
    _calculate_employee) – normaltids-/OT13-loftet hører til vagten og skal
    IKKE nulstilles ved midnat for almindelige hverdage/lørdage (bekræftet af
    bruger 2026-07-02).
    """
    if act.segments:
        raw_pauses = [
            (datetime.fromisoformat(seg[0]), datetime.fromisoformat(seg[1]))
            for seg in act.segments if len(seg) >= 3 and seg[2] == "rest"
        ]
    else:
        raw_pauses = [
            (datetime.fromisoformat(s), datetime.fromisoformat(e))
            for s, e in (act.pause_intervals or [])
        ]
    pieces = []
    cur = act.start_time
    while cur < act.end_time:
        next_midnight = datetime.combine(cur.date() + timedelta(days=1), datetime.min.time())
        piece_end = min(act.end_time, next_midnight)
        piece_pauses = []
        for p_start, p_end in raw_pauses:
            clipped_start, clipped_end = max(p_start, cur), min(p_end, piece_end)
            if clipped_start < clipped_end:
                piece_pauses.append([clipped_start.isoformat(), clipped_end.isoformat()])
        pieces.append(_DayPiece(
            start_time=cur,
            end_time=piece_end,
            pause_intervals=piece_pauses,
            activity_type=act.activity_type,
            salt_supplement=act.salt_supplement,
            vehicle_number=act.vehicle_number,
        ))
        cur = piece_end
    return pieces


def _calculate_employee(emp: Employee, start: date, end: date, db: Session) -> dict:
    """Beregn timefordeling og kr. for én medarbejder i et datointerval.
    Alle dage i perioden medtages – dage uden aktivitet vises som 0,
    fraværsdage vises med typenavn (beregning tilføjes senere)."""
    from collections import defaultdict
    from datetime import datetime as _dt

    activities = (
        db.query(Activity)
        .filter(
            Activity.employee_id == emp.id,
            Activity.status == ActivityStatus.approved,
            Activity.start_time < (end + timedelta(days=1)).isoformat(),
            Activity.end_time > start.isoformat(),
        )
        .order_by(Activity.start_time)
        .all()
    )

    try:
        hourly_rate = load_agreement_types_from_db(db).get(emp.agreement_type, Decimal("0"))
    except Exception:
        hourly_rate = Decimal("0")
    supplement = get_active_supplement_for_period(db, emp.id, start, end)
    if supplement:
        hourly_rate += supplement.value
    ot_rates = load_overtime_rates_from_db(db)
    salt_rate = load_salt_supplement_rate_from_db(db)
    overnight_rate = load_overnight_rate_from_db(db)
    dagpenge_sats = load_dagpenge_rate_from_db(db)
    springer_rate = load_springer_rate_from_db(db)
    _springer_period = get_or_create_period_for_date(start, db)
    springer_enabled = db.query(EmployeeSpringerFlag).filter(
        EmployeeSpringerFlag.employee_id == emp.id,
        EmployeeSpringerFlag.pay_period_id == _springer_period.id,
        EmployeeSpringerFlag.enabled == True,
    ).first() is not None

    _ABSENCE_LABELS = {
        "ferie":        "Ferie",
        "fri":          "Fri",
        "afspadsering": "Afspadsering",
        "skole_kursus": "Skole/kursus",
        "sygdom":                  "Sygdom",
        "sygdom_u_8uger":          "Sygdom u. 8 uger",
        "sygdom_u_8_uger":         "Sygdom u. 8 uger",
        "barn_1sygedag":           "Barn 1.sygedag",
        "barn_1sygedag_u_8uger":   "Barn 1.sygedag u. 8 uger",
        "barn_2_3sygedag":         "Barn 2-3.sygedag",
        "paragraf_56_syg":         "§56 syg",
        "selvbetalt_fridag":       "Selvbetalt fridag",
        "feriefri":                "Feriefri",
        "barsel":                        "Barsel",
        "barsel_u_loen":                 "Barsel u. løn",
        "graviditetsbetinget_sygdom":    "Graviditetsbetinget sygdom",
    }

    # Indlæs helligdage for perioden (fra v14-helligdagskalender) – bruges også
    # til at afgøre om en aktivitet der strækker sig over midnat skal splittes.
    holiday_rows = db.query(Holiday).filter(
        Holiday.date >= start,
        Holiday.date <= end,
    ).all()
    holiday_map = {h.date: h for h in holiday_rows}

    _ABSOLUTE_DAY_TYPES = (
        DayType.SUNDAY, DayType.HOLIDAY_FULL,
        DayType.HOLIDAY_HALF_1MAJ, DayType.HOLIDAY_HALF_GRUNDLOV,
    )

    # Gruppér aktiviteter på dato (kan være flere pr. dag ved opdelinger).
    # Normaltids-/OT13-loftet hører til VAGTEN (den dag den startede) og
    # fortsætter uændret hen over midnat, så længe det ikke er brugt op – det
    # håndterer calculate_overtime() automatisk ved at behandle vagten som ét
    # sammenhængende opslag. Kun søndage/helligdage har en loft-uafhængig regel
    # ("alle kørte timer, uanset tidspunkt"), så en vagt der STARTER på en
    # søndag/helligdag SKAL splittes ved midnat, så resten af vagten falder
    # tilbage til den følgende dags egne (loft-baserede) regler.
    # Bekræftet af bruger 2026-07-02.
    # Fraværstyper og overnatning er altid ét-dags og splittes aldrig.
    acts_by_date = defaultdict(list)
    for act in activities:
        if act.activity_type == "overnatning" or _ABSENCE_LABELS.get(act.activity_type):
            acts_by_date[act.start_time.date()].append(act)
        elif classify_day(act.start_time.date(), holiday_map) in _ABSOLUTE_DAY_TYPES:
            for piece in _split_into_day_pieces(act):
                acts_by_date[piece.start_time.date()].append(piece)
        else:
            acts_by_date[act.start_time.date()].append(act)

    totals = {
        "normal": Decimal("0"), "ot_before": Decimal("0"),
        "ot_13": Decimal("0"), "ot_extra": Decimal("0"),
        "sh_kode8": Decimal("0"), "sh_kode9": Decimal("0"),
        "sh_fuldloennet": Decimal("0"), "sh_timeloennet": Decimal("0"),
        "afspadsering": Decimal("0"),
        "sygdom": Decimal("0"),
        "paragraf_56_syg": Decimal("0"),
        "barn_1sygedag_u_loen": Decimal("0"),
        "feriefri":     Decimal("0"),
        "barsel":       Decimal("0"),
        "skole_kursus": Decimal("0"),
        "salt_hours": Decimal("0"), "salt_kr": Decimal("0"),
        "overnight_count": 0,
    }
    days = []
    total_kr = Decimal("0")

    # Overnatning håndteres som kolonne (ikke fraværsrække) – forhåndsberegn datoer
    overnight_dates = {a.start_time.date() for a in activities if a.activity_type == "overnatning"}
    totals["overnight_count"] = sum(1 for a in activities if a.activity_type == "overnatning")

    # Gennemløb alle dage i perioden
    cur = start
    while cur <= end:
        acts_today = [a for a in acts_by_date.get(cur, []) if a.activity_type != "overnatning"]
        overnight_today = 1 if cur in overnight_dates else 0

        # Dag-klassifikation og SH-betaling (gælder uanset om der køres)
        day_type = classify_day(cur, holiday_map)
        guaranteed_today = _normal_hours_for_day(emp, cur)
        sh_h = compute_sh_hours(day_type, guaranteed_today)
        if sh_h > 0:
            if emp.fuldloennet:
                totals["sh_fuldloennet"] += sh_h
            else:
                totals["sh_timeloennet"] += sh_h
            total_kr += sh_h * hourly_rate

        # Normaltids-/OT13-loft deles på tværs af dagens aktiviteter (ikke nulstillet
        # pr. aktivitet), så en dag der er delt i flere godkendte aktiviteter (fx efter
        # split) regnes som ét sammenhængende skift.
        day_normal_remaining = guaranteed_today
        day_ot13_remaining = OT_13_MAX

        if not acts_today:
            days.append({
                "date": cur.isoformat(),
                "normal": 0.0, "ot_before": 0.0, "ot_13": 0.0,
                "ot_extra": 0.0, "total_hours": 0.0, "total_kr": 0.0,
                "absence_type": None,
                "start_time": None, "end_time": None,
                "vehicle_number": None,
                "overnight": overnight_today,
            })
        else:
            for act in acts_today:
                label = _ABSENCE_LABELS.get(act.activity_type)
                if label:
                    if act.activity_type == "afspadsering":
                        dur = _afspadsering_hours(emp, act)
                        totals["afspadsering"] += dur
                    elif act.activity_type in ("sygdom", "barn_1sygedag", "graviditetsbetinget_sygdom"):
                        dur = Decimal(str((act.end_time - act.start_time).total_seconds())) / 3600
                        totals["sygdom"] += dur
                    elif act.activity_type == "paragraf_56_syg":
                        dur = Decimal(str((act.end_time - act.start_time).total_seconds())) / 3600
                        totals["paragraf_56_syg"] += dur
                    elif act.activity_type == "feriefri":
                        dur = Decimal(str((act.end_time - act.start_time).total_seconds())) / 3600
                        totals["feriefri"] += dur
                    elif act.activity_type == "barsel":
                        dur = Decimal(str((act.end_time - act.start_time).total_seconds())) / 3600
                        totals["barsel"] += dur
                    elif act.activity_type == "barn_1sygedag_u_8uger":
                        dur = Decimal(str((act.end_time - act.start_time).total_seconds())) / 3600
                        totals["barn_1sygedag_u_loen"] += dur
                    elif act.activity_type == "skole_kursus":
                        dur = Decimal(str((act.end_time - act.start_time).total_seconds())) / 3600
                        totals["skole_kursus"] += dur
                    # sygdom_u_8uger / barn_2_3sygedag / selvbetalt_fridag / barsel_u_loen: ikke i CSV
                    days.append({
                        "date": cur.isoformat(),
                        "normal": 0.0, "ot_before": 0.0, "ot_13": 0.0,
                        "ot_extra": 0.0, "total_hours": 0.0, "total_kr": 0.0,
                        "absence_type": label,
                        "start_time": None, "end_time": None,
                        "vehicle_number": None,
                        "overnight": overnight_today,
                    })
                else:
                    _segs = getattr(act, "segments", None)
                    if _segs:
                        pauses = [
                            (_dt.fromisoformat(seg[0]), _dt.fromisoformat(seg[1]))
                            for seg in _segs if len(seg) >= 3 and seg[2] == "rest"
                        ]
                    else:
                        pauses = [
                            (_dt.fromisoformat(s), _dt.fromisoformat(e))
                            for s, e in (act.pause_intervals or [])
                        ]
                    if day_type in (DayType.NORMAL, DayType.SATURDAY):
                        # Lørdag er ikke længere en særlig dag – den bruger samme
                        # tidsvindues-beregning som en hverdag, med lørdagens egne
                        # garanterede timer (typisk 0) som loft (bekræftet 2026-07-02).
                        ot = calculate_overtime(
                            act.start_time, act.end_time,
                            guaranteed_today, pauses, ot_rates,
                            normal_remaining=day_normal_remaining,
                            ot13_remaining=day_ot13_remaining,
                        )
                        day_normal_remaining = ot.normal_remaining_after
                        day_ot13_remaining = ot.ot13_remaining_after
                    else:
                        ot = calculate_special_day_overtime(
                            act.start_time, act.end_time,
                            day_type, pauses,
                            kode8_remaining=day_ot13_remaining,
                        )
                        day_ot13_remaining = ot.ot13_remaining_after
                    day_salt_hours = ot.total_hours if act.salt_supplement else Decimal("0")
                    day_salt_kr = day_salt_hours * salt_rate
                    day_kr = (
                        ot.total_hours * hourly_rate
                        + ot.ot_before_hours * ot_rates[OT_BEFORE_KEY]
                        + ot.ot_13_hours * ot_rates[OT_13_KEY]
                        + ot.ot_extra_hours * ot_rates[OT_EXTRA_KEY]
                        + ot.sh_kode8_hours * ot_rates[OT_13_KEY]
                        + ot.sh_kode9_hours * ot_rates[OT_EXTRA_KEY]
                        + day_salt_kr
                    )
                    totals["normal"]     += ot.normal_hours
                    totals["ot_before"]  += ot.ot_before_hours
                    totals["ot_13"]      += ot.ot_13_hours
                    totals["ot_extra"]   += ot.ot_extra_hours
                    totals["sh_kode8"]   += ot.sh_kode8_hours
                    totals["sh_kode9"]   += ot.sh_kode9_hours
                    totals["salt_hours"] += day_salt_hours
                    totals["salt_kr"]    += day_salt_kr
                    total_kr             += day_kr
                    days.append({
                        "date": cur.isoformat(),
                        "normal":       float(_round2(ot.normal_hours)),
                        "ot_before":    float(_round2(ot.ot_before_hours)),
                        "ot_13":        float(_round2(ot.ot_13_hours)),
                        "ot_extra":     float(_round2(ot.ot_extra_hours)),
                        "total_hours":  float(_round2(ot.total_hours)),
                        "total_kr":     float(_round2(day_kr)),
                        "absence_type": None,
                        "sh_kode8":     float(_round2(ot.sh_kode8_hours)),
                        "sh_kode9":     float(_round2(ot.sh_kode9_hours)),
                        "salt_hours":   float(_round2(day_salt_hours)),
                        "salt_kr":      float(_round2(day_salt_kr)),
                        "start_time":   act.start_time.strftime("%H:%M"),
                        "end_time":     act.end_time.strftime("%H:%M"),
                        "vehicle_number": act.vehicle_number or "",
                        "overnight":    overnight_today,
                    })
        cur += timedelta(days=1)

    has_pending = (
        db.query(Activity)
        .filter(
            Activity.employee_id == emp.id,
            Activity.status == ActivityStatus.pending,
            Activity.start_time >= start.isoformat(),
            Activity.start_time < (end + timedelta(days=1)).isoformat(),
        )
        .count() > 0
    )

    # normal_hours indeholder nu alle arbejdede timer (tillæg er additive)
    total_hours = totals["normal"]

    return {
        "employee_id":        emp.id,
        "employee_number":    emp.employee_number,
        "employee_name":      emp.name,
        "email":              emp.email,
        "agreement_type":     emp.agreement_type,
        "hourly_rate":        float(hourly_rate),
        "salt_rate":          float(salt_rate),
        "ot_rates":           {k: float(v) for k, v in ot_rates.items()},
        "days":               days,
        "normal_hours":       float(_round2(totals["normal"])),
        "ot_before_hours":    float(_round2(totals["ot_before"])),
        "ot_13_hours":        float(_round2(totals["ot_13"])),
        "ot_extra_hours":     float(_round2(totals["ot_extra"])),
        "salt_hours":         float(_round2(totals["salt_hours"])),
        "salt_kr":            float(_round2(totals["salt_kr"])),
        "overnight_count":    totals["overnight_count"],
        "overnight_rate":     float(overnight_rate),
        "overnight_kr":       float(_round2(Decimal(str(totals["overnight_count"])) * overnight_rate)),
        "springer_rate":      float(springer_rate),
        "springer_enabled":   springer_enabled,
        "afspadsering_hours":   float(_round2(totals["afspadsering"])),
        "sygdom_hours":         float(_round2(totals["sygdom"])),
        "paragraf_56_syg_hours":  float(_round2(totals["paragraf_56_syg"])),
        "barn_1sygedag_u_loen_hours": float(_round2(totals["barn_1sygedag_u_loen"])),
        "feriefri_hours":         float(_round2(totals["feriefri"])),
        "barsel_hours":           float(_round2(totals["barsel"])),
        "skole_kursus_hours":     float(_round2(totals["skole_kursus"])),
        "dagpenge_sats":          float(dagpenge_sats),
        "total_hours":        float(_round2(total_hours)),
        "total_kr":                float(_round2(total_kr)),
        "activity_count":          len(activities),
        "has_pending":             has_pending,
        "sh_fuldloennet_hours":    float(_round2(totals["sh_fuldloennet"])),
        "sh_timeloennet_hours":    float(_round2(totals["sh_timeloennet"])),
        "sh_kode8_hours":          float(_round2(totals["sh_kode8"])),
        "sh_kode9_hours":          float(_round2(totals["sh_kode9"])),
    }


def _resolve_period(period_start: Optional[str], db: Session):
    d = date.fromisoformat(period_start) if period_start else date.today()
    return get_or_create_period_for_date(d, db)


def _active_employees(db: Session, employee_id: Optional[int] = None):
    q = db.query(Employee).filter(Employee.active == True)
    if employee_id:
        q = q.filter(Employee.id == employee_id)
    return q.order_by(Employee.first_name, Employee.last_name).all()


@router.get("/preview")
def payroll_preview(period_start: Optional[str] = None,
                    current_user: AppUser = Depends(_payroll_access),
                    db: Session = Depends(get_db)):
    period = _resolve_period(period_start, db)
    employees = _active_employees(db)
    results = [_calculate_employee(e, period.start_date, period.end_date, db) for e in employees]
    return {
        "period_start": period.start_date.isoformat(),
        "period_end": period.end_date.isoformat(),
        "period_status": period.status.value,
        "employees": results,
        "has_unresolved_pending": any(r["has_pending"] for r in results),
    }


def _build_proevekoersel_workbook(employees, period, db):
    """Bygger prøvekørsel-Excel-arbejdsbog og returnerer den (fælles for download og gem)."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prøvekørsel"
    bold = Font(bold=True)
    header_fill = PatternFill(start_color="317423", end_color="317423", fill_type="solid")
    row_fill = PatternFill(start_color="D4EDCC", end_color="D4EDCC", fill_type="solid")

    headers = ["Medarbejder", "Lønnr", "Vognnr.", "Dag", "Starttid", "Sluttid", "Normal tid",
               "Overtid 1 time før", "Overtid 1-3 timer efter", "Øvrig overtid",
               "Salttillæg (t)", "Salttillæg (kr.)", "Overnatning", "Total tid", "Total kr."]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
    ws.freeze_panes = "A2"

    for emp in employees:
        calc = _calculate_employee(emp, period.start_date, period.end_date, db)
        first_row = True
        for day in calc["days"]:
            vn = day.get("vehicle_number") or ""
            st = day.get("start_time") or ""
            et = day.get("end_time") or ""
            on = day.get("overnight", 0) or ""
            if day["absence_type"]:
                row = [calc["employee_name"], calc["employee_number"], "", day["date"],
                       "", "", day["absence_type"], "", "", "", "", "",
                       on, "", ""]
            else:
                salt_t = day.get("salt_hours", 0) or ""
                salt_kr = day.get("salt_kr", 0) or ""
                row = [calc["employee_name"], calc["employee_number"], vn, day["date"],
                       st, et,
                       day["normal"], day["ot_before"],
                       day["ot_13"] + day.get("sh_kode8", 0),
                       day["ot_extra"] + day.get("sh_kode9", 0),
                       salt_t, salt_kr, on,
                       day["total_hours"], day["total_kr"]]
            ws.append(row)
            if first_row:
                for cell in ws[ws.max_row]:
                    cell.fill = row_fill
                first_row = False
        total_row = [calc["employee_name"], calc["employee_number"], "", "TOTAL",
                     "", "",
                     calc["normal_hours"], calc["ot_before_hours"],
                     calc["ot_13_hours"] + calc.get("sh_kode8_hours", 0),
                     calc["ot_extra_hours"] + calc.get("sh_kode9_hours", 0),
                     calc.get("salt_hours", 0) or "", calc.get("salt_kr", 0) or "",
                     calc.get("overnight_count", 0) or "",
                     calc["total_hours"], calc["total_kr"]]
        ws.append(total_row)
        for cell in ws[ws.max_row]:
            cell.font = bold
        sh_fl = calc.get("sh_fuldloennet_hours", 0)
        sh_tl = calc.get("sh_timeloennet_hours", 0)
        hr = calc["hourly_rate"]
        if sh_fl > 0:
            sh_row = [calc["employee_name"], calc["employee_number"], "", "Søgnehelligdag",
                      "", "", sh_fl, "", "", "", "", "", "", sh_fl, round(sh_fl * hr, 2)]
            ws.append(sh_row)
            for cell in ws[ws.max_row]:
                cell.font = bold
        if sh_tl > 0:
            sh_row = [calc["employee_name"], calc["employee_number"], "", "SH-Udbetaling",
                      "", "", sh_tl, "", "", "", "", "", "", sh_tl, round(sh_tl * hr, 2)]
            ws.append(sh_row)
            for cell in ws[ws.max_row]:
                cell.font = bold
        on_kr = calc.get("overnight_kr", 0.0)
        dagpenge = calc.get("dagpenge_sats", 137.43)
        for abs_lbl, abs_h, abs_rate in [
            ("Sygdom med løn",  calc.get("sygdom_hours", 0),              hr),
            ("§56 syg",         calc.get("paragraf_56_syg_hours", 0),     dagpenge),
            ("Barn 1.sygedag",  calc.get("barn_1sygedag_u_loen_hours", 0), dagpenge),
            ("Feriefri",        calc.get("feriefri_hours", 0),            hr),
            ("Barsel",          calc.get("barsel_hours", 0),              hr),
            ("Kursus/Skole",    calc.get("skole_kursus_hours", 0),        hr),
        ]:
            if abs_h > 0:
                ws.append([calc["employee_name"], calc["employee_number"], "", abs_lbl,
                           "", "", abs_h, "", "", "", "", "", "", abs_h, round(abs_h * abs_rate, 2)])
                for cell in ws[ws.max_row]:
                    cell.font = bold
        if on_kr > 0:
            ws.append([calc["employee_name"], calc["employee_number"], "", "Overnatning (kr.)",
                       "", "", "", "", "", "", "", "", "", "", round(on_kr, 2)])
            for cell in ws[ws.max_row]:
                cell.font = bold
        ws.append([])

    for col in "ABCDEFGHIJKLMNO":
        ws.column_dimensions[col].width = 22
    return wb


@router.get("/proevekoersel")
def proevekoersel(
    period_start: Optional[str] = None,
    employee_id: Optional[int] = None,
    current_user: AppUser = Depends(_payroll_access),
    db: Session = Depends(get_db),
):
    """Prøvekørsel: Excel-fil med mellemregninger – alle eller én medarbejder."""
    period = _resolve_period(period_start, db)
    employees = _active_employees(db, employee_id)
    if not employees:
        raise HTTPException(404, "Ingen medarbejdere fundet")

    wb = _build_proevekoersel_workbook(employees, period, db)
    filename = f"proevekoersel_{period.start_date.isoformat()}_{period.end_date.isoformat()}.xlsx"
    OUTPUT_DIR.mkdir(exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    (OUTPUT_DIR / filename).write_bytes(buf.getvalue())
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


class ProevekoerselSaveRequest(BaseModel):
    period_start: Optional[str] = None
    employee_id: Optional[int] = None
    output_folder: str


@router.post("/proevekoersel-gem")
def proevekoersel_gem(body: ProevekoerselSaveRequest,
                      current_user: AppUser = Depends(_payroll_access),
                      db: Session = Depends(get_db)):
    """Prøvekørsel gemt til valgt mappe i stedet for browser-download."""
    period = _resolve_period(body.period_start, db)
    employees = _active_employees(db, body.employee_id)
    if not employees:
        raise HTTPException(404, "Ingen medarbejdere fundet")

    wb = _build_proevekoersel_workbook(employees, period, db)
    save_dir = _safe_save_dir(body.output_folder)
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        _logging.error(f"Kan ikke oprette mappe '{save_dir}': {exc}")
        raise HTTPException(400, "Mappen kunne ikke oprettes – tjek stien og rettigheder")

    filename = f"proevekoersel_{period.start_date.isoformat()}_{period.end_date.isoformat()}.xlsx"
    filepath = save_dir / filename
    try:
        wb.save(str(filepath))
    except PermissionError:
        raise HTTPException(
            400,
            f"Kunne ikke gemme filen '{filename}' – tjek om den er åben i Excel eller et andet program, og prøv igen.",
        )
    return {"path": str(filepath), "filename": filename}


@router.get("/export-csv")
def export_csv(period_start: Optional[str] = None,
               current_user: AppUser = Depends(_payroll_access),
               db: Session = Depends(get_db)):
    """
    Kør løn: Danløn CSV.
    Kolonner: A=CVR, B=medarbejdernummer, C=Danløn-kode,
              D=antal timer, E=time-/tillægssats.
    """
    period = _resolve_period(period_start, db)
    employees = _active_employees(db)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")

    def fmt(v: float) -> str:
        return str(round(v * 100))

    pt = _get_pay_type_data(db)
    _code     = lambda k: pt.get(k, {}).get("code", "1")
    _in_csv   = lambda k: pt.get(k, {}).get("in_csv", True)
    _inc_rate = lambda k: pt.get(k, {}).get("inc_rate", True)
    _inc_tot  = lambda k: pt.get(k, {}).get("inc_total", False)

    for emp in employees:
        calc = _calculate_employee(emp, period.start_date, period.end_date, db)
        if (calc["activity_count"] == 0
                and calc["afspadsering_hours"] == 0
                and calc["sygdom_hours"] == 0
                and calc["paragraf_56_syg_hours"] == 0
                and calc["barn_1sygedag_u_loen_hours"] == 0
                and calc["feriefri_hours"] == 0
                and calc["barsel_hours"] == 0
                and calc["skole_kursus_hours"] == 0
                and calc.get("sh_fuldloennet_hours", 0) == 0
                and calc.get("sh_timeloennet_hours", 0) == 0):
            continue

        raw_rows = [
            ("NORMAL",         calc["normal_hours"],                                               calc["hourly_rate"]),
            _springer_row(calc),
            ("OT_BEFORE",      calc["ot_before_hours"],                                            calc["ot_rates"][OT_BEFORE_KEY]),
            ("OT_13",          calc["ot_13_hours"] + calc.get("sh_kode8_hours", 0),               calc["ot_rates"][OT_13_KEY]),
            ("OT_EXTRA",       calc["ot_extra_hours"] + calc.get("sh_kode9_hours", 0),            calc["ot_rates"][OT_EXTRA_KEY]),
            ("SH_FULDLOENNET", calc.get("sh_fuldloennet_hours", 0),                               calc["hourly_rate"]),
            ("SH_TIMELOENNET", calc.get("sh_timeloennet_hours", 0),                               calc["hourly_rate"]),
            ("SALT",           calc.get("salt_hours", 0),                                         calc.get("salt_rate", 0)),
            ("OVERNATNING",    calc.get("overnight_count", 0),                                    calc.get("overnight_rate", 0)),
            ("AFSPADSERING",   calc["afspadsering_hours"],                                        calc["hourly_rate"]),
            ("SYGDOM",         calc["sygdom_hours"],                                              calc["hourly_rate"]),
            ("PARAGRAF_56",    calc["paragraf_56_syg_hours"],                                     calc.get("dagpenge_sats", 137.43)),
            ("BARN_1SYGEDAG",  calc["barn_1sygedag_u_loen_hours"],                                calc.get("dagpenge_sats", 137.43)),
            ("FERIEFRI",       _builtin_absence_qty(pt, "FERIEFRI", "feriefri", calc["feriefri_hours"],
                                                      emp.id, period.start_date, period.end_date, db), calc["hourly_rate"]),
            ("BARSEL",         calc["barsel_hours"],                                              calc["hourly_rate"]),
            ("SKOLE_KURSUS",   calc["skole_kursus_hours"],                                        calc["hourly_rate"]),
        ] + _user_pay_type_rows(emp.id, period.start_date, period.end_date, calc, db)
        for key, qty, rate in raw_rows:
            if not _in_csv(key) or qty == 0:
                continue
            qty_fmt = fmt(qty)
            row = [_get_employee_cvr(emp, db), calc["employee_number"], _code(key), qty_fmt]
            if _inc_rate(key) or _inc_tot(key):
                row.append(fmt(rate) if _inc_rate(key) else "")
            if _inc_tot(key):
                row.append(fmt(qty * float(rate)))
            writer.writerow(row)

    filename = f"danloen_{period.start_date.isoformat()}_{period.end_date.isoformat()}.csv"
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / filename).write_text(output.getvalue(), encoding="utf-8-sig")

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


class ExportCsvRequest(BaseModel):
    period_start: Optional[str] = None
    output_folder: str


@router.post("/export-csv")
def export_csv_post(body: ExportCsvRequest,
                    current_user: AppUser = Depends(_payroll_access),
                    db: Session = Depends(get_db)):
    """
    Kør løn: låser perioden og gemmer Danløn CSV til valgt mappe.
    """
    period = _resolve_period(body.period_start, db)

    if period.status == PayPeriodStatus.closed:
        raise HTTPException(
            400,
            "Lønperioden er allerede låst – lønnen er allerede kørt for denne periode. "
            "Åbn perioden igen under Administration, hvis der skal foretages ændringer.",
        )

    pending_count = (
        db.query(Activity)
        .join(Employee, Activity.employee_id == Employee.id)
        .filter(
            Employee.active == True,
            Activity.status == ActivityStatus.pending,
            Activity.start_time >= period.start_date.isoformat(),
            Activity.start_time < (period.end_date + timedelta(days=1)).isoformat(),
        )
        .count()
    )
    if pending_count > 0:
        raise HTTPException(
            400,
            "Lønnen kan ikke køres – der er aktiviteter, der afventer godkendelse eller deaktivering.",
        )

    employees = _active_employees(db)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\n")

    def fmt(v: float) -> str:
        return str(round(v * 100))

    pt = _get_pay_type_data(db)
    _code     = lambda k: pt.get(k, {}).get("code", "1")
    _in_csv   = lambda k: pt.get(k, {}).get("in_csv", True)
    _inc_rate = lambda k: pt.get(k, {}).get("inc_rate", True)
    _inc_tot  = lambda k: pt.get(k, {}).get("inc_total", False)

    for emp in employees:
        calc = _calculate_employee(emp, period.start_date, period.end_date, db)
        if (calc["activity_count"] == 0
                and calc["afspadsering_hours"] == 0
                and calc["sygdom_hours"] == 0
                and calc["paragraf_56_syg_hours"] == 0
                and calc["barn_1sygedag_u_loen_hours"] == 0
                and calc["feriefri_hours"] == 0
                and calc["barsel_hours"] == 0
                and calc["skole_kursus_hours"] == 0
                and calc.get("sh_fuldloennet_hours", 0) == 0
                and calc.get("sh_timeloennet_hours", 0) == 0):
            continue
        raw_rows = [
            ("NORMAL",         calc["normal_hours"],                                               calc["hourly_rate"]),
            _springer_row(calc),
            ("OT_BEFORE",      calc["ot_before_hours"],                                            calc["ot_rates"][OT_BEFORE_KEY]),
            ("OT_13",          calc["ot_13_hours"] + calc.get("sh_kode8_hours", 0),               calc["ot_rates"][OT_13_KEY]),
            ("OT_EXTRA",       calc["ot_extra_hours"] + calc.get("sh_kode9_hours", 0),            calc["ot_rates"][OT_EXTRA_KEY]),
            ("SH_FULDLOENNET", calc.get("sh_fuldloennet_hours", 0),                               calc["hourly_rate"]),
            ("SH_TIMELOENNET", calc.get("sh_timeloennet_hours", 0),                               calc["hourly_rate"]),
            ("SALT",           calc.get("salt_hours", 0),                                         calc.get("salt_rate", 0)),
            ("OVERNATNING",    calc.get("overnight_count", 0),                                    calc.get("overnight_rate", 0)),
            ("AFSPADSERING",   calc["afspadsering_hours"],                                        calc["hourly_rate"]),
            ("SYGDOM",         calc["sygdom_hours"],                                              calc["hourly_rate"]),
            ("PARAGRAF_56",    calc["paragraf_56_syg_hours"],                                     calc.get("dagpenge_sats", 137.43)),
            ("BARN_1SYGEDAG",  calc["barn_1sygedag_u_loen_hours"],                                calc.get("dagpenge_sats", 137.43)),
            ("FERIEFRI",       _builtin_absence_qty(pt, "FERIEFRI", "feriefri", calc["feriefri_hours"],
                                                      emp.id, period.start_date, period.end_date, db), calc["hourly_rate"]),
            ("BARSEL",         calc["barsel_hours"],                                              calc["hourly_rate"]),
            ("SKOLE_KURSUS",   calc["skole_kursus_hours"],                                        calc["hourly_rate"]),
        ] + _user_pay_type_rows(emp.id, period.start_date, period.end_date, calc, db)
        for key, qty, rate in raw_rows:
            if not _in_csv(key) or qty == 0:
                continue
            qty_fmt = fmt(qty)
            row = [_get_employee_cvr(emp, db), calc["employee_number"], _code(key), qty_fmt]
            if _inc_rate(key) or _inc_tot(key):
                row.append(fmt(rate) if _inc_rate(key) else "")
            if _inc_tot(key):
                row.append(fmt(qty * float(rate)))
            writer.writerow(row)

    filename = f"danloen_{period.start_date.isoformat()}_{period.end_date.isoformat()}.csv"
    save_dir = _safe_save_dir(body.output_folder)
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        import logging; logging.error(f"Kan ikke oprette mappe '{save_dir}': {exc}")
        raise HTTPException(400, "Mappen kunne ikke oprettes – tjek stien og rettigheder")
    try:
        (save_dir / filename).write_text(output.getvalue(), encoding="utf-8-sig")
    except PermissionError:
        raise HTTPException(
            400,
            f"Kunne ikke gemme filen '{filename}' – tjek om den er åben i Excel eller et andet program, og prøv igen.",
        )

    period.status = PayPeriodStatus.closed
    period.closed_at = datetime.utcnow()
    period.closed_by = current_user.initials
    log_action(db, current_user, "payroll_run", "pay_period", period.id,
               f"Løn kørt for periode {period.start_date} – {period.end_date}")
    db.commit()

    return {"filename": filename, "path": str(save_dir / filename)}


@router.post("/reopen-period")
def reopen_period(period_start: Optional[str] = None,
                  current_user: AppUser = Depends(_reopen_access),
                  db: Session = Depends(get_db)):
    """Åbner en lukket lønperiode igen (sætter status tilbage til 'open')."""
    period = _resolve_period(period_start, db)
    period.status = PayPeriodStatus.open
    period.closed_at = None
    period.closed_by = None

    # Aktiviteter der blev oprettet manuelt mens perioden var lukket, ruller automatisk
    # frem til næste åbne periode (se get_billing_period i calculators/pay_period.py).
    # Nu hvor perioden genåbnes, skal de aktiviteter der reelt hører til denne periodes
    # datointerval, men fejlagtigt peger på en senere periode, flyttes tilbage - ellers
    # bliver de usynlige i Aktiviteter-fanen for begge perioder.
    start_str = period.start_date.isoformat()
    end_str = (period.end_date + timedelta(days=1)).isoformat()
    stray = (
        db.query(Activity)
        .filter(
            Activity.pay_period_id != period.id,
            Activity.start_time >= start_str,
            Activity.start_time < end_str,
        )
        .all()
    )
    for a in stray:
        a.pay_period_id = period.id
    if stray:
        log_action(db, current_user, "reassign_pay_period_id", "pay_period", period.id,
                   f"{len(stray)} aktivitet(er) flyttet tilbage til periode {period.start_date} – {period.end_date} ved genåbning")

    log_action(db, current_user, "reopen_period", "pay_period", period.id,
               f"Lønperiode genåbnet: {period.start_date} – {period.end_date}")
    db.commit()
    return {"status": "open", "period_start": period.start_date.isoformat()}


class PdfRequest(BaseModel):
    from_date: date
    to_date: date
    employee_id: Optional[int] = None
    output_folder: Optional[str] = None


@router.get("/downloads-folder")
def get_downloads_folder(current_user: AppUser = Depends(_payroll_access)):
    """Returnerer brugerens Downloads-mappe som forslag til gem-placering."""
    from pathlib import Path as _P
    folder = _P.home() / "Downloads"
    return {"path": str(folder)}


@router.get("/browse-folder")
def browse_folder(initial: str = "",
                  current_user: AppUser = Depends(_payroll_access)):
    """Åbner en native Windows-mappevælger og returnerer den valgte sti."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", True)
    start = initial if initial else str(Path.home() / "Downloads")
    chosen = filedialog.askdirectory(initialdir=start, title="Vælg mappe til PDF-filer")
    root.destroy()
    if not chosen:
        return {"path": None}
    return {"path": str(Path(chosen))}


@router.post("/pdf-timesedler")
def pdf_timesedler(body: PdfRequest,
                   current_user: AppUser = Depends(_payroll_access),
                   db: Session = Depends(get_db)):
    """
    Dan PDF-timesedler for valgt datointerval.
    PDF'erne gemmes i output/timesedler/ (e-mail-afsendelse tilføjes senere).
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        raise HTTPException(500, "reportlab er ikke installeret (pip install reportlab)")

    if body.to_date < body.from_date:
        raise HTTPException(400, "Til-dato skal være efter fra-dato")

    employees = _active_employees(db, body.employee_id)
    if body.output_folder:
        pdf_dir = _safe_save_dir(body.output_folder)
    else:
        pdf_dir = OUTPUT_DIR / "timesedler"
    try:
        pdf_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        import logging; logging.error(f"Kan ikke oprette mappe '{pdf_dir}': {exc}")
        raise HTTPException(400, "Mappen kunne ikke oprettes – tjek stien og rettigheder")

    styles = getSampleStyleSheet()
    created = []
    skipped = []

    for emp in employees:
        calc = _calculate_employee(emp, body.from_date, body.to_date, db)
        if calc["activity_count"] == 0:
            skipped.append(calc["employee_name"])
            continue

        filename = f"timeseddel_{emp.employee_number}_{body.from_date.isoformat()}_{body.to_date.isoformat()}.pdf"
        path = pdf_dir / filename

        doc = SimpleDocTemplate(str(path), pagesize=landscape(A4),
                                topMargin=15 * mm, bottomMargin=15 * mm,
                                leftMargin=15 * mm, rightMargin=15 * mm)
        elements = [
            Paragraph(f"Timeseddel – {calc['employee_name']} (lønnr. {calc['employee_number']})", styles["Title"]),
            Paragraph(f"Periode: {body.from_date.strftime('%d-%m-%Y')} til {body.to_date.strftime('%d-%m-%Y')}", styles["Normal"]),
            Paragraph(f"Overenskomst: {calc['agreement_type']}", styles["Normal"]),
            Spacer(1, 8 * mm),
        ]

        header = ["Dag", "Vognnr.", "Starttid", "Sluttid", "Normal tid", "Overtid 1 time før",
                  "Overtid 1-3 timer efter", "Øvrig overtid", "Salttillæg (t)", "Total tid", "Total kr."]
        rates_row = ["Satser", "", "", "", f"{calc['hourly_rate']:.2f}",
                     f"{calc['ot_rates'][OT_BEFORE_KEY]:.2f}",
                     f"{calc['ot_rates'][OT_13_KEY]:.2f}",
                     f"{calc['ot_rates'][OT_EXTRA_KEY]:.2f}",
                     f"{calc.get('salt_rate', 0):.2f}", "", ""]
        data = [header, rates_row]
        for day in calc["days"]:
            d = date.fromisoformat(day["date"])
            vn = day.get("vehicle_number") or ""
            st = day.get("start_time") or ""
            et = day.get("end_time") or ""
            if day["absence_type"]:
                data.append([d.strftime("%d-%m-%Y"), "", "", "", day["absence_type"], "", "", "", "", "", ""])
            else:
                data.append([
                    d.strftime("%d-%m-%Y"), vn, st, et,
                    f"{day['normal']:.2f}", f"{day['ot_before']:.2f}",
                    f"{day['ot_13']:.2f}", f"{day['ot_extra']:.2f}",
                    f"{day.get('salt_hours', 0):.2f}",
                    f"{day['total_hours']:.2f}", f"{day['total_kr']:.2f}",
                ])
        data.append(["Total for perioden, kr.", "", "", "", "", "", "", "", "", "", f"{calc['total_kr']:.2f}"])

        col_widths = [25*mm, 20*mm, 19*mm, 19*mm, 24*mm, 27*mm, 31*mm, 23*mm, 21*mm, 20*mm, 22*mm]
        table = Table(data, colWidths=col_widths, repeatRows=2)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#317423")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#d4edcc")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#d4edcc")),
            ("ALIGN", (2, 2), (3, -1), "CENTER"),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
        ]))
        elements.append(table)
        doc.build(elements)
        created.append({"employee": calc["employee_name"], "email": calc["email"], "file": str(path)})

    return {
        "created": created,
        "skipped": skipped,
        "folder": str(pdf_dir),
        "note": "PDF'er gemt lokalt – e-mail-afsendelse er ikke konfigureret endnu.",
    }
