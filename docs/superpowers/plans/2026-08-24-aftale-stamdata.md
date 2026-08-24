# Aftale som Stamdata-tabel — Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flyt "Aftale" (medarbejderens `hourly_fixed`/`hourly_flexible`-valg) fra en hardcoded liste til en Stamdata-administreret tabel, med mulighed for at tilføje nye aftaletyper der styrer om "Overenskomsttype" er påkrævet, uden at ændre den eksisterende overtidsberegning for de to originale typer.

**Architecture:** Ny tabel `master_agreement_kinds` (samme mønster som `master_absence_types`) erstatter Python-enummet som kilde til gyldige værdier. `Employee.agreement_kind` bliver en almindelig streng-kolonne (ingen DB-migration nødvendig — kolonnen er allerede `VARCHAR` uden CHECK-constraint). Stamdata-CRUD følger nøjagtigt samme mønster som Fraværstyper. Medarbejdere med en ny, ikke-genkendt Aftale-type springes automatisk over i overtidsberegningen via en ny "flad timer, ingen tillæg"-gren.

**Tech Stack:** FastAPI + SQLAlchemy (SQLite), Pydantic, vanilla JS (`app.js`) + server-renderet HTML (`index.html`), pytest.

## Global Constraints

- `key`/`normalized_key` for en Aftale-type kan **aldrig ændres** efter oprettelse — kun `label`, `is_active`, `requires_agreement_type` er redigerbare. Overtidsberegningen (`overtime.py`, `payroll_router.py`) grener direkte på de faste strengværdier `hourly_fixed`/`hourly_flexible`.
- De to systemtyper (`hourly_fixed`, `hourly_flexible`) kan ikke slettes.
- Medarbejdere med en Aftale-type der ikke er `hourly_fixed`/`hourly_flexible` springes automatisk over i OT-beregningen — ingen fejl, ingen OT-tillæg, kun flad normaltid.
- `agreement_type`-kolonnen forbliver `NOT NULL` i databasen — når en Aftale-type har `requires_agreement_type=false`, gemmes tom streng `""` i stedet for `NULL` (ingen tabel-genopbygning i SQLite).
- Reference: `docs/superpowers/specs/2026-08-24-aftale-stamdata-design.md`.

---

## Task 1: Datamodel — `MasterAgreementKind` + `Employee.agreement_kind` som streng

**Files:**
- Modify: `app/database/models.py`
- Modify: `app/database/schemas.py`
- Test: `tests/test_agreement_kind_model.py`

**Interfaces:**
- Produces: `MasterAgreementKind` SQLAlchemy-model med felterne `id, key, label, is_active, is_user_created, requires_agreement_type, sort_order`. Senere tasks (2, 3, 4) importerer denne klasse fra `database.models`.
- Produces: `Employee.agreement_kind` er nu en almindelig `str` (ikke længere `AgreementKind`-enum-typet i Pydantic-schemas).

- [ ] **Step 1: Skriv den fejlende test**

```python
# tests/test_agreement_kind_model.py
from datetime import date

from database.models import MasterAgreementKind, Employee, AgreementKind


def test_master_agreement_kind_row_has_expected_fields(db):
    row = MasterAgreementKind(
        key="hourly_fixed",
        label="Timelønnet, fast arbejdstid",
        is_active=True,
        is_user_created=False,
        requires_agreement_type=True,
        sort_order=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.id is not None
    assert row.key == "hourly_fixed"
    assert row.is_user_created is False
    assert row.requires_agreement_type is True


def test_employee_agreement_kind_accepts_new_custom_string(db):
    """agreement_kind skal kunne gemme en helt ny, brugeroprettet nøgle –
    ikke kun de to gamle enum-værdier."""
    emp = Employee(
        employee_number="9001",
        first_name="Ny",
        last_name="Type",
        agreement_kind="mit_nye_aftale_flag",
        agreement_type="",
        hire_date=date(2026, 1, 1),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    assert emp.agreement_kind == "mit_nye_aftale_flag"


def test_employee_agreement_kind_still_accepts_system_enum_values(db):
    """De to eksisterende værdier skal fortsat kunne gemmes uændret."""
    emp = Employee(
        employee_number="9002",
        first_name="Gammel",
        last_name="Type",
        agreement_kind=AgreementKind.hourly_flexible,
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    assert emp.agreement_kind == "hourly_flexible"
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `pytest tests/test_agreement_kind_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'MasterAgreementKind'` (klassen findes ikke endnu), og/eller `LookupError`/`ValueError` på `agreement_kind="mit_nye_aftale_flag"` fordi kolonnen i dag er en streng `Enum(AgreementKind)`.

- [ ] **Step 3: Tilføj `MasterAgreementKind`-modellen**

I `app/database/models.py`, indsæt lige efter `MasterAgreementType`-klassen (efter linjen `hourly_rate = Column(Numeric(10, 2), nullable=False)`, før `class MasterCvrNumber(Base):`):

```python
class MasterAgreementKind(Base):
    __tablename__ = "master_agreement_kinds"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False)
    label = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False)
    requires_agreement_type = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
```

- [ ] **Step 4: Ændr `Employee.agreement_kind` fra enum-kolonne til streng**

I `app/database/models.py`, find linjen (i `class Employee`):

```python
    agreement_kind = Column(Enum(AgreementKind), nullable=False, default=AgreementKind.hourly_fixed)
```

Erstat med:

```python
    # Nøgle fra master_agreement_kinds.key – ikke længere en hård enum-kolonne,
    # da nye Aftale-typer kan tilføjes via Stamdata (se AgreementKind for de to
    # systemnøgler, som overtidsberegningen fortsat kender).
    agreement_kind = Column(String(50), nullable=False, default="hourly_fixed")
```

`AgreementKind`-enummet i samme fil bevares uændret — det bruges stadig af `overtime.py`/`payroll_router.py` som reference for de to systemnøgler.

- [ ] **Step 5: Kør testen og bekræft at den nu består**

Run: `pytest tests/test_agreement_kind_model.py -v`
Expected: PASS (alle 3 tests)

- [ ] **Step 6: Ret Pydantic-schemas til at bruge `str` i stedet for `AgreementKind`**

I `app/database/schemas.py`:

Fjern `AgreementKind` fra importen:
```python
from database.models import ActivitySource, ActivityStatus, ActivityType, AgreementKind
```
bliver til:
```python
from database.models import ActivitySource, ActivityStatus, ActivityType
```

Ret de tre felter:
```python
    agreement_kind: AgreementKind = AgreementKind.hourly_fixed
