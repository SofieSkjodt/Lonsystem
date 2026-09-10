# Design: "Ændret af"-felt på aktiviteter

**Dato:** 2026-09-10

## Baggrund

Aktiviteter har allerede felter der sporer hvem der har udført en handling:
`created_by` (manuel oprettelse), `approved_by` (godkendelse) og
`deactivated_by` (deaktivering) — alle gemt som brugerens initialer
(`current_user.initials`). Der findes desuden præcedens for et `updated_by`-felt
("initialer på seneste bruger der ændrede") på `SystemSettings`.

Ønsket: Når en bruger redigerer en aktivitet og gemmer ændringen, skal
brugerens initialer vises i et felt "Ændret af". Feltet skal kun eksistere
(vises) når aktiviteten faktisk er blevet ændret, og hvis en anden bruger
ændrer aktiviteten senere, skal dennes initialer overskrive de forrige.

## Løsning

Genbrug det eksisterende `updated_by`-mønster fra `SystemSettings` på
`Activity`.

### 1. Databasemodel

Ny kolonne på `Activity` i [app/database/models.py](../../../app/database/models.py):

```python
updated_by = Column(String, nullable=True)  # initialer – seneste bruger der ændrede aktiviteten
```

Placeres ved siden af de øvrige `*_by`-felter (`created_by`, `approved_by`,
`deactivated_by`).

### 2. Migration

Tilføj til `_migrate()` i
[app/database/session.py](../../../app/database/session.py), samme stil som
de øvrige `activities`-kolonner (guard med `PRAGMA table_info`):

```python
if "updated_by" not in act_cols2:
    conn.execute("ALTER TABLE activities ADD COLUMN updated_by VARCHAR")
    conn.commit()
```

### 3. Schema

Tilføj `updated_by: Optional[str] = None` til `ActivityResponse` i
[app/database/schemas.py](../../../app/database/schemas.py), og medtag feltet
i `_to_response()` i
[app/routers/activities.py](../../../app/routers/activities.py).

### 4. Backend – sæt feltet ved gem

I `PATCH /api/activities/{activity_id}` (`update_activity`,
[app/routers/activities.py:662](../../../app/routers/activities.py)) sættes:

```python
a.updated_by = current_user.initials
```

ubetinget ved hvert kald. Dette endpoint rammes både af "Gem ændringer"-knappen
i redigeringsmodalen og af de øvrige steder der patcher en aktivitet (fx
pauseredigering, felter gemt i forbindelse med godkendelse) — alle disse er
reelle ændringer af aktiviteten, så feltet skal opdateres ved dem alle
(bekræftet med bruger).

Feltet er `NULL` indtil første ændring (opfylder "skal kun eksistere når
ændret") og overskrives ubetinget ved hver efterfølgende ændring (opfylder
"ny brugers initialer overskriver de gamle").

### 5. Frontend

I aktivitets-detaljevisningen i
[app/static/js/app.js](../../../app/static/js/app.js) (omkring linje 1253,
ved siden af "Godkendt af" / "Deaktiveret af"), tilføjes en ny linje der kun
vises når `a.updated_by` er sat:

```js
${a.updated_by ? `<div class="detail-item"><label>Ændret af</label><span>${h(a.updated_by)}</span></div>` : ""}
```

## Ikke i scope

- Der føres ikke historik over tidligere redigeringer — kun seneste ændrers
  initialer gemmes, i tråd med hvordan `approved_by`/`deactivated_by` allerede
  fungerer.
- Ingen ændring af `PATCH`-endpointets adfærd udover at sætte `updated_by`.
