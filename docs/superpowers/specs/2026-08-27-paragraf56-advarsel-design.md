# §56-advarsel som rollestyret permission – Design

**Dato:** 2026-08-27
**Status:** Godkendt af bruger, afventer implementeringsplan

## Baggrund

Når en medarbejders §56-slutdato (jf. `Employee.paragraf_56`/`paragraf_56_start_date`/`paragraf_56_end_date`, se `docs/superpowers/specs/2026-08-27-paragraf56-medarbejder-design.md`) nærmer sig, skal brugere med en ny, rollestyret tilladelse advares via en pop-up. Overskrides slutdatoen uden handling, skal §56 automatisk deaktiveres, og de samme brugere skal have en separat informationsbesked om at det er sket.

Bygges efter samme grundmønster som det eksisterende anciennitetsvarsel (`anciennitet_alert`-permission, `checkAnciennitetsAlerts()`, `modal-anciennitet`), med én vigtig forskel: afvisning skal være **pr. bruger**, ikke global på medarbejderen – bekræftet under brainstorming.

## 1. Datamodel

**Ny tabel** `Paragraf56AlertDismissal` (`app/database/models.py`), oprettes automatisk af `Base.metadata.create_all()` (ingen manuel migration nødvendig, da det er en helt ny tabel):
```python
class Paragraf56AlertDismissal(Base):
    __tablename__ = "paragraf_56_alert_dismissals"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False)
    alert_type = Column(String(20), nullable=False)  # "upcoming" | "expired"
    dismissed_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("employee_id", "user_id", "alert_type", name="uq_paragraf56_dismissal"),
    )
```

Ingen ændring af `Employee`-modellen ud over allerede eksisterende felter.

## 2. Auto-deaktivering ved overskredet slutdato

**Vigtig arkitekturbeslutning:** Sweepet skal køre uafhængigt af `paragraf_56_alert`-tilladelsen – ellers ville §56 ALDRIG blive auto-deaktiveret, hvis ingen aktiv bruger har tilladelsen slået til på deres rolle. Sweepet lægges derfor i `list_employees()` (`GET /api/employees`), som rammes af enhver indlogget bruger uanset rolle – ikke i det tilladelses-gate'ede advarselsendpoint. Selve NOTIFIKATIONEN forbliver tilladelses-styret; selve DATA-KORREKTHEDEN er det ikke.

```python
def _sweep_expired_paragraf_56(db: Session) -> None:
    today = date.today()
    expired = db.query(Employee).filter(
        Employee.paragraf_56 == True,
        Employee.paragraf_56_end_date.isnot(None),
        Employee.paragraf_56_end_date < today,
    ).all()
    for emp in expired:
        emp.paragraf_56 = False
    if expired:
        db.commit()
```

**Datoerne nulstilles IKKE** ved auto-deaktivering (i modsætning til en manuel afkrydsning-fra i modalen, som stadig nulstiller dem, jf. eksisterende, testdækkede adfærd) – de skal kunne vises i informationsbeskeden om at §56 er udløbet. `paragraf_56=false` + udfyldt `paragraf_56_end_date` bliver dermed signalet for "netop auto-udløbet, ikke set endnu" og adskiller sig fra en medarbejder der aldrig har haft §56, eller som er manuelt slået fra (begge har `paragraf_56_end_date=NULL`).

## 3. Permission

**`app/auth.py`**, `ALL_PERMISSIONS`: ny nøgle `"paragraf_56_alert": "§56-advarsel"`.
**`app/static/js/app.js`**, `PERMISSION_LABELS`: samme nøgle/label, holdt i sync (eksisterende mønster – ingen fælles kilde mellem backend/frontend for disse labels i dag).
**`app/database/session.py`**: ny idempotent `_ensure_paragraf_56_alert_permission()`, tilføjer permissionen til `lonbogholder`-rollen som udgangspunkt (samme mønster som `_ensure_anciennitet_alert_permission()`), kaldt fra `init_db()`. Admin har den altid (systemrolle, bypasser alle permission-tjek). Fuldt togglbar for alle roller under Brugere → Roller uden yderligere frontend-arbejde (rolleeditoren læser dynamisk fra `ALL_PERMISSIONS`/`PERMISSION_LABELS`).

## 4. Backend-endpoints (`app/routers/employees.py`)

