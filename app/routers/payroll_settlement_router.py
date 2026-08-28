"""
Lønafregning:
- /api/payroll-settlement/preview           – JSON til Lønafregning-siden (periodetotaler
                                              + pr. medarbejder headline + 14-dages tabel)
- /api/payroll-settlement/downloads-folder  – forslag til gem-mappe (samme mønster som Lønkørsel)
- /api/payroll-settlement/export-csv        – CSV med Dato/Lønnummer/timer/kr/vognnummer pr.
                                              dag pr. medarbejder; kræver låst periode (admin altid)
"""
import csv
import io
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import log_action, require_permission
from database.models import AppUser, PayPeriodStatus
from database.session import get_db

from calculators.overtime import OT_13_KEY, OT_BEFORE_KEY, OT_EXTRA_KEY
from calculators.pay_period import get_or_create_period_for_date
from calculators.rates_loader import get_active_supplement_for_period, load_agreement_types_from_db

from routers.payroll_router import _active_employees, _calculate_employee, _safe_save_dir

router = APIRouter(prefix="/api/payroll-settlement", tags=["payroll-settlement"])

_view_access = require_permission("payroll_settlement_view")
_export_access = require_permission("payroll_settlement_export")


def _display_day(day: dict) -> dict:
    """Klargør én dag til visning/CSV i Lønafregning: folder søgnehelligdags-
    tillæg ind i OT13/OT-extra (samme konvention som Lønkørsel-visningen), og
    viser fraværsdages (sygdom/§56 syg/sygdom u. 8 uger/barn 1.sygedag/
    graviditetsbetinget sygdom/barsel/skole-kursus/ferie/afspadsering) egne
    timer+beløb i 'Total tid'/'Total i kr.' for netop DEN dag."""
    result = {**day, "ot_13": day["ot_13"] + day.get("sh_kode8", 0),
              "ot_extra": day["ot_extra"] + day.get("sh_kode9", 0)}
    if day.get("absence_hours") is not None:
        result["total_hours"] = day["absence_hours"]
        result["total_kr"] = day["absence_kr"]
    return result


def _employee_settlement_data(emp, start: date, end: date, db: Session) -> dict:
    """Headline-info (satser vist separat) + periodetotal for én medarbejder,
    oven på den fælles _calculate_employee()-beregning (samme datakilde som Lønkørsel)."""
    calc = _calculate_employee(emp, start, end, db)

    agreement_rate = load_agreement_types_from_db(db).get(emp.agreement_type, Decimal("0"))
    supplement = get_active_supplement_for_period(db, emp.id, start, end)
    personal_supplement_rate = supplement.value if supplement else Decimal("0")

    springer_kr = (
        Decimal(str(calc["normal_hours"])) * Decimal(str(calc["springer_rate"]))
        if calc["springer_enabled"] else Decimal("0")
    )

    days = [_display_day(day) for day in calc["days"]]
    # Alle fraværstyper med et beregnet beløb (sygdom, §56 syg, sygdom u. 8 uger,
    # barn 1.sygedag, graviditetsbetinget sygdom, barsel, skole/kursus, ferie,
    # afspadsering) tæller nu med i medarbejderens samlede løn – bekræftet af
    # bruger 2026-08-25 ("fravær skal ... tælle med i totalen").
    absence_kr_total = sum(
        (Decimal(str(d["absence_kr"])) for d in days if d.get("absence_kr") is not None),
        Decimal("0"),
    )
    total_kr_with_extras = Decimal(str(calc["total_kr"])) + springer_kr + absence_kr_total

    return {
        "employee_id": calc["employee_id"],
        "employee_number": calc["employee_number"],
        "employee_name": calc["employee_name"],
        "agreement_type": calc["agreement_type"],
        "agreement_rate": float(agreement_rate),
        "personal_supplement_rate": float(personal_supplement_rate),
        "springer_enabled": calc["springer_enabled"],
        "springer_rate": calc["springer_rate"],
        "springer_kr": float(springer_kr),
        "normal_hours": calc["normal_hours"],
        "hourly_rate": calc["hourly_rate"],
        "ot_before_hours": calc["ot_before_hours"],
        "ot_13_hours": calc["ot_13_hours"] + calc["sh_kode8_hours"],
        "ot_extra_hours": calc["ot_extra_hours"] + calc["sh_kode9_hours"],
        "ot_rates": calc["ot_rates"],
        "salt_kr": calc["salt_kr"],
        "total_kr": float(total_kr_with_extras),
        "days": days,
    }