```
(i `EmployeeCreate`) bliver til:
```python
    agreement_kind: str = "hourly_fixed"
```

```python
    agreement_kind: Optional[AgreementKind] = None
```
(i `EmployeeUpdate`) bliver til:
```python
    agreement_kind: Optional[str] = None
```

```python
    agreement_kind: AgreementKind
```
(i `EmployeeResponse`) bliver til:
```python
    agreement_kind: str
```

- [ ] **Step 7: Kør hele testsuiten for at sikre ingen regression**

Run: `pytest -v`
Expected: PASS (ingen nye fejl — eksisterende tests der bruger `AgreementKind.hourly_fixed`/`hourly_flexible` som værdi til `agreement_kind` virker uændret, da disse stadig er gyldige strenge)

- [ ] **Step 8: Commit**

```bash
git add app/database/models.py app/database/schemas.py tests/test_agreement_kind_model.py
git commit -m "feat: gør Employee.agreement_kind til fri streng, tilføj MasterAgreementKind"
```

---

## Task 2: Seed de to systemtyper ved opstart

**Files:**
- Modify: `app/database/session.py`
- Test: `tests/test_agreement_kind_seed.py`

**Interfaces:**
- Consumes: `MasterAgreementKind` fra Task 1.
- Produces: `_seed_agreement_kinds(db)` — funktion der (idempotent) opretter de to systemrækker `hourly_fixed`/`hourly_flexible`, hvis tabellen er tom. Kaldes fra `_seed_master_data()`.

- [ ] **Step 1: Skriv den fejlende test**

```python
# tests/test_agreement_kind_seed.py
from database.models import MasterAgreementKind
from database.session import _seed_agreement_kinds


def test_seed_creates_the_two_system_kinds(db):
    _seed_agreement_kinds(db)

    rows = db.query(MasterAgreementKind).order_by(MasterAgreementKind.sort_order).all()
    assert [r.key for r in rows] == ["hourly_fixed", "hourly_flexible"]
    assert all(r.is_user_created is False for r in rows)
    assert all(r.requires_agreement_type is True for r in rows)
    assert all(r.is_active is True for r in rows)


def test_seed_is_idempotent(db):
    _seed_agreement_kinds(db)
    _seed_agreement_kinds(db)

    count = db.query(MasterAgreementKind).count()
    assert count == 2
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `pytest tests/test_agreement_kind_seed.py -v`
Expected: FAIL — `ImportError: cannot import name '_seed_agreement_kinds'`

- [ ] **Step 3: Tilføj seed-funktionen**

I `app/database/session.py`, tilføj importen af `MasterAgreementKind` i `_seed_master_data`'s importblok (find linjen):

```python
    from database.models import (
        MasterAgreementType, MasterOvertimeRate,
        MasterSupplementRate, MasterPayType, MasterAbsenceType,
    )
```

og udvid til:

```python
    from database.models import (
        MasterAgreementType, MasterOvertimeRate,
        MasterSupplementRate, MasterPayType, MasterAbsenceType,
        MasterAgreementKind,
    )
```

Tilføj derefter en ny, selvstændig funktion (placeres lige før `def _seed_master_data():`):

```python
def _seed_agreement_kinds(db):
    from database.models import MasterAgreementKind
    if db.query(MasterAgreementKind).count() == 0:
        db.add(MasterAgreementKind(
            key="hourly_fixed", label="Timelønnet, fast arbejdstid",
            is_active=True, is_user_created=False,
            requires_agreement_type=True, sort_order=1,
        ))
        db.add(MasterAgreementKind(
            key="hourly_flexible", label="Timelønnet, ikke fastlagt arbejdstid",
            is_active=True, is_user_created=False,
            requires_agreement_type=True, sort_order=2,
        ))
        db.commit()
```

Kald den til sidst i `_seed_master_data()`, lige inden `except Exception as e:`-blokken der afslutter funktionen (efter Fraværstyper-sektionen, stadig inden for den yderste `try:`):

```python
        _seed_agreement_kinds(db)
```

- [ ] **Step 4: Kør testen og bekræft at den nu består**

Run: `pytest tests/test_agreement_kind_seed.py -v`
Expected: PASS

- [ ] **Step 5: Kør hele testsuiten**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/database/session.py tests/test_agreement_kind_seed.py
git commit -m "feat: seed de to system-aftaletyper ved opstart"
```

---

## Task 3: Stamdata CRUD-endpoints for Aftaletyper

**Files:**
- Modify: `app/routers/stamdata.py`
- Test: `tests/test_agreement_kind_stamdata.py`

**Interfaces:**
- Consumes: `MasterAgreementKind` (Task 1), `_normalize_absence_key()` (eksisterende generisk slug-normalisering i `stamdata.py`).
- Produces: `AgreementKindBody` (Pydantic-body), `_agreement_kind_row(r) -> dict`, router-funktionerne `list_agreement_kinds`, `create_agreement_kind`, `update_agreement_kind`, `delete_agreement_kind` — importeres direkte af tests (samme mønster som `test_dispatcher_group_visibility.py`).

- [ ] **Step 1: Skriv de fejlende tests**

```python
# tests/test_agreement_kind_stamdata.py
from database.models import AppUser, Employee, MasterAgreementKind
from routers.stamdata import (
    AgreementKindBody,
    list_agreement_kinds,
    create_agreement_kind,
    update_agreement_kind,
    delete_agreement_kind,
)
from datetime import date


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _seed_two_system_kinds(db):
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.add(MasterAgreementKind(
        key="hourly_flexible", label="Timelønnet, ikke fastlagt arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=2,
    ))
    db.commit()


def test_list_returns_seeded_kinds_in_sort_order(db):
    _seed_two_system_kinds(db)
    rows = list_agreement_kinds(current_user=_dummy_user(), db=db)
    assert [r["key"] for r in rows] == ["hourly_fixed", "hourly_flexible"]


def test_create_new_agreement_kind(db):
    _seed_two_system_kinds(db)
    body = AgreementKindBody(label="Månedslønnet", requires_agreement_type=False)
    result = create_agreement_kind(body, current_user=_dummy_user(), db=db)
    assert result["key"] == "maanedsloennet"
    assert result["is_user_created"] is True
    assert result["requires_agreement_type"] is False


def test_create_without_label_fails(db):
    _seed_two_system_kinds(db)
    body = AgreementKindBody(label=None)
    try:
        create_agreement_kind(body, current_user=_dummy_user(), db=db)
        assert False, "skulle have fejlet"
    except Exception as e:
        assert "påkrævet" in str(e).lower() or "400" in str(e)


