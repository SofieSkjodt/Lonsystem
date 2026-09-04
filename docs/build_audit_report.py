"""
Bygger systemaudit-rapporten som PDF og gemmer den i docs/.
Kør: python docs/build_audit_report.py
"""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

OUTPUT = Path(__file__).parent / "Systemaudit-rapport 2026-06-24.pdf"

# Status per issue:  "LØST" | "AFVENTER" | "ACCEPTERET" | "BEHOLDER"
ISSUE_STATUS = {
    1:  ("AFVENTER",   "Skal ikke ændres nu."),
    2:  ("ACCEPTERET", "Danløn tager barnets 1. sygedag under sygdom – accepteret adfærd."),
    3:  ("LØST",       "Koder hentes fra Stamdata → Løntypekoder. Separate konstanter tilføjet for §56 og barn 1.sygedag."),
    4:  ("LØST",       "Rettet."),
    5:  ("LØST",       "Rettet."),
    6:  ("ACCEPTERET", "Delvist – de øvrige felter (loading_minutes, vehicle_registration m.fl.) kopieres nu til begge dele. trip_number kopieres stadig ikke, men er harmløst: feltet bruges ingen steder i kodebasen (hverken sat af .ddd-import, eksponeret i noget API-skema eller vist i UI) – 'Turnummer' er en åben, ufærdig funktion, så der er intet at miste i praksis."),
    7:  ("LØST",       "Rettet."),
    8:  ("LØST",       "Verificeret 2026-09: _safe_save_dir bruger nu is_under_allowed_root() (app/utils/safe_paths.py) som hvidliste."),
    9:  ("LØST",       "CODEREF.md opdateret: app.js-linjeantal, admin-login, manglende filer tilføjet."),
    10: ("LØST",       "Rettet."),
    11: ("LØST",       "Rettet."),
    12: ("LØST",       "Rettet."),
    13: ("AFVENTER",   "Verificeret 2026-09: ActivityType-enumen har stadig kun de samme 5 typer (models.py:33-38) – hverken udvidet eller fjernet."),
    14: ("ACCEPTERET", "Det er korrekt."),
    15: ("LØST",       "Rettet – --reload fjernet fra produktionskommando i dokumentation."),
    16: ("LØST",       "Ja, tilføjet."),
    17: ("BEHOLDER",   "Nej, lad denne være som den er."),
    18: ("AFVENTER",   "Delvist – CVR læses fra Stamdata i den normale flow, men pay_rates.CVR_NUMBER bruges stadig som runtime-default i timeseddel_router.py:_build_pdf()."),
    19: ("ACCEPTERET", "Korrekt."),
    20: ("LØST",       "Rettet."),
    21: ("AFVENTER",   "Løses af eksterne. Ingen systemmæssig ændring nu."),
    22: ("LØST",       "Ja, koder hentes fra Stamdata → Løntypekoder."),
    23: ("LØST",       "Det er mindre eller lig med 56 dage – rettet til <=."),
}

# --- Farver (PS Løn brand) ---
PS_GREEN      = colors.HexColor("#317423")
PS_ACCENT     = colors.HexColor("#78b21a")
PS_LIGHT      = colors.HexColor("#d4edcc")
PS_DARK       = colors.HexColor("#26631e")
RED_CRIT      = colors.HexColor("#c0392b")
ORANGE_HIGH   = colors.HexColor("#d35400")
YELLOW_MED    = colors.HexColor("#f39c12")
BLUE_LOW      = colors.HexColor("#2980b9")
GRAY_TEXT     = colors.HexColor("#333333")
GRAY_LIGHT    = colors.HexColor("#f5f5f5")
GRAY_BORDER   = colors.HexColor("#cccccc")

# --- Typografi ---
styles = getSampleStyleSheet()

def make_style(name, parent="Normal", **kw):
    s = ParagraphStyle(name, parent=styles[parent], **kw)
    return s

title_style = make_style("ReportTitle", "Title",
    fontSize=22, textColor=PS_GREEN, spaceAfter=4, leading=26)

subtitle_style = make_style("SubTitle", "Normal",
    fontSize=10, textColor=colors.HexColor("#555555"), spaceAfter=16)