# Fraværstyper der får deres egen navngivne linje i "Total sum for perioden" –
# én linje pr. fraværstype der reelt har et beregnet beløb (bekræftet af bruger
# 2026-08-25). Selvbetalt fridag, Barn 2-3.sygedag, Barsel u. løn og "Fri" har
# ingen etableret betalingsregel i systemet og får derfor ingen linje.
_PAGE_TOTAL_ABSENCE_LABELS = {
    "sygdom_kr": "Sygdom",
    "sygdom_u_8_uger_kr": "Sygdom u. 8 uger",
    "barn_1sygedag_kr": "Barn 1.sygedag",
    "barn_1sygedag_u_8_uger_kr": "Barn 1.sygedag u. 8 uger",
    "graviditetsbetinget_sygdom_kr": "Graviditetsbetinget sygdom",
    "paragraf_56_syg_kr": "§56 syg",
    "barsel_kr": "Barsel",
    "feriefri_kr": "Feriefri",
    "ferie_kr": "Ferie",
    "skole_kursus_kr": "Skole/kursus",
    "afspadsering_kr": "Afspadsering",
}


def _sum_absence_kr(employees_data: list, label: str) -> float:
    return sum(
        d["absence_kr"]
        for e in employees_data
        for d in e["days"]
        if d.get("absence_type") == label and d.get("absence_kr") is not None
    )


def _page_totals(employees_data: list) -> dict:
    """Periodetotaler for hele siden – aggregeret på tværs af alle medarbejdere.
    Grundtimeløn/OT/salt-rækkerne er informative highlights af arbejdstid;
    Sygdom/Ferie/Skole-kursus/Afspadsering-rækkerne er de fraværstyper brugeren
    bad om at få vist for sig. total_kr er den fulde sum af alle medarbejderes
    total_kr (som nu inkluderer al fraværsbetaling, jf. _employee_settlement_data)."""
    grundtimeloen_kr = sum(e["normal_hours"] * e["hourly_rate"] + e["springer_kr"] for e in employees_data)
    ot_before_kr = sum(e["ot_before_hours"] * e["ot_rates"].get(OT_BEFORE_KEY, 0) for e in employees_data)
    ot_13_kr = sum(e["ot_13_hours"] * e["ot_rates"].get(OT_13_KEY, 0) for e in employees_data)
    ot_extra_kr = sum(e["ot_extra_hours"] * e["ot_rates"].get(OT_EXTRA_KEY, 0) for e in employees_data)
    salt_kr = sum(e["salt_kr"] for e in employees_data)
    total_kr = sum(e["total_kr"] for e in employees_data)
    # Delsum "Total uden fravær": grundtimeløn t.o.m. øvrig overtid – IKKE salt
    # (bruger var eksplicit: "fra grundtimeløn til og med øvrig overtid").
    total_excl_absence_kr = grundtimeloen_kr + ot_before_kr + ot_13_kr + ot_extra_kr
    result = {
        "grundtimeloen_incl_tillaeg_kr": round(grundtimeloen_kr, 2),
        "ot_before_kr": round(ot_before_kr, 2),
        "ot_13_kr": round(ot_13_kr, 2),
        "ot_extra_kr": round(ot_extra_kr, 2),
        "total_excl_absence_kr": round(total_excl_absence_kr, 2),
        "salt_kr": round(salt_kr, 2),
        "total_kr": round(total_kr, 2),
    }
    for key, label in _PAGE_TOTAL_ABSENCE_LABELS.items():
        result[key] = round(_sum_absence_kr(employees_data, label), 2)
    return result


def _resolve_period(period_start: Optional[str], db: Session):
    """Slår perioden op ud fra en valgt periode-startdato, ligesom Lønkørsel
    (payroll_router._resolve_period) – falder tilbage til dagens periode, hvis
    ingen er valgt (fx via aktivitetsoversigtens frem/tilbage-navigation)."""
    d = date.fromisoformat(period_start) if period_start else date.today()
    return get_or_create_period_for_date(d, db)


@router.get("/preview")
def payroll_settlement_preview(period_start: Optional[str] = None,
                               current_user: AppUser = Depends(_view_access),
                               db: Session = Depends(get_db)):
    period = _resolve_period(period_start, db)
    employees = _active_employees(db)
    employees_data = [_employee_settlement_data(e, period.start_date, period.end_date, db) for e in employees]
    employees_data.sort(key=lambda e: e["employee_name"] or "")
    return {
        "period_start": period.start_date.isoformat(),
        "period_end": period.end_date.isoformat(),
        "period_status": period.status.value,
        "page_totals": _page_totals(employees_data),
        "employees": employees_data,
    }