def test_create_duplicate_label_fails(db):
    _seed_two_system_kinds(db)
    create_agreement_kind(AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db)
    try:
        create_agreement_kind(AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db)
        assert False, "skulle have fejlet på duplikeret nøgle"
    except Exception:
        pass


def test_update_can_change_label_but_not_key(db):
    _seed_two_system_kinds(db)
    created = create_agreement_kind(
        AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db
    )
    updated = update_agreement_kind(
        created["id"], AgreementKindBody(label="Vikar (ny tekst)"),
        current_user=_dummy_user(), db=db,
    )
    assert updated["label"] == "Vikar (ny tekst)"
    assert updated["key"] == created["key"]


def test_delete_system_kind_is_blocked(db):
    _seed_two_system_kinds(db)
    fixed = db.query(MasterAgreementKind).filter(MasterAgreementKind.key == "hourly_fixed").first()
    try:
        delete_agreement_kind(fixed.id, current_user=_dummy_user(), db=db)
        assert False, "skulle have fejlet – systemtype"
    except Exception as e:
        assert "400" in str(e) or "system" in str(e).lower()


def test_delete_user_created_kind_in_use_is_blocked(db):
    _seed_two_system_kinds(db)
    created = create_agreement_kind(
        AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db
    )
    emp = Employee(
        employee_number="9003", first_name="Brug", last_name="Er",
        agreement_kind=created["key"], agreement_type="",
        hire_date=date(2026, 1, 1),
    )
    db.add(emp)
    db.commit()
    try:
        delete_agreement_kind(created["id"], current_user=_dummy_user(), db=db)
        assert False, "skulle have fejlet – i brug"
    except Exception as e:
        assert "400" in str(e) or "brug" in str(e).lower()


def test_delete_unused_user_created_kind_succeeds(db):
    _seed_two_system_kinds(db)
    created = create_agreement_kind(
        AgreementKindBody(label="Vikar"), current_user=_dummy_user(), db=db
    )
    delete_agreement_kind(created["id"], current_user=_dummy_user(), db=db)
    assert db.query(MasterAgreementKind).filter(MasterAgreementKind.id == created["id"]).first() is None
```

- [ ] **Step 2: Kør testene og bekræft at de fejler**

Run: `pytest tests/test_agreement_kind_stamdata.py -v`
Expected: FAIL — `ImportError: cannot import name 'AgreementKindBody'`

- [ ] **Step 3: Tilføj router-koden**

I `app/routers/stamdata.py`, udvid importen fra `database.models`:

```python
from database.models import (
    AppUser, Employee, DispatcherGroup,
    MasterAgreementType, MasterOvertimeRate,
    MasterSupplementRate, MasterPayType, MasterAbsenceType, MasterCvrNumber,
    Holiday,
)
```
bliver til:
```python
from database.models import (
    AppUser, Employee, DispatcherGroup,
    MasterAgreementType, MasterAgreementKind, MasterOvertimeRate,
    MasterSupplementRate, MasterPayType, MasterAbsenceType, MasterCvrNumber,
    Holiday,
)
```

Tilføj en ny sektion — indsæt den lige efter `# ── Fraværstyper ──...` sektionens sidste funktion (`delete_absence_type`), før `# ── Disponentgrupper ──...`:

```python
# ── Aftaletyper ───────────────────────────────────────────────────────────


class AgreementKindBody(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None
    requires_agreement_type: Optional[bool] = None


def _agreement_kind_row(r) -> dict:
    return {
        "id": r.id,
        "key": r.key,
        "label": r.label,
        "is_active": r.is_active,
        "is_user_created": r.is_user_created,
        "requires_agreement_type": r.requires_agreement_type,
    }


@router.get("/agreement-kinds")
def list_agreement_kinds(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    rows = db.query(MasterAgreementKind).order_by(
        MasterAgreementKind.sort_order, MasterAgreementKind.label
    ).all()
    return [_agreement_kind_row(r) for r in rows]


@router.post("/agreement-kinds", status_code=201)
def create_agreement_kind(
    body: AgreementKindBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.label:
        raise HTTPException(400, "Betegnelse er påkrævet")
    label = body.label.strip()
    key = _normalize_absence_key(label)  # generisk slug-normalisering, trods navnet
    if db.query(MasterAgreementKind).filter(MasterAgreementKind.key == key).first():
        raise HTTPException(400, "En aftaletype med denne betegnelse (eller tilsvarende nøgle) eksisterer allerede")
    max_order = db.query(MasterAgreementKind).count()
    row = MasterAgreementKind(
        key=key, label=label,
        is_active=True, is_user_created=True,
        requires_agreement_type=(
            body.requires_agreement_type if body.requires_agreement_type is not None else True
        ),
        sort_order=max_order + 1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "agreement_kind", row.id,
               f"Oprettet aftaletype: {row.label}")
    db.commit()
    return _agreement_kind_row(row)


@router.patch("/agreement-kinds/{kind_id}")
def update_agreement_kind(
    kind_id: int,
    body: AgreementKindBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterAgreementKind).filter(MasterAgreementKind.id == kind_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if body.label is not None:
        row.label = body.label.strip()
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.requires_agreement_type is not None:
        row.requires_agreement_type = body.requires_agreement_type
    db.commit()
    log_action(db, current_user, "stamdata_update", "agreement_kind", row.id,
               f"Aftaletype opdateret: {row.label}, aktiv={row.is_active}")
    db.commit()
    return _agreement_kind_row(row)


@router.delete("/agreement-kinds/{kind_id}", status_code=204)
def delete_agreement_kind(
    kind_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterAgreementKind).filter(MasterAgreementKind.id == kind_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if not row.is_user_created:
        raise HTTPException(400, "Systemtyper kan ikke slettes")
    in_use = db.query(Employee).filter(Employee.agreement_kind == row.key).first()
    if in_use:
        raise HTTPException(400, f"Kan ikke slettes – bruges af medarbejderen '{in_use.name}'")
    log_action(db, current_user, "stamdata_delete", "agreement_kind", row.id,
               f"Slettet aftaletype: {row.label}")
    db.delete(row)
    db.commit()
```

Bemærk: `key` indgår bevidst ikke i `AgreementKindBody` — den kan ikke sendes med fra klienten og ændres derfor aldrig efter oprettelse (jf. Global Constraints).

- [ ] **Step 4: Kør testene og bekræft at de består**

Run: `pytest tests/test_agreement_kind_stamdata.py -v`
Expected: PASS (alle 8 tests)

