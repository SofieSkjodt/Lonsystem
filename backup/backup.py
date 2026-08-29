"""
Lønsystem backup-utility
Kører 4 gange dagligt via Windows Task Scheduler.
Gemmer database + Excel-konfigurationsfiler i et ZIP-arkiv.
Bevarer backups fra de seneste KEEP_DAYS dage og sletter ældre automatisk.
"""

import os
import sqlite3
import zipfile
import logging
from pathlib import Path
from datetime import datetime, timedelta

# ── Konfiguration ───────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent   # Lønsystem/
APP        = ROOT / "app"
DB_PATH    = APP / "database" / "lonsystem.db"
BACKUP_DIR = Path(os.environ.get("LONSYSTEM_BACKUP_DIR") or (Path(__file__).resolve().parent / "arkiv"))
LOG_FILE   = Path(__file__).resolve().parent / "backup.log"
KEEP_DAYS  = 5   # Antal dage backup-historik bevares

EXCEL_FILES = [
    APP / "Overtid satser.xlsx",
    APP / "Overenskomsttyper og timesatser.xlsx",
    APP / "Afdelinger.xlsx",
]

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)


def log(msg, level="info"):
    getattr(logging, level)(msg)
    print(msg)


def _backup_db_to_file(dest_path: Path):
    """
    Bruger SQLites eget backup-API – sikker selv mens databasen er åben
    og der skrives til den (WAL-mode). Resultatet er en konsistent snapshot.
    """
    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(dest_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def run_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    now      = datetime.now()
    filename = f"lonsystem_{now.strftime('%Y-%m-%d_%H-%M')}.zip"
    zip_path = BACKUP_DIR / filename
    tmp_db   = BACKUP_DIR / "_tmp_db.db"

    log(f"=== Backup starter -> {filename} ===")

    if not DB_PATH.exists():
        log(f"FEJL: Database ikke fundet: {DB_PATH}", "error")
        return

    # Tag sikker kopi af databasen til en midlertidig fil
    _backup_db_to_file(tmp_db)

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, "lonsystem.db")
            log(f"  + lonsystem.db ({round(tmp_db.stat().st_size / 1024, 1)} KB)")

            for excel in EXCEL_FILES:
                if excel.exists():
                    zf.write(excel, excel.name)
                    log(f"  + {excel.name}")
                else:
                    log(f"  (ikke fundet, springes over: {excel.name})", "warning")
    finally:
        if tmp_db.exists():
            tmp_db.unlink()

    size_kb = round(zip_path.stat().st_size / 1024, 1)
    log(f"Backup gemt: {filename} ({size_kb} KB)")

    # ── Ryd backups ældre end KEEP_DAYS dage ───────────────────────────────
    cutoff  = now - timedelta(days=KEEP_DAYS)
    deleted = 0

    for old in sorted(BACKUP_DIR.glob("lonsystem_????-??-??_??-??.zip")):
        try:
            date_str  = old.stem[len("lonsystem_"):]          # "YYYY-MM-DD_HH-MM"
            file_time = datetime.strptime(date_str, "%Y-%m-%d_%H-%M")
            if file_time < cutoff:
                old.unlink()
                deleted += 1
                log(f"  Slettet gammel backup: {old.name}")
        except ValueError:
            pass  # Ukendt filnavnformat – rør ikke ved filen

    if deleted:
        log(f"Ryddede {deleted} backup(s) ældre end {KEEP_DAYS} dage.")

    remaining = len(list(BACKUP_DIR.glob("lonsystem_*.zip")))
    log(f"=== Backup færdig. {remaining} backup(s) i arkivet. ===")


def main():
    try:
        run_backup()
    except Exception:
        logging.exception("Backup fejlede med en uventet fejl")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