h1_style = make_style("H1", "Heading1",
    fontSize=14, textColor=PS_GREEN, spaceBefore=18, spaceAfter=6,
    borderPadding=(0, 0, 4, 0))

h2_style = make_style("H2", "Heading2",
    fontSize=11, textColor=PS_DARK, spaceBefore=12, spaceAfter=4)

body_style = make_style("Body", "Normal",
    fontSize=9, textColor=GRAY_TEXT, leading=14, spaceAfter=4)

code_style = make_style("Code", "Normal",
    fontSize=8, textColor=colors.HexColor("#555555"),
    fontName="Courier", leading=12,
    leftIndent=12, spaceAfter=4)

bullet_style = make_style("Bullet", "Normal",
    fontSize=9, textColor=GRAY_TEXT, leading=14,
    leftIndent=16, spaceAfter=3,
    bulletIndent=6)

label_style = make_style("Label", "Normal",
    fontSize=8, textColor=colors.white, fontName="Helvetica-Bold",
    leading=11)

def p(text, style=None):
    return Paragraph(text, style or body_style)

def h1(text):
    return Paragraph(text, h1_style)

def h2(text):
    return Paragraph(text, h2_style)

def spacer(h=0.3):
    return Spacer(1, h * cm)

def hr():
    return HRFlowable(width="100%", thickness=1, color=PS_LIGHT, spaceAfter=6)

def bullet(text, indent=0):
    prefix = "&nbsp;" * indent
    return Paragraph(f"{prefix}• {text}", bullet_style)

PRIO_COLORS = {
    "KRITISK": (RED_CRIT,    colors.white),
    "HØJ":     (ORANGE_HIGH, colors.white),
    "MEDIUM":  (YELLOW_MED,  colors.white),
    "LAV":     (BLUE_LOW,    colors.white),
}

STATUS_COLORS = {
    "LØST":      (colors.HexColor("#1e7e34"), colors.white),
    "AFVENTER":  (colors.HexColor("#856404"), colors.white),
    "ACCEPTERET":(colors.HexColor("#1a6c9e"), colors.white),
    "BEHOLDER":  (colors.HexColor("#555555"), colors.white),
}

STATUS_LABELS = {
    "LØST":      "LØST",
    "AFVENTER":  "AFVENTER",
    "ACCEPTERET":"ACCEPTERET",
    "BEHOLDER":  "BEHOLDER",
}

