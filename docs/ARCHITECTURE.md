# Arkitektur – Lønsystem

## Overordnet valg: Lokal web-applikation

Systemet bygges som en **lokal web-applikation** der kører på ét centralt Windows-system (server/dedikeret PC) og tilgås af alle medarbejdere via browser på det lokale netværk.

---

## Stakken

| Lag | Teknologi | Begrundelse |
|-----|-----------|-------------|
| Backend | Python 3.11+ med FastAPI | Hurtig API, god .ddd-fil-support, type-hints |
| Database | SQLite (fil på server) | Simpel, filbaseret, nem backup, ingen separat server |
| Frontend | HTML + Vanilla JS + CSS (eller Jinja2 templates) | Ingen framework-overhead, kører i browser |
| .ddd-parsing | Selvskrevet binær parser (`struct`/`re`, ingen ekstern pakke) | EU-standardformat, ingen egnet open-source-pakke fundet – se `app/parsers/ddd_parser.py` |
| Excel-output | openpyxl | Prøvekørsel Excel-fil |
| CSV-output | Python stdlib csv | Danløn-eksport |

---

## Deployment

```
[Server/PC]
├── Python FastAPI app (kører som Windows Service eller autostart)
├── SQLite database fil (lønsystem.db)
├── .ddd inputmappe (sti AFKLARES)
├── Output-mappe (CSV, Excel)
└── Lyt på port 8000 (lokalt netværk)

[Klient PC'er]
└── Browser → http://[server-ip]:8000
```

---

## Mappestruktur (kodebase)

Verificeret mod den faktiske kodebase 2026-09-04. Se `CODEREF.md` i rodmappen for den
løbende vedligeholdte, mere detaljerede version af denne oversigt.

```
Lønsystem/
├── requirements.txt         # Python afhængigheder
└── app/
    ├── main.py               # FastAPI app entry point, routerinkludering, sikkerhedsheaders
    ├── database/
    │   ├── models.py         # SQLAlchemy ORM-modeller
    │   ├── schemas.py        # Pydantic-skemaer
    │   ├── session.py        # get_db(), init_db()/seeding, migrationer
    │   └── lonsystem.db      # SQLite database (auto-oprettet)
    ├── parsers/
    │   └── ddd_parser.py     # .ddd fil parsing (selvskrevet)
    ├── calculators/
    │   ├── overtime.py       # Overtidsberegning
    │   ├── pay_period.py     # Lønperiode-beregning
    │   ├── pay_rates.py      # Danløn-kode-konstanter (placeholder)
    │   ├── rates_loader.py   # Excel-satser
    │   ├── day_type.py       # Søn-/helligdagsberegning
    │   ├── auto_approval.py  # Auto-godkendelse
    │   └── baseline_updater.py
    ├── exporters/             # Findes, men er tom – CSV-/Excel-eksport ligger i dag inline i payroll_router.py
    ├── routers/
    │   ├── activities.py, employees.py, payroll_router.py, payroll_settlement_router.py,
    │   │   absence_overview_router.py, timeseddel_router.py, stamdata.py, vehicles.py,
    │   │   import_ddd.py, auto_approval_router.py, employee_supplements.py,
    │   │   vagtplan_comments.py, auth.py, users.py, roles.py
    ├── static/
    │   ├── css/style.css
    │   └── js/app.js
    └── templates/
        ├── index.html        # Eneste HTML-side (alle modaler herinde)
        └── timeseddel.html   # PDF-timeseddel-skabelon
```

---

## Databaser og synkronisering

- Alle brugere tilgår samme SQLite-fil via FastAPI (enkelt-process)
- FastAPI håndterer samtidige requests asynkront
- SQLite WAL-mode aktiveres for bedre concurrent read performance
- Ved vækst i antal brugere/data: migration til PostgreSQL er ligetil

---

## Åbne punkter

- [ ] IP-adresse/hostname på server
- [ ] Port (default: 8000)
- [ ] Backup-strategi for database-filen
- [ ] Windows Service setup (autostart)