- [ ] **Step 5: Kør hele testsuiten**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/stamdata.py tests/test_agreement_kind_stamdata.py
git commit -m "feat: CRUD-endpoints for aftaletyper i Stamdata"
```

---

## Task 4: `employees.py` — offentlig liste-endpoint + validering

**Files:**
- Modify: `app/routers/employees.py`
- Test: `tests/test_employee_agreement_kind_validation.py`

**Interfaces:**
- Consumes: `MasterAgreementKind` (Task 1).
- Produces: `GET /api/employees/agreement-kinds` (kun aktive rækker) og udvidet validering i `create_employee`/`update_employee`.

- [ ] **Step 1: Skriv de fejlende tests**

```python
# tests/test_employee_agreement_kind_validation.py
import pytest
from datetime import date
from fastapi import HTTPException

from database.models import AppUser, MasterAgreementKind
from database.schemas import EmployeeCreate, WorkSchedule
from routers.employees import agreement_kinds, create_employee


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _seed_kinds(db):
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.add(MasterAgreementKind(
        key="ingen_overenskomst", label="Ny type uden krav",
        is_active=True, is_user_created=True,
        requires_agreement_type=False, sort_order=2,
    ))
    db.add(MasterAgreementKind(
        key="skjult", label="Inaktiv type",
        is_active=False, is_user_created=True,
        requires_agreement_type=True, sort_order=3,
    ))
    db.commit()


