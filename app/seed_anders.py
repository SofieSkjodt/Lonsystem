"""
Opretter Anders Gervig Jensen som første testmedarbejder (ny datamodel)
og kopierer hans .ddd-fil til ddd_input/.

Normaltid 7 timer man-fre (jf. eksemplerne i kravdokumentet:
"Hvis Anders arbejder 10 timer en mandag, hvor hans normaltid er 7 timer").
"""
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database.session import get_db, init_db
from database.models import Employee, AgreementKind

BASE_DIR = Path(__file__).resolve().parent
DDD_INPUT = BASE_DIR / "ddd_input"
DDD_INPUT.mkdir(exist_ok=True)

for ddd_file in BASE_DIR.glob("C_*Jensen_Anders*.ddd"):
    dest = DDD_INPUT / ddd_file.name
    if not dest.exists():
        shutil.copy2(ddd_file, dest)
        print(f"Kopieret: {ddd_file.name} -> ddd_input/")

init_db()
db = next(get_db())

existing = db.query(Employee).filter(Employee.employee_number == "001").first()
if existing:
    print(f"Medarbejder eksisterer allerede: {existing.name}")
else:
    anders = Employee(
        employee_number="001",
        tachograph_card_number="DK00000178901010",
        first_name="Anders Gervig",
        last_name="Jensen",
        agreement_kind=AgreementKind.hourly_fixed,
        agreement_type="Chauffør",
        fuldloennet=True,
        active=True,
        hire_date=date(2026, 1, 20),
        termination_date=date(9999, 12, 31),
        work_schedule={
            "even": [7, 7, 7, 7, 7, 0, 0],
            "odd": [7, 7, 7, 7, 7, 0, 0],
        },
    )
    db.add(anders)
    db.commit()
    db.refresh(anders)
    print(f"Oprettet: {anders.name} (id={anders.id}, loennr={anders.employee_number})")
    print(f"  Overenskomst: {anders.agreement_type}")
    print(f"  Ansat:        {anders.hire_date}")
    print(f"  Normaltid:    7 t man-fre (lige og ulige uger)")

db.close()
print("\nFaerdig.")
