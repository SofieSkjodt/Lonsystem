"""
Bygger Teknisk dokumentation.docx og Brugervejledning.docx til Lønsystemet.
Kør med: python build_docs.py
"""
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

OUT = Path(__file__).parent

DARK_BLUE = RGBColor(0x1B, 0x3A, 0x6B)
MID_BLUE  = RGBColor(0x2E, 0x6D, 0xB8)
LIGHT_BLUE = RGBColor(0xD5, 0xE8, 0xF5)
GRAY      = RGBColor(0x60, 0x60, 0x60)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
BLACK     = RGBColor(0x00, 0x00, 0x00)


# ─── helpers ───────────────────────────────────────────────────────────────

def set_cell_bg(cell, hex_color: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def set_cell_borders(cell, color="CCCCCC"):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), color)
        tcBorders.append(el)
    tcPr.append(tcBorders)


def add_run(para, text, bold=False, italic=False, color=None, size=None):
    run = para.add_run(text)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = color
    if size:
        run.font.size = Pt(size)
    run.font.name = "Arial"
    return run


def heading(doc, text, level=1, num=None):
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.space_before = Pt(18 if level == 1 else 10)
    p.paragraph_format.space_after  = Pt(6)
    label = f"{num}  " if num else ""
    run = p.add_run(label + text)
    run.font.name = "Arial"
    run.font.bold = True
    run.font.size = Pt(16 if level == 1 else 13 if level == 2 else 11)
    run.font.color.rgb = DARK_BLUE if level == 1 else MID_BLUE if level == 2 else BLACK
    return p


