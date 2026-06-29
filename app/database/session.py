import logging
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "lonsystem.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def set_wal_mode(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception as e:
        logging.error(f"WAL-mode opsætning fejlede: {e}")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    from database.models import Base
    Base.metadata.create_all(bind=engine)
    _migrate()
    _seed_roles()
    _seed_admin()
    _seed_master_data()
    _seed_cvr()
    _seed_holidays()
    _ensure_sh_pay_types()    # SH-løntypekoder kode 4 og 63
    _ensure_anciennitet_alert_permission()


def _migrate():
    """Tilføjer nye kolonner til eksisterende databaser uden at miste data."""
    import sqlite3 as _sqlite3
    with _sqlite3.connect(str(DB_PATH)) as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(activities)")}
        if "created_by" not in existing:
            conn.execute("ALTER TABLE activities ADD COLUMN created_by VARCHAR")
            conn.commit()
        ot_cols = {row[1] for row in conn.execute("PRAGMA table_info(master_overtime_rates)")}
        if "is_user_created" not in ot_cols:
            conn.execute("ALTER TABLE master_overtime_rates ADD COLUMN is_user_created BOOLEAN DEFAULT 0")
            conn.commit()
        sup_cols = {row[1] for row in conn.execute("PRAGMA table_info(master_supplement_rates)")}
        if "is_user_created" not in sup_cols:
            conn.execute("ALTER TABLE master_supplement_rates ADD COLUMN is_user_created BOOLEAN DEFAULT 0")
            conn.commit()
        pt_cols = {row[1] for row in conn.execute("PRAGMA table_info(master_pay_types)")}
        if "is_user_created" not in pt_cols:
            conn.execute("ALTER TABLE master_pay_types ADD COLUMN is_user_created BOOLEAN DEFAULT 0")
            conn.commit()
        if "csv_quantity_type" not in pt_cols:
            conn.execute("ALTER TABLE master_pay_types ADD COLUMN csv_quantity_type VARCHAR(20) NOT NULL DEFAULT 'hours'")
            conn.execute("ALTER TABLE master_pay_types ADD COLUMN csv_rate_source VARCHAR(30) NOT NULL DEFAULT 'hourly'")
            conn.execute("ALTER TABLE master_pay_types ADD COLUMN csv_include_rate BOOLEAN NOT NULL DEFAULT 1")
            conn.execute("ALTER TABLE master_pay_types ADD COLUMN csv_include_total BOOLEAN NOT NULL DEFAULT 0")
            conn.commit()
            conn.execute("UPDATE master_pay_types SET csv_rate_source='ot_before' WHERE code_key='OT_BEFORE'")
            conn.execute("UPDATE master_pay_types SET csv_rate_source='ot_13' WHERE code_key='OT_13'")
            conn.execute("UPDATE master_pay_types SET csv_rate_source='ot_extra' WHERE code_key='OT_EXTRA'")
            conn.execute("UPDATE master_pay_types SET csv_rate_source='salt' WHERE code_key='SALT'")
            conn.execute("UPDATE master_pay_types SET csv_quantity_type='count', csv_rate_source='overnight' WHERE code_key='OVERNATNING'")
            conn.execute("UPDATE master_pay_types SET csv_rate_source='dagpenge' WHERE code_key='PARAGRAF_56'")
            conn.execute("UPDATE master_pay_types SET csv_rate_source='dagpenge' WHERE code_key='BARN_1SYGEDAG'")
            conn.commit()
        if "csv_include_rate" not in pt_cols:
            conn.execute("ALTER TABLE master_pay_types ADD COLUMN csv_include_rate BOOLEAN NOT NULL DEFAULT 1")
            conn.commit()
        emp_cols = {row[1] for row in conn.execute("PRAGMA table_info(employees)")}
        if "cvr_number" not in emp_cols:
            conn.execute("ALTER TABLE employees ADD COLUMN cvr_number VARCHAR(20)")
            conn.commit()
        if "anciennitet_dismissed_at" not in emp_cols:
            conn.execute("ALTER TABLE employees ADD COLUMN anciennitet_dismissed_at DATETIME")
            conn.commit()
        act_cols2 = {row[1] for row in conn.execute("PRAGMA table_info(activities)")}
        if "deactivated_by" not in act_cols2:
            conn.execute("ALTER TABLE activities ADD COLUMN deactivated_by VARCHAR")
            conn.commit()