def issue_block(num, title, prio, problem_text, solution_text, code_ref=None):
    """Returnerer en KeepTogether-blok for ét issue."""
    prio_bg, prio_fg = PRIO_COLORS.get(prio, (GRAY_BORDER, GRAY_TEXT))
    status, user_comment = ISSUE_STATUS.get(num, ("AFVENTER", ""))
    status_bg, status_fg = STATUS_COLORS.get(status, (GRAY_BORDER, GRAY_TEXT))

    # Overskrift-tabel: nummer + titel + prioritetsbadge + statusbadge
    prio_badge = Paragraph(prio, make_style(f"Badge_{num}", "Normal",
        fontSize=7.5, textColor=prio_fg, fontName="Helvetica-Bold", leading=10))
    status_badge = Paragraph(STATUS_LABELS[status], make_style(f"SBadge_{num}", "Normal",
        fontSize=7.5, textColor=status_fg, fontName="Helvetica-Bold", leading=10))

    num_para = Paragraph(f"<b>#{num}</b>", make_style(f"Num_{num}", "Normal",
        fontSize=10, textColor=colors.white, fontName="Helvetica-Bold", leading=12))

    title_para = Paragraph(f"<b>{title}</b>", make_style(f"IssueTitle_{num}", "Normal",
        fontSize=10, textColor=GRAY_TEXT, fontName="Helvetica-Bold", leading=13))

    header_table = Table(
        [[num_para, title_para, prio_badge, status_badge]],
        colWidths=[1.0*cm, 10.5*cm, 2.0*cm, 2.0*cm],
        rowHeights=[0.65*cm],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), PS_GREEN),
        ("BACKGROUND", (1, 0), (1, 0), GRAY_LIGHT),
        ("BACKGROUND", (2, 0), (2, 0), prio_bg),
        ("BACKGROUND", (3, 0), (3, 0), status_bg),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",      (0, 0), (0, 0), "CENTER"),
        ("ALIGN",      (2, 0), (2, 0), "CENTER"),
        ("ALIGN",      (3, 0), (3, 0), "CENTER"),
        ("LEFTPADDING",  (1, 0), (1, 0), 8),
        ("RIGHTPADDING", (1, 0), (1, 0), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, GRAY_BORDER),
    ]))

    items = [header_table]

    # Kode-reference
    if code_ref:
        items.append(Paragraph(
            f'<font color="#888888" size="7.5"><i>{code_ref}</i></font>',
            make_style(f"CodeRef_{num}", "Normal", fontSize=7.5,
                       textColor=colors.HexColor("#888888"), leading=10,
                       leftIndent=4, spaceAfter=2)))

    # Problem / Løsning / Brugerkommentar
    pbox_data = [
        [Paragraph("<b>Problem</b>", make_style(f"PL_{num}", "Normal",
                    fontSize=8, textColor=PS_DARK, fontName="Helvetica-Bold")),
         Paragraph(problem_text, body_style)],
        [Paragraph("<b>Løsning</b>", make_style(f"LL_{num}", "Normal",
                    fontSize=8, textColor=PS_GREEN, fontName="Helvetica-Bold")),
         Paragraph(solution_text, body_style)],
        [Paragraph("<b>Beslutning</b>", make_style(f"UL_{num}", "Normal",
                    fontSize=8, textColor=colors.HexColor("#555555"), fontName="Helvetica-Bold")),
         Paragraph(user_comment, make_style(f"UC_{num}", "Normal",
                    fontSize=9, textColor=GRAY_TEXT, leading=14, spaceAfter=4,
                    fontName="Helvetica-Oblique"))],
    ]
    pbox = Table(pbox_data, colWidths=[1.8*cm, 13.7*cm])
    pbox.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("BACKGROUND",  (0, 0), (0, -1), colors.HexColor("#f9f9f9")),
        ("BACKGROUND",  (1, 2), (1, 2), colors.HexColor("#f0f7ee")),
        ("LINEABOVE",   (0, 1), (-1, 1), 0.3, GRAY_BORDER),
        ("LINEABOVE",   (0, 2), (-1, 2), 0.3, GRAY_BORDER),
        ("BOX",         (0, 0), (-1, -1), 0.5, GRAY_BORDER),
    ]))
    items.append(pbox)
    items.append(spacer(0.25))

    return KeepTogether(items)


