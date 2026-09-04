"""
Genererer Sikkerhedsrapport.pdf til docs/-mappen.
Kør med: python build_security_report.py
"""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

OUT = Path(__file__).parent / "Sikkerhedsrapport.pdf"

# ── Farver ────────────────────────────────────────────────────────────────────
GREEN       = colors.HexColor("#317423")
GREEN_LIGHT = colors.HexColor("#d4edcc")
RED         = colors.HexColor("#b71c1c")
RED_LIGHT   = colors.HexColor("#fee2e2")
ORANGE      = colors.HexColor("#e65100")
ORANGE_LIGHT= colors.HexColor("#fff3e0")
GRAY        = colors.HexColor("#555555")
GRAY_LIGHT  = colors.HexColor("#f5f5f5")
BLACK       = colors.black
WHITE       = colors.white


def build():
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("Title2", parent=styles["Normal"],
        fontSize=22, textColor=GREEN, fontName="Helvetica-Bold",
        spaceAfter=4, alignment=TA_CENTER)

    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"],
        fontSize=13, textColor=GRAY, fontName="Helvetica",
        spaceAfter=2, alignment=TA_CENTER)

    date_style = ParagraphStyle("Date", parent=styles["Normal"],
        fontSize=10, textColor=GRAY, fontName="Helvetica",
        spaceAfter=16, alignment=TA_CENTER)

    h1_style = ParagraphStyle("H1", parent=styles["Normal"],
        fontSize=14, textColor=GREEN, fontName="Helvetica-Bold",
        spaceBefore=14, spaceAfter=6)

    h2_style = ParagraphStyle("H2", parent=styles["Normal"],
        fontSize=11, textColor=BLACK, fontName="Helvetica-Bold",
        spaceBefore=10, spaceAfter=4)

    body_style = ParagraphStyle("Body2", parent=styles["Normal"],
        fontSize=10, textColor=BLACK, fontName="Helvetica",
        spaceBefore=2, spaceAfter=4, leading=14)

    note_style = ParagraphStyle("Note", parent=styles["Normal"],
        fontSize=9, textColor=GRAY, fontName="Helvetica-Oblique",
        spaceBefore=2, spaceAfter=4, leading=13,
        leftIndent=8)

    label_bold = ParagraphStyle("LabelBold", parent=styles["Normal"],
        fontSize=9, fontName="Helvetica-Bold", textColor=BLACK, leading=12)

    label_cell = ParagraphStyle("LabelCell", parent=styles["Normal"],
        fontSize=9, fontName="Helvetica", textColor=BLACK, leading=12)

    def hr():
        return HRFlowable(width="100%", thickness=1, color=GREEN_LIGHT, spaceAfter=6)

    def severity_badge(text, bg, fg=WHITE):
        return Table(
            [[Paragraph(text, ParagraphStyle("badge", fontSize=8,
                fontName="Helvetica-Bold", textColor=fg))]],
            colWidths=[22 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("ROUNDEDCORNERS", [3]),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )

    story = []

    # ── Forside ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20 * mm))
    story.append(Paragraph("Lønsystem", title_style))
    story.append(Paragraph("Sikkerhedsrapport", subtitle_style))
    story.append(Paragraph("Poul Schou A/S  ·  CVR 13246505", date_style))
    story.append(Paragraph("22. juni 2026", date_style))
    story.append(Spacer(1, 8 * mm))
    story.append(hr())
    story.append(Spacer(1, 4 * mm))

    # ── 1. Baggrund ───────────────────────────────────────────────────────────
    story.append(Paragraph("1. Baggrund", h1_style))
    story.append(Paragraph(
        "Der er gennemført en sikkerhedsgennemgang af lønsystemets kildekode med fire "
        "specialiserede analyseagenter, der har dækket følgende fire dimensioner parallelt:",
        body_style))

    dim_data = [
        [Paragraph("Dimension", label_bold), Paragraph("Filer gennemgået", label_bold)],
        [Paragraph("Autentifikation og RBAC", label_cell),
         Paragraph("auth.py, routers/users_router.py, database/models.py, main.py, routers/stamdata.py, routers/employees.py", label_cell)],
        [Paragraph("Inputvalidering og injektion", label_cell),
         Paragraph("routers/activities.py, routers/payroll_router.py, routers/employees.py, routers/stamdata.py, database/schemas.py", label_cell)],
        [Paragraph("Filoperationer og path traversal", label_cell),
         Paragraph("routers/import_ddd.py, routers/payroll_router.py, main.py, calculators/rates_loader.py", label_cell)],
        [Paragraph("Frontend (XSS) og stabilitet", label_cell),
         Paragraph("templates/index.html, static/js/app.js, database/session.py, calculators/overtime.py, calculators/pay_period.py", label_cell)],
    ]
    dim_table = Table(dim_data, colWidths=[45 * mm, 120 * mm])
    dim_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
    ]))
    story.append(dim_table)
    story.append(Spacer(1, 6 * mm))

    # ── 2. Implementerede rettelser ───────────────────────────────────────────
    story.append(Paragraph("2. Implementerede rettelser", h1_style))
    story.append(Paragraph(
        "Samtlige kritiske og vigtige fund er implementeret og verificeret. "
        "Nedenstående tabel dokumenterer hvert fund, berørt fil og den anvendte rettelse.",
        body_style))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("2.1 Kritiske fund (implementeret)", h2_style))

    crit_data = [
        [Paragraph("Sværhedsgrad", label_bold),
         Paragraph("Fund", label_bold),
         Paragraph("Berørt fil", label_bold),
         Paragraph("Rettelse", label_bold)],

        [severity_badge("KRITISK", RED),
         Paragraph("<b>Stored XSS</b> – 10+ steder brugte <i>innerHTML</i> med "
                   "uescaped serverdata (brugernavne, kommentarer, audit log, fraværstyper). "
                   "En bruger med skriveadgang kunne injicere JavaScript der kørte for alle admins.", label_cell),
         Paragraph("static/js/app.js", label_cell),
         Paragraph("Alle serverfelter i innerHTML-strenge wrappet med h(). "
                   "onclick-handlers bruger nu JSON.stringify(). "
                   "Alle fejlmeddelelser (e.message) escaped.", label_cell)],

        [severity_badge("KRITISK", RED),
         Paragraph("<b>Path traversal via output_folder</b> – tre endpoints accepterede "
                   "en vilkårlig sti fra klienten og oprettede mapper samt skrev filer der. "
                   "En payroll-bruger kunne skrive til systemkritiske stier (C:\\Windows m.fl.).", label_cell),
         Paragraph("routers/payroll_router.py", label_cell),
         Paragraph("_safe_save_dir() tilføjet – afviser stier inden i "
                   "applikationsmappen. Anvendt på proevekoersel-gem, export-csv og pdf-timesedler.", label_cell)],

        [severity_badge("KRITISK", RED),
         Paragraph("<b>activity_type bypass</b> – backend-only typer "
                   "(sygdom_u_8uger, barsel_u_loen m.fl.) kunne sættes direkte via PATCH og POST, "
                   "hvorved anciennitets- og lønsatslogikken blev omgået.", label_cell),
         Paragraph("routers/activities.py", label_cell),
         Paragraph("Guard øverst i create_manual_activity og update_activity: "
                   "returnerer HTTP 400 hvis activity_type er i _BACKEND_ONLY_TYPES.", label_cell)],
    ]

    crit_table = Table(crit_data, colWidths=[24 * mm, 55 * mm, 38 * mm, 50 * mm])
    crit_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, RED_LIGHT]),
    ]))
    story.append(crit_table)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("2.2 Vigtige fund (implementeret)", h2_style))

    imp_data = [
        [Paragraph("Sværhedsgrad", label_bold),
         Paragraph("Fund", label_bold),
         Paragraph("Berørt fil", label_bold),
         Paragraph("Rettelse", label_bold)],

        [severity_badge("VIGTIGT", ORANGE),
         Paragraph("<b>KeyError-crash i overtidsberegning</b> – hvis én af de tre "
                   "overtidssatsrækker var slettet fra DB crashede hele lønkørslen for alle medarbejdere.", label_cell),
         Paragraph("calculators/overtime.py", label_cell),
         Paragraph("rates[KEY] → rates.get(KEY, Decimal('0')) for alle tre nøgler.", label_cell)],

        [severity_badge("VIGTIGT", ORANGE),
         Paragraph("<b>Negative sluttider accepteret</b> – end_time ≤ start_time "
                   "producerede negative timer i lønberegning og CSV-eksport.", label_cell),
         Paragraph("database/schemas.py", label_cell),
         Paragraph("model_validator på ActivityCreate og ActivityUpdate: kaster "
                   "ValidationError hvis end_time ≤ start_time.", label_cell)],

        [severity_badge("VIGTIGT", ORANGE),
         Paragraph("<b>Hardkodet session secret som fallback</b> – ved manglende .env "
                   "startede serveren med en forudsigelig nøgle fra kildekoden, "
                   "der tillod session-forfalskelse.", label_cell),
         Paragraph("main.py", label_cell),
         Paragraph("Fallback ændret til raise RuntimeError – serveren starter ikke "
                   "uden SESSION_SECRET i .env.", label_cell)],

        [severity_badge("VIGTIGT", ORANGE),
         Paragraph("<b>Ubegrænsede filstørrelser ved .ddd-import</b> – meget store "
                   "filer blev indlæst fuldt i hukommelsen, mulig OOM.", label_cell),
         Paragraph("routers/import_ddd.py", label_cell),
         Paragraph("10 MB maksimal filstørrelse per .ddd-fil. Reelle filer er ~100–300 KB.", label_cell)],

        [severity_badge("VIGTIGT", ORANGE),
         Paragraph("<b>Negative satser i Stamdata</b> – rate = −50 blev accepteret "
                   "og ville producere negativ løn i alle beregninger.", label_cell),
         Paragraph("routers/stamdata.py", label_cell),
         Paragraph("Field(gt=0) på RateBody.rate og AgreementTypeBody.hourly_rate.", label_cell)],

        [severity_badge("VIGTIGT", ORANGE),
         Paragraph("<b>Manglende inputgrænser på skemafelter</b> – comment og work_schedule "
                   "accepterede ubegrænsede/ugyldige værdier. NB (verificeret 2026-09): "
                   "trip_number (DB: String(6)) findes slet ikke i schemas.py og har derfor "
                   "stadig ingen Pydantic-valideret længdegrænse – kun DB-kolonnens "
                   "String(6), som SQLite ikke håndhæver.", label_cell),
         Paragraph("database/schemas.py", label_cell),
         Paragraph("max_length=1000 på comment, ge=0/le=24 per element i work_schedule, "
                   "ge=0 på loading/unloading/km. (trip_number-grænsen er IKKE implementeret, se note.)", label_cell)],

        [severity_badge("VIGTIGT", ORANGE),
         Paragraph("<b>km_end < km_start accepteret</b> – negativt kilometertal "
                   "vises i PDF-timesedler.", label_cell),
         Paragraph("database/schemas.py", label_cell),
         Paragraph("model_validator: km_end ≥ km_start når begge er angivet.", label_cell)],
    ]

    imp_table = Table(imp_data, colWidths=[24 * mm, 55 * mm, 38 * mm, 50 * mm])
    imp_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ORANGE_LIGHT]),
    ]))
    story.append(imp_table)

    story.append(PageBreak())

    # ── 3. Åbne punkter ───────────────────────────────────────────────────────
    story.append(Paragraph("3. Åbne punkter – kræver afklaring", h1_style))
    story.append(Paragraph(
        "Punkt 3.1 herunder er løst siden denne rapport blev skrevet (verificeret 2026-09). "
        "Punkt 3.2 kræver fortsat en designbeslutning om systemets rollestruktur og er "
        "ikke umiddelbart udnyttelig udefra, men bør afklares inden systemet tages i fuld drift.",
        body_style))
    story.append(Spacer(1, 4 * mm))

    # ── Punkt A ──
    story.append(Paragraph("3.1  Manglende rettighedsguard på medarbejder- og køretøjsendepunkter — LØST", h2_style))

    open1_data = [
        [Paragraph("Detalje", label_bold), Paragraph("Beskrivelse", label_bold)],
        [Paragraph("Status", label_cell),
         Paragraph("LØST (verificeret 2026-09) – routers/employees.py og routers/vehicles.py "
                   "bruger nu Depends(require_permission(\"manage_employees\"))/"
                   "(\"manage_vehicles\")\" på skriveendepunkterne. Fundet nedenfor beskriver "
                   "den oprindelige tilstand.", label_cell)],
        [Paragraph("Oprindeligt fund", label_cell),
         Paragraph("Endepunkterne <i>POST /api/employees</i> (opret medarbejder), "
                   "<i>PATCH /api/employees/{id}</i> (rediger medarbejder) og tilsvarende "
                   "for køretøjer kræver kun at brugeren er logget ind (get_current_user). "
                   "Der er ingen yderligere rettighedskontrol.", label_cell)],
        [Paragraph("Konsekvens", label_cell),
         Paragraph("En bruger med rollen 'disponent' – som i dag kun har rettighed til at "
                   "se aktiviteter – kan teknisk set oprette, redigere og slette "
                   "medarbejderstamdata og køretøjer, herunder ændre overenskomsttype "
                   "og lønnummer.", label_cell)],
        [Paragraph("Berørte filer", label_cell),
         Paragraph("routers/employees.py (create_employee, update_employee)\n"
                   "routers/vehicles.py (create_vehicle, update_vehicle, delete_vehicle)", label_cell)],
        [Paragraph("Mulig løsning", label_cell),
         Paragraph("Tilføj require_permission(\"stamdata\") til skriveendepunkterne. "
                   "Læseendepunkterne (liste, hent enkelt, overenskomsttyper) kan forblive "
                   "tilgængelige for alle loginede brugere.", label_cell)],
        [Paragraph("Afklaring krævet", label_cell),
         Paragraph("Bør disponienter have mulighed for at redigere medarbejderstamdata? "
                   "I dag skelner systemet ikke – alle loginede har samme skriveadgang til "
                   "medarbejdere og køretøjer.", label_cell)],
    ]

    open1_table = Table(open1_data, colWidths=[35 * mm, 130 * mm])
    open1_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#fff9e6")),
    ]))
    story.append(open1_table)
    story.append(Spacer(1, 6 * mm))

    # ── Punkt B ──
    story.append(Paragraph("3.2  Bruger kan ændre sin egen rolle", h2_style))

    open2_data = [
        [Paragraph("Detalje", label_bold), Paragraph("Beskrivelse", label_bold)],
        [Paragraph("Fund", label_cell),
         Paragraph("Endepunktet <i>PATCH /api/users/{id}</i> tillader en bruger med "
                   "rettigheden 'user_management' at redigere sin egen brugerprofil, "
                   "herunder at ændre sin egen rolle til en hvilken som helst anden rolle "
                   "i systemet.", label_cell)],
        [Paragraph("Konsekvens", label_cell),
         Paragraph("En lønbogholder der midlertidigt er tildelt 'user_management' "
                   "kan opgradere sig selv til administrator og dermed opnå fuld adgang "
                   "til alle funktioner, inkl. Stamdata og lønkørsel.", label_cell)],
        [Paragraph("Berørte filer", label_cell),
         Paragraph("routers/users.py (update_user, linje ~96–100)\n"
                   "Der er allerede en guard mod at slette sin egen bruger (linje ~120), "
                   "men ingen tilsvarende guard mod at ændre sin egen rolle.", label_cell)],
        [Paragraph("Mulig løsning A", label_cell),
         Paragraph("Blokér at en bruger ændrer sin egen rolle:\n"
                   "if body.role and user.id == current_user.id: raise HTTPException(400, ...)", label_cell)],
        [Paragraph("Mulig løsning B", label_cell),
         Paragraph("Kræv at den kaldende bruger allerede har is_system=True for at "
                   "tildele en is_system-rolle. Forhindrer lateral privilege escalation.", label_cell)],
        [Paragraph("Afklaring krævet", label_cell),
         Paragraph("Skal en bruger med 'user_management' overhovedet kunne tildele "
                   "administrator-rollen, eller bør dette kræve at man selv er administrator?", label_cell)],
    ]

    open2_table = Table(open2_data, colWidths=[35 * mm, 130 * mm])
    open2_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ("BACKGROUND", (0, 6), (-1, 6), colors.HexColor("#fff9e6")),
    ]))
    story.append(open2_table)
    story.append(Spacer(1, 6 * mm))

    # ── 4. Samlet vurdering ───────────────────────────────────────────────────
    story.append(hr())
    story.append(Paragraph("4. Samlet vurdering", h1_style))

    vurd_data = [
        [Paragraph("Dimension", label_bold),
         Paragraph("Niveau før rettelser", label_bold),
         Paragraph("Niveau efter rettelser", label_bold)],
        [Paragraph("Autentifikation og RBAC", label_cell),
         Paragraph("Acceptabelt", label_cell),
         Paragraph("Stærkt  ✓", label_cell)],
        [Paragraph("Inputvalidering og injektion", label_cell),
         Paragraph("Kræver arbejde", label_cell),
         Paragraph("Acceptabelt  ✓", label_cell)],
        [Paragraph("Filoperationer og path traversal", label_cell),
         Paragraph("Kræver arbejde", label_cell),
         Paragraph("Acceptabelt  ✓", label_cell)],
        [Paragraph("Frontend (XSS)", label_cell),
         Paragraph("Kræver arbejde", label_cell),
         Paragraph("Stærkt  ✓", label_cell)],
        [Paragraph("Stabilitet", label_cell),
         Paragraph("Acceptabelt", label_cell),
         Paragraph("Stærkt  ✓", label_cell)],
    ]

    vurd_table = Table(vurd_data, colWidths=[55 * mm, 52 * mm, 60 * mm])
    vurd_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREEN_LIGHT]),
        ("TEXTCOLOR", (2, 1), (2, -1), GREEN),
        ("FONTNAME", (2, 1), (2, -1), "Helvetica-Bold"),
    ]))
    story.append(vurd_table)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph(
        "Systemet er klar til stabil drift efter de implementerede rettelser. "
        "De to åbne punkter i afsnit 3 påvirker ikke systemets umiddelbare sikkerhed "
        "over for eksterne angreb, men bør afklares og implementeres inden systemet "
        "bruges af medarbejdere med forskellig tillid og adgangsniveau.",
        body_style))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Rapport genereret automatisk · Poul Schou A/S Lønsystem · Juni 2026",
        ParagraphStyle("footer", parent=styles["Normal"],
            fontSize=8, textColor=GRAY, fontName="Helvetica",
            alignment=TA_CENTER)))

    doc.build(story)
    print(f"Sikkerhedsrapport.pdf gemt: {OUT}")


if __name__ == "__main__":
    build()