def _base_employee_body(**overrides):
    data = dict(
        employee_number="9101",
        first_name="Ny",
        last_name="Medarbejder",
        agreement_kind="hourly_fixed",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    return EmployeeCreate(**data)


def test_agreement_kinds_endpoint_only_returns_active(db):
    _seed_kinds(db)
    rows = agreement_kinds(current_user=_dummy_user(), db=db)
    keys = {r["key"] for r in rows}
    assert keys == {"hourly_fixed", "ingen_overenskomst"}


def test_create_employee_rejects_unknown_agreement_kind(db):
    _seed_kinds(db)
    body = _base_employee_body(agreement_kind="findes_ikke")
    with pytest.raises(HTTPException) as exc:
        create_employee(body, current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400


def test_create_employee_requires_agreement_type_when_flagged(db):
    _seed_kinds(db)
    body = _base_employee_body(agreement_kind="hourly_fixed", agreement_type="")
    with pytest.raises(HTTPException) as exc:
        create_employee(body, current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400


def test_create_employee_allows_empty_agreement_type_when_not_required(db):
    _seed_kinds(db)
    body = _base_employee_body(
        employee_number="9102",
        agreement_kind="ingen_overenskomst",
        agreement_type="",
    )
    result = create_employee(body, current_user=_dummy_user(), db=db)
    assert result.agreement_kind == "ingen_overenskomst"
    assert result.agreement_type == ""
```

- [ ] **Step 2: Kør testene og bekræft at de fejler**

Run: `pytest tests/test_employee_agreement_kind_validation.py -v`
Expected: FAIL — `ImportError: cannot import name 'agreement_kinds' from 'routers.employees'`

- [ ] **Step 3: Tilføj endpoint og valideringslogik**

I `app/routers/employees.py`, udvid importen:

```python
from database.models import AppUser, DispatcherGroup, Employee
```
bliver til:
```python
from database.models import AppUser, DispatcherGroup, Employee, MasterAgreementKind
```

Tilføj en ny endpoint lige efter `agreement_types` (efter `return [{"name": k, "hourly_rate": float(v)} for k, v in types.items()]`):

```python
@router.get("/agreement-kinds")
def agreement_kinds(current_user: AppUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Aktive Aftale-typer fra Stamdata – bruges til at udfylde medarbejder-modalens dropdown."""
    rows = db.query(MasterAgreementKind).filter(MasterAgreementKind.is_active == True).order_by(
        MasterAgreementKind.sort_order, MasterAgreementKind.label
    ).all()
    return [
        {"key": r.key, "label": r.label, "requires_agreement_type": r.requires_agreement_type}
        for r in rows
    ]


def _agreement_type_required(db: Session, agreement_kind: str) -> bool:
    row = db.query(MasterAgreementKind).filter(MasterAgreementKind.key == agreement_kind).first()
    return row.requires_agreement_type if row else True
```

Ret `create_employee` — find:

```python
    if body.agreement_type not in load_agreement_types_from_db(db):
        raise HTTPException(400, f"Ukendt overenskomsttype: {body.agreement_type}")
```

og erstat med:

```python
    if not db.query(MasterAgreementKind).filter(MasterAgreementKind.key == body.agreement_kind).first():
        raise HTTPException(400, f"Ukendt aftaletype: {body.agreement_kind}")
    if _agreement_type_required(db, body.agreement_kind):
        if not body.agreement_type or body.agreement_type not in load_agreement_types_from_db(db):
            raise HTTPException(400, f"Ukendt overenskomsttype: {body.agreement_type}")
    else:
        body.agreement_type = ""
```

Ret `update_employee` — find:

```python
    if body.agreement_type and body.agreement_type not in load_agreement_types_from_db(db):
        raise HTTPException(400, f"Ukendt overenskomsttype: {body.agreement_type}")
```

og erstat med:

```python
    if body.agreement_kind and not db.query(MasterAgreementKind).filter(
        MasterAgreementKind.key == body.agreement_kind
    ).first():
        raise HTTPException(400, f"Ukendt aftaletype: {body.agreement_kind}")
    effective_kind = body.agreement_kind or emp.agreement_kind
    effective_agreement_type = (
        body.agreement_type if body.agreement_type is not None else emp.agreement_type
    )
    if _agreement_type_required(db, effective_kind):
        if not effective_agreement_type or effective_agreement_type not in load_agreement_types_from_db(db):
            raise HTTPException(400, f"Ukendt overenskomsttype: {effective_agreement_type}")
    elif body.agreement_type is None and body.agreement_kind and body.agreement_kind != emp.agreement_kind:
        # Skiftes til en type der ikke kræver Overenskomsttype, uden at et nyt
        # felt er angivet samtidig – nulstil det gemte felt til "ikke relevant".
        body.agreement_type = ""
```

- [ ] **Step 4: Kør testene og bekræft at de består**

Run: `pytest tests/test_employee_agreement_kind_validation.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Kør hele testsuiten**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/routers/employees.py tests/test_employee_agreement_kind_validation.py
git commit -m "feat: valider Aftale mod Stamdata, gør Overenskomsttype betinget påkrævet"
```

---

## Task 5: Overtidsberegning — `calculate_flat_hours()`

**Files:**
- Modify: `app/calculators/overtime.py`
- Test: `tests/test_overtime_flat_hours.py`

**Interfaces:**
- Produces: `calculate_flat_hours(start, end, pause_intervals=None) -> OvertimeResult` — bruges af Task 6.

- [ ] **Step 1: Skriv den fejlende test**

```python
# tests/test_overtime_flat_hours.py
from datetime import datetime
from decimal import Decimal

from calculators.overtime import calculate_flat_hours


def test_flat_hours_counts_all_worked_time_as_normal():
    start = datetime(2026, 8, 24, 6, 0)
    end = datetime(2026, 8, 24, 22, 0)  # 16 timer, ville normalt give aften/nat-tillæg

    result = calculate_flat_hours(start, end)

    assert result.total_hours == Decimal("16")
    assert result.normal_hours == Decimal("16")
    assert result.ot_before_hours == Decimal("0")
    assert result.ot_13_hours == Decimal("0")
    assert result.ot_extra_hours == Decimal("0")
    assert result.sh_kode8_hours == Decimal("0")
    assert result.sh_kode9_hours == Decimal("0")


def test_flat_hours_subtracts_pauses():
    start = datetime(2026, 8, 24, 8, 0)
    end = datetime(2026, 8, 24, 16, 0)  # 8 timer
    pauses = [(datetime(2026, 8, 24, 12, 0), datetime(2026, 8, 24, 12, 30))]  # 0,5 t pause

    result = calculate_flat_hours(start, end, pauses)

    assert result.total_hours == Decimal("7.5")
    assert result.normal_hours == Decimal("7.5")
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `pytest tests/test_overtime_flat_hours.py -v`
Expected: FAIL — `ImportError: cannot import name 'calculate_flat_hours'`

- [ ] **Step 3: Tilføj funktionen**

I `app/calculators/overtime.py`, tilføj til sidst i filen:

```python
def calculate_flat_hours(
    start: datetime,
    end: datetime,
    pause_intervals: list[tuple[datetime, datetime]] | None = None,
) -> OvertimeResult:
    """
    Bruges til medarbejdere med en Aftale-type uden for de to kendte nøgler
    (hourly_fixed/hourly_flexible, jf. AgreementKind i database/models.py) –
    ingen tillæg eller loft, kun rene arbejdstimer til normal sats.
    """
    result = OvertimeResult()
    work_intervals = _subtract_pauses(start, end, pause_intervals or [])
    for seg_start, seg_end in work_intervals:
        duration = Decimal(str((seg_end - seg_start).total_seconds())) / 3600
        if duration <= 0:
            continue
        result.total_hours += duration
        result.normal_hours += duration
    return result
```

- [ ] **Step 4: Kør testen og bekræft at den nu består**

Run: `pytest tests/test_overtime_flat_hours.py -v`
Expected: PASS

- [ ] **Step 5: Kør hele testsuiten**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/calculators/overtime.py tests/test_overtime_flat_hours.py
git commit -m "feat: tilføj calculate_flat_hours til Aftale-typer uden OT-beregning"
```

---

## Task 6: Spring OT-beregning over for ikke-genkendte Aftale-typer

**Files:**
- Modify: `app/routers/payroll_router.py`
- Test: `tests/test_payroll_unrecognized_agreement_kind.py`

**Interfaces:**
- Consumes: `calculate_flat_hours` (Task 5).
- Produces: `_calculate_employee()` returnerer nu `ot_before_hours=0, ot_13_hours=0, ot_extra_hours=0, sh_kode8_hours=0, sh_kode9_hours=0` og `normal_hours` = fulde arbejdstimer for medarbejdere med en ikke-genkendt `agreement_kind`.

- [ ] **Step 1: Skriv den fejlende test**

```python
# tests/test_payroll_unrecognized_agreement_kind.py
from datetime import datetime, date

from database.models import Employee, ActivitySource, ActivityStatus
from routers.payroll_router import _calculate_employee
from conftest import make_activity


def test_unrecognized_agreement_kind_gets_flat_hours_no_overtime(db):
    emp = Employee(
        employee_number="9201",
        first_name="Ny",
        last_name="Aftaletype",
        agreement_kind="fremtidig_type",  # findes ikke i AgreementKind
        agreement_type="",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    # Vagt der ville udløse aftentillæg for en normal medarbejder (18-22)
    make_activity(
        db, emp,
        datetime(2026, 8, 24, 14, 0), datetime(2026, 8, 24, 22, 0),
        activity_type="normal", source=ActivitySource.tachograph,
        status=ActivityStatus.approved,
    )

    result = _calculate_employee(emp, date(2026, 8, 24), date(2026, 8, 24), db)

    assert result["normal_hours"] == 8.0
    assert result["ot_before_hours"] == 0.0
    assert result["ot_13_hours"] == 0.0
    assert result["ot_extra_hours"] == 0.0
    assert result["sh_kode8_hours"] == 0.0
    assert result["sh_kode9_hours"] == 0.0
```

- [ ] **Step 2: Kør testen og bekræft at den fejler**

Run: `pytest tests/test_payroll_unrecognized_agreement_kind.py -v`
Expected: FAIL — assertion fejler, fordi den nuværende kode i dag ville behandle `emp` som `hourly_fixed`-lignende (falder i `else`-grenen af `is_hourly_flexible`) og generere aftentillæg (`ot_extra_hours` eller `ot_13_hours` > 0) for timerne efter kl. 18.

- [ ] **Step 3: Tilføj `is_recognized_agreement_kind`-flaget**

I `app/routers/payroll_router.py`, find (i `_calculate_employee`):

```python
    is_hourly_flexible = emp.agreement_kind == AgreementKind.hourly_flexible
```

og indsæt lige før:

```python
    is_recognized_agreement_kind = emp.agreement_kind in (
        AgreementKind.hourly_fixed, AgreementKind.hourly_flexible,
    )
```

- [ ] **Step 4: Importér `calculate_flat_hours` og omstrukturér dag-grenen**

Udvid importen:
```python
from calculators.overtime import (
    OT_13_KEY,
    OT_13_MAX,
    OT_BEFORE_KEY,
    OT_EXTRA_KEY,
    calculate_overtime,
)
```
bliver til:
```python
from calculators.overtime import (
    OT_13_KEY,
    OT_13_MAX,
    OT_BEFORE_KEY,
    OT_EXTRA_KEY,
    calculate_overtime,
    calculate_flat_hours,
)
```

Find blokken:

```python
                    if day_type in (DayType.NORMAL, DayType.SATURDAY):
```

(den er del af en større `if/else`, med `calculate_special_day_overtime` i `else`-grenen umiddelbart efter). Erstat starten af denne `if` med en ny yderste gren, så hele blokken bliver:

```python
                    if not is_recognized_agreement_kind:
                        # Aftale-type uden for de to kendte nøgler – ingen
                        # automatisk OT-beregning endnu (se
                        # docs/superpowers/specs/2026-08-24-aftale-stamdata-design.md).
                        ot = calculate_flat_hours(act.start_time, act.end_time, pauses)
                    elif day_type in (DayType.NORMAL, DayType.SATURDAY):
```

Resten af den eksisterende `elif`-gren (den tidligere `if`-gren) og den afsluttende `else`-gren (`calculate_special_day_overtime`) forbliver helt uændrede — kun den indledende betingelse ændres fra `if` til `elif`, og en ny `if not is_recognized_agreement_kind:`-gren tilføjes foran.

- [ ] **Step 5: Kør testen og bekræft at den nu består**

Run: `pytest tests/test_payroll_unrecognized_agreement_kind.py -v`
Expected: PASS

- [ ] **Step 6: Kør hele testsuiten**

Run: `pytest -v`
Expected: PASS (bekræfter at `hourly_fixed`/`hourly_flexible`-medarbejdere er upåvirkede)

- [ ] **Step 7: Commit**

```bash
git add app/routers/payroll_router.py tests/test_payroll_unrecognized_agreement_kind.py
git commit -m "feat: spring OT-beregning over for ikke-genkendte aftaletyper"
```

---

## Task 7: Stamdata-fane "Aftale" i frontend

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`

**Interfaces:**
- Consumes: `GET/POST/PATCH/DELETE /api/stamdata/agreement-kinds` (Task 3).
- Produces: `loadStamdataAgreementKinds()`, `openStamdataAgreementKindModal()`, `confirmStamdataAgreementKind()`, `deleteStamdataAgreementKind()` i `app.js` — kaldes fra Task 8 via `state.agreementKinds`.

- [ ] **Step 1: Tilføj fane-knap og "+ Tilføj"-knap**

I `app/templates/index.html`, find toolbar-knapperne (efter `btn-stamdata-add-dispatcher`):

```html
        <button id="btn-stamdata-add-dispatcher" class="btn btn-primary" style="display:none" onclick="openStamdataDispatcherModal()">+ Tilføj</button>
      </div>
```

Indsæt en ny knap før den lukkende `</div>`:

```html
        <button id="btn-stamdata-add-dispatcher" class="btn btn-primary" style="display:none" onclick="openStamdataDispatcherModal()">+ Tilføj</button>
        <button id="btn-stamdata-add-agreementkind" class="btn btn-primary" style="display:none" onclick="openStamdataAgreementKindModal()">+ Tilføj</button>
      </div>
```

Find fane-knappen for Disponentgrupper:

```html
        <button id="sd-tab-dispatcher" onclick="switchStamdataTab('dispatcher')"
                style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer">
          Disponentgrupper
        </button>
      </div>
```

Indsæt en ny fane-knap før den lukkende `</div>`:

```html
        <button id="sd-tab-dispatcher" onclick="switchStamdataTab('dispatcher')"
                style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer">
          Disponentgrupper
        </button>
        <button id="sd-tab-agreementkind" onclick="switchStamdataTab('agreementkind')"
                style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer">
          Aftale
        </button>
      </div>
```

- [ ] **Step 2: Tilføj tabel-pane**

Find Fraværstyper-panen (`<div id="sd-pane-absence" ...> ... </div>`, linje ~499-514) og indsæt en ny pane lige efter dens lukkende `</div>`, før `<!-- CVR nummer -->`:

```html
        <!-- Aftale -->
        <div id="sd-pane-agreementkind" style="display:none">
          <table style="width:100%;border-collapse:collapse;font-size:14px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
            <thead>
              <tr style="background:var(--primary);color:#fff">
                <th style="padding:10px 14px;text-align:left;font-weight:600">Betegnelse</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Type</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Kræver overenskomsttype</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Aktiv</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Handlinger</th>
              </tr>
            </thead>
            <tbody id="stamdata-agreementkind-tbody">
              <tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>
            </tbody>
          </table>
        </div>
```

- [ ] **Step 3: Tilføj modal til opret/redigér**

Find modalen "Stamdata: Opret/rediger CVR nummer" (starter ved kommentaren `<!-- ── Stamdata: Opret/rediger CVR nummer ── -->`, ca. linje 1681) og indsæt en ny modal lige før den:

```html
<!-- ── Stamdata: Opret/rediger aftaletype ── -->
<div id="modal-stamdata-agreementkind" class="modal-overlay hidden">
  <div class="modal">
    <div class="modal-header">
      <h2 id="stamdata-agreementkind-title">Ny aftaletype</h2>
      <button class="modal-close" onclick="closeModal('modal-stamdata-agreementkind')">&times;</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="stamdata-agreementkind-id">
      <div class="form-group">
        <label>Betegnelse</label>
        <input type="text" id="stamdata-agreementkind-label" placeholder="fx Månedslønnet">
      </div>
      <div class="form-group">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
          <input type="checkbox" id="stamdata-agreementkind-requires" style="width:16px;height:16px;cursor:pointer" checked>
          Kræver overenskomsttype
        </label>
      </div>
      <div class="form-group">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
          <input type="checkbox" id="stamdata-agreementkind-active" style="width:16px;height:16px;cursor:pointer" checked>
          Aktiv
        </label>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-stamdata-agreementkind')">Annuller</button>
      <button class="btn btn-primary" onclick="confirmStamdataAgreementKind()">Gem</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Tilføj JS til `switchStamdataTab` og `loadStamdata`**

I `app/static/js/app.js`, find:

```javascript
function switchStamdataTab(tab) {
  ["agreement", "overtime", "supplement", "paytype", "absence", "cvr", "holiday", "dispatcher"].forEach(t => {
```

Ret til:

```javascript
function switchStamdataTab(tab) {
  ["agreement", "overtime", "supplement", "paytype", "absence", "cvr", "holiday", "dispatcher", "agreementkind"].forEach(t => {
```

Find:

```javascript
  document.getElementById("btn-stamdata-add-dispatcher").style.display = tab === "dispatcher" ? "" : "none";
}
```

Ret til:

```javascript
  document.getElementById("btn-stamdata-add-dispatcher").style.display = tab === "dispatcher" ? "" : "none";
  document.getElementById("btn-stamdata-add-agreementkind").style.display = tab === "agreementkind" ? "" : "none";
}
```

Find:

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
    loadStamdataDispatcherGroups(),
  ]);
}
```

Ret til:

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
    loadStamdataDispatcherGroups(),
    loadStamdataAgreementKinds(),
  ]);
}
```

- [ ] **Step 5: Tilføj `state.agreementKinds` og CRUD-funktionerne**

Find state-initialiseringen:

```javascript
  agreementTypes: [],
  absenceTypes: [],
```

Ret til:

```javascript
  agreementTypes: [],
  agreementKinds: [],
  absenceTypes: [],
```

Tilføj til sidst i filen (efter de øvrige Stamdata-funktioner, fx lige efter `deleteStamdataAbsence`):

```javascript
// ── Aftaletyper (stamdata) ────────────────────────────────────────────────

async function loadStamdataAgreementKinds() {
  const tbody = document.getElementById("stamdata-agreementkind-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/agreement-kinds");
    const badge = (v, yes, no) => v
      ? `<span style="color:var(--primary);font-weight:600">${yes}</span>`
      : `<span style="color:var(--text-light)">${no}</span>`;
    tbody.innerHTML = rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.label)}</td>
        <td style="padding:10px 14px;text-align:center">
          <span style="display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;
                       background:${r.is_user_created ? "var(--light-tint)" : "#f5f5f5"};
                       color:${r.is_user_created ? "var(--primary)" : "var(--text-light)"}">
            ${r.is_user_created ? "Brugeroprettet" : "System"}
          </span>
        </td>
        <td style="padding:10px 14px;text-align:center">${badge(r.requires_agreement_type, "Ja", "Nej")}</td>
        <td style="padding:10px 14px;text-align:center">${badge(r.is_active, "Aktiv", "Inaktiv")}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataAgreementKindModal(${r.id},${jq(r.label)},${r.is_active},${r.requires_agreement_type},${r.is_user_created})">Rediger</button>
          ${r.is_user_created
            ? `<button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                       onclick="deleteStamdataAgreementKind(${r.id},${jq(r.label)})">Slet</button>`
            : ""}
        </td>
      </tr>`).join("");
  } catch (e) { tbody.innerHTML = `<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
  // Ny/ændret aftaletype skal med det samme kunne vælges i medarbejder-modalen
  try {
    state.agreementKinds = await GET("/api/employees/agreement-kinds");
  } catch (_) {}
}

function openStamdataAgreementKindModal(id, label, isActive, requiresAgreementType, isUserCreated) {
  document.getElementById("stamdata-agreementkind-id").value = id || "";
  document.getElementById("stamdata-agreementkind-label").value = label || "";
  document.getElementById("stamdata-agreementkind-active").checked = isActive !== false;
  document.getElementById("stamdata-agreementkind-requires").checked = requiresAgreementType !== false;
  document.getElementById("stamdata-agreementkind-title").textContent = id ? "Rediger aftaletype" : "Ny aftaletype";
  openModal("modal-stamdata-agreementkind");
}

async function confirmStamdataAgreementKind() {
  const id       = document.getElementById("stamdata-agreementkind-id").value;
  const label    = document.getElementById("stamdata-agreementkind-label").value.trim();
  const active   = document.getElementById("stamdata-agreementkind-active").checked;
  const requires = document.getElementById("stamdata-agreementkind-requires").checked;
  if (!label) { toast("Betegnelse er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/agreement-kinds/${id}`, { label, is_active: active, requires_agreement_type: requires });
      toast("Aftaletype opdateret");
    } else {
      await POST("/api/stamdata/agreement-kinds", { label, requires_agreement_type: requires });
      toast("Aftaletype oprettet");
    }
    closeModal("modal-stamdata-agreementkind");
    await loadStamdataAgreementKinds();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataAgreementKind(id, label) {
  if (!confirm(`Slet aftaletypen "${label}"?`)) return;
  try {
    await DEL(`/api/stamdata/agreement-kinds/${id}`);
    toast("Aftaletype slettet");
    await loadStamdataAgreementKinds();
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 6: Manuel verifikation**

Start serveren og log ind som administrator:

```bash
cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- Gå til Stamdata → fanen "Aftale" skal vise de to systemtyper ("Timelønnet, fast arbejdstid" / "Timelønnet, ikke fastlagt arbejdstid") med badge "System" og uden Slet-knap.
- Klik "+ Tilføj" → opret en testtype uden "Kræver overenskomsttype" → den skal fremgå med badge "Brugeroprettet", "Nej" under Kræver overenskomsttype, og have en Slet-knap.
- Slet testtypen igen → raden forsvinder.
- Prøv at redigere en systemtype → kun label/aktiv kan ændres, ingen fejl.

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: Stamdata-fane til administration af aftaletyper"
```

---

## Task 8: Dynamisk Aftale-dropdown i medarbejder-modalen

**Files:**
- Modify: `app/templates/index.html`
- Modify: `app/static/js/app.js`

**Interfaces:**
- Consumes: `GET /api/employees/agreement-kinds` (Task 4), `state.agreementKinds` (Task 7).

- [ ] **Step 1: Fjern de hardcodede `<option>`-tags og giv asterisken et id**

I `app/templates/index.html`, find:

```html
      <div class="form-row">
        <div class="form-group">
          <label>Aftale <span style="color:var(--danger)">*</span></label>
          <select id="emp-agreement-kind">
            <option value="">[Vælg aftale]</option>
            <option value="hourly_fixed">Timelønnet, fast arbejdstid</option>
            <option value="hourly_flexible">Timelønnet, ikke fastlagt arbejdstid</option>
          </select>
        </div>
        <div class="form-group">
          <label>Overenskomsttype <span style="color:var(--danger)">*</span></label>
          <select id="emp-agreement-type"></select>
        </div>
      </div>
```

Ret til:

```html
      <div class="form-row">
        <div class="form-group">
          <label>Aftale <span style="color:var(--danger)">*</span></label>
          <select id="emp-agreement-kind" onchange="onAgreementKindChange()"></select>
        </div>
        <div class="form-group">
          <label>Overenskomsttype <span id="emp-agreement-type-required-star" style="color:var(--danger)">*</span></label>
          <select id="emp-agreement-type"></select>
        </div>
      </div>
```

- [ ] **Step 2: Tilføj `loadAgreementKinds`, `fillAgreementKindSelect` og `onAgreementKindChange`**

I `app/static/js/app.js`, find:

```javascript
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
```

Indsæt lige efter:

```javascript
async function loadAgreementKinds() {
  state.agreementKinds = await GET("/api/employees/agreement-kinds");
}

function fillAgreementKindSelect(selected = null) {
  const sel = document.getElementById("emp-agreement-kind");
  const placeholder = selected ? "" : `<option value="">[Vælg aftale]</option>`;
  sel.innerHTML = placeholder + state.agreementKinds
    .map(k => `<option value="${k.key}" ${k.key === selected ? "selected" : ""}>${h(k.label)}</option>`)
    .join("");
  onAgreementKindChange();
}

function onAgreementKindChange() {
  const key = document.getElementById("emp-agreement-kind").value;
  const kind = state.agreementKinds.find(k => k.key === key);
  const requires = kind ? kind.requires_agreement_type : true;
  document.getElementById("emp-agreement-type-required-star").style.display = requires ? "" : "none";
}
```

Bemærk: `loadAgreementKinds()` cacher bevidst ikke (`if (state.agreementKinds.length) return`) som `loadAgreementTypes()` gør — den genindlæses hver gang modalen åbnes, så en netop oprettet aftaletype i Stamdata er tilgængelig med det samme uden sideopdatering.

- [ ] **Step 3: Kald `loadAgreementKinds()` og `fillAgreementKindSelect()` i stedet for den statiske værdi-nulstilling**

Find i `openNewEmployeeModal`:

```javascript
async function openNewEmployeeModal() {
  await loadAgreementTypes();
  document.getElementById("emp-modal-title").textContent = "Opret medarbejder";
  document.getElementById("emp-save-btn").textContent = "Opret";
  document.getElementById("emp-id").value = "";
  ["emp-number","emp-card","emp-initials","emp-firstname","emp-lastname","emp-address","emp-postal",
   "emp-email","emp-phone","emp-mobile"].forEach(id => document.getElementById(id).value = "");
  document.getElementById("emp-agreement-kind").value = "";
  fillAgreementTypeSelect();
```

Ret til:

```javascript
async function openNewEmployeeModal() {
  await loadAgreementTypes();
  await loadAgreementKinds();
  document.getElementById("emp-modal-title").textContent = "Opret medarbejder";
  document.getElementById("emp-save-btn").textContent = "Opret";
  document.getElementById("emp-id").value = "";
  ["emp-number","emp-card","emp-initials","emp-firstname","emp-lastname","emp-address","emp-postal",
   "emp-email","emp-phone","emp-mobile"].forEach(id => document.getElementById(id).value = "");
  fillAgreementKindSelect();
  fillAgreementTypeSelect();
```

Find i `openEditEmployee`:

```javascript
async function openEditEmployee(id) {
  await loadAgreementTypes();
  const e = state.employees.find(x => x.id === id);
  if (!e) return;
  document.getElementById("emp-modal-title").textContent = "Rediger medarbejder";
  document.getElementById("emp-save-btn").textContent = "Opdater";
  document.getElementById("emp-id").value = e.id;
  document.getElementById("emp-number").value = e.employee_number;
  document.getElementById("emp-card").value = e.tachograph_card_number || "";
  document.getElementById("emp-initials").value = e.initials || "";
  document.getElementById("emp-firstname").value = e.first_name;
  document.getElementById("emp-lastname").value = e.last_name;
  document.getElementById("emp-address").value = e.address || "";
  document.getElementById("emp-postal").value = e.postal_code || "";
  document.getElementById("emp-email").value = e.email || "";
  document.getElementById("emp-phone").value = e.phone || "";
  document.getElementById("emp-mobile").value = e.mobile || "";
  document.getElementById("emp-agreement-kind").value = e.agreement_kind;
  fillAgreementTypeSelect(e.agreement_type);
```

Ret til:

```javascript
async function openEditEmployee(id) {
  await loadAgreementTypes();
  await loadAgreementKinds();
  const e = state.employees.find(x => x.id === id);
  if (!e) return;
  document.getElementById("emp-modal-title").textContent = "Rediger medarbejder";
  document.getElementById("emp-save-btn").textContent = "Opdater";
  document.getElementById("emp-id").value = e.id;
  document.getElementById("emp-number").value = e.employee_number;
  document.getElementById("emp-card").value = e.tachograph_card_number || "";
  document.getElementById("emp-initials").value = e.initials || "";
  document.getElementById("emp-firstname").value = e.first_name;
  document.getElementById("emp-lastname").value = e.last_name;
  document.getElementById("emp-address").value = e.address || "";
  document.getElementById("emp-postal").value = e.postal_code || "";
  document.getElementById("emp-email").value = e.email || "";
  document.getElementById("emp-phone").value = e.phone || "";
  document.getElementById("emp-mobile").value = e.mobile || "";
  fillAgreementKindSelect(e.agreement_kind);
  fillAgreementTypeSelect(e.agreement_type);
```

- [ ] **Step 4: Manuel verifikation**

Med serveren kørende (`cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload`):

- Åbn "Tilføj medarbejder" → "Aftale"-dropdown viser nu de aktive typer hentet fra Stamdata (inkl. en evt. testtype fra Task 7), ikke længere hardcoded.
- Vælg en type med "Kræver overenskomsttype" = Nej → den røde `*` ved "Overenskomsttype" forsvinder.
- Vælg en type med "Kræver overenskomsttype" = Ja → `*` vises igen.
- Opret en medarbejder med en type uden krav og tomt Overenskomsttype-felt → skal lykkes.
- Rediger en eksisterende medarbejder → "Aftale" og "Overenskomsttype" viser korrekt de gemte værdier, og stjernen matcher den valgte types krav.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html app/static/js/app.js
git commit -m "feat: dynamisk Aftale-dropdown i medarbejder-modalen"
```

---

## Self-Review Summary

- **Spec-dækning:** Alle 5 beslutningspunkter i design-spec'en er dækket: (1) redigerbar label for de 2 systemtyper → Task 3+7; (2) flere aftaletyper via Stamdata → Task 3+7; (3) "kræver overenskomsttype"-styring → Task 3, 4, 8; (4) OT springes over for ukendte typer → Task 5+6; (5) `key` er fast/uredigerbar → Task 3 (`AgreementKindBody` har bevidst intet `key`-felt).
- **Ingen placeholders:** Al kode i planen er komplet og eksekverbar, ingen "TODO"/"tilføj fejlhåndtering".
- **Typekonsistens tjekket:** `MasterAgreementKind`-feltnavne (`key`, `label`, `is_active`, `is_user_created`, `requires_agreement_type`, `sort_order`) er identiske på tværs af Task 1 (model), Task 2 (seed), Task 3 (CRUD + `_agreement_kind_row`), Task 4 (læsning) og frontend (Task 7-8). `calculate_flat_hours`-signaturen i Task 5 matches nøjagtigt af kaldet i Task 6.