**Nyt schema** (`app/database/schemas.py`):
```python
class Paragraf56Alert(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    paragraf_56_end_date: date

class Paragraf56AlertsResponse(BaseModel):
    upcoming: list[Paragraf56Alert]
    expired: list[Paragraf56Alert]

class Paragraf56AlertDismiss(BaseModel):
    alert_type: str  # valideres i routeren mod {"upcoming","expired"}
```

**`GET /api/employees/paragraf56-alerts`** (kun `get_current_user`, samme niveau som `anciennitet-alerts` – tilladelsen håndhæves klientside før kaldet, matcher eksisterende mønster):
1. Kalder `_sweep_expired_paragraf_56(db)` (defensivt, selvom `list_employees()` allerede burde have kørt den) – billigt no-op hvis intet er udløbet.
2. `upcoming`: `paragraf_56=true`, `paragraf_56_end_date` mellem i dag og i dag+30 dage, ikke afvist (type "upcoming") af den aktuelle bruger.
3. `expired`: `paragraf_56=false`, `paragraf_56_end_date` udfyldt og < i dag, ikke afvist (type "expired") af den aktuelle bruger.

**`POST /api/employees/{employee_id}/dismiss-paragraf56-alert`** (body: `Paragraf56AlertDismiss`, kun `get_current_user`): opretter en `Paragraf56AlertDismissal`-række for `(employee_id, current_user.id, alert_type)` hvis den ikke allerede findes (idempotent).

**`update_employee`**: udvides så en ÆNDRET `paragraf_56_end_date` (uanset om §56 samtidig slås til/fra/forbliver til) sletter ALLE `Paragraf56AlertDismissal`-rækker for medarbejderen – nulstiller for alle brugere, jf. bekræftet under brainstorming.

**`list_employees()`**: kalder `_sweep_expired_paragraf_56(db)` først, før medarbejderne hentes – se punkt 2.

## 5. Frontend

**Ny modal** i `index.html`, `modal-paragraf56-alert` (samme struktur som `modal-anciennitet`): overskrift og brødtekst afhænger af om det er en "upcoming"- eller "expired"-besked (sættes dynamisk af JS).

**`app.js`**:
- `checkParagraf56Alerts()`, kaldt fra `loadApp()` lige efter `checkAnciennitetsAlerts()`: tjekker `paragraf_56_alert`-tilladelsen klientside, henter `GET /paragraf56-alerts`. Viser `expired`-beskeden hvis der er nogen (mest presserende – er allerede sket), ellers `upcoming`-beskeden hvis der er nogen. Samme "vis den første, nævn '+N flere'"-mønster som anciennitetsvarslet.
- `dismissParagraf56Alert(employeeId, alertType)`: `POST /dismiss-paragraf56-alert` med `{alert_type}`, lukker modalen.
- "Gå til medarbejder"-knap genbruges (samme mønster som anciennitet: `setView("employees")` + `openEditEmployee(id)`).

## Ikke i scope

- Ingen ændring af den eksisterende §56 syg-fraværstype/aktivitetslogik.
- Ingen periodisk baggrundstjek – sweepet kører udelukkende ved (enhver bruger's) medarbejderopslag, ikke på et fast tidspunkt i døgnet.
- Ingen ændring af Brugervejledningen i denne omgang (samme begrundelse som forrige §56-opgave).

## Test-dækning (til implementeringsplan)

- `_sweep_expired_paragraf_56`: en medarbejder med `paragraf_56=true` og udløbet slutdato bliver sat til `false`, med datoerne bevaret. En medarbejder med fremtidig slutdato røres ikke.
- `list_employees()` udløser sweepet (kald endpointet, bekræft at en udløbet medarbejder nu har `paragraf_56=false` i responsen).
- `paragraf56-alerts`: korrekt opdelt i `upcoming` (inden for 30 dage, stadig aktiv) og `expired` (netop auto-slukket, ikke afvist). Afvist-af-bruger-A vises stadig for bruger B. Medarbejder uden §56 (aldrig sat) optræder i ingen af listerne.
- `dismiss-paragraf56-alert`: opretter rækken idempotent (dobbeltkald fejler ikke), og kun den ene bruger/type kombination påvirkes.
- `update_employee`: ændring af `paragraf_56_end_date` sletter alle eksisterende afvisningsrækker for medarbejderen.
- Permission: rolle uden `paragraf_56_alert` ser aldrig popup'en (klientside-gate); admin ser den altid.
- Frontend: "expired" vises før "upcoming" hvis begge findes samtidig for samme bruger.
