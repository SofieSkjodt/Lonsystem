# Hærdet mailafsendelse fra PDF-timeseddel-knapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gøre den allerede eksisterende mailafsendelse fra "✉ Send" (pr. medarbejder) og "Send Timeseddel" (batch i PDF-Timesedler-modal) klar til produktion: generiske fejlbeskeder til klienten, fuld fejl logget internt, og en reel SMTP-adgangskode sat op.

**Architecture:** Ingen ny funktionalitet eller nye endpoints. To eksisterende endpoints i `app/routers/timeseddel_router.py` (`POST /{employee_id}/send` og `POST /send-all`) ændres til at følge kodebasens etablerede fejlmønster (se `payroll_router.py:308`): `logging.error(...)` med den fulde exception, og en generisk besked til klienten. Derudover en dokumenterende kommentar i `app/.env` og en manuel slutverifikation i browseren.

**Tech Stack:** FastAPI, SQLAlchemy, pytest (direkte funktionskald mod routerfunktioner, ingen `TestClient`/HTTP-lag — se eksisterende mønster i `tests/test_payroll_settlement.py` og `tests/test_backup.py`).

## Global Constraints

- Generisk fejlbesked for `/send`: `"Mailen kunne ikke sendes – kontakt administrator"` (HTTP 500).
- Generisk fejltekst i `/send-all`s `failed`-liste: `"Kunne ikke sendes"` (erstatter `str(e)`).
- Den fulde exception-tekst skal ALTID logges internt via `logging.error(...)`, inkl. medarbejdernavn og id, i begge endpoints.
- Ingen SSL/465-understøttelse tilføjes (bevidst fravalgt i spec).
- `SMTP_PASSWORD` i `app/.env` udfyldes af brugeren selv — skriv den ALDRIG i chat eller i nogen fil-kommentar.
- Testmønster: importér routerfunktionen direkte og kald den med almindelige argumenter (`db=`, `current_user=`) — ingen FastAPI `TestClient`. Kør tests med `python -m pytest tests/<fil> -q` fra repo-roden.

---

### Task 1: Hærd fejlhåndtering i `/send`-endpointet (enkelt medarbejder)

**Files:**
- Modify: `app/routers/timeseddel_router.py:1` (tilføj `import logging`), `app/routers/timeseddel_router.py:368-377` (except-blok)
- Test: Create `tests/test_timeseddel_mail_error_handling.py`

**Interfaces:**
- Consumes: `routers.timeseddel_router.send_timeseddel(employee_id, period_start, db, current_user)` (eksisterende signatur, uændret), `utils.email_sender.send_timeseddel(to_email, employee_name, period_label, pdf_bytes)` (eksisterende, monkeypatches i test), `tests/conftest.py`-fixtures `db` og `employee`.
- Produces: Intet nyt til andre tasks — dette er en selvstændig hærdning.

- [ ] **Step 1: Write the failing test**

Opret `tests/test_timeseddel_mail_error_handling.py`:

```python
import logging
from datetime import date

import pytest
from fastapi import HTTPException


def test_send_timeseddel_logs_full_error_and_returns_generic_message(db, employee, monkeypatch, caplog):
    from routers.timeseddel_router import send_timeseddel
    from calculators.pay_period import get_or_create_period_for_date
    import utils.email_sender as email_sender

    employee.email = "chauffoer@example.com"
    db.commit()

    period = get_or_create_period_for_date(date(2026, 1, 5), db)

    def _boom(**kwargs):
        raise RuntimeError("535 5.7.3 Authentication unsuccessful")

    monkeypatch.setattr(email_sender, "send_timeseddel", _boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as exc_info:
            send_timeseddel(
                employee_id=employee.id,
                period_start=period.start_date.isoformat(),
                db=db,
                current_user=None,
            )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Mailen kunne ikke sendes – kontakt administrator"
    assert "Authentication unsuccessful" not in exc_info.value.detail
    assert "Authentication unsuccessful" in caplog.text
    assert employee.name in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_timeseddel_mail_error_handling.py -q`
Expected: FAIL — `exc_info.value.detail` er i dag `"E-mail kunne ikke sendes: 535 5.7.3 Authentication unsuccessful"`, så både ligheds-asserten og "not in"-asserten fejler.

- [ ] **Step 3: Write minimal implementation**

Tilføj `import logging` øverst i `app/routers/timeseddel_router.py` (efter `import io`, linje 1):

```python
import io
import logging
from datetime import date, datetime
```

Ret except-blokken i `send_timeseddel` (`app/routers/timeseddel_router.py:368-377`) fra:

```python
    try:
        from utils.email_sender import send_timeseddel as _send
        _send(
            to_email      = emp.email,
            employee_name = emp.name,
            period_label  = period_label,
            pdf_bytes     = pdf_bytes,
        )
    except Exception as e:
        raise HTTPException(500, f"E-mail kunne ikke sendes: {e}")
```

til:

```python
    try:
        from utils.email_sender import send_timeseddel as _send
        _send(
            to_email      = emp.email,
            employee_name = emp.name,
            period_label  = period_label,
            pdf_bytes     = pdf_bytes,
        )
    except Exception as e:
        logging.error(f"Kunne ikke sende timeseddel til {emp.name} (id={emp.id}): {e}")
        raise HTTPException(500, "Mailen kunne ikke sendes – kontakt administrator")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_timeseddel_mail_error_handling.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/timeseddel_router.py tests/test_timeseddel_mail_error_handling.py
git commit -m "fix: log fuld SMTP-fejl internt og vis generisk besked ved enkelt-mailafsendelse"
```

---

### Task 2: Hærd fejlhåndtering i `/send-all`-endpointet (batch)

**Files:**
- Modify: `app/routers/timeseddel_router.py:428-429` (except-blok i løkken)
- Test: Modify `tests/test_timeseddel_mail_error_handling.py` (tilføj test)

**Interfaces:**
- Consumes: `routers.timeseddel_router.send_all_timesedler(body: SendAllRequest, db, current_user)`, `routers.timeseddel_router.SendAllRequest(from_date, to_date, employee_id)` (begge eksisterende, uændrede), `tests/conftest.py`-hjælperen `make_activity(db, employee, start, end, status=...)`, `database.models.ActivityStatus.approved`.
- Produces: Intet nyt til senere tasks.

- [ ] **Step 1: Write the failing test**

Tilføj til `tests/test_timeseddel_mail_error_handling.py`:

```python
from datetime import datetime

from database.models import ActivityStatus


def test_send_all_timesedler_logs_full_error_and_returns_generic_failed_entry(db, employee, monkeypatch, caplog):
    from routers.timeseddel_router import send_all_timesedler, SendAllRequest
    from calculators.pay_period import get_or_create_period_for_date
    from conftest import make_activity
    import utils.email_sender as email_sender

    employee.email = "chauffoer@example.com"
    db.commit()

    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    make_activity(
        db, employee,
        datetime.combine(period.start_date, datetime.min.time()).replace(hour=8),
        datetime.combine(period.start_date, datetime.min.time()).replace(hour=16),
        status=ActivityStatus.approved,
    )

    def _boom(**kwargs):
        raise RuntimeError("535 5.7.3 Authentication unsuccessful")

    monkeypatch.setattr(email_sender, "send_timeseddel", _boom)

    with caplog.at_level(logging.ERROR):
        result = send_all_timesedler(
            SendAllRequest(from_date=period.start_date, to_date=period.end_date, employee_id=employee.id),
            db=db,
            current_user=None,
        )

    assert result["failed"] == [{"name": employee.name, "error": "Kunne ikke sendes"}]
    assert "Authentication unsuccessful" in caplog.text
    assert employee.name in caplog.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_timeseddel_mail_error_handling.py -q`
Expected: FAIL — `result["failed"]` indeholder i dag `{"name": employee.name, "error": "535 5.7.3 Authentication unsuccessful"}`, så ligheds-asserten på `failed`-listen fejler.

- [ ] **Step 3: Write minimal implementation**

Ret except-blokken i løkken i `send_all_timesedler` (`app/routers/timeseddel_router.py:428-429`) fra:

```python
        except Exception as e:
            failed.append({"name": emp.name, "error": str(e)})
```

til:

```python
        except Exception as e:
            logging.error(f"Kunne ikke sende timeseddel til {emp.name} (id={emp.id}): {e}")
            failed.append({"name": emp.name, "error": "Kunne ikke sendes"})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_timeseddel_mail_error_handling.py -q`
Expected: PASS (begge tests i filen)

- [ ] **Step 5: Commit**

```bash
git add app/routers/timeseddel_router.py tests/test_timeseddel_mail_error_handling.py
git commit -m "fix: log fuld SMTP-fejl internt og vis generisk besked ved batch-mailafsendelse"
```

---

### Task 3: Dokumentér SMTP-konfiguration i `.env`

**Files:**
- Modify: `app/.env:2-7`

**Interfaces:**
- Consumes: Intet (ren dokumentation).
- Produces: Intet nyt til senere tasks.

- [ ] **Step 1: Tilføj forklarende kommentar over SMTP-blokken**

Ret `app/.env` fra:

```
ENTRA_TENANT_ID=
ENTRA_CLIENT_ID=
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=skj@poulschou.dk
SMTP_PASSWORD=<Indsæt kodeord>
SMTP_FROM=skj@poulschou.dk
SESSION_SECRET=ps-loen-G7kXmQ2vNpR8wL4jTdYsAe9hFcZuBn3K
```

til:

```
ENTRA_TENANT_ID=
ENTRA_CLIENT_ID=
# SMTP-afsender til timeseddel-mails (STARTTLS/587). Skift SMTP_USER/SMTP_FROM
# ved skift til en anden afsender-postkasse — ingen kodeændring nødvendig.
# SMTP_PASSWORD er den rigtige adgangskode (eller app-adgangskode) til SMTP_USER-kontoen.
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=skj@poulschou.dk
SMTP_PASSWORD=<Indsæt kodeord>
SMTP_FROM=skj@poulschou.dk
SESSION_SECRET=ps-loen-G7kXmQ2vNpR8wL4jTdYsAe9hFcZuBn3K
```

Herefter udfylder brugeren selv `SMTP_PASSWORD` direkte i filen med den rigtige adgangskode til `skj@poulschou.dk` — dette sker uden for denne plan og skrives ikke i chatten.

- [ ] **Step 2: Verificér**

Læs `app/.env` og bekræft at kommentaren er til stede, og at `SMTP_PASSWORD`-linjen er uændret (stadig kun en placeholder, indtil brugeren selv udfylder den).

- [ ] **Step 3: Commit**

```bash
git add app/.env
git commit -m "docs: forklar SMTP-konfiguration i .env"
```

---

### Task 4: Manuel end-to-end-verifikation i browseren

**Forudsætning:** Brugeren har udfyldt `SMTP_PASSWORD` i `app/.env` med en reel adgangskode til `skj@poulschou.dk`, og bekræftet at "Authenticated SMTP" er aktiveret for kontoen i Microsoft 365 Exchange admin center.

**Files:** Ingen kodeændringer — kun verifikation af Task 1-3's ændringer i drift.

- [ ] **Step 1: Genstart serveren**

Start/genstart dev-serveren (`lonsystem`-konfigurationen i `.claude/launch.json`, port 8000) så den nye `.env` indlæses.

- [ ] **Step 2: Test enkelt-afsendelse**

I browseren: gå til Lønkørsel, vælg en periode, find en medarbejder med en gyldig e-mailadresse, tryk **"✉ Send"**. Bekræft:
- Succes-toast med teksten "Timeseddel sendt til ...".
- Ingen fejl i server-konsollen.
- Bed brugeren bekræfte at mailen faktisk er modtaget i den angivne medarbejders indbakke (kan ikke verificeres automatisk).

- [ ] **Step 3: Test batch-afsendelse**

Åbn PDF-Timesedler-modalen, vælg en periode (evt. "alle medarbejdere" eller én enkelt), tryk **"Send Timeseddel"**. Bekræft:
- Toast med optælling af sendt/skipped/failed matcher det forventede antal medarbejdere med e-mail og aktiviteter i perioden.
- Ingen rå SMTP-fejltekst vises i toasten, selv hvis noget fejler.

- [ ] **Step 4: Test fejlscenarie (valgfrit, hvis tid)**

Sæt midlertidigt en forkert værdi i `SMTP_PASSWORD`, genstart serveren, gentag Step 2. Bekræft:
- Klienten viser kun "Mailen kunne ikke sendes – kontakt administrator".
- Serverloggen indeholder den fulde SMTP-fejl (fx en autentificeringsfejl fra Office 365).
- Sæt herefter `SMTP_PASSWORD` tilbage til den rigtige værdi og genstart serveren igen.

---

## Self-Review

- **Spec coverage:** Mål 1 (hærdet fejlhåndtering) dækkes af Task 1 + 2. Mål 2 (reel adgangskode) dækkes af Task 3 (dokumentation) + forudsætning for Task 4. Mål 3 (end-to-end-test) dækkes af Task 4. Alle spec-punkter har en task.
- **Placeholder-scan:** Ingen "TBD"/"senere" i planen — Task 4 er bevidst manuel, da den kræver en reel postkasse og et menneske til at bekræfte modtagelse, hvilket er eksplicit angivet, ikke en udskudt detalje.
- **Typekonsistens:** `send_timeseddel(employee_id, period_start, db, current_user)` og `send_all_timesedler(body, db, current_user)` bruges identisk i Task 1/2's tests og matcher den eksisterende signatur i `timeseddel_router.py`. Fejltekster (`"Mailen kunne ikke sendes – kontakt administrator"` og `"Kunne ikke sendes"`) er identiske mellem Global Constraints, spec og task-implementeringerne.