def _fmt_hm(decimal_hours: float) -> str:
    """Konverterer decimaltimer til 'Tt:mm'-format, fx 7.5 -> '7:30'."""
    total_minutes = round((decimal_hours or 0) * 60)
    hh, mm = divmod(total_minutes, 60)
    return f"{hh}:{mm:02d}"


def _fmt_decimal_comma(v: float) -> str:
    """Decimaltal med dansk komma, fx 7.5 -> '7,50'."""
    return f"{(v or 0):.2f}".replace(".", ",")


def _fmt_kr_da(v: float) -> str:
    """Dansk kr-format med tusindtalspunktum og kommadecimal, fx 1234.5 -> '1.234,50'."""
    return f"{(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@router.get("/downloads-folder")
def get_downloads_folder(current_user: AppUser = Depends(_export_access)):
    """Returnerer brugerens Downloads-mappe som forslag til gem-placering."""
    return {"path": str(Path.home() / "Downloads")}


class ExportSettlementCsvRequest(BaseModel):
    period_start: Optional[str] = None
    output_folder: str


def _csv_zeroed_absence_types(emp) -> set:
    """Fraværstyper der vises som 0 kr/0 timer i CSV-eksporten (men IKKE på
    siden selv) – Vognnummer-kolonnen viser stadig typens navn. Feriefri
    zeroes kun for timelønnede medarbejdere. Bekræftet af bruger 2026-08-26."""
    types = {"Ferie", "Afspadsering"}
    if not emp.fuldloennet:
        types.add("Feriefri")
    return types


def _csv_days(emp, employee_data: dict) -> list:
    """Bygger CSV-specifikke dagsrækker hvor de zero'ede fraværstypers timer/
    beløb er nulstillet (Vognnummer beholder stadig typens navn)."""
    zero_types = _csv_zeroed_absence_types(emp)
    return [
        {**day, "total_hours": 0, "total_kr": 0} if day.get("absence_type") in zero_types else day
        for day in employee_data["days"]
    ]


@router.post("/export-csv")
def export_settlement_csv(body: ExportSettlementCsvRequest,
                          current_user: AppUser = Depends(_export_access),
                          db: Session = Depends(get_db)):
    """
    Eksporterer Lønafregning som CSV: én række pr. dag pr. medarbejder (alle 14
    dage), med lønnummer tilføjet – ingen 'Total løn for'-rækker og ingen
    topsummering. Kræver at den valgte periode er låst – administratorer kan
    altid eksportere.
    """
    period = _resolve_period(body.period_start, db)
    is_admin = current_user.role == "admin"
    if period.status != PayPeriodStatus.closed and not is_admin:
        raise HTTPException(
            400,
            "Lønperioden skal være låst, før den kan eksporteres. Kør løn under Lønkørsel-fanen først.",
        )

    employees = _active_employees(db)
    employee_pairs = sorted(
        (
            (e, _employee_settlement_data(e, period.start_date, period.end_date, db))
            for e in employees
        ),
        key=lambda pair: pair[1]["employee_name"] or "",
    )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Dato", "Lønnummer", "Normal timer", "Overtid 1 time før",
                      "Overtid 1-3 timer efter", "Øvrig overtid", "Total tid",
                      "Total i kr.", "Vognnummer", "Beløb"])
    for emp, e in employee_pairs:
        for day in _csv_days(emp, e):
            d = date.fromisoformat(day["date"])
            vognnummer = day["absence_type"] or day["vehicle_number"] or ""
            writer.writerow([
                d.strftime("%d-%m-%Y"), e["employee_number"],
                _fmt_hm(day["normal"]), _fmt_hm(day["ot_before"]),
                _fmt_hm(day["ot_13"]), _fmt_hm(day["ot_extra"]),
                _fmt_decimal_comma(day["total_hours"]), _fmt_kr_da(day["total_kr"]),
                vognnummer, _fmt_kr_da(day["total_kr"]),
            ])

    filename = f"lonafregning_{period.start_date.isoformat()}_{period.end_date.isoformat()}.csv"
    save_dir = _safe_save_dir(body.output_folder)
    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logging.error(f"Kan ikke oprette mappe '{save_dir}': {exc}")
        raise HTTPException(400, "Mappen kunne ikke oprettes – tjek stien og rettigheder")
    try:
        (save_dir / filename).write_bytes(output.getvalue().encode("utf-8-sig"))
    except PermissionError:
        raise HTTPException(
            400,
            f"Kunne ikke gemme filen '{filename}' – tjek om den er åben i Excel eller et andet program, og prøv igen.",
        )

    log_action(db, current_user, "payroll_settlement_export", "pay_period", period.id,
               f"Lønafregning eksporteret for periode {period.start_date} – {period.end_date}")
    db.commit()

    return {"filename": filename, "path": str(save_dir / filename)}