def _seed_roles():
    from database.models import Role
    db = SessionLocal()
    try:
        if db.query(Role).count() == 0:
            for r in [
                Role(name="admin", display_name="Administrator", is_system=True,
                     permissions=["payroll", "import_ddd", "user_management", "reopen_period"]),
                Role(name="lonbogholder", display_name="Lønbogholder", is_system=False,
                     permissions=["payroll", "absence_overview", "import_ddd", "anciennitet_alert"]),
                Role(name="disponent", display_name="Disponent", is_system=False,
                     permissions=[]),
            ]:
                db.add(r)
            db.commit()
    finally:
        db.close()


def _seed_admin():
    from database.models import AppUser
    from auth import hash_password
    db = SessionLocal()
    try:
        if db.query(AppUser).count() == 0:
            db.add(AppUser(
                name="Administrator",
                initials="admin",
                email="",
                role="admin",
                password_hash=hash_password("admin"),
                active=True,
            ))
            db.commit()
    finally:
        db.close()


def _normalize_absence_key(label: str) -> str:
    overrides = {"Kursus/Skole": "skole_kursus"}
    if label in overrides:
        return overrides[label]
    s = label.lower()
    s = s.replace("§", "paragraf_")
    s = s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    s = s.replace(" ", "_").replace("/", "_").replace(".", "").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _seed_master_data():
    from decimal import Decimal
    from database.models import (
        MasterAgreementType, MasterOvertimeRate,
        MasterSupplementRate, MasterPayType, MasterAbsenceType,
    )
    db = SessionLocal()
    try:
        if db.query(MasterAgreementType).count() == 0:
            try:
                from calculators.rates_loader import load_agreement_types
                for name, rate in load_agreement_types().items():
                    db.add(MasterAgreementType(name=name, hourly_rate=rate))
                db.commit()
            except Exception as e:
                db.rollback()
                logging.warning(f"Overenskomsttyper – seeding fra Excel slog fejl: {e}")

        if db.query(MasterOvertimeRate).count() == 0:
            try:
                from calculators.rates_loader import load_overtime_rates
                for label, rate in load_overtime_rates().items():
                    db.add(MasterOvertimeRate(label=label, rate=rate))
                db.commit()
            except Exception as e:
                db.rollback()
                logging.warning(f"Overtidssatser – seeding fra Excel slog fejl: {e}")

        if db.query(MasterSupplementRate).count() == 0:
            try:
                from calculators.rates_loader import load_salt_supplement_rate, load_overnight_rate
                db.add(MasterSupplementRate(label="Salttillæg", rate=load_salt_supplement_rate()))
                db.add(MasterSupplementRate(label="Overnatning", rate=load_overnight_rate()))
                db.add(MasterSupplementRate(label="Dagpenge §56", rate=Decimal("137.43")))
                db.commit()
            except Exception as e:
                db.rollback()
                logging.warning(f"Tillægssatser – seeding slog fejl: {e}")

        if db.query(MasterPayType).count() == 0:
            from calculators.pay_rates import (
                DANLOEN_CODE_NORMAL, DANLOEN_CODE_OT_BEFORE, DANLOEN_CODE_OT_13,
                DANLOEN_CODE_OT_EXTRA, DANLOEN_CODE_SALT, DANLOEN_CODE_AFSPADSERING,
                DANLOEN_CODE_SYGDOM, DANLOEN_CODE_FERIEFRI, DANLOEN_CODE_BARSEL,
                DANLOEN_CODE_SKOLE_KURSUS, DANLOEN_CODE_OVERNATNING,
                DANLOEN_CODE_PARAGRAF_56, DANLOEN_CODE_BARN_1SYGEDAG,
            )
            pay_types = [
                # (code_key, label, danloen_code, include_in_csv, sort_order, qty_type, rate_src)
                ("NORMAL",        "Normal tid",           DANLOEN_CODE_NORMAL,        True,  1, "hours", "hourly"),
                ("OT_BEFORE",     "Overtid 1 time før",   DANLOEN_CODE_OT_BEFORE,     True,  2, "hours", "ot_before"),
                ("OT_13",         "Overtid 1-3 timer",    DANLOEN_CODE_OT_13,         True,  3, "hours", "ot_13"),
                ("OT_EXTRA",      "Øvrig overtid",        DANLOEN_CODE_OT_EXTRA,      True,  4, "hours", "ot_extra"),
                ("SALT",          "Salttillæg",           DANLOEN_CODE_SALT,          True,  5, "hours", "salt"),
                ("OVERNATNING",   "Overnatning",          DANLOEN_CODE_OVERNATNING,   True,  6, "count", "overnight"),
                ("AFSPADSERING",  "Afspadsering",         DANLOEN_CODE_AFSPADSERING,  True,  7, "hours", "hourly"),
                ("SYGDOM",        "Sygdom med løn",       DANLOEN_CODE_SYGDOM,        True,  8, "hours", "hourly"),
                ("PARAGRAF_56",   "§56 syg",              DANLOEN_CODE_PARAGRAF_56,   True,  9, "hours", "dagpenge"),
                ("BARN_1SYGEDAG", "Barn 1.sygedag",       DANLOEN_CODE_BARN_1SYGEDAG, True, 10, "hours", "dagpenge"),
                ("FERIEFRI",      "Feriefri",             DANLOEN_CODE_FERIEFRI,      True, 11, "hours", "hourly"),
                ("BARSEL",        "Barsel",               DANLOEN_CODE_BARSEL,        True, 12, "hours", "hourly"),
                ("SKOLE_KURSUS",  "Kursus/Skole",         DANLOEN_CODE_SKOLE_KURSUS,  True, 13, "hours", "hourly"),
            ]
            for ck, lbl, code, inc, order, qty, rate_src in pay_types:
                db.add(MasterPayType(
                    code_key=ck, label=lbl, danloen_code=code,
                    include_in_csv=inc, sort_order=order,
                    csv_quantity_type=qty, csv_rate_source=rate_src,
                    csv_include_rate=True, csv_include_total=False,
                ))
            db.commit()
        if db.query(MasterAbsenceType).count() == 0:
            try:
                from openpyxl import load_workbook
                xlsx_path = BASE_DIR / "Fraværstyper.xlsx"
                _backend_only = {
                    "sygdom_u_8uger", "sygdom_u_8_uger",
                    "barn_1sygedag_u_8uger", "barsel_u_loen",
                }
                if xlsx_path.exists():
                    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
                    ws = wb.active
                    order = 1
                    first = True
                    for row in ws.iter_rows(values_only=True):
                        if first:
                            first = False
                            continue
                        cell = row[0]
                        if cell:
                            lbl = str(cell).strip()
                            key = _normalize_absence_key(lbl)
                            if key not in _backend_only:
                                db.add(MasterAbsenceType(
                                    label=lbl, normalized_key=key,
                                    is_active=True, is_user_created=False,
                                    sort_order=order,
                                ))
                                order += 1
                    wb.close()
                    db.commit()
            except Exception as e:
                db.rollback()
                logging.warning(f"Fraværstyper – seeding fra Excel slog fejl: {e}")

    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved seeding af stamdata: {e}")
    finally:
        db.close()


