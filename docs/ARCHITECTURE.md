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
| .ddd-parsing | Python-bibliotek (tachograph/python-ddd) | EU-standardformat, open-source parsere |
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

```
lønsystem/
├── main.py                 # FastAPI app entry point
├── requirements.txt        # Python afhængigheder
├── database/
│   ├── models.py           # SQLAlchemy ORM modeller
│   ├── crud.py             # Database CRUD operationer
│   └── lønsystem.db        # SQLite database (auto-oprettet)
├── parsers/
│   └── ddd_parser.py       # .ddd fil parsing
├── calculators/
│   ├── payroll.py          # Lønberegning
│   └── overtime.py         # Overtidsberegning
├── exporters/
│   ├── danloen_csv.py      # Danløn CSV eksport
│   └── preview_excel.py    # Prøvekørsel Excel
├── routers/
│   ├── activities.py       # API endpoints for aktiviteter
│   ├── employees.py        # API endpoints for medarbejdere
│   └── payroll.py          # API endpoints for lønkørsel
├── static/
│   ├── css/style.css
│   └── js/app.js
└── templates/
    ├── index.html          # Startside
    ├── employee.html       # Medarbejderoprettelse
    └── activity.html       # Aktivitetsdetail
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