def body(doc, text, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(11)
    return p


def bullet(doc, text, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.left_indent = Cm(0.8)
    if bold_prefix:
        rb = p.add_run(bold_prefix)
        rb.bold = True
        rb.font.name = "Arial"
        rb.font.size = Pt(11)
        r = p.add_run(text)
    else:
        r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(11)
    return p


def cover(doc, title, subtitle, date_str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(80)
    p.paragraph_format.space_after  = Pt(4)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(title)
    r.font.name = "Arial"
    r.font.bold = True
    r.font.size = Pt(28)
    r.font.color.rgb = DARK_BLUE

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(6)
    r2 = p2.add_run(subtitle)
    r2.font.name = "Arial"
    r2.font.size = Pt(14)
    r2.font.color.rgb = MID_BLUE

    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.paragraph_format.space_before = Pt(60)
    r3 = p3.add_run("Poul Schou A/S  ·  CVR 13246505")
    r3.font.name = "Arial"
    r3.font.size = Pt(11)
    r3.font.color.rgb = GRAY

    p4 = doc.add_paragraph()
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r4 = p4.add_run(date_str)
    r4.font.name = "Arial"
    r4.font.size = Pt(11)
    r4.font.color.rgb = GRAY

    doc.add_page_break()


def two_col_table(doc, rows, col1_w=Cm(5), col2_w=Cm(11.5)):
    tbl = doc.add_table(rows=0, cols=2)
    tbl.style = "Table Grid"
    for label, val in rows:
        row = tbl.add_row()
        c0, c1 = row.cells[0], row.cells[1]
        set_cell_bg(c0, "D5E8F5")
        set_cell_borders(c0, "9BBDD6")
        set_cell_borders(c1, "9BBDD6")
        c0.width = col1_w
        c1.width = col2_w
        p0 = c0.paragraphs[0]
        r0 = p0.add_run(label)
        r0.bold = True; r0.font.name = "Arial"; r0.font.size = Pt(10)
        p1 = c1.paragraphs[0]
        r1 = p1.add_run(val)
        r1.font.name = "Arial"; r1.font.size = Pt(10)
    doc.add_paragraph()


def header_table(doc, headers, rows, col_widths=None):
    ncols = len(headers)
    tbl = doc.add_table(rows=1, cols=ncols)
    tbl.style = "Table Grid"
    hdr_row = tbl.rows[0]
    for i, h in enumerate(headers):
        cell = hdr_row.cells[i]
        set_cell_bg(cell, "1B3A6B")
        p = cell.paragraphs[0]
        r = p.add_run(h)
        r.bold = True; r.font.name = "Arial"; r.font.size = Pt(10)
        r.font.color.rgb = WHITE
    for row_data in rows:
        row = tbl.add_row()
        for i, val in enumerate(row_data):
            cell = row.cells[i]
            set_cell_borders(cell)
            p = cell.paragraphs[0]
            r = p.add_run(str(val))
            r.font.name = "Arial"; r.font.size = Pt(10)
    doc.add_paragraph()


def note_box(doc, text, label="OBS"):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent  = Cm(0.5)
    p.paragraph_format.right_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(8)
    rb = p.add_run(f"{label}: ")
    rb.bold = True; rb.font.name = "Arial"; rb.font.size = Pt(11)
    rb.font.color.rgb = MID_BLUE
    r = p.add_run(text)
    r.font.name = "Arial"; r.font.size = Pt(11)
    r.font.color.rgb = GRAY
    return p


# ══════════════════════════════════════════════════════════════════════════════
#  TEKNISK DOKUMENTATION
# ══════════════════════════════════════════════════════════════════════════════

def build_teknisk():
    doc = Document()

    # Sider og margener
    for section in doc.sections:
        section.page_width  = Cm(21)
        section.page_height = Cm(29.7)
        section.left_margin = section.right_margin = Cm(2.5)
        section.top_margin  = section.bottom_margin = Cm(2.5)

    # Forside
    cover(doc, "Lønsystem", "Teknisk dokumentation", "Juni 2026")

    # ── 1. Systemarkitektur ────────────────────────────────────────────────
    heading(doc, "Systemarkitektur", 1, "1")
    body(doc, (
        "Lønsystemet er en webbaseret applikation til registrering og lønberegning for "
        "lastbilchauffører hos Poul Schou A/S. Systemet kører på én central server og "
        "tilgås via en webbrowser på det lokale netværk."
    ))

    heading(doc, "Teknologistack", 2, "1.1")
    header_table(doc,
        ["Komponent", "Teknologi", "Formål"],
        [
            ["Backend", "Python 3.13 + FastAPI", "REST-API, forretningslogik, filgenerering"],
            ["Database", "SQLite (WAL-mode)", "Vedvarende lagring af medarbejder- og aktivitetsdata"],
            ["Frontend", "HTML5 + Vanilla JavaScript + CSS", "Brugerflade – ét HTML-dokument"],
            ["Server", "Uvicorn (ASGI)", "Serverer FastAPI-applikationen"],
            ["PDF-generering", "ReportLab", "Timesedler til medarbejdere"],
            ["Excel-generering", "openpyxl", "Prøvekørsel og satser"],
            ["Filparsing", "Binær parsing (ingen eksternt bibliotek)", "Indlæsning af .ddd tachografdata"],
        ],
        [Cm(3), Cm(5), Cm(8.5)]
    )

    heading(doc, "Mappestruktur", 2, "1.2")
    body(doc, "Projektmappen er organiseret i fire hoveddele:")
    two_col_table(doc, [
        ["app/",          "Al Python-kode, statiske filer, database og Excel-satser"],
        ["docs/",         "Projektdokumentation (.md-filer og denne fil)"],
        ["præsentation/", "Præsentationsbygger og slides (til intern brug)"],
        ["Rodmappen",     "Brugerdokumenter: overenskomst-PDF, kravdokument, statusmøde-pptx m.m."],
    ])

    heading(doc, "Centrale filer i app/", 2, "1.3")
    two_col_table(doc, [
        ["main.py",                   "Applikationens indgangspunkt. Registrerer alle routere, monterer statiske filer og serverer index.html med cache-busting."],
        ["routers/activities.py",     "API-endepunkter for aktivitetshåndtering (opret, godkend, ret, opdel, fortryd)."],
        ["routers/employees.py",      "API-endepunkter for medarbejderstamdata og overenskomsttyper."],
        ["routers/payroll_router.py", "Lønkørsel: preview, prøvekørsel (Excel), Danløn CSV og PDF-timesedler."],
        ["routers/import_ddd.py",     "Import af .ddd-filer via fildialoger (tkinter) og batch-import."],
        ["calculators/overtime.py",   "Overtids- og tillægsberegning pr. aktivitet."],
        ["calculators/rates_loader.py","Indlæser timesatser og overtidssatser fra DB (Stamdata). Excel-funktioner bruges kun som fallback ved tom DB."],
        ["routers/stamdata.py",       "CRUD-endepunkter for stamdata: overenskomsttyper, overtidssatser, tillæg, løntypekoder og fraværstyper. Kræver 'stamdata'-rettighed."],
        ["calculators/pay_period.py", "Beregner og opretter 14-dages lønperioder."],
        ["database/models.py",        "SQLAlchemy-modeller (Employee, Activity, PayPeriod m.fl.)."],
        ["database/schemas.py",       "Pydantic-skemaer til validering af API-input og -output."],
        ["parsers/ddd_parser.py",     "Binær parser for EU-tachografdata (.ddd-format)."],
        ["templates/index.html",      "Hele frontend-applikationen (ét HTML-dokument)."],
        ["static/js/app.js",          "JavaScript-applikationslogik (~1700 linjer)."],
    ])

    # ── 2. Databasemodel ──────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Databasemodel", 1, "2")
    body(doc, (
        "Databasen er SQLite og oprettes automatisk ved første opstart. WAL-mode "
        "(Write-Ahead Logging) aktiveres, så flere samtidige læsere kan tilgå databasen "
        "mens en skrivning foregår."
    ))

    heading(doc, "Employee – medarbejdere", 2, "2.1")
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["employee_number",       "String (unik)",   "Lønnummer – primær identifikator i lønsystemet"],
            ["tachograph_card_number","String (unik)",   "EU-førerkortnummer – bruges til at matche .ddd-filer"],
            ["first_name / last_name","String",          "Navn"],
            ["address / postal_code", "String (opt.)",   "Adresse"],
            ["email / phone / mobile","String (opt.)",   "Kontaktoplysninger"],
            ["agreement_kind",        "Enum",            "hourly_fixed (fast arbejdstid) / hourly_flexible (ikke fastlagt)"],
            ["agreement_type",        "String",          "Overenskomsttype fra Excel-filen – bestemmer timesats"],
            ["fuldloennet",           "Boolean",         "Fuldlønnet status"],
            ["active",                "Boolean",         "Aktiv medarbejder (filtreres ved opslag)"],
            ["hire_date",             "Date",            "Ansættelsesdato"],
            ["termination_date",      "Date",            "Fratrædelsesdato (default 31-12-9999)"],
            ["work_schedule",         "JSON",            '{"even":[man..søn], "odd":[man..søn]} – normaltimer pr. dag i lig/ulige uge'],
            ["dispatcher_group",      "String (opt.)",   "Disponentgruppe/afdeling til filtrering i aktivitetstabellen"],
            ["anciennitet_dismissed_at","DateTime (opt.)","Tidspunkt for afvisning af anciennitetsvarsel (nulstilles ved overenskomstskifte)"],
        ]
    )

    heading(doc, "Activity – aktiviteter", 2, "2.2")
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["employee_id",           "FK → Employee",  "Tilknyttet medarbejder"],
            ["pay_period_id",         "FK → PayPeriod", "Tilknyttet lønperiode"],
            ["trip_number",           "String (opt.)",  "Turnummer (max 6 tegn)"],
            ["source",                "Enum",           "tachograph (DDD-import) / manual (manuelt oprettet)"],
            ["activity_type",         "String(50)",     "normal / ferie / fri / afspadsering / skole_kursus / overnatning"],
            ["start_time / end_time", "DateTime",       "Start- og sluttidspunkt"],
            ["availability_time_pct", "Decimal",        "Rådighedstid i % (fra tachograf)"],
            ["rest_pause_pct",        "Decimal",        "Hvil/pause i % (fra tachograf)"],
            ["other_work_pct",        "Decimal",        "Andet arbejde i % (fra tachograf)"],
            ["driving_pct",           "Decimal",        "Kørsel i % (fra tachograf)"],
            ["loading_minutes",       "Integer (opt.)", "Pålæsningstid i minutter"],
            ["unloading_minutes",     "Integer (opt.)", "Aflæsningstid i minutter"],
            ["pause_intervals",       "JSON",           '[ ["ISO-start","ISO-slut"], ... ] – pauseintervaller'],
            ["segments",              "JSON",           '[ ["ISO-start","ISO-slut","type"], ... ] – tachografsegmenter'],
            ["original_start_time",   "DateTime (opt.)","Original tachograftid inden første rettelse"],
            ["original_end_time",     "DateTime (opt.)","Original tachograftid inden første rettelse"],
            ["status",                "Enum",           "pending / approved / deactivated"],
            ["approved_by",           "String (opt.)",  "Initialer på godkender (kun ved godkendelse)"],
            ["approved_at",           "DateTime (opt.)","Godkendelsestidspunkt"],
            ["deactivated_by",        "String (opt.)",  "Initialer på den der deaktiverede (kun ved deaktivering)"],
            ["comment",               "Text (opt.)",    "Kommentar (påkrævet ved godkendelse < 4 timer)"],
            ["parent_activity_id",    "FK → Activity",  "Peger på moderaktivitet ved opdeling"],
            ["split_part",            "Integer (opt.)", "1 eller 2 – rækkefølge af opdelingsdele"],
        ]
    )

    heading(doc, "PayPeriod – lønperioder", 2, "2.3")
    two_col_table(doc, [
        ["start_date / end_date", "Altid mandag–søndag, 14 dage"],
        ["status",                "open (aktiv) / preview (under kørsel) / closed (afsluttet)"],
        ["closed_at / closed_by", "Tidspunkt og bruger ved afslutning"],
    ])

    heading(doc, "PayrollRun – lønkørsler", 2, "2.4")
    two_col_table(doc, [
        ["pay_period_id", "FK til lønperioden"],
        ["run_type",      '"preview" (prøvekørsel) eller "final" (endelig kørsel)'],
        ["run_at",        "Tidspunkt for kørslen"],
        ["run_by",        "Initialer på den der kørte løn"],
        ["csv_path",      "Sti til genereret Danløn CSV-fil"],
        ["excel_path",    "Sti til genereret Excel-fil"],
    ])

    heading(doc, "Stamdata – masterdatatabeller", 2, "2.5")
    body(doc, (
        "Fem tabeller holder systemets masterdata. De seedes automatisk fra Excel-filerne ved "
        "første opstart og redigeres derefter via Stamdata-modulet i systemets brugerflade. "
        "Excel-filerne bruges herefter kun som fallback hvis en tabel er tom."
    ))
    header_table(doc,
        ["Tabel", "Indhold", "Vigtige felter"],
        [
            ["master_agreement_types",  "Overenskomsttyper og timesatser", "name (unik), hourly_rate"],
            ["master_overtime_rates",   "De tre overtidssatser",           "label (unik), rate"],
            ["master_supplement_rates", "Salttillæg, Overnatning, Dagpenge §56", "label (unik), rate"],
            ["master_pay_types",        "Løntypekoder til Danløn CSV",     "code_key (unik), danloen_code, include_in_csv, csv_quantity_type, csv_rate_source, csv_include_rate, csv_include_total, sort_order"],
            ["master_absence_types",    "Fraværstyper der vises i UI",     "label, normalized_key (unik), is_active, is_user_created, sort_order"],
        ]
    )
    body(doc, (
        "Normaliserede nøgler i master_absence_types genereres én gang ved oprettelse og ændres "
        "ikke efterfølgende – de bruges internt i beregnings- og aktivitetslogikken. "
        "Alle fraværstyper kan slettes via Stamdata-UI'et."
    ))

    heading(doc, "Holidays – helligdagskalender", 2, "2.6")
    body(doc, (
        "Holidays-tabellen gemmer danske helligdage og administreres separat fra de Excel-seedede "
        "masterdatatabeller. Den seedes automatisk ved serveropstart via _seed_holidays() i session.py."
    ))
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["date",              "DATE UNIQUE NOT NULL", "Helligdagens dato – UNIQUE constraint forhindrer dubletter"],
            ["name",              "String NOT NULL",      "Navn, fx 'Påskedag', '1. maj', 'Grundlovsdag'"],
            ["half_day_from",     "String(5) NULL",       "'12:00' = fri fra middag; NULL = heldagshelligdag"],
            ["is_auto_generated", "Boolean DEFAULT TRUE", "TRUE = genereret af systemet; FALSE = manuelt oprettet"],
        ]
    )
    for item in [
        "5 løbende år genereres ved opstart (indeværende år + 4 fremover).",
        "Seeding er idempotent – eksisterende datoer springes over.",
        "Påskedato beregnes via anonym Gregoriansk Computus-algoritme i app/calculators/holidays.py.",
        "Deduplicering: faste helligdage vinder over bevægelige ved datokollision "
        "(fx 2028: 2. pinsedag og Grundlovsdag falder begge den 5. juni – Grundlovsdag bevares).",
        "Store Bededag medtages ikke (afskaffet fra 2024).",
    ]:
        bullet(doc, item)
    note_box(doc,
        "half_day_from-feltet er forberedt til brug i fremtidig lønberegning (helligdagstillæg). "
        "Feltet bruges allerede i aktivitetskalenderens '½ fra HH:MM'-badge.",
        "TEKNISK NOTE"
    )

    # ── 3. Lønperioder ────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Lønperioder", 1, "3")
    body(doc, (
        "Lønperioderne er faste 14-dages intervaller fra mandag til søndag. "
        "Systemet bruger en ankerperiode til at beregne alle andre perioder."
    ))
    two_col_table(doc, [
        ["Ankerperiode",  "Mandag 1. juni 2026 – søndag 14. juni 2026"],
        ["Periode-start", "Altid en mandag"],
        ["Periode-slut",  "Altid en søndag (14 dage efter start)"],
        ["Beregning",     "period_start_for_date(d): finder nærmeste mandag via modulo-14 fra ankerpunktet"],
    ])
    body(doc, (
        "Timefordelingen på medarbejderen skelner mellem 'lige' og 'ulige' uger. "
        "Dette bestemmes af is_even_week(d): ISO-ugenummer % 2 == 0 → 'even' (lige uge). "
        "Mandag 1. juni 2026 er i ISO-uge 23 (ulige), så 'even'-skemaet bruges i ISO-uge 24, 26 osv."
    ))

    # ── 4. DDD-filparsing ─────────────────────────────────────────────────
    heading(doc, "DDD-filparsing (tachografdata)", 1, "4")
    body(doc, (
        "EU-tachografer gemmer data i .ddd-filer (EU Forordning 165/2014). Filen er binær "
        "og indeholder daglige poster med tidsstempler og aktivitetsskift."
    ))

    heading(doc, "Parsingsflow", 2, "4.1")
    for i, step in enumerate([
        ("Filidentifikation", "Kortnummeret matches som landekode (2 bogstaver) + 14 cifre (fx DK00000012666013), men kun de første 14 tegn (landekode + 12 cifre = driverIdentification) er det stabile kortnummer der bruges til medarbejder-matching. De sidste 2 cifre er cardReplacementIndex + cardRenewalIndex og ændrer sig når kortet udskiftes/fornys."),
        ("Lokalisering af poster", "Heuristisk søgning efter timestamp-mønstre identificerer starten på daglige poster."),
        ("Afkodning af ActivityChangeInfo", "2-byte records afkodes bit-for-bit: slot (bit 15-14), aktivitetstype (bit 13-11), minutter fra midnat (bit 10-0). Dato og minutter er UTC."),
        ("Aktivitetstyper", "Rest (hvil), Availability (rådighedstid), Work (andet arbejde), Driving (kørsel)."),
        ("Dagsstart", "Hver dags aktivitetsarray starter altid med en hvil-post ved minut 0 (videreført status fra dagen før, ikke en reel pause). Findes der en ekstra hvil-post lige derefter, er det chaufførens faktiske dagsstart – en kort pause inden arbejdet begynder – og den bruges som visningsstart for dagen."),
        ("Tidszonekonvertering", "Start/sluttid, segmenter og pauseintervaller konverteres fra UTC til dansk lokal tid (Europe/Copenhagen, DST-korrekt via Python-modulet zoneinfo) inden de gemmes."),
        ("Bygning af ParsedActivity", "Start/sluttid, procentfordelinger, pauseintervaller og segmenter samles til et ParsedActivity-objekt."),
        ("Duplikat-tjek", "Eksisterende aktiviteter med samme medarbejder + starttid springes over."),
    ], 1):
        bullet(doc, f"{step[1]}", f"{i}. {step[0]}: ")

    note_box(doc,
        "zoneinfo kræver på Windows Python-pakken tzdata (installeret via requirements.txt), "
        "da Windows ikke leverer sin egen IANA-tidszonedatabase.",
        "TEKNISK NOTE"
    )
    note_box(doc,
        "En indledende kort pause (fx 1-11 minutter) tælles med i den viste arbejdstid og "
        "fremgår af pause_intervals, men er stadig ubetalt – pause_intervals fratrækkes altid "
        "i lønberegningen uanset hvor i dagen de ligger.",
        "GODT AT VIDE"
    )

    heading(doc, "Import-flow", 2, "4.2")
    body(doc, (
        "Brugeren klikker 'Vælg filer' eller 'Vælg mappe' i browsergrænsefladen. "
        "En tkinter-dialog (Windows-nativ) åbnes via GET /api/browse-ddd-files eller "
        "/api/browse-ddd-folder. Den valgte sti sendes med POST /api/import-ddd-from, "
        "som parser filerne og gemmer nye aktiviteter i databasen."
    ))

    # ── 5. Overtidsberegning ──────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Overtidsberegning", 1, "5")
    body(doc, (
        "Beregningen udføres i calculators/overtime.py ved funktionen "
        "calculate_overtime(start, end, pause_intervals, normal_hours, rates). "
        "Satserne hentes fra Stamdata-databasen (master_overtime_rates). "
        "Excel bruges kun som fallback hvis DB-tabellen er tom."
    ))

    heading(doc, "De tre tillægstyper", 2, "5.1")
    header_table(doc,
        ["Nøgle", "Tidsvindue", "Betingelse", "Beskrivelse"],
        [
            ["OT_BEFORE\n(1 time før)", "05:00–06:00", "Arbejde i dette interval", "Tillæg for arbejde 1 time inden normal arbejdstid. Sats × timer i vinduet."],
            ["OT_13\n(1-3 timer efter)", "18:00–21:00\n+ 06:00–18:00 over normaltid", "Max 3 timer samlet", "Tillæg for de første 3 overarbejdstimer. Inkluderer dag-timer ud over normaltid (06-18) og aftentimer (18-21)."],
            ["OT_EXTRA\n(Øvrigt overtid)", "21:00–05:00\n+ overarbejde > 3 timer", "Al resterende overarbejde", "Tillæg for natarbejde og overarbejde ud over 3 timer. Højeste sats."],
        ]
    )

    heading(doc, "Beregningsgang", 2, "5.2")
    for step in [
        "Pauseintervaller fratrækkes i de tidsrum de afholdes (korrekt placering i tillægsvindue).",
        "Arbejdstimerne opdeles i 4 vinduer: before (05-06), day (06-18), evening (18-21), night (21-05).",
        "Day-timer sammenlignes med normaltid for dagen: timer op til normaltid = normale timer, overskydende tæller mod OT_13.",
        "OT_13-puljen er max 3 timer: day-overtid fylder først, derefter evening-timer. Resterende evening- og alle night-timer går til OT_EXTRA.",
        "Night-timer (21-05) er altid OT_EXTRA.",
        "Normaltimer = min(faktiske day-timer, normaltid for dagen fra medarbejderens timefordeling).",
        "Resultat: OvertimeResult med normal_hours, ot_before_hours, ot_13_hours, ot_extra_hours samt beregnede tillæg i kr.",
    ]:
        bullet(doc, step)

    note_box(doc,
        "Pauser skal altid registreres korrekt, da de fratrækkes i det præcise tidsvindue de afholdes. "
        "En pause kl. 20:00 fratrækkes i OT_13-vinduet og reducerer dermed tillægget korrekt.",
        "VIGTIGT"
    )

    # ── 6. Timesatser og overenskomst ─────────────────────────────────────
    heading(doc, "Timesatser og overenskomst", 1, "6")
    body(doc, (
        "Alle timesatser og overenskomsttyper opbevares i Stamdata-databasen og redigeres "
        "via Stamdata-modulet i systemets brugerflade. Excel-filerne bruges kun til initial "
        "seeding af databasen ved første opstart og er derefter irrelevante for driften."
    ))

    heading(doc, "Stamdata-tabeller og DB-funktioner", 2, "6.1")
    header_table(doc,
        ["Stamdata-tabel", "DB-funktion (rates_loader.py)", "Indhold"],
        [
            ["master_agreement_types",  "load_agreement_types_from_db(db)", "Overenskomstnavn → timesats i kr."],
            ["master_overtime_rates",   "load_overtime_rates_from_db(db)",  "De tre overtidstillæg og deres satser."],
            ["master_supplement_rates", "load_supplement_rates_from_db(db)","Salttillæg, Overnatning, Dagpenge §56."],
            ["master_pay_types",        "load_pay_types_from_db(db)",       "Løntypekoder og Danløn-koder."],
            ["master_absence_types",    "— (forespørges direkte i routers)", "Fraværstyper der vises i UI."],
        ]
    )

    body(doc, "")
    bullet(doc, "load_agreement_types_from_db(db): returnerer dict {navn: Decimal sats}", "rates_loader.py: ")
    bullet(doc, "load_overtime_rates_from_db(db): returnerer dict {nøgle: Decimal sats}")
    bullet(doc, "load_salt_supplement_rate_from_db(db): returnerer Decimal sats for salttillæg pr. time")
    bullet(doc, "load_overnight_rate_from_db(db): returnerer Decimal sats for overnatning pr. forekomst")
    bullet(doc, "seniority_variant_exists(type, db): tjekker om der findes en '9 mdr anciennitet'-variant i DB")
    bullet(doc, "Alle _from_db-funktioner har Excel som fallback, der kun aktiveres hvis DB-tabellen er tom")

    body(doc, "")
    body(doc, (
        "Anciennitetsvarsler: systemet kontrollerer løbende om aktive medarbejdere har ≥9 måneder "
        "og en tilsvarende 9-mdr-variant af overenskomsttypen – i så fald vises et varsel i UI. "
        "Varslet styres af tilladelsen 'anciennitet_alert' (checkAnciennitetsAlerts() returnerer tidligt "
        "hvis !state.currentUser.permissions.includes('anciennitet_alert')). "
        "Tilladelsen er som standard slået til for Administrator og Lønbogholder, og kan klikkes til/fra "
        "per rolle i Brugerstyring."
    ))

    heading(doc, "Stamdata-modulet i brugerfladen", 2, "6.2")
    body(doc, (
        "Stamdata-menupunktet (⚙️ Stamdata) i venstre menu giver administratorer adgang til "
        "seks faner med CRUD-funktionalitet for alle masterdatatabeller:"
    ))
    header_table(doc,
        ["Fane", "Indhold", "CRUD-muligheder"],
        [
            ["Overenskomsttyper", "master_agreement_types", "Opret, rediger navn/sats, slet"],
            ["Overtidssatser",    "master_overtime_rates",  "Rediger satser for de tre tillægstyper"],
            ["Tillæg",            "master_supplement_rates","Rediger satser for salttillæg, overnatning, §56"],
            ["Løntypekoder",      "master_pay_types",       "Opret nye, rediger type/kode/CSV-flag/antal-type/sats-kilde/inkl. sats/inkl. total, slet alle"],
            ["Fraværstyper",      "master_absence_types",   "Opret nye, aktiver/deaktiver, slet alle"],
            ["Helligdage",        "holidays",               "Auto-generer for år, opret manuelt, slet. Kræver 'manage_holidays'-rettighed."],
        ]
    )
    note_box(doc,
        "Alle handlinger i Stamdata-modulet kræver 'stamdata'-rettighed. "
        "Helligdage-fanen kræver desuden 'manage_holidays'-rettighed.",
        "BEMÆRK"
    )

    heading(doc, "Helligdage – API-endepunkter", 2, "6.3")
    header_table(doc,
        ["Endepunkt", "Metode", "Rettighed", "Beskrivelse"],
        [
            ["GET /api/stamdata/holidays",                  "GET",    "stamdata",        "Henter alle helligdage. Valgfri ?year=YYYY-filter."],
            ["POST /api/stamdata/holidays",                 "POST",   "manage_holidays", "Opretter helligdag. Body: date (YYYY-MM-DD), name, half_day_from (opt.)."],
            ["DELETE /api/stamdata/holidays/{id}",          "DELETE", "manage_holidays", "Sletter helligdag med angivet id."],
            ["POST /api/stamdata/holidays/generate/{year}", "POST",   "manage_holidays", "Auto-genererer helligdage for ét år (idempotent). År: 2020–2100."],
        ]
    )
    body(doc, (
        "Helligdagsdata bruges i aktivitetskalenderens frontend: "
        "loadHolidaysForPeriod(startDate, endDate) kaldes parallelt med loadActivities() og "
        "gemmer resultatet i state.holidays[]. renderActivitiesTable() markerer helligdagskolonner "
        "med baggrundsfarven #056a10 (mørkegrøn). Halvdagshelligdage vises med et '½ fra HH:MM'-badge "
        "og helligdagsnavnet som tooltip. Hvis dagens dato falder på en helligdag, bevares "
        "today-indikatoren via border-bottom i accentfarven."
    ))

    # ── 7. Lønkørsel ─────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Lønkørsel", 1, "7")
    body(doc, (
        "Lønkørslen foregår i routers/payroll_router.py. KUN aktiviteter med status "
        "'approved' indgår i beregningen."
    ))

    heading(doc, "API-endepunkter", 2, "7.1")
    header_table(doc,
        ["Endepunkt", "Metode", "Beskrivelse"],
        [
            ["/api/payroll/preview",         "POST", "Returnerer JSON med mellemregninger for alle eller én medarbejder."],
            ["/api/payroll/proevekoersel",   "POST", "Genererer Excel-fil med prøvekørsel og returnerer download-link."],
            ["/api/payroll/proevekoersel-gem","POST","Gemmer Excel-fil i brugervalgt mappe (tkinter-dialog)."],
            ["/api/payroll/export-csv",      "POST", "Genererer Danløn CSV-fil og downloader den."],
            ["/api/payroll/pdf-timesedler",  "POST", "Genererer PDF-timesedler og gemmer i valgt mappe."],
            ["/api/payroll/browse-folder",   "GET",  "Åbner Windows-mappe-dialog (tkinter) og returnerer valgt sti."],
            ["/api/payroll/downloads-folder","GET",  "Returnerer stien til brugerens Downloads-mappe."],
        ]
    )

    heading(doc, "Beregningslogik (_calculate_employee)", 2, "7.2")
    for step in [
        "Itererer alle 14 dage i perioden – ikke kun dage med aktiviteter.",
        "Dage uden aktivitet returneres med 0 timer på alle kolonner.",
        "Overnatning (activity_type = 'overnatning'): tæller forekomster som overnight_count og springer dagslinje-logikken over (continue). Eksponeres i resultatet som overnight_count, overnight_rate og overnight_kr (flat sats pr. forekomst fra Salttillæg og overnatning.xlsx).",
        "Fraværsdage (ferie/fri/afspadsering/skole_kursus): vises med typenavn i stedet for timer; lønberegning for fraværstyper er endnu ikke implementeret og afventer regler.",
        "For normale aktiviteter: kalder calculate_overtime() med aktivitetens start/slut, pauseintervaller og normaltimer for den pågældende dag.",
        "Summerer normal tid, OT_BEFORE, OT_13 og OT_EXTRA timer samt pålæsning/aflæsning.",
        "Beregner kr. = timer × timesats (normal) + tillægstimer × satser.",
        "Returnerer dict med totaler og linjeposter pr. dag (alle 14 dage i perioden).",
    ]:
        bullet(doc, step)

    heading(doc, "Excel-formatering i prøvekørsel", 2, "7.3")
    body(doc, "Excel-filen der genereres ved prøvekørsel har følgende formatering:")
    two_col_table(doc, [
        ["Grøn første række",    "Første datalinje for hver medarbejder markeres med grøn baggrund (farve #C6EFCE) for nem identifikation af ny medarbejder."],
        ["Tom skillerække",      "Efter hver medarbejders totallinje indsættes en tom række som visuel adskillelse."],
        ["Frossen headerrække",  "Headerrækken (række 1) er frossen og følger med ved lodret scroll."],
        ["Fraværstyper",         "Fraværsdage (ferie, fri, afspadsering, skole/kursus) vises med typenavn i Normal tid-kolonnen; øvrige kolonner er blanke."],
        ["Nul-dage",             "Dage uden aktivitet vises med 0 på alle talkolonner."],
    ])

    heading(doc, "Danløn CSV-format", 2, "7.4")
    body(doc, (
        "Kolonnerne i den eksporterede CSV-fil (semikolon-separeret). "
        "Kolonne 5 og 6 er valgfrie per løntypekode og styres via Stamdata:"
    ))
    header_table(doc,
        ["Kolonne", "Altid med?", "Indhold"],
        [
            ["CVR",           "Ja",      "Virksomhedens CVR-nummer"],
            ["Medarbejdernr", "Ja",      "Lønnummer fra medarbejderkortet"],
            ["Lønkode",       "Ja",      "Danløn-kode for lønarten (konfigureres i Stamdata)"],
            ["Antal",         "Ja",      "Timer (2 decimaler) eller antal forekomster (heltal) afhængigt af Antal-type"],
            ["Sats",          "Valgfri", "Sats i kr. (2 decimaler). Slås fra ved 'Inkluder sats' = Nej i Stamdata"],
            ["Total",         "Valgfri", "Antal × Sats (2 decimaler). Tilføjes ved 'Inkluder total' = Ja i Stamdata"],
        ]
    )
    body(doc, (
        "CSV-kolonneopsætningen konfigureres per løntypekode i Stamdata → Løntypekoder: "
        "Antal-type (Timer/Antal), Sats-kilde (timesats, overtidssatser, salttillæg, overnatning, dagpenge), "
        "Inkluder sats og Inkluder total."
    ))

    # ── 8. Aktivitetshåndtering ───────────────────────────────────────────
    heading(doc, "Aktivitetshåndtering", 1, "8")

    heading(doc, "Statusflow", 2, "8.1")
    body(doc,
        "pending → approved (godkendt – approved_by sættes til brugerens initialer) → "
        "deactivated (deaktiveret – deactivated_by sættes til brugerens initialer).\n"
        "Fraværstyper (ferie/fri/afspadsering/skole_kursus) oprettes direkte som approved med approved_by='System'.\n"
        "approved_by og deactivated_by er separate felter – approved_by bruges udelukkende til godkendelser."
    )

    heading(doc, "Rettelse og fortryd", 2, "8.2")
    for step in [
        "Første rettelse: original_start_time og original_end_time gemmes automatisk.",
        "Efterfølgende rettelser: originaltiderne overskrives ikke.",
        "Fortryd: nulstiller start_time og end_time til de gemte originaler.",
    ]:
        bullet(doc, step)

    heading(doc, "Opdeling (split)", 2, "8.3")
    body(doc, (
        "En aktivitet kan opdeles ved et valgt tidspunkt. Systemet opretter to "
        "børneaktiviteter med parent_activity_id og split_part (1 og 2). "
        "Pauser og segmenter fordeles proportionalt til den korrekte del."
    ))

    heading(doc, "Aktivitetsflags", 2, "8.4")
    two_col_table(doc, [
        ["is_under_4h",  "Aktiviteten er under 4 timer – kommentar påkrævet ved godkendelse."],
        ["is_over_12h",  "Aktiviteten er over 12 timer – vises som advarsel i UI."],
        ["is_manual",    "Aktiviteten er manuelt oprettet (source=manual, ikke fra tachograf)."],
        ["is_edited",    "Tiderne er blevet ændret fra tachografdata."],
        ["has_split_children", "Aktiviteten er opdelt i to børneaktiviteter."],
    ])

    # ── 9. Frontend ───────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Frontendarkitektur", 1, "9")
    body(doc, (
        "Hele frontenden er én HTML-fil (templates/index.html) med én JavaScript-fil "
        "(static/js/app.js). Der bruges ingen React, Vue eller andre frameworks."
    ))

    heading(doc, "State-management", 2, "9.1")
    body(doc, "Et globalt state-objekt holder applikationens tilstand:")
    two_col_table(doc, [
        ["state.employees",      "Liste af alle aktive medarbejdere (inkl. dispatcher_group, work_schedule osv.)"],
        ["state.activities",     "Alle aktiviteter for den valgte periode"],
        ["state.periodInfo",     "Aktuel periodeinfo: start/slut, tæller for pending/approved/deactivated"],
        ["state.agreementTypes", "Overenskomsttyper og satser"],
        ["state.splitMin/Max",   "Grænser for opdeling (gemmes i state for validering)"],
        ["manualPauses",         "Pauseintervaller for aktivitet under oprettelse: liste af [ISO-start, ISO-slut]-par. Nulstilles ved åbning af oprettelsesmodalen."],
    ])

    heading(doc, "Cache-busting", 2, "9.2")
    body(doc, (
        "main.py beregner app.js's ændringstidspunkt (st_mtime) og indsætter det som "
        "forespørgselsparameter: <script src='/static/js/app.js?v={mtime}'>. "
        "Browsercachen brydes automatisk ved hver ændring af filen."
    ))

    heading(doc, "Datetime-picker", 2, "9.3")
    body(doc, (
        "En brugerdefineret datetime-komponent erstatter browserens native datetime-local "
        "scroll-input. Komponenten består af: date-input (dato) + number-input (time, 0-23) "
        "+ ':' + number-input (minut, 0-59). Alle styles er inline i JavaScript for at "
        "undgå browsercache-problemer."
    ))
    two_col_table(doc, [
        ["buildDatetimePicker(id, isoValue)", "Bygger komponenten og indsætter den i elementet med det givne id."],
        ["readDatetimePicker(id)",            "Læser de tre felter og returnerer ISO-datetime-streng."],
        ["setDatetimePicker(id, isoValue)",   "Sætter alle tre felter fra en ISO-datetime-streng."],
    ])

    heading(doc, "Date-picker (datovalg)", 2, "9.4")
    body(doc, (
        "En brugerdefineret dato-komponent (buildDatePicker) erstatter browserens native "
        "date-input på steder hvor det er vigtigt at kunne vælge årstal fra dropdown. "
        "Komponenten består af et tekstfelt der åbner et popup-kalender med måned-dropdown, "
        "årstal-dropdown (1950–2100) og en klassisk månedsgrid med klikbare datoer."
    ))
    two_col_table(doc, [
        ["buildDatePicker(id, initialValue)", "Bygger komponenten i elementet med det givne id. Accepts ISO-dato eller tom streng."],
        ["readDatePicker(id)",                "Returnerer den valgte dato som ISO-streng (YYYY-MM-DD)."],
        ["setDatePicker(id, iso)",            "Opdaterer display og hidden-felt til en ny ISO-dato. Opdaterer også kalender-griddet."],
    ])
    body(doc, "Bruges på to steder i applikationen:")
    bullet(doc, "Medarbejdermodal: 'Ansættelsesdato' og 'Fratrædelsesdato'.")
    bullet(doc, "Aktivitetsoversigt: Datovælgeren i periodelinjen (hop til dato).")
    note_box(doc,
        "Popup'en bruger position:fixed og getBoundingClientRect() for korrekt placering "
        "inde i scrollbare modaler. Specialtilfældet 9999-12-31 (ingen fratrædelse) "
        "vises som '31-12-9999' og åbner kalenderen ved indeværende år.",
        "TEKNISK NOTE"
    )

    heading(doc, "Filtrering", 2, "9.5")
    body(doc, "Aktivitetstabellen har tre filtre der kombineres:")
    two_col_table(doc, [
        ["Status-filter",      "Alle / Afventer / Godkendt / Deaktiveret"],
        ["Medarbejder-filter", "Viser kun aktiviteter for valgte medarbejder. Opdateres automatisk når afdelingsfilter ændres."],
        ["Afdelings-filter",   "Filtrerer aktivitetstabellen OG medarbejder-dropdown til kun at vise medarbejdere i den valgte disponentgruppe."],
    ])

    heading(doc, "Stamdata-view", 2, "9.6")
    body(doc, (
        "Stamdata-view aktiveres fra menupunktet '⚙️ Stamdata' i venstre menu (kræver 'stamdata'-rettighed). "
        "View'et indeholder en tab-navigator med fem faner – kun én pane er synlig ad gangen:"
    ))
    two_col_table(doc, [
        ["switchStamdataTab(tab)", "Skifter aktiv pane og opdaterer fane-styling (border, farve, vægt)."],
        ["loadStamdata()",         "Kaldes fra setView('stamdata') og indlæser data til alle fem faner parallelt."],
        ["btn-stamdata-add-*",     "'+Tilføj'-knap i toolbar vises kun for den aktive fane (Overenskomsttyper og Fraværstyper)."],
    ])
    body(doc, (
        "Fraværstyper-fanen viser alle rækker fra master_absence_types med Aktiv-badge (grøn/grå). "
        "Alle typer har Rediger- og Slet-knap. "
        "Løntypekoder-fanen giver mulighed for at redigere type (label), Danløn-kode, Medtag i CSV, "
        "Antal-type (Timer/Antal), Sats-kilde, Inkluder sats og Inkluder total samt slette alle koder. "
        "Alle disse felter kan også sættes ved oprettelse af en ny løntypekode."
    ))

    heading(doc, "Pausehåndtering i oprettelsesmodalen", 2, "9.7")
    body(doc, (
        "Når en manuel aktivitet oprettes, kan der tilføjes et vilkårligt antal pauser via "
        "'+ Tilføj pause'-knappen. Pauserne gemmes i databasefeltet pause_intervals og fratrækkes "
        "automatisk i lønberegning, varighedsvisning og aktivitetsfordeling."
    ))
    header_table(doc,
        ["Funktion (app.js)", "Beskrivelse"],
        [
            ["addManualPause()",      "Læser startdato fra aktivitetens starttid og åbner modal-pause med dt-picker (datofeltet skjult – kun HH:MM vises)."],
            ["confirmPause()",        "Validerer at slut > start, tilføjer [ISO-start, ISO-slut] til manualPauses[] og lukker modal-pause."],
            ["deleteManualPause(idx)","Fjerner pause ved index fra manualPauses[] og opdaterer listen."],
            ["renderManualPauses()", "Tegner #manual-pauses-list med pause-badges og ×-slet-knapper."],
        ]
    )
    body(doc, "Pauseinterval-flow ved POST af aktivitet:")
    for step in [
        "manualPauses[] sendes som pause_intervals i POST-body til POST /api/activities.",
        "ActivityCreate-skemaet validerer listen (list[list[str]]).",
        "_duration_minutes(a) i activities.py klipper hvert interval til aktivitetens bounds og fratrækker det fra bruttotiden. Påvirker is_under_4h og is_over_12h.",
        "calculate_overtime() i overtime.py bruger _subtract_pauses() til at fratrække pauserne i det korrekte tillægsvindue.",
        "openActivityDetail() i app.js beregner Aktivitetsfordeling-bjælken: for manuelle aktiviteter uden tachografsegmentdata beregnes Hvil/pause-% fra pause_intervals og Effektiv tid-% som resten.",
    ]:
        bullet(doc, step)
    note_box(doc,
        "Pausemodalen (modal-pause) bruger buildDatetimePicker med datofeltet skjult – "
        "brugeren ser kun HH:MM. Datoen arves fra aktivitetens startdato.",
        "TEKNISK NOTE"
    )

    # ── 10. Drift og vedligehold (FAQ) ────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Drift og vedligehold – ofte stillede spørgsmål", 1, "10")

    heading(doc, "Hvor er databasen, og hvordan kører den?", 2, "10.1")
    body(doc, (
        "Databasen er én enkelt fil: app/database/lonsystem.db. "
        "SQLite er ikke et separat program der skal startes – Python-koden "
        "læser og skriver direkte i filen. Ingen databaseserver, ingen porte, "
        "ingen baggrundstjeneste. Systemet opretter automatisk en ny, tom database "
        "første gang det startes, hvis filen ikke eksisterer."
    ))
    two_col_table(doc, [
        ["Placering",   "app/database/lonsystem.db"],
        ["Størrelse",   "Starter ved ~140 KB, vokser efterhånden som data opbygges"],
        ["Backup",      "Kopiér filen (mens serveren er stoppet) for at tage backup"],
        ["Nulstilling", "Slet filen – systemet opretter en tom database ved næste opstart"],
    ])

    note_box(doc,
        "Filen bør IKKE ligge i en OneDrive- eller Dropbox-mappe når systemet er i produktion. "
        "Cloud-synkronisering og SQLite konflikter og kan i sjældne tilfælde korruptere databasen. "
        "På en produktionsserver skal filen ligge lokalt på serveren.",
        "VIGTIGT"
    )

    heading(doc, "Hvordan starter og stopper jeg serveren?", 2, "10.2")
    body(doc, "Serveren (uvicorn) er den proces der holder systemet kørende og svarer på browser-forespørgsler.")

    p = doc.add_paragraph()
    r = p.add_run("Stop serveren")
    r.bold = True; r.font.name = "Arial"; r.font.size = Pt(11)
    body(doc, "Tryk Ctrl+C i det terminalvindue hvor uvicorn kører.", space_after=2)
    body(doc, "Alternativt: Åbn Task Manager → find python.exe → Afslut opgave.", space_after=6)

    p2 = doc.add_paragraph()
    r2 = p2.add_run("Start serveren")
    r2.bold = True; r2.font.name = "Arial"; r2.font.size = Pt(11)

    body(doc, "Der er to måder at starte serveren på, afhængigt af situationen:", space_after=4)

    body(doc, "Daglig drift (anbefalet):", space_after=2)
    code = doc.add_paragraph()
    code.paragraph_format.left_indent = Cm(1)
    code.paragraph_format.space_after = Pt(4)
    cr = code.add_run(
        'python.exe -m uvicorn --app-dir app main:app --host 0.0.0.0 --port 8000'
    )
    cr.font.name = "Courier New"; cr.font.size = Pt(9)
    body(doc, "Hurtig og stabil. Ændringer i Python-filer kræver manuel servergenstart (Ctrl+C → start igen).", space_after=8)

    body(doc, "Under udvikling (når programmet ændres af en udvikler):", space_after=2)
    code2 = doc.add_paragraph()
    code2.paragraph_format.left_indent = Cm(1)
    code2.paragraph_format.space_after = Pt(4)
    cr2 = code2.add_run(
        'python.exe -m uvicorn --app-dir app main:app --host 0.0.0.0 --port 8000 --reload'
    )
    cr2.font.name = "Courier New"; cr2.font.size = Pt(9)
    body(doc, (
        "Med --reload genstarter serveren automatisk hver gang en Python-fil gemmes, "
        "så ændringer træder i kraft ved næste browser-reload uden manuel genstart. "
        "Lidt langsommere end daglig drift, men bekvem under aktiv udvikling."
    ), space_after=8)

    body(doc, (
        "Når serveren kører, er systemet tilgængeligt i browseren på "
        "http://127.0.0.1:8000 (lokal maskine) eller serverens IP-adresse "
        "på netværket."
    ))

    note_box(doc,
        "Ændringer i JavaScript-, CSS- og HTML-filer (app.js, style.css, index.html) "
        "træder altid i kraft ved browser-reload – uanset om serveren kører med eller uden --reload. "
        "Det er kun ændringer i Python-filer (.py) der kræver servergenstart.",
        "BEMÆRK"
    )

    heading(doc, "Hvad kræves for at flytte systemet til en fælles server?", 2, "10.3")
    body(doc, (
        "Da systemet er bygget som en webapplikation er det designet til delt brug. "
        "Alle ansatte tilgår det via en browser – ingen installation på klientmaskinen. "
        "Flytningen til en fælles server kræver:"
    ))
    for step in [
        "En dedikeret maskine (eksisterende server, spare-PC eller cloud-VM) der er tændt i arbejdstiden.",
        "Python 3.13 installeret på serveren.",
        "Koden og databasefilen kopieret til serveren (uden for en cloud-synkroniseret mappe).",
        "En fast lokal IP-adresse på servermaskinen (konfigureres i router eller af IT).",
        "Serveren sat op til at starte uvicorn automatisk ved opstart – anbefalet via NSSM (gratis Windows-værktøj der kører uvicorn som en Windows-tjeneste).",
        "Ansatte åbner browseren og går til serverens IP-adresse og port, f.eks. http://192.168.1.50:8000.",
    ]:
        bullet(doc, step)

    note_box(doc,
        "Hvis systemet skal tilgås uden for virksomhedens netværk (hjemmefra, fra mobil), "
        "kræves enten VPN-adgang til netværket eller en cloudserver med HTTPS-certifikat. "
        "Dette er en IT-beslutning der også indebærer en GDPR-vurdering af datalokation.",
        "BEMÆRK"
    )

    heading(doc, "Hvordan ryddes testdata og systemet gøres klar til produktion?", 2, "10.4")
    body(doc, "Følgende fremgangsmåde sikrer et rent produktionssystem:")
    for i, step in enumerate([
        "Stop serveren (Ctrl+C eller Task Manager).",
        "Notér alle rigtige medarbejdere der skal oprettes: lønnumre, førerkortnumre, overenskomsttyper, timefordeling og afdelinger.",
        "Slet filen app/database/lonsystem.db.",
        "Kontrollér at Excel-filerne (Overtid satser.xlsx, Overenskomsttyper og timesatser.xlsx, Fraværstyper.xlsx) indeholder de korrekte satser – de bruges som udgangspunkt for seeding af Stamdata-tabellerne.",
        "Start serveren igen – systemet opretter automatisk en tom database og seeder Stamdata-tabellerne fra Excel-filerne.",
        "Kontrollér og juster om nødvendigt satser og fraværstyper i Stamdata-modulet (⚙️ Stamdata i menuen).",
        "Opret de rigtige medarbejdere i systemet.",
        "Systemet er klar til produktionsbrug.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    body(doc, (
        "Excel-filerne bruges kun til den initiale seeding. Efterfølgende ændringer i satser og "
        "fraværstyper skal foretages via Stamdata-modulet i brugerfladen – ikke i Excel-filerne."
    ))

    # ── 11. Backup-utility ────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Backup-utility", 1, "11")
    body(doc, (
        "Systemet leveres med et separat backup-utility der kører automatisk 4 gange "
        "dagligt og bevarer de seneste 5 dages backup-historik. Utility'et ligger i "
        "backup/-mappen ved siden af app/-mappen."
    ))

    heading(doc, "Filer", 2, "11.1")
    two_col_table(doc, [
        ["backup/backup.py",       "Selve backup-scriptet. Kan køres manuelt eller via Task Scheduler."],
        ["backup/installer.ps1",   "PowerShell-script der registrerer backup-opgaven i Windows Task Scheduler."],
        ["backup/arkiv/",          "Mappe med ZIP-filer – én pr. kørsel."],
        ["backup/backup.log",      "Logfil med tidsstempler og resultater for alle kørsler."],
    ])

    heading(doc, "Hvad der tages backup af", 2, "11.2")
    two_col_table(doc, [
        ["app/database/lonsystem.db",                    "Databasen – det vigtigste. Kopieres via SQLites eget backup-API, sikkert mens systemet kører."],
        ["app/Overtid satser.xlsx",                      "Overtidssatser."],
        ["app/Overenskomsttyper og timesatser.xlsx",     "Timesatser og overenskomsttyper."],
        ["app/Afdelinger.xlsx",                          "Disponentgrupper/afdelinger."],
    ])
    body(doc, (
        "Hvert backup gemmes som en ZIP-fil med navneformatet lonsystem_YYYY-MM-DD_HH-MM.zip. "
        "ZIP-filer ældre end 5 dage slettes automatisk. Med 4 kørsler dagligt i 5 dage "
        "er der til enhver tid 20 backups i arkivet."
    ))

    heading(doc, "Teknisk detalje – sikker kopiering", 2, "11.3")
    body(doc, (
        "SQLite-databasen kopieres via Pythons sqlite3.backup()-metode. Denne metode "
        "bruger SQLites interne backup-API og producerer en konsistent snapshot selv "
        "om der skrives til databasen samtidig (WAL-mode). Det er ikke sikkert blot "
        "at kopiere .db-filen direkte med shutil.copy() mens systemet kører."
    ))

    heading(doc, "Installation", 2, "11.4")
    body(doc, "Kør installer.ps1 én gang som Administrator:")
    for i, step in enumerate([
        "Søg på 'PowerShell' i Start-menuen.",
        "Højreklik → Kør som administrator.",
        'Kør: & "...\\backup\\installer.ps1"',
        "Test med: Start-ScheduledTask -TaskName \"Lønsystem Backup\"",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    body(doc, (
        "Opgaven kører som NT AUTHORITY\\SYSTEM og kræver ingen gemt adgangskode. "
        "Den kører selv når ingen bruger er logget ind på serveren."
    ))

    heading(doc, "Gendannelse fra backup", 2, "11.5")
    for i, step in enumerate([
        "Stop serveren (uvicorn).",
        "Pak den ønskede ZIP-fil ud.",
        "Kopier lonsystem.db til app/database/lonsystem.db (erstat den eksisterende).",
        "Kopier eventuelt Excel-filerne tilbage til app/ hvis de også er beskadigede.",
        "Start serveren igen.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    # ── 12. Netværksadgang og adgang fra andre maskiner ────────────────────
    heading(doc, "Netværksadgang fra andre maskiner", 1, "12")
    body(doc, (
        "Systemet er designet til at køre på én server og tilgås fra mange klientmaskiner "
        "via en webbrowser. Der kræves ingen installation på klientmaskinerne."
    ))

    heading(doc, "Forudsætninger", 2, "12.1")
    two_col_table(doc, [
        ["--host 0.0.0.0",          "Uvicorn skal lytte på alle netværksgrænseflader (ikke kun 127.0.0.1). Sat i .claude/launch.json."],
        ["Windows Firewall",        "Port 8000 skal åbnes for indgående TCP-trafik på det private netværk."],
        ["Fast lokal IP-adresse",   "Servermaskinens IP bør være fast (konfigureres i router eller netværksindstillinger)."],
    ])

    heading(doc, "Åbn port 8000 i Windows Firewall", 2, "12.2")
    body(doc, "Kør én gang som Administrator i PowerShell:")
    code = doc.add_paragraph()
    code.paragraph_format.left_indent = Cm(1)
    code.paragraph_format.space_after = Pt(8)
    cr = code.add_run(
        'New-NetFirewallRule -DisplayName "Lønsystem port 8000" '
        '-Direction Inbound -Protocol TCP -LocalPort 8000 '
        '-Action Allow -Profile Private'
    )
    cr.font.name = "Courier New"; cr.font.size = Pt(9)

    heading(doc, "Find serverens IP-adresse", 2, "12.3")
    body(doc, "Kør ipconfig i PowerShell og aflæs IPv4 Address under det aktive netværkskort:")
    code2 = doc.add_paragraph()
    code2.paragraph_format.left_indent = Cm(1)
    code2.paragraph_format.space_after = Pt(8)
    cr2 = code2.add_run("ipconfig | Select-String 'IPv4'")
    cr2.font.name = "Courier New"; cr2.font.size = Pt(9)

    heading(doc, "Tilgang fra klientmaskine", 2, "12.4")
    body(doc, (
        "Åbn en webbrowser på klientmaskinen og gå til serverens IP-adresse og port 8000. "
        "Eksempel hvis serverens IP er 192.168.1.29:"
    ))
    code3 = doc.add_paragraph()
    code3.paragraph_format.left_indent = Cm(1)
    code3.paragraph_format.space_after = Pt(8)
    cr3 = code3.add_run("http://192.168.1.29:8000")
    cr3.font.name = "Courier New"; cr3.font.size = Pt(9)

    note_box(doc,
        "Adressen 127.0.0.1 eller localhost virker kun på selve servermaskinen. "
        "Andre maskiner skal bruge serverens rigtige IP-adresse på netværket.",
        "OBS"
    )

    doc.save(OUT / "Teknisk dokumentation.docx")
    print("Teknisk dokumentation.docx gemt.")


# ══════════════════════════════════════════════════════════════════════════════
#  BRUGERVEJLEDNING
# ══════════════════════════════════════════════════════════════════════════════

def build_bruger():
    doc = Document()

    for section in doc.sections:
        section.page_width  = Cm(21)
        section.page_height = Cm(29.7)
        section.left_margin = section.right_margin = Cm(2.5)
        section.top_margin  = section.bottom_margin = Cm(2.5)

    cover(doc, "Lønsystem", "Brugervejledning", "Juni 2026")

    # ── Introduktion ───────────────────────────────────────────────────────
    heading(doc, "Introduktion", 1, "1")
    body(doc, (
        "Lønsystemet er et webbaseret program der håndterer registrering og lønberegning "
        "for lastbilchauffører hos Poul Schou A/S. Systemet henter automatisk kørselsdata "
        "fra chaufførernes digitale tachografer (.ddd-filer) og giver mulighed for at "
        "godkende, rette og eksportere løndata til Danløn."
    ))
    body(doc, (
        "Systemet tilgås via en almindelig webbrowser – der er ingen installation nødvendig "
        "på den enkelte computer. Åbn browseren og gå til systemets adresse på det lokale netværk."
    ))

    heading(doc, "Tre hovedområder", 2, "1.1")
    header_table(doc,
        ["Område", "Formål"],
        [
            ["Aktiviteter",  "Viser og håndterer alle chaufførers registrerede arbejdsdage i den aktuelle lønperiode."],
            ["Lønkørsel",    "Beregner og eksporterer løn til Danløn samt genererer timesedler og prøvekørsler."],
            ["Medarbejdere", "Stamdata for alle chauffører: lønnummer, overenskomst, normaltimer, afdeling m.m."],
        ]
    )

    # ── 2. Navigation ─────────────────────────────────────────────────────
    heading(doc, "Navigation", 1, "2")

    heading(doc, "Venstre menu", 2, "2.1")
    two_col_table(doc, [
        ["Aktiviteter",    "Viser aktivitetstabellen for den aktuelle lønperiode."],
        ["Lønkørsel",      "Åbner lønkørselspanelet med prøvekørsel, PDF og CSV-eksport."],
        ["Importer .ddd",  "Import af tachografdata fra fil eller mappe."],
        ["Medarbejdere",   "Oversigt over og redigering af medarbejderstamdata."],
        ["⚙️ Stamdata",    "Konfiguration af systemets masterdata: overenskomsttyper, overtidssatser, tillæg, løntypekoder (inkl. CSV-kolonneopsætning), fraværstyper og helligdage. Alle typer og koder kan oprettes, redigeres og slettes. Kun synlig for administratorer."],
    ])

    heading(doc, "Periodenavigation", 2, "2.2")
    body(doc, (
        "Øverst på skærmen vises den aktuelle lønperiode (14 dage). "
        "Brug piletasterne (‹ og ›) til at navigere til forrige eller næste periode. "
        "Du kan også bruge datovælgeren til at hoppe direkte til en specifik dato: "
        "klik på datofeltet for at åbne en kalender med måned- og årstaldropdown."
    ))

    heading(doc, "Statuschips", 2, "2.3")
    header_table(doc,
        ["Chip", "Farve", "Betydning"],
        [
            ["Afventer",     "Rød",   "Antal aktiviteter der venter på godkendelse."],
            ["Godkendt",     "Grøn",  "Antal godkendte aktiviteter."],
            ["Deaktiveret",  "Grå",   "Antal deaktiverede (inaktive) aktiviteter."],
        ]
    )
    body(doc, "Du kan klikke på en chip for hurtigt at filtrere tabellen til den pågældende status.")

    # ── 3. Import af tachografdata ────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Import af tachografdata", 1, "3")
    body(doc, (
        "Tachografdata gemmes på chaufførernes digitale fører-kort som .ddd-filer. "
        "Disse filer importeres i systemet, som automatisk opretter aktiviteter for "
        "alle registrerede arbejdsdage."
    ))

    heading(doc, "Fremgangsmåde", 2, "3.1")
    for i, step in enumerate([
        "Klik på 'Importer .ddd' i den venstre menu.",
        "Vælg 'Vælg filer' for at importere enkeltfiler, eller 'Vælg mappe' for at importere alle .ddd-filer i en mappe.",
        "En Windows-filhåndterings-dialog åbner sig – naviger til filerne og bekræft valget.",
        "Systemet importerer filerne og viser et resume: antal importerede, antal opdaterede, antal sprunget over og eventuelle fejl.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    note_box(doc,
        "Systemet springer automatisk allerede importerede aktiviteter over "
        "(baseret på medarbejder + starttidspunkt). Det er sikkert at importere "
        "samme mappe flere gange. 'Sprunget over' kan dog OGSÅ betyde at ingen "
        "medarbejder i systemet har det kortnummer der findes i filen – der vises "
        "ingen fejlmelding i dette tilfælde, se Forudsætninger nedenfor.",
        "GODT AT VIDE"
    )

    heading(doc, "Forudsætninger", 2, "3.2")
    bullet(doc, "Chaufføren skal være oprettet i systemet med korrekt førerkortnummer.")
    bullet(doc, (
        "Førerkortnummeret i systemet skal være de første 14 tegn af kortnummeret: "
        "landekode (2 bogstaver) + 12 cifre (f.eks. DK000000178901) – IKKE de sidste "
        "2 cifre. De sidste 2 cifre er kortets udskiftnings-/fornyelsesindeks og "
        "ændrer sig hver gang kortet fornys, så de er ikke en del af det stabile "
        "kortnummer."
    ))
    bullet(doc, (
        "Stemmer kortnummeret ikke, importeres 0 aktiviteter uden fejlmelding – kun "
        "'Sprunget over'-tallet stiger. Kontrollér og ret kortnummeret i Stamdata "
        "hvis en import ikke giver de forventede aktiviteter."
    ))

    note_box(doc,
        "Starter chaufførens dag med en kort pause (fx et par minutter inden kørslen "
        "begynder), vises denne pause nu som en del af dagens arbejdstid i "
        "aktivitetstabellen. Pausen aflønnes stadig ikke – den trækkes fra som hvil/pause "
        "ligesom systemets øvrige pauser.",
        "GODT AT VIDE"
    )

    # ── 4. Aktivitetstabellen ─────────────────────────────────────────────
    heading(doc, "Aktivitetstabellen", 1, "4")
    body(doc, (
        "Aktivitetstabellen er systemets hovedvisning. Den viser alle chauffører "
        "i rækker og de 14 dage i perioden som kolonner. Hver celle indeholder "
        "aktiviteternes start- og sluttidspunkt."
    ))

    heading(doc, "Farvekodning", 2, "4.1")
    header_table(doc,
        ["Farve", "Betydning"],
        [
            ["Rød/mørk",   "Afventer godkendelse (pending)."],
            ["Grøn",       "Godkendt aktivitet."],
            ["Orange",     "Deaktiveret aktivitet."],
            ["Blå/neutral","Manuel aktivitet (ikke fra tachograf) eller korrigeret aktivitet."],
            ["FERIE/FRI",  "Fraværstype – vises med tekst i grøn boks."],
            ["Mørkegrøn kolonne (#056a10)", "Helligdag – søjleoverskriften fremhæves med mørk grøn baggrund. Halvdagshelligdage vises med '½ fra HH:MM'-badge og navn som tooltip."],
        ]
    )

    heading(doc, "Symboler og advarsler", 2, "4.2")
    two_col_table(doc, [
        ["❗ (udråbstegn)",        "Aktiviteten er under 4 timer lang. Kræver kommentar ved godkendelse. Vises kun når status er Afventer eller Deaktiveret – forsvinder ved godkendelse."],
        ["⚠️ (advarselstrekant)", "Aktiviteten er over 12 timer lang. Advarsel om usædvanlig lang vagt. Vises kun når status er Afventer eller Deaktiveret – forsvinder ved godkendelse."],
        ["(K) prefix",             "Aktiviteten er et barn af en opdelt aktivitet."],
    ])

    heading(doc, "Filtrering", 2, "4.3")
    body(doc, "Brug filtrene i toppen af tabellen til at indsnævre visningen:")
    bullet(doc, "Vis alle aktiviteter, kun afventende, kun godkendte eller kun deaktiverede.", "Status: ")
    bullet(doc, "Filtrer til én bestemt chauffør.", "Medarbejder: ")
    bullet(doc, "Vis kun chauffører fra den valgte afdeling. Medarbejder-filteret opdateres automatisk.", "Afdeling: ")

    # ── 5. Aktivitetsdetaljer og godkendelse ──────────────────────────────
    doc.add_page_break()
    heading(doc, "Aktivitetsdetaljer og godkendelse", 1, "5")
    body(doc, (
        "Klik på et tidsemærke i tabellen for at åbne detaljevisningen for aktiviteten. "
        "Her kan du se alle oplysninger og foretage ændringer."
    ))

    heading(doc, "Hvad kan du se?", 2, "5.1")
    two_col_table(doc, [
        ["Start- og sluttid",        "Registreret tidspunkt fra tachografen (eller manuelt angivet)."],
        ["Effektiv tid",              "Samlet arbejdstid fratrukket pauser."],
        ["Aktivitetsfordeling",       "Fordeling mellem kørsel, rådighedstid, andet arbejde og hvil/pause (fra tachografen)."],
        ["Detaljeret tidslinje",      "Alle segmenter med præcise tidspunkter."],
        ["Status og godkender",       "Hvem har godkendt og hvornår."],
    ])

    heading(doc, "Hvad kan du gøre?", 2, "5.2")

    p = doc.add_paragraph()
    r = p.add_run("Ret starttid / sluttid")
    r.bold = True; r.font.name = "Arial"; r.font.size = Pt(11)
    body(doc, (
        "Angiv en ny dato og et nyt klokkeslæt. Brug piltasterne i time- og minutfeltet "
        "eller skriv tallene direkte. Klik 'Gem rettelse' for at gemme. "
        "Systemet bevarer de originale tachograftider automatisk."
    ), space_after=4)

    p2 = doc.add_paragraph()
    r2 = p2.add_run("Fortryd rettelse")
    r2.bold = True; r2.font.name = "Arial"; r2.font.size = Pt(11)
    body(doc, "Nulstiller tiderne til de originale værdier fra tachografen.", space_after=4)

    p3 = doc.add_paragraph()
    r3 = p3.add_run("Opdel aktivitet")
    r3.bold = True; r3.font.name = "Arial"; r3.font.size = Pt(11)
    body(doc, (
        "Del en vagt i to – fx hvis en chauffør skifter tur midt på dagen. "
        "Vælg tidspunktet for opdelingen. Systemet opretter to nye aktiviteter "
        "og fordeler pauser og segmenter korrekt."
    ), space_after=4)

    p4 = doc.add_paragraph()
    r4 = p4.add_run("Godkend")
    r4.bold = True; r4.font.name = "Arial"; r4.font.size = Pt(11)
    body(doc, (
        "Godkend aktiviteten så den indgår i lønkørslen. Angiv dine initialer. "
        "Aktiviteter under 4 timer kræver altid en kommentar."
    ), space_after=4)

    p5 = doc.add_paragraph()
    r5 = p5.add_run("Deaktiver")
    r5.bold = True; r5.font.name = "Arial"; r5.font.size = Pt(11)
    body(doc, (
        "Markér aktiviteten som inaktiv. Den indgår ikke i lønberegningen "
        "men slettes ikke fra databasen."
    ), space_after=8)

    note_box(doc,
        "KUN godkendte aktiviteter medtages i lønkørslen. Husk at gennemgå og "
        "godkende alle relevante aktiviteter inden du kører løn.",
        "VIGTIGT"
    )

    # ── 6. Manuelle aktiviteter ───────────────────────────────────────────
    heading(doc, "Manuelle aktiviteter", 1, "6")
    body(doc, (
        "Brug manuelle aktiviteter til at registrere ferie, afspadsering, fri, "
        "skole/kursus eller andre vagter der ikke fremgår af tachografen."
    ))

    heading(doc, "Oprettelse", 2, "6.1")
    for i, step in enumerate([
        "Klik på '+ Tilføj aktivitet' knappen i aktivitetstabellen.",
        "Vælg medarbejder og aktivitetstype.",
        "Angiv start- og sluttidspunkt.",
        "Tilføj eventuelle pauser ved at klikke '+ Tilføj pause' (se afsnit 6.3).",
        "Udfyld eventuelt turnummer og pålæsning/aflæsning (kun for normale aktiviteter).",
        "Klik 'Gem aktivitet'.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    heading(doc, "Fraværstyper og overnatning", 2, "6.2")
    body(doc, "Når du vælger en fraværstype eller overnatning, sker følgende automatisk:")
    bullet(doc, "Felterne for turnummer, pålæsning og aflæsning skjules (ikke relevante).")
    bullet(doc, "Aktiviteten godkendes automatisk med 'System' som godkender.")
    bullet(doc, "Ferie: starttidspunktet sættes automatisk til 06:00, og sluttidspunktet beregnes ud fra medarbejderens normaltimer den pågældende dag.")

    body(doc, (
        "De tilgængelige fraværstyper administreres i Stamdata-modulet under fanen 'Fraværstyper'. "
        "Her kan du aktivere og deaktivere typer, tilføje nye typer og slette eksisterende."
    ))
    header_table(doc,
        ["Type", "Beskrivelse"],
        [
            ["Ferie",          "Registrerer en feriedag. Start: 06:00. Slut: 06:00 + normaltimer for dagen."],
            ["Afspadsering",   "Registrerer afspadsering."],
            ["Fri",            "Registrerer fridag."],
            ["Skole/kursus",   "Registrerer skole- eller kursusdag."],
            ["Overnatning",    "Registrerer en overnatning (flat sats pr. forekomst – ikke timer). Angiv blot datoen. Satsen hentes automatisk fra Stamdata (Tillæg-fanen)."],
        ]
    )

    heading(doc, "Registrering af pauser", 2, "6.3")
    body(doc, (
        "For normale aktiviteter kan du registrere de pauser chaufforen har holdt i løbet af "
        "arbejdsdagen. Pauserne fratrækkes automatisk i den effektive arbejdstid og indgår korrekt "
        "i beregningen af overtidstillæg."
    ))
    for i, step in enumerate([
        "Angiv aktivitetens starttidspunkt (påkrævet – pausedatoen arves herfra).",
        "Klik '+ Tilføj pause'. En dialogboks åbner sig med titel 'Pause 1', 'Pause 2' osv.",
        "Angiv pausens starttidspunkt og sluttidspunkt (kun klokkeslæt – dato sættes automatisk).",
        "Klik 'Tilføj'. Pausen vises i listen med start- og sluttid og en ×-slet-knap.",
        "Gentag for yderligere pauser. Klik × for at fjerne en pause.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")
    note_box(doc,
        "Pausefelterne vises kun for normale aktiviteter. "
        "For fraværstyper (ferie, fri m.fl.) og overnatning er pausesektionen skjult.",
        "GODT AT VIDE"
    )
    body(doc, "Pauserne påvirker tre steder i systemet:")
    bullet(doc, "Sum, effektiv tid – vises i aktivitetsdetaljerne og er fratrukket pausetid.")
    bullet(doc, "Aktivitetsfordeling – manuelle aktiviteter med pauser viser 'Effektiv tid' (blå) og 'Hvil/pause' (grå) i %-bjælken.")
    bullet(doc, "Lønberegning – pauser fratrækkes i det præcise tidsvindue de afholdes, så overtidstillæg beregnes korrekt.")

    # ── 7. Medarbejdere ───────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Medarbejdere", 1, "7")
    body(doc, "Klik på 'Medarbejdere' i venstre menu for at se og redigere medarbejderstamdata.")

    heading(doc, "Opret ny medarbejder", 2, "7.1")
    body(doc, "Klik '+ Opret medarbejder' og udfyld felterne:")

    header_table(doc,
        ["Felt", "Påkrævet", "Beskrivelse"],
        [
            ["Aftale",              "Ja", "Timelønnet med fast arbejdstid eller ikke fastlagt arbejdstid."],
            ["Overenskomsttype",    "Ja", "Bestemmer timesatsen. Vælg fra listen der stammer fra Stamdata (Overenskomsttyper-fanen)."],
            ["Disponentgruppe",     "Nej","Afdeling – bruges til at filtrere aktivitetstabellen."],
            ["Lønnummer",           "Ja", "Unikt lønnummer (bruges i Danløn-eksporten)."],
            ["Førerkortnummer",     "Nej","EU-førerkortnummer – påkrævet for at importere .ddd-filer korrekt."],
            ["Navn",                "Ja", "Fornavn og efternavn."],
            ["Adresse / postnummer","Nej","Adresseoplysninger."],
            ["E-mail / telefon",    "Nej","Kontaktoplysninger."],
            ["Ansættelsesdato",     "Ja", "Startdato for ansættelsen. Klik på feltet for at åbne en kalender med måned- og årstaldropdown."],
            ["Fratrædelsesdato",    "Nej","Udfyldes KUN ved fratrædelse. Default er 31-12-9999. Klik på feltet for at åbne kalender-pickeren."],
            ["Aktiv",               "—", "Afkryd for at medarbejderen er aktiv i systemet."],
            ["Fuldlønnet",          "—", "Afkryd hvis medarbejderen er fuldlønnet."],
        ]
    )

    heading(doc, "Timefordeling", 2, "7.2")
    body(doc, (
        "Timefordelingen angiver medarbejderens normaltimer pr. ugedag i en 14-dages periode "
        "(uge A og uge B, svarende til ulige og lige ISO-uger). Standardværdier er:"
    ))
    bullet(doc, "Mandag–torsdag: 7,5 timer")
    bullet(doc, "Fredag: 7 timer")
    bullet(doc, "Lørdag–søndag: 0 timer")
    body(doc, (
        "Juster timeantallet ved at klikke i felterne og skrive det ønskede antal. "
        "Normaltimerne bruges til beregning af overtidstillæg og til at auto-udfylde sluttidspunktet ved registrering af ferie."
    ))

    heading(doc, "Anciennitetsvarsler", 2, "7.3")
    body(doc, (
        "Systemet kontrollerer løbende om medarbejdere har nået 9 måneders anciennitet "
        "og en tilsvarende overenskomsttype med højere sats. Hvis det er tilfældet, vises "
        "et pop-up-varsel. Varslet er styret af tilladelsen 'Anciennitetsvarsel' i Brugerstyring – "
        "som standard er den slået til for Administrator og Lønbogholder og fra for Disponent. "
        "En administrator kan klikke tilladelsen til eller fra for enhver rolle. "
        "Husk at opdatere overenskomsttypen for medarbejderen."
    ))
    body(doc, (
        "Når du klikker \"Ændring foretaget\" i varslet, gemmes afvisningen på medarbejderen i databasen "
        "(feltet anciennitet_dismissed_at). Varslet vises ikke igen – uanset computer eller browser. "
        "Hvis overenskomsttypen ændres på medarbejderen, nulstilles afvisningen automatisk, "
        "så varslet kan dukke op igen hvis ancienniteten stadig er relevant."
    ))

    # ── 8. Helligdagskalender ─────────────────────────────────────────────
    heading(doc, "Helligdagskalender", 1, "8")
    body(doc, (
        "Systemet vedligeholder automatisk en kalender over danske helligdage. "
        "Helligdage fremhæves i aktivitetskalenderen og danner grundlag for fremtidig "
        "beregning af helligdagstillæg."
    ))

    heading(doc, "Markering i aktivitetskalenderen", 2, "8.1")
    body(doc, (
        "Dage der er helligdage fremhæves med mørk grøn baggrund (#056a10) i "
        "aktivitetskalenderens kolonneoverskrifter. Halvdagshelligdage (1. maj og Grundlovsdag) "
        "vises med et '½ fra 12:00'-badge. Hold musen over overskriften for at se helligdagens navn."
    ))
    note_box(doc,
        "Helligdagskalenderen genereres automatisk for de næste 5 år ved serveropstart. "
        "Du behøver ikke gøre noget – den opdaterer sig selv.",
        "GODT AT VIDE"
    )

    heading(doc, "Administration af helligdage (Stamdata → Helligdage)", 2, "8.2")
    body(doc, (
        "Brugere med rettigheden 'Administrér helligdage' kan administrere helligdagskalenderen "
        "via Stamdata-menupunktet → fanen 'Helligdage':"
    ))
    header_table(doc,
        ["Handling", "Beskrivelse"],
        [
            ["Generer for år",   "Klik 'Generer [årstal]' for at auto-generere alle danske helligdage for det valgte år. Eksisterende datoer overskrives ikke."],
            ["Tilføj manuelt",   "Klik '+Tilføj helligdag' for at oprette en særlig fridag med valgfri halvdagstid (fx en lukkedag)."],
            ["Slet helligdag",   "Klik 'Slet' på en helligdag for at fjerne den fra kalenderen. Auto-genererede og manuelle helligdage kan begge slettes."],
        ]
    )
    two_col_table(doc, [
        ["Faste helligdage",      "Nytårsdag, 1. maj (½), Grundlovsdag (½), Juleaftensdag, 1. og 2. juledag, Nytårsaftensdag"],
        ["Bevægelige helligdage", "Skærtorsdag, Langfredag, Påskedag, 2. påskedag, Kristi Himmelfartsdag, Pinsedag, 2. pinsedag"],
        ["Store Bededag",         "Medtages ikke – afskaffet fra 2024"],
    ])

    # ── 9. Lønkørsel ─────────────────────────────────────────────────────
    heading(doc, "Lønkørsel", 1, "9")
    body(doc, (
        "Klik på 'Lønkørsel' i venstre menu for at beregne og eksportere løn. "
        "Husk: kun aktiviteter med status 'Godkendt' indgår i beregningen."
    ))

    heading(doc, "Prøvekørsel", 2, "9.1")
    body(doc, (
        "Prøvekørslen beregner lønnen og gemmer resultatet som en Excel-fil. "
        "Brug denne til at tjekke tallene inden den endelige kørsel."
    ))
    bullet(doc, "Klik 'Prøvekørsel'.")
    bullet(doc, "Vælg evt. en bestemt medarbejder, eller lad feltet stå tomt for alle.")
    bullet(doc, "Klik 'Gennemse' for at vælge hvilken mappe filen skal gemmes i (foreslår Downloads-mappen).")
    bullet(doc, "Klik 'Kør prøvekørsel'. Filen gemmes og pop-up-vinduet lukker automatisk.")

    body(doc, "Excel-filen viser alle 14 dage i perioden for hver medarbejder:")
    bullet(doc, "Dage med normal aktivitet: timer fordelt på Normal tid, Tillæg 05-06, Tillæg OT1-3 og Øvrigt OT.")
    bullet(doc, "Fraværsdage (Ferie, Fri, Afspadsering, Skole/kursus): vises med fraværstype i Normal tid-kolonnen.")
    bullet(doc, "Dage uden registrering: vises med 0 på alle kolonner.")
    bullet(doc, "Første linje pr. medarbejder er markeret med grøn baggrund. Tom linje adskiller medarbejdere.")

    heading(doc, "Dan PDF'er", 2, "9.2")
    body(doc, "Genererer individuelle timesedler til alle medarbejdere som PDF-filer.")
    bullet(doc, "Klik 'Dan PDF'er'.")
    bullet(doc, "Vælg mappe at gemme i (brug 'Gennemse').")
    bullet(doc, "Klik 'Dan PDF'er'. Én PDF pr. medarbejder gemmes i mappen.")

    heading(doc, "Kør løn (Danløn CSV)", 2, "9.3")
    body(doc, (
        "Eksporterer den endelige lønfil til Danløn. "
        "Filen er i CSV-format og kan importeres direkte i Danløn."
    ))
    bullet(doc, "Klik 'Kør løn'.")
    bullet(doc, "Bekræft at du er klar til at køre endelig løn.")
    bullet(doc, "CSV-filen downloades til din computer.")
    body(doc, (
        "CSV-filen indeholder op til 6 kolonner per lønpost: CVR-nummer, medarbejdernr., lønkode, "
        "antal (timer eller forekomster), sats og evt. total. "
        "Hvilke kolonner der medtages afhænger af opsætningen i Stamdata → Løntypekoder."
    ))

    heading(doc, "CSV-kolonneopsætning per løntypekode", 2, "9.3.1")
    body(doc, (
        "Under Stamdata → Løntypekoder kan du for hver løntype styre præcis hvad der eksporteres i CSV-filen:"
    ))
    header_table(doc,
        ["Indstilling", "Valgmuligheder", "Beskrivelse"],
        [
            ["Antal-type",    "Timer / Antal",                 "Timer: eksporterer timetal med 2 decimaler. Antal: eksporterer antal forekomster som heltal (fx overnatninger)."],
            ["Sats-kilde",    "Timesats, OT-satser, Salt, Overnatning, Dagpenge §56", "Bestemmer hvilken sats der bruges til kolonnen Sats og beregning af Total."],
            ["Inkluder sats", "Ja / Nej",                      "Ja: sats-kolonnen skrives i CSV. Nej: satsen udelades fra CSV, men bruges stadig til beregning af Total."],
            ["Inkluder total","Ja / Nej",                      "Ja: en ekstra total-kolonne tilføjes (antal × sats). Nej: ingen total-kolonne."],
        ]
    )
    note_box(doc,
        "Inkluder sats = Nej og Inkluder total = Ja giver en CSV med kun antal og total – "
        "nyttigt når Danløn selv beregner satsen ud fra lønkoden.",
        "TIP"
    )

    heading(doc, "Hvad beregnes?", 2, "9.4")
    body(doc, "For hver godkendt aktivitet beregnes følgende lønposter:")
    header_table(doc,
        ["Lønpost", "Beskrivelse"],
        [
            ["Normal løn",         "Timesats × normaltimer for dagen (fra medarbejderens timefordeling)."],
            ["Tillæg 05-06",       "Forhøjet sats for arbejde mellem kl. 05:00 og 06:00."],
            ["Tillæg 18-21 / OT",  "Forhøjet sats for arbejde kl. 18-21 og overarbejde op til 3 timer."],
            ["Nat / ekstra OT",    "Højeste sats for natarbejde (21-05) og overarbejde over 3 timer."],
            ["Pålæsning",          "Tillæg for pålæsningstid (minutter × minutsats)."],
            ["Aflæsning",          "Tillæg for aflæsningstid (minutter × minutsats)."],
            ["Salttillæg",         "Tillæg pr. time for kørsel med salt (registreret på aktiviteten). Sats fra Stamdata (Tillæg-fanen)."],
            ["Overnatning",        "Fast sats pr. overnatning (antal forekomster × sats). Sats fra Stamdata (Tillæg-fanen)."],
        ]
    )

    # ── 10. Vigtige regler ────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Vigtige regler og opmærksomhedspunkter", 1, "10")

    heading(doc, "Inden lønkørsel – tjekliste", 2, "10.1")
    for item in [
        "Alle .ddd-filer er importeret for perioden.",
        "Alle relevante aktiviteter er gennemgået og godkendt.",
        "Aktiviteter med ! (under 4 timer) er godkendt med kommentar.",
        "Eventuelle rettelser er kontrolleret – brug 'Fortryd rettelse' ved fejl.",
        "Prøvekørsel er gennemgået og tallene ser korrekte ud.",
    ]:
        bullet(doc, item)

    heading(doc, "Opdatering af satser", 2, "10.2")
    body(doc, (
        "Timesatser og overtidssatser opdateres via Stamdata-modulet i systemets brugerflade. "
        "Ændringerne slår igennem ved næste beregning uden genstart."
    ))
    for i, step in enumerate([
        "Klik på '⚙️ Stamdata' i venstre menu (kræver administrator-login).",
        "Vælg den relevante fane: 'Overenskomsttyper', 'Overtidssatser' eller 'Tillæg'.",
        "Klik på 'Rediger' ud for den sats der skal ændres.",
        "Indtast den nye sats og klik 'Gem'.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")
    two_col_table(doc, [
        ["Overenskomsttyper-fanen", "Timesatser for overenskomsttyper (normal løn)."],
        ["Overtidssatser-fanen",    "Satser for de tre overtidstillæg (1 time før, 1-3 timer efter, øvrigt)."],
        ["Tillæg-fanen",            "Sats for salttillæg (pr. time), overnatning (pr. forekomst) og §56."],
    ])
    note_box(doc,
        "Rediger ikke Excel-filerne med forventning om at ændringerne slår igennem. "
        "Excel bruges KUN til den initiale seeding af databasen ved første opstart. "
        "Al efterfølgende konfiguration sker via Stamdata-modulet.",
        "VIGTIGT"
    )

    heading(doc, "Fejl og usædvanlige situationer", 2, "10.3")
    header_table(doc,
        ["Situation", "Hvad gør du?"],
        [
            ["Forkert start- eller sluttid importeret",
             "Åbn aktiviteten og brug 'Ret starttid/sluttid'. Brug 'Fortryd rettelse' hvis du fortryder."],
            ["Chauffør er ikke i systemet (import fejler)",
             "Opret medarbejderen med korrekt førerkortnummer og importér .ddd-filen igen."],
            ["Import viser 0 importerede og mange 'sprunget over', selvom filerne er nye",
             "Kontrollér medarbejderens førerkortnummer i Stamdata: det skal være de "
             "første 14 tegn (landekode + 12 cifre), uden de sidste 2 udskiftnings-/"
             "fornyelsescifre. Ret nummeret og importér filen igen."],
            ["Aktivitet skal deles i to (f.eks. skift af tur)",
             "Brug 'Opdel aktivitet' og angiv tidspunktet for opdelingen."],
            ["Aktivitet skal ignoreres",
             "Brug 'Deaktiver' – aktiviteten medtages ikke i lønberegningen men slettes ikke."],
            ["Medarbejder har nået 9 måneder",
             "Systemet viser et varsel. Opdater overenskomsttypen for medarbejderen."],
            ["Lønkørslen viser ikke nye lønposter (fx overnatning)",
             "Genstart serveren: stop og start igen via Preview-panelet i Claude Code. Systemet indlæser ny beregningslogik ved opstart."],
        ]
    )

    note_box(doc,
        "Fratrædelsesdatoen for aktive medarbejdere skal stå på 31-12-9999. "
        "Udfyld kun fratrædelsesdatoen den dag en medarbejder forlader virksomheden.",
        "HUSK"
    )

    doc.save(OUT / "Brugervejledning.docx")
    print("Brugervejledning.docx gemt.")


if __name__ == "__main__":
    build_teknisk()
    build_bruger()
    print("Begge dokumenter er gemt i docs/-mappen.")