def _seed_cvr():
    from database.models import MasterCvrNumber
    from calculators.pay_rates import CVR_NUMBER
    db = SessionLocal()
    try:
        if db.query(MasterCvrNumber).count() == 0:
            db.add(MasterCvrNumber(
                cvr_number=CVR_NUMBER,
                company_name="Poul Schou A/S",
                is_default=True,
            ))
            db.commit()
    finally:
        db.close()


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


def _ensure_sh_pay_types():
    """Tilføjer SH-løntypekoder til eksisterende databaser (idempotent)."""
    from database.models import MasterPayType
    from calculators.pay_rates import DANLOEN_CODE_SH_FULDLOENNET, DANLOEN_CODE_SH_TIMELOENNET
    db = SessionLocal()
    try:
        entries = [
            ("SH_FULDLOENNET", "Søgnehelligdag", DANLOEN_CODE_SH_FULDLOENNET, True, 14, "hours", "hourly"),
            ("SH_TIMELOENNET", "SH-Udbetaling", DANLOEN_CODE_SH_TIMELOENNET, True, 15, "hours", "hourly"),
        ]
        for ck, lbl, code, inc, order, qty, rate_src in entries:
            existing = db.query(MasterPayType).filter(MasterPayType.code_key == ck).first()
            if not existing:
                db.add(MasterPayType(
                    code_key=ck, label=lbl, danloen_code=code,
                    include_in_csv=inc, sort_order=order,
                    csv_quantity_type=qty, csv_rate_source=rate_src,
                    csv_include_rate=True, csv_include_total=False,
                ))
            elif existing.label != lbl:
                existing.label = lbl
        db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved seeding af SH-løntypekoder: {e}")
    finally:
        db.close()


def _ensure_anciennitet_alert_permission():
    """Tilføjer anciennitet_alert til lonbogholder-rollen (idempotent)."""
    from database.models import Role
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "lonbogholder").first()
        if role and not role.is_system:
            perms = list(role.permissions or [])
            if "anciennitet_alert" not in perms:
                perms.append("anciennitet_alert")
                role.permissions = perms
                db.commit()
    except Exception as e:
        db.rollback()
        logging.error(f"Fejl ved opdatering af anciennitet_alert-tilladelse: {e}")
    finally:
        db.close()
