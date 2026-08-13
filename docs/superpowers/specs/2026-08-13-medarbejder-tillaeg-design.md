# Design: Medarbejdertillæg ("Tillæg"-fane)

**Dato:** 2026-08-13
**Status:** Godkendt

---

## Oversigt

Ny funktion der lader lønbogholderi tildele et fast kr/time-tillæg til den enkelte medarbejder, oveni medarbejderens normale sats (fra overenskomsttype). Tillægget er historisk sporet (gyldighedsperiode) og slår igennem i selve lønberegningen — kode 1 (normaltid) i både CSV-eksport og beregning, samt afspadsering, der bruger samme sats.

Funktionen er inspireret af kravdokumentet `Tillæg i PS Løn.docx`, men afviger fra det på et par punkter efter afklaring med lønbogholderi (se "Afvigelser fra kravdokument" nedenfor).

**Vigtigt — navnekonflikt:** Der findes allerede en fane "Tillæg" under Stamdata (`MasterSupplementRate` — tillægs**typer**/satser som Salttillæg, Overnatning, Dagpenge §56). Den nye funktion er noget helt andet (et medarbejder-specifikt, historisk sporet kr-tillæg til grundsatsen). Begge faner hedder "Tillæg" og ligger forskellige steder i menuen — det er accepteret som ok, ingen omdøbning.

---

## Afvigelser fra kravdokument

| Krav i dokument | Besluttet løsning |
|---|---|
| "Type" har eksempel "Timebaseret", andre typer uspecificeret | Kun ét fast type-felt: altid `"Timebaseret"`, ingen valgmulighed |
| "Tillægsnavn" har eksempel "Ikke overenskomstmæssigt tillæg" | Altid hardcoded til denne tekst, ikke redigerbar/styrbar noget sted |
| Ingen omtale af løneffekt | Tillægget lægges til grundsatsen og slår igennem kode 1 (normaltid) i CSV og beregning, samt afspadsering |
| "under vognpark" | Tolket som eget sidebar-punkt, placeret efter "Vognpark" — ikke en underfane inde i Vognpark-viewet |
| Status: Aktiv (grøn)/Inaktiv (gul) | Aktiv = grøn, Inaktiv = **rød tekst** (ikke gul) |
| Ingen omtale af redigering | Kun oprettelse af nye rækker — ingen redigering/sletning af eksisterende |

---

## Datamodel

Ny tabel `employee_supplements` (`app/database/models.py`):

```python
class EmployeeSupplement(Base):
    __tablename__ = "employee_supplements"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    name = Column(String(200), nullable=False, default="Ikke overenskomstmæssigt tillæg")
    type = Column(String(50), nullable=False, default="Timebaseret")
    value = Column(Numeric(10, 2), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False, default=date(9999, 12, 31))
    created_at = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee")
```

Ny tabel oprettes automatisk via `Base.metadata.create_all()` i `init_db()` — ingen manuel migration nødvendig (samme mønster som andre nye tabeller).

**Status er ikke et lagret felt — beregnes ved visning:**
- **Aktiv (grøn tekst):** i dag ligger i `[start_date, end_date]`
- **Inaktiv (rød tekst):** alt andet — både historiske og fremtidige (endnu ikke påbegyndte) rækker

**Kun én åbentstående række pr. medarbejder** (`end_date = 9999-12-31`) på et givent tidspunkt — det er "den næste/nuværende" i kæden.

---

## Livscyklus-regel ved oprettelse

Ved `POST /api/employee-supplements`:

1. Valider `value > 0` — afvis med fejl hvis ikke.
2. Find medarbejderens nuværende åbentstående række (`end_date = 9999-12-31`), hvis den findes.
3. Valider at ny `start_date` er **efter** denne rækkes `start_date` — afvis med fejl hvis ikke (forhindrer overlap/tilbagedatering).
4. Sæt den fundne rækkes `end_date = ny_start_dato − 1 dag`.
5. Indsæt ny række med `end_date = 9999-12-31`, `name`/`type` hardcoded server-side.

Et tillæg med fremtidig startdato bliver altså ikke "Aktiv" før datoen er nået — den gamle række forbliver Aktiv indtil da, fordi dens `end_date` er sat til dagen inden den nyes `start_date`.

---

## Satsopslag ved lønberegning

I `app/routers/payroll_router.py`, `_calculate_employee()`, umiddelbart efter det eksisterende opslag af `hourly_rate` (linje ~270):

1. Find alle `employee_supplements`-rækker for medarbejderen hvis gyldighedsperiode **overlapper** den beregnede lønperiode: `NOT (end_date < periode_start OR start_date > periode_slut)`.
2. Er der overlap fra flere rækker (fordi et nyt tillæg er oprettet midt i perioden), bruges rækken med **nyeste** `start_date` — for **hele** perioden (ingen dag-for-dag splitning).
3. Er der intet overlap, bruges intet tillæg (medarbejdere der aldrig har fået oprettet et tillæg, eller hvis tillæg er udløbet uden efterfølger, får `0`).
4. `hourly_rate = hourly_rate_base + tillæg.value` (eller uændret hvis intet tillæg).