# ============================================================
# INDHOLD
# ============================================================
def build_story():
    story = []

    # --- Forside-header ---
    story.append(spacer(0.5))
    story.append(Paragraph("PS Lønsystem", title_style))
    story.append(Paragraph("Systemaudit-rapport", make_style("SubH", "Normal",
        fontSize=16, textColor=PS_ACCENT, spaceAfter=6, fontName="Helvetica-Bold")))
    story.append(Paragraph(
        "Dato: 24-06-2026 &nbsp;|&nbsp; Udarbejdet af: Claude Code &nbsp;|&nbsp; "
        "Scope: Fuld kodegennemgang (alle .py, app.js, style.css, templates, CODEREF.md)",
        subtitle_style))
    story.append(hr())
    story.append(spacer(0.2))

    # --- Styrker ---
    story.append(h1("Styrker"))
    styrker = [
        ("Sikkerhedshærdning er gennemgribende",
         "CSP-headers, XSS-escaping via h(), path-traversal-tjek, SMTP header-sanitering, bcrypt-hashing. "
         "Tydeligt at v10 var en seriøs indsats."),
        ("Audit trail er konsekvent",
         "log_action() kaldes ved alle muterende operationer."),
        ("DB som single source of truth",
         "Stamdata i MasterPayType, MasterAgreementType etc. Fallback til Excel er der stadig, men DB vinder."),
        ("Overtime-algoritmen er korrekt",
         "_subtract_pauses() + _work_segments() + tidsvindue-klassifikation er veldesignet og præcis."),
        ("Split-logikken fordeler pauser korrekt",
         "Klipning ved splitpunkt er implementeret rigtigt."),
        ("Brand-konsistens",
         "Farver (#317423, #78b21a, #d4edcc) er konsekvente på tværs af PDF, Excel og UI."),
    ]
    for titel, tekst in styrker:
        story.append(p(f"<b>{titel}</b> – {tekst}"))
    story.append(spacer(0.3))

    # --- Oversigtstabel ---
    story.append(h1("Oversigt"))
    tabel_data = [
        [p("<b>Prioritet</b>"), p("<b>Antal</b>"), p("<b>Berørte filer</b>")],
        [Paragraph("KRITISK", make_style("tc", "Normal", fontSize=9,
                    textColor=colors.white, fontName="Helvetica-Bold")),
         p("3"), p("session.py, payroll_router.py, pay_rates.py")],
        [Paragraph("HØJ", make_style("th", "Normal", fontSize=9,
                    textColor=colors.white, fontName="Helvetica-Bold")),
         p("5"), p("activities.py, payroll_router.py, schemas.py")],
        [Paragraph("MEDIUM", make_style("tm", "Normal", fontSize=9,
                    textColor=colors.white, fontName="Helvetica-Bold")),
         p("8"), p("payroll_router.py, models.py, overtime.py, app.js")],
        [Paragraph("LAV", make_style("tl", "Normal", fontSize=9,
                    textColor=colors.white, fontName="Helvetica-Bold")),
         p("7"), p("session.py, email_sender.py, pay_rates.py, diverse")],
    ]
    tabel = Table(tabel_data, colWidths=[2.5*cm, 1.8*cm, 11.2*cm])
    tabel.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), PS_GREEN),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND",   (0, 1), (0, 1), RED_CRIT),
        ("BACKGROUND",   (0, 2), (0, 2), ORANGE_HIGH),
        ("BACKGROUND",   (0, 3), (0, 3), YELLOW_MED),
        ("BACKGROUND",   (0, 4), (0, 4), BLUE_LOW),
        ("ROWBACKGROUNDS", (1, 1), (-1, -1), [colors.white, GRAY_LIGHT]),
        ("ALIGN",        (0, 0), (0, -1), "CENTER"),
        ("ALIGN",        (1, 0), (1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",         (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    story.append(tabel)
    story.append(spacer(0.4))

    # --- Statusoversigt ---
    story.append(h1("Status efter gennemgang"))
    story.append(p(
        "Alle 23 punkter er gennemgået med brugeren. Nedenstående tabel viser beslutningen for hvert punkt."
    ))
    story.append(spacer(0.2))

    status_counts = {}
    for num, (st, _) in ISSUE_STATUS.items():
        status_counts[st] = status_counts.get(st, 0) + 1

    status_tabel_data = [
        [Paragraph("<b>Status</b>", make_style("shd", "Normal", fontSize=9,
                    textColor=colors.white, fontName="Helvetica-Bold")),
         Paragraph("<b>Antal</b>", make_style("shd2", "Normal", fontSize=9,
                    textColor=colors.white, fontName="Helvetica-Bold")),
         Paragraph("<b>Betydning</b>", make_style("shd3", "Normal", fontSize=9,
                    textColor=colors.white, fontName="Helvetica-Bold"))],
    ]
    for st, label, meaning in [
        ("LØST",       "LØST",       "Rettelse implementeret i koden"),
        ("AFVENTER",   "AFVENTER",   "Udskydes – skal løses på et senere tidspunkt"),
        ("ACCEPTERET", "ACCEPTERET", "Adfærden er korrekt og accepteres som den er"),
        ("BEHOLDER",   "BEHOLDER",   "Bevidst valg om ikke at ændre"),
    ]:
        bg, fg = STATUS_COLORS[st]
        status_tabel_data.append([
            Paragraph(label, make_style(f"stl_{st}", "Normal",
                        fontSize=8.5, textColor=fg, fontName="Helvetica-Bold")),
            Paragraph(str(status_counts.get(st, 0)), make_style(f"stc_{st}", "Normal",
                        fontSize=9, textColor=GRAY_TEXT)),
            Paragraph(meaning, make_style(f"stm_{st}", "Normal",
                        fontSize=9, textColor=GRAY_TEXT)),
        ])

    status_tabel = Table(status_tabel_data, colWidths=[2.8*cm, 1.5*cm, 11.2*cm])
    status_tabel.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), PS_DARK),
        ("BACKGROUND",   (0, 1), (0, 1), STATUS_COLORS["LØST"][0]),
        ("BACKGROUND",   (0, 2), (0, 2), STATUS_COLORS["AFVENTER"][0]),
        ("BACKGROUND",   (0, 3), (0, 3), STATUS_COLORS["ACCEPTERET"][0]),
        ("BACKGROUND",   (0, 4), (0, 4), STATUS_COLORS["BEHOLDER"][0]),
        ("ALIGN",        (1, 0), (1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",         (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(status_tabel)
    story.append(spacer(0.5))

    # --- Kritiske problemer ---
    story.append(h1("🔴  Kritiske problemer"))
    story.append(hr())

    story.append(issue_block(
        1,
        "Standardadgangskode er \"admin\", ikke \"admin2026\"",
        "KRITISK",
        "session.py linje 127 sætter hash_password(\"admin\"). CODEREF.md dokumenterer fejlagtigt "
        "\"ADM / admin2026\". Initialer er \"admin\", ikke \"ADM\". En simpel og gætbar "
        "standardkode – ingen advarsel ved første login om at skifte den.",
        "Kræv adgangskodeskift ved første login (flag must_change_password i AppUser), eller "
        "generer en tilfældig adgangskode ved seeding. Ret CODEREF.md straks.",
        "app/database/session.py:297",
    ))

    story.append(issue_block(
        2,
        "barn_1sygedag eksporteres med SYGDOM-kode, ikke BARN_1SYGEDAG",
        "KRITISK",
        "I payroll_router.py:266 lander barn_1sygedag (med tilstrækkelig anciennitet) i "
        "totals[\"sygdom\"]. Danløn-CSV sender disse timer under SYGDOM-koden. "
        "BARN_1SYGEDAG-kodelinjen bruges kun for barn_1sygedag_u_8uger-timer. "
        "Hvis Danløn kræver distinkte koder, er CSV'en forkert.",
        "Separat bucket for barn_1sygedag i _calculate_employee() og eksporter med "
        "BARN_1SYGEDAG-koden. Verificer med lønafdelingen hvilken kode der gælder.",
        "app/routers/payroll_router.py:266",
    ))

    story.append(issue_block(
        3,
        "Alle Danløn-koder undtagen SH er \"1\" (placeholder)",
        "KRITISK",
        "pay_rates.py – DANLOEN_CODE_NORMAL, OT_BEFORE, OT_13, OT_EXTRA, SALT, "
        "AFSPADSERING, SYGDOM, FERIEFRI, BARSEL, SKOLE_KURSUS og OVERNATNING er alle \"1\". "
        "Disse seedes ind i MasterPayType ved første start. "
        "Da DB kun seedes én gang, har eksisterende databaser sandsynligvis stadig kode "
        "\"1\" for alle typer.",
        "Afklar de rigtige koder med Danløn/lønafdelingen og opdater dem i Stamdata-UI'et. "
        "Overvej en migrering der sætter koder til \"UKENDT\" som synlig sentinel.",
        "app/calculators/pay_rates.py:12-21",
    ))

    story.append(spacer(0.3))

    # --- Høje problemer ---
    story.append(h1("🟠  Høje problemer"))
    story.append(hr())

    story.append(issue_block(
        4,
        "approved_by-kolonnen bruges til deaktiveringer",
        "HØJ",
        "deactivate_activity() sætter a.approved_by = current_user.initials. Feltet hedder "
        "approved_by men gemmer nu initialer for en deaktivering. I audit log og UI vises "
        "\"Godkendt af: SKJ\" selv om handlingen var en deaktivering.",
        "Tilføj en separat deactivated_by-kolonne i Activity-modellen. Bevar approved_by "
        "kun for godkendelser. Opdater _to_response() og frontend.",
        "app/routers/activities.py:406",
    ))

    story.append(issue_block(
        5,
        "body.approved_by og body.deactivated_by ignoreres stille",
        "HØJ",
        "ActivityApprove.approved_by (str, required) og ActivityDeactivate.deactivated_by "
        "(str, required) valideres af Pydantic men bruges aldrig i endpointene. "
        "UI'ets \"Initialer\"-felt er en placebo – session-brugerens initialer bruges altid.",
        "Fjern approved_by og deactivated_by fra schemerne, eller dokumenter eksplicit "
        "at session-brugeren altid bruges. UI-feltet bør enten fjernes eller vise "
        "session-brugerens initialer i read-only.",
        "app/routers/activities.py:387",
    ))

    story.append(issue_block(
        6,
        "Del 2 af et split mister trip_number og andre felter",
        "HØJ",
        "split_activity(): part1 får trip_number=a.trip_number, men part2 mangler det. "
        "Begge dele mangler: loading_minutes, unloading_minutes, salt_supplement, "
        "vehicle_registration, vehicle_number, km_start, km_end. "
        "Part1 mangler desuden availability_time_pct og pct-felterne.",
        "Kopier alle felter fra originalen til begge dele via en "
        "_copy_activity_fields(source, target) hjælpefunktion.",
        "app/routers/activities.py:468-499",
    ))

    story.append(issue_block(
        7,
        "deactivate_activity sletter eksisterende kommentar ved manglende input",
        "HØJ",
        "a.comment = body.comment – body.comment er Optional[str], så hvis ingen "
        "kommentar sendes, sættes a.comment = None og eksisterende kommentarer slettes. "
        "approve_activity bruger korrekt if body.comment: a.comment = body.comment.",
        "Ret til: if body.comment is not None: a.comment = body.comment i "
        "deactivate_activity, svarende til approve_activity.",
        "app/routers/activities.py:408",
    ))

    story.append(issue_block(
        8,
        "_safe_save_dir blokerer kun app-mappen, ikke systemstier",
        "HØJ",
        "Funktionen tjekker at stien IKKE er inde i app-mappen – men C:\\Windows\\System32, "
        "C:\\Program Files og andre kritiske mapper er fuldt tilgængelige. "
        "En bruger (eller angriber med session) kan bede systemet skrive filer til "
        "systemkritiske steder.",
        "Hvidblist eksplicitte tilladte rødder (fx kun brugerens desktop/dokumenter/ "
        "netdrev) i stedet for at sortliste app-mappen.",
        "app/routers/payroll_router.py:60-71",
    ))

    story.append(spacer(0.3))

    # --- Medium problemer ---
    story.append(h1("🟡  Medium problemer"))
    story.append(hr())

    medium_issues = [
        (9,  "CODEREF.md er forældet på tre punkter",
         "Siger app.js er ~1700 linjer (er 3117). Dokumenterer admin-login som "
         "\"ADM / admin2026\" (er \"admin / admin\"). Mangler day_type.py, holidays.py "
         "og timeseddel_router.py i fillisten.",
         "Opdater CODEREF.md. Overvej at automatisere linjetælling i en pre-commit hook.",
         "CODEREF.md"),
        (10, "Pauser arver dato fra aktivitetens startdato",
         "Pauser oprettes kun med HH:MM – datoen arves fra aktivitetens startdato. "
         "Hvis et skift krydser midnat (fx 22:00-06:00), får en pause kl. 02:00 den "
         "næste dag forkert dato og dermed forkert tidsvindue i overtidsberegningen.",
         "Ved gemning af pause-ISO-timestamps: brug startdato for pauser i første halvdel, "
         "startdato+1 for pauser i anden halvdel. Alternativt: vis datovælger i modal-pause "
         "hvis aktiviteten krydser midnat.",
         "app/static/js/app.js (modal-pause logik)"),
        (11, "localStorage[\"anciennitet_dismissed\"] er browserbundet",
         "Afviste anciennitetsvarsler gemmes i browserens localStorage. Skift af computer, "
         "browser eller rydning af cache viser alle varsler igen.",
         "Gem dismissed_at timestamp server-side på medarbejderen (ny kolonne "
         "anciennitet_dismissed_at) eller i en separat tabel.",
         "app/static/js/app.js:1112"),
        (12, "Prøvekørsel-Excel er duplikeret kode (DRY-violation)",
         "proevekoersel() og proevekoersel_gem() er næsten identiske – ca. 80 linjer "
         "Excel-genereringslogik er kopieret.",
         "Udtræk Excel-genereringen til en fælles "
         "_build_proevekoersel_workbook(employees, period) hjælpefunktion.",
         "app/routers/payroll_router.py:427-626"),
        (13, "ActivityType-enum er delvist forældet",
         "ActivityType-enum indeholder kun 5 typer. Alle nyere typer (sygdom, barsel, "
         "overnatning etc.) eksisterer kun som string-literals spredt i koden. "
         "Kommentarer siger enumen \"bevares for bagudkompatibilitet\".",
         "Enten: udvid enumen til alle kendte typer, eller fjern den helt og erstat "
         "sammenligninger med string-literals konsekvent.",
         "app/database/models.py:32-38"),
        (14, "graviditetsbetinget_sygdom og barn_1sygedag grupperes under sygdom",
         "payroll_router.py:266 – graviditetsbetinget_sygdom lander i totals[\"sygdom\"]. "
         "Uklart om graviditetsbetinget sygdom har samme Danløn-kode som almindelig sygdom. "
         "Overenskomsten behandler dem typisk forskelligt.",
         "Verificer med lønafdelingen om koden er den samme. Hvis forskellig: separat bucket.",
         "app/routers/payroll_router.py:266"),
        (15, "--reload flag i produktionsserver",
         "Ifølge v11-ændringer er --reload tilføjet til serveropstart. Dette er en "
         "udviklingsindstilling der genstarter serveren ved filændringer og er "
         "10-20x langsommere end produktionskonfiguration.",
         "Fjern --reload fra produktionsopstart. Brug evt. --workers 2 i stedet.",
         "CODEREF.md (server-opstart)"),
        (16, "split_activity deaktiverer original uden at sætte approved_by",
         "a.status = ActivityStatus.deactivated sættes, men a.approved_by og "
         "a.approved_at sættes ikke. En via-split deaktiveret aktivitet mangler "
         "dermed \"hvem\" i audit-sporet.",
         "Tilføj a.approved_by = current_user.initials og "
         "a.approved_at = datetime.utcnow() i split-deaktiveringen.",
         "app/routers/activities.py:447"),
    ]
    for num, title, prob, sol, ref in medium_issues:
        story.append(issue_block(num, title, "MEDIUM", prob, sol, ref))

    story.append(spacer(0.3))

    # --- Lave problemer ---
    story.append(h1("🔵  Lave problemer"))
    story.append(hr())

    lave_issues = [
        (17, "seed_anders.py og seed_testdata.py ligger i app/",
         "Testdata-scripts hører ikke til i produktionskoden og kan køres ved et uheld.",
         "Flyt til tests/ eller scripts/ mappe, eller slet dem.",
         "app/seed_anders.py, app/seed_testdata.py"),
        (18, "CVR-nummer er defineret tre steder",
         "pay_rates.CVR_NUMBER, MasterCvrNumber tabel og Employee.cvr_number. "
         "Fallback-hierarkiet er OK, men pay_rates.CVR_NUMBER bruges stadig som "
         "runtime-fallback i kode der burde bruge DB.",
         "pay_rates.CVR_NUMBER bør kun bruges ved seeding. Fjern den som runtime-fallback "
         "og rejs en fejl hvis DB ikke har et default-CVR.",
         "app/calculators/pay_rates.py:8"),
        (19, "approve kræver kommentar under 4 timer, deaktiver gør ikke",
         "activities.py:381-385 kræver begrundelse ved godkendelse af under-4-timers "
         "aktiviteter. Deaktivering af samme aktiviteter kræver ingen begrundelse.",
         "Afklar med bruger om det samme krav gælder deaktivering. Implementer symmetrisk.",
         "app/routers/activities.py:381"),
        (20, "OT_EXTRA_KEY stavefejlrisiko ved Excel-header-ændring",
         "Kommentaren \"# NB: med 't' (ikke 'g')\" advarer om at strengen er "
         "\"Ovrigt\" ikke \"Ovrig\". Hvis Excel-filen ændres en stavelse, "
         "loader overtidssatsen ikke.",
         "Lav et opstartscheck der verificerer at OT_BEFORE_KEY, OT_13_KEY og "
         "OT_EXTRA_KEY faktisk findes i load_overtime_rates(). Rejs fejl ved serverstart.",
         "app/calculators/overtime.py"),
        (21, "email_sender.py fejler utydeligt uden SMTP-konfiguration",
         "Hvis SMTP_HOST, SMTP_USER eller SMTP_PASSWORD ikke er sat i .env, kaster "
         "funktionen en uspecifik exception og brugeren ser en generisk 500-fejl.",
         "Tjek ved funktionsstart om de nødvendige env-vars er sat, og returner en klar "
         "fejlbesked: \"E-mail er ikke konfigureret – kontakt administrator\".",
         "app/utils/email_sender.py"),
        (22, "PARAGRAF_56 og BARN_1SYGEDAG deler DANLOEN_CODE_SYGDOM ved seeding",
         "session.py:203-204 – begge koder seedes med DANLOEN_CODE_SYGDOM (= \"1\"). "
         "Når de rigtige koder oplyses, er det uklart at disse startede med sygdomskoden.",
         "Giv dem egne placeholder-konstanter i pay_rates.py fra start: "
         "DANLOEN_CODE_PARAGRAF_56 = \"1\" og DANLOEN_CODE_BARN_1SYGEDAG = \"1\".",
         "app/database/session.py:203-204"),
        (23, "Sygdom-anciennitetsgraense: < 56 vs. <= 56",
         "activities.py:234 – if employed_days < _EIGHT_WEEKS: (< 56). En medarbejder "
         "ansat praecis 56 dage (= 8 uger) faar sygdom MED loen. Graensens fortolkning "
         "er ikke dokumenteret.",
         "Afklar med loenafdelingen/overenskomst om graensen er < 56 eller <= 56 "
         "og ret kommentar/konstant derefter.",
         "app/routers/activities.py:234"),
    ]
    for num, title, prob, sol, ref in lave_issues:
        story.append(issue_block(num, title, "LAV", prob, sol, ref))

    story.append(spacer(0.5))
    story.append(hr())
    story.append(p(
        "<i>Rapporten er genereret automatisk af Claude Code den 24-06-2026. "
        "Ingen kodeændringer er foretaget – rapporten er udelukkende analyse og anbefalinger.</i>",
        make_style("Footer", "Normal", fontSize=8, textColor=colors.HexColor("#888888"),
                   alignment=TA_CENTER)
    ))

    return story


def build_pdf():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2.0*cm,
        rightMargin=2.0*cm,
        topMargin=2.0*cm,
        bottomMargin=2.0*cm,
        title="PS Lønsystem – Systemaudit-rapport 2026-06-24",
        author="Claude Code",
        subject="Systemaudit – styrker, svagheder og inkonsistenser",
    )

    story = build_story()

    def on_page(canvas, doc):
        canvas.saveState()
        # Header-linje
        canvas.setFillColor(PS_GREEN)
        canvas.rect(0, A4[1] - 0.8*cm, A4[0], 0.8*cm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(2.0*cm, A4[1] - 0.55*cm, "PS Lønsystem – Systemaudit-rapport")
        canvas.drawRightString(A4[0] - 2.0*cm, A4[1] - 0.55*cm, "24-06-2026")
        # Footer
        canvas.setFillColor(GRAY_BORDER)
        canvas.rect(0, 0, A4[0], 0.7*cm, fill=1, stroke=0)
        canvas.setFillColor(GRAY_TEXT)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawCentredString(A4[0] / 2, 0.25*cm, f"Side {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF gemt: {OUTPUT}")


if __name__ == "__main__":
    build_pdf()