Denne ene `hourly_rate`-variabel bruges allerede alle steder i beregningen (normaltid/kode 1, SH-betaling, CSV-eksport, Excel-prøvekørsel, PDF-timesedler) og for afspadseringens CSV-række (`calc["hourly_rate"]`) — tillægget slår derfor automatisk igennem alle disse steder uden yderligere ændringer i `overtime.py`/`day_type.py` (som kun beregner timer, ikke kr).

Denne regel giver samtidig historisk korrekt genberegning af gamle, afsluttede perioder: det tillæg der dengang overlappede perioden, ændres ikke bagudrettet (kun dets `end_date` sættes ved en senere oprettelse) og bliver derfor stadig fundet ved en senere genberegning.

---

## Backend API

Ny fil `app/routers/employee_supplements.py`:

| Endpoint | Beskrivelse |
|---|---|
| `GET /api/employee-supplements?employee_id=&from=&to=` | Liste, filtreret på medarbejder og/eller gyldighedsperiode-overlap. Uden filtre: hele historikken for alle. |
| `GET /api/employee-supplements/active/{employee_id}` | Det aktuelt aktive tillæg (status = Aktiv) for én medarbejder. Returnerer `null` hvis intet aktivt. |
| `POST /api/employee-supplements` | Opret nyt tillæg — se livscyklus-regel ovenfor. |

Alle tre kræver permission `manage_employee_supplements`.

Ny permission tilføjes til `ALL_PERMISSIONS` i `auth.py`, plus en idempotent `_ensure_employee_supplements_permission()` i `app/database/session.py` (samme mønster som `_ensure_anciennitet_alert_permission()`), så eksisterende roller automatisk kan tildeles den.

---

## Frontend

**Nyt sidebar-punkt "Tillæg"**, placeret efter "Vognpark", skjult for roller uden `manage_employee_supplements` (`data-perm-require`).

**Siden:**
1. Søgefelt (samme client-side filter-mønster som `employee-search`/`vehicle-search`) + "Tilføj"-knap.
2. Klik på en medarbejder → viser dennes tillægshistorik:
   - To dato-pickere (fra/til), genbrug af `buildDatePicker`/`readDatePicker`. Tomme som udgangspunkt — viser hele historikken, jf. kravet om at ingen valgte datoer = hele historikken vist.
   - Tabel: Status (grøn/rød tekst) | Lønnummer | Tillægsnavn | Type | Gyldighedsperiode start | Gyldighedsperiode slut | Værdi (kr) — filtreret på om gyldighedsperioden overlapper det valgte interval.
3. "Tilføj"-knap åbner modal:
   - Medarbejder-dropdown (forudvalgt hvis man kom fra en medarbejders visning)
   - Startdato (dt-picker, default i dag)
   - Værdi (kr, numerisk input, kun positive — valideres både frontend og backend)
   - Navn/Type vises som read-only tekst (til info), ikke redigerbare felter

**Medarbejder-modalens read-only boks** (`templates/index.html`, under `#emp-agreement-type`-feltet i `modal-employee`): nyt disabled tekstfelt der viser værdien af det aktive tillæg via `GET /api/employee-supplements/active/{id}`, tomt hvis intet aktivt. Feltet indgår ikke i modalens gem-logik (`confirmEmployee()`).

---

## Validering & fejlhåndtering

- `value` skal være > 0 — både frontend (input-validering) og backend (afvises med fejlbesked).
- `start_date` skal være efter den nuværende åbentstående rækkes `start_date` — afvises med fejl i modal hvis ikke opfyldt.
- Ugyldig `employee_id` → 404, samme mønster som resten af API'et.

---

## Test/verifikation

- **Satsopslag:** unit-tests på overlap-lookup (ingen tillæg / ét overlap / to overlappende hvor nyeste vindes / genberegning af gammel, afsluttet periode efter senere tillæg tilføjet).
- **CSV/kode-1:** verificer at `hourly_rate` i CSV-rækken og i beregningen stiger med tillæggets værdi, og at afspadserings-rækken også påvirkes.
- **Livscyklus:** opret tillæg #1 (Aktiv) → opret tillæg #2 med senere startdato → #1 får `end_date` sat og bliver Inaktiv; #2 er Inaktiv til dets startdato nås, hvorefter det bliver Aktiv.
- **Frontend i browser:** søg medarbejder, opret tillæg, se det i tabellen og i medarbejder-modalens read-only boks, filtrér med dato-picker, tjek permission-baseret synlighed af sidebar-punktet.

---

## Åbne punkter

Ingen — alle punkter er afklaret med lønbogholderi under brainstorming.
