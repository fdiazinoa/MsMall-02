#!/usr/bin/env python3
"""Generate the executive brochure for the MsMall Big Data module."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "msmall_big_data_brochure.pdf"
LOGO = ROOT / "public" / "msmall-icon-512.png"

W, H = A4
NAVY = colors.HexColor("#102A5E")
NAVY_DARK = colors.HexColor("#081A3D")
INDIGO = colors.HexColor("#4256D0")
TEAL = colors.HexColor("#00A884")
SKY = colors.HexColor("#2F80ED")
AMBER = colors.HexColor("#F3A83B")
ROSE = colors.HexColor("#E4576B")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#DDE4EE")
PALE = colors.HexColor("#F5F7FB")
WHITE = colors.white


def style(size=10, color=INK, leading=None, bold=False, align=TA_LEFT):
    return ParagraphStyle(
        name=f"s-{size}-{bold}-{align}",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size,
        leading=leading or size * 1.3,
        textColor=color,
        alignment=align,
        spaceAfter=0,
        spaceBefore=0,
    )


def para(c, text, x, y_top, width, size=10, color=INK, leading=None, bold=False,
         align=TA_LEFT, max_height=200):
    p = Paragraph(text, style(size, color, leading, bold, align))
    _, height = p.wrap(width, max_height)
    p.drawOn(c, x, y_top - height)
    return height


def rounded(c, x, y, width, height, fill=WHITE, stroke=LINE, radius=12, line=0.8):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(line)
    c.roundRect(x, y, width, height, radius, fill=1, stroke=1)


def pill(c, text, x, y, fill=PALE, color=NAVY, font_size=8):
    width = stringWidth(text, "Helvetica-Bold", font_size) + 18
    c.setFillColor(fill)
    c.roundRect(x, y, width, 20, 10, fill=1, stroke=0)
    c.setFillColor(color)
    c.setFont("Helvetica-Bold", font_size)
    c.drawCentredString(x + width / 2, y + 6.5, text)
    return width


def section_label(c, text, x=40, y=H - 48):
    c.setFillColor(TEAL)
    c.circle(x + 4, y + 3, 4, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + 15, y, text.upper())


def page_title(c, title, subtitle=None):
    title_height = para(c, title, 40, H - 70, W - 80, size=24, leading=27,
                        bold=True, color=NAVY_DARK)
    if subtitle:
        para(c, subtitle, 40, H - 76 - title_height, W - 80, size=10.2,
             leading=14, color=MUTED)


def footer(c, page, label):
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(40, 30, W - 40, 30)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.2)
    c.drawString(40, 18, f"MsMall Big Data  |  {label}")
    c.drawRightString(W - 40, 18, f"{page:02d}")


def icon_circle(c, x, y, label, fill=INDIGO):
    c.setFillColor(fill)
    c.circle(x, y, 14, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x, y - 3, label)


def metric_card(c, x, y, width, height, number, label, accent=TEAL, note=None):
    rounded(c, x, y, width, height, fill=WHITE)
    c.setFillColor(accent)
    c.roundRect(x, y, 5, height, 2, fill=1, stroke=0)
    para(c, number, x + 17, y + height - 17, width - 27, size=22, leading=23,
         bold=True, color=NAVY_DARK)
    para(c, label, x + 17, y + height - 45, width - 27, size=8.3, leading=10,
         bold=True, color=INK)
    if note:
        para(c, note, x + 17, y + 20, width - 27, size=6.8, leading=8.4, color=MUTED)


def capability_card(c, x, y, width, height, number, title, body, accent):
    rounded(c, x, y, width, height, fill=WHITE)
    icon_circle(c, x + 28, y + height - 28, number, accent)
    para(c, title, x + 52, y + height - 17, width - 66, size=11, leading=13,
         bold=True, color=NAVY_DARK)
    para(c, body, x + 18, y + height - 53, width - 36, size=8.2, leading=11,
         color=MUTED)


def flow_node(c, x, y, width, title, detail, color):
    rounded(c, x, y, width, 60, fill=colors.HexColor("#FFFFFF"), stroke=color)
    c.setFillColor(color)
    c.circle(x + 18, y + 42, 6, fill=1, stroke=0)
    para(c, title, x + 32, y + 51, width - 43, size=8.5, leading=10, bold=True,
         color=NAVY_DARK)
    para(c, detail, x + 12, y + 28, width - 24, size=6.8, leading=8.5, color=MUTED)


def arrow(c, x1, y, x2, color=LINE):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.4)
    c.line(x1, y, x2 - 5, y)
    c.line(x2 - 10, y + 4, x2 - 5, y)
    c.line(x2 - 10, y - 4, x2 - 5, y)


def cover(c):
    c.setFillColor(NAVY_DARK)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#153A7A"))
    c.circle(W + 35, H - 55, 205, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#0C7C7A"))
    c.circle(W - 65, H - 35, 110, fill=1, stroke=0)
    c.setStrokeColor(colors.Color(0.35, 0.55, 0.9, alpha=0.16))
    c.setLineWidth(1)
    for i in range(7):
        c.circle(65 + i * 45, 124 + (i % 2) * 18, 48 + i * 7, fill=0, stroke=1)

    if LOGO.exists():
        c.drawImage(ImageReader(str(LOGO)), 42, H - 132, 74, 74, mask="auto")
    pill(c, "INTELIGENCIA COMERCIAL", 42, H - 168,
         fill=colors.HexColor("#1D4B8E"), color=colors.HexColor("#BFECE4"), font_size=8)
    para(c, "Big Data", 42, H - 220, W - 84, size=42, leading=44, bold=True, color=WHITE)
    para(c, "De ventas operativas a decisiones explicables", 42, H - 272, 440,
         size=21, leading=26, bold=True, color=colors.HexColor("#D7E5FF"))
    para(c,
         "Una capa analítica multi-mall que agrega, detecta, diagnostica, predice y permite planificar escenarios sin alterar el POS ni los flujos Legacy.",
         42, H - 346, 420, size=12, leading=17, color=colors.HexColor("#C8D4EA"))

    y = 280
    for value, label, accent in [
        ("6", "vistas de inteligencia", TEAL),
        ("7/30/90", "días de predicción", SKY),
        ("360°", "diagnóstico por local", AMBER),
    ]:
        width = 150
        rounded(c, 42 + (width + 12) * ["6", "7/30/90", "360°"].index(value), y,
                width, 78, fill=colors.HexColor("#102B57"), stroke=colors.HexColor("#315184"))
        para(c, value, 55 + (width + 12) * ["6", "7/30/90", "360°"].index(value), y + 60,
             width - 26, size=19, leading=20, bold=True, color=accent)
        para(c, label, 55 + (width + 12) * ["6", "7/30/90", "360°"].index(value), y + 32,
             width - 26, size=8, leading=10, color=colors.HexColor("#D7E5FF"))

    para(c, "Brochure ejecutivo  |  Corte de implementación: 5 agosto 2026", 42, 54,
         W - 84, size=8.5, color=colors.HexColor("#9FB2D1"))


def overview(c):
    section_label(c, "01 / Plataforma")
    page_title(c, "Una capa de decisión sobre la operación existente",
               "Big Data aprovecha la venta ya capturada, crea agregados optimizados y expone inteligencia por API autenticada.")

    x0, y = 42, 586
    nodes = [
        ("Fuentes", "FTP, SFTP, CSV, API y exportador", TEAL),
        ("Ventas", "Operación Legacy intacta", SKY),
        ("Motor", "Cola + worker incremental", INDIGO),
        ("Analítica", "Agregados diarios y mensuales", AMBER),
        ("Decisión", "Panel, API y Copilot", ROSE),
    ]
    nw, gap = 93, 16
    for idx, (title, detail, color) in enumerate(nodes):
        x = x0 + idx * (nw + gap)
        flow_node(c, x, y, nw, title, detail, color)
        if idx < len(nodes) - 1:
            arrow(c, x + nw + 2, y + 30, x + nw + gap - 2)

    metric_card(c, 42, 455, 158, 94, "4", "granos analíticos",
                TEAL, "mall, local, categoría y mes")
    metric_card(c, 218, 455, 158, 94, "0", "consultas a venta cruda",
                INDIGO, "en predicción y diagnóstico")
    metric_card(c, 394, 455, 158, 94, "100%", "aislamiento por mall",
                SKY, "validación de acceso y alcance")

    rounded(c, 42, 184, 510, 242, fill=PALE, stroke=LINE)
    para(c, "Diseño operativo", 60, 404, 200, size=13, bold=True, color=NAVY_DARK)
    points = [
        ("01", "Actualización incremental", "Cada venta encola mall + fecha; el trabajo pesado ocurre fuera de la importación."),
        ("02", "Idempotencia", "Las claves de agregado evitan duplicados y permiten reconstrucciones por rango."),
        ("03", "Trazabilidad", "Runs, watermarks, cobertura, versión de modelo y errores quedan observables."),
        ("04", "Compatibilidad", "No sustituye POS, importadores, Dashboard BI, Finanzas ni reportes Legacy."),
    ]
    yy = 355
    for num, title, body in points:
        icon_circle(c, 73, yy + 8, num, INDIGO if num != "04" else TEAL)
        para(c, title, 98, yy + 18, 175, size=9.2, bold=True, color=NAVY_DARK)
        para(c, body, 275, yy + 18, 250, size=7.8, leading=10.2, color=MUTED)
        yy -= 50
    footer(c, 2, "Arquitectura")


def intelligence(c):
    section_label(c, "02 / Inteligencia")
    page_title(c, "Seis vistas para entender qué pasó y por qué",
               "La experiencia organiza la investigación desde el resumen ejecutivo hasta la evidencia de calidad.")
    cards = [
        ("01", "Resumen", "KPIs, evolución, ranking, categorías, patrones, contribuyentes y explicación ejecutiva.", INDIGO),
        ("02", "Calendario", "Feriados, promociones, ventas de pasillo, actividades y otros eventos sobre el comportamiento diario.", TEAL),
        ("03", "Anomalías", "Picos y caídas priorizados por impacto, desviación, fecha y confianza; búsqueda y filtros incluidos.", ROSE),
        ("04", "Investigación", "Estados por explicar, en revisión, explicada o descartada; causa, responsable, evidencia y notas.", AMBER),
        ("05", "Diagnóstico 360°", "Local contribuyente, referencia por día, pares homologados, evolución, archivos y logs vinculados.", SKY),
        ("06", "Calidad", "Cobertura día y local-día, frescura, watermark, completitud y trazabilidad del dato.", INDIGO),
    ]
    cw, ch = 245, 128
    for idx, card in enumerate(cards):
        col, row = idx % 2, idx // 2
        capability_card(c, 42 + col * 264, 525 - row * 145, cw, ch, *card)
    rounded(c, 42, 90, 510, 72, fill=colors.HexColor("#EEF5FF"), stroke=colors.HexColor("#CFE0F7"))
    para(c, "Lectura responsable", 60, 143, 130, size=9.5, bold=True, color=NAVY)
    para(c,
         "El motor distingue movimiento comercial, problema de datos, causa mixta o evidencia insuficiente. La clasificación orienta la investigación: no afirma causalidad absoluta.",
         60, 124, 470, size=8.1, leading=10.4, color=MUTED)
    footer(c, 3, "Inteligencia comercial")


def prediction(c):
    section_label(c, "03 / Predicción y planificación")
    page_title(c, "Del pronóstico explicable al plan de acción",
               "La Fase 3 combina patrones robustos, calendario comercial y escenarios documentados.")

    rounded(c, 42, 420, 510, 210, fill=NAVY_DARK, stroke=NAVY_DARK)
    para(c, "Predicción explicable", 62, 608, 220, size=15, bold=True, color=WHITE)
    para(c, "Horizontes acumulados", 62, 578, 170, size=8, bold=True,
         color=colors.HexColor("#9FB2D1"))
    xx = 62
    for days, color in [("7 días", TEAL), ("30 días", SKY), ("90 días", AMBER)]:
        rounded(c, xx, 518, 94, 50, fill=colors.HexColor("#102B57"), stroke=colors.HexColor("#315184"))
        para(c, days, xx + 8, 551, 78, size=11, align=TA_CENTER, bold=True, color=color)
        xx += 106
    para(c,
         "Mediana por día de semana + tendencia reciente limitada + efectos históricos de eventos + intervalo explicable del 80%.",
         62, 492, 300, size=8.2, leading=11, color=colors.HexColor("#D7E5FF"))
    # Small illustrative trajectory
    c.setStrokeColor(colors.HexColor("#315184")); c.setLineWidth(0.6)
    for i in range(4):
        c.line(385, 458 + i * 34, 525, 458 + i * 34)
    pts = [(386, 474), (406, 492), (426, 480), (446, 523), (466, 510), (486, 548), (506, 536), (526, 570)]
    c.setStrokeColor(TEAL); c.setLineWidth(2.4)
    for a, b in zip(pts, pts[1:]): c.line(a[0], a[1], b[0], b[1])
    for x, y in pts:
        c.setFillColor(TEAL); c.circle(x, y, 2.5, fill=1, stroke=0)

    left_x, right_x = 42, 307
    rounded(c, left_x, 151, 245, 245, fill=WHITE)
    para(c, "Simulación de escenarios", left_x + 18, 374, 205, size=12, bold=True, color=NAVY_DARK)
    types = ["Promoción", "Venta de pasillo", "Actividad del mall", "Feriado", "Horario extendido"]
    yy = 342
    for idx, item in enumerate(types):
        c.setFillColor([TEAL, SKY, INDIGO, AMBER, ROSE][idx])
        c.circle(left_x + 24, yy + 2, 3.5, fill=1, stroke=0)
        para(c, item, left_x + 34, yy + 8, 175, size=8.5, bold=True, color=INK)
        yy -= 27
    para(c, "Supuesto permitido: -60% a +80% sobre los días seleccionados.", left_x + 18, 190,
         205, size=7.3, leading=9, color=MUTED)

    rounded(c, right_x, 151, 245, 245, fill=WHITE)
    para(c, "Ciclo de decisión", right_x + 18, 374, 205, size=12, bold=True, color=NAVY_DARK)
    states = [("DRAFT", "Borrador", INDIGO), ("APPROVED", "Aprobado", SKY),
              ("ACTIVE", "En ejecución", AMBER), ("COMPLETED", "Completado", TEAL)]
    yy = 334
    for idx, (code, label, color) in enumerate(states):
        pill(c, label, right_x + 18, yy, fill=colors.HexColor("#F0F3F8"), color=color, font_size=7.5)
        if idx < len(states) - 1:
            c.setFillColor(LINE); c.rect(right_x + 40, yy - 15, 2, 10, fill=1, stroke=0)
        yy -= 43
    para(c, "Acciones con responsable y fecha. Al cerrar el período se compara venta real vs. base, escenario y rango.",
         right_x + 18, 190, 205, size=7.3, leading=9.2, color=MUTED)
    footer(c, 4, "Predicción y escenarios")


def operations(c):
    section_label(c, "04 / Operación y gobierno")
    page_title(c, "Inteligencia accionable, segura y auditable",
               "Las capacidades comerciales están acompañadas por controles de acceso, observabilidad y gestión del trabajo.")

    features = [
        ("Anomalías determinísticas", "10 reglas explicables: caídas, picos, cero actividad, cambios de registros, incompletitud y brechas de tendencia.", ROSE),
        ("Operations Center", "Eventos, hallazgos, observaciones y patrones con revisión, resolución, reapertura y comentarios.", INDIGO),
        ("Contexto para Copilot", "Resumen comercial acotado y trazable para enriquecer respuestas sin reemplazar los cálculos oficiales.", TEAL),
    ]
    yy = 542
    for title, body, accent in features:
        rounded(c, 42, yy, 510, 88, fill=WHITE)
        c.setFillColor(accent); c.roundRect(42, yy, 7, 88, 3, fill=1, stroke=0)
        para(c, title, 66, yy + 66, 190, size=11, bold=True, color=NAVY_DARK)
        para(c, body, 257, yy + 68, 272, size=8.1, leading=10.5, color=MUTED)
        yy -= 103

    para(c, "Controles integrados", 42, 310, 200, size=12.5, bold=True, color=NAVY_DARK)
    controls = [
        ("Acceso", "Autenticación, rol y mall autorizados"),
        ("Licencias", "Flags CORE, FORECAST, OPERATIONS y COPILOT"),
        ("Datos", "RLS forzado y acceso directo revocado"),
        ("Escala", "Rangos, paginación y límites por consulta"),
        ("Workers", "SKIP LOCKED, claim token y recuperación"),
        ("Auditoría", "Cambios de estado y evidencia preservada"),
    ]
    for idx, (title, body) in enumerate(controls):
        col, row = idx % 3, idx // 3
        x, y = 42 + col * 173, 224 - row * 82
        rounded(c, x, y, 164, 68, fill=PALE, stroke=LINE)
        para(c, title, x + 12, y + 51, 140, size=8.5, bold=True, color=NAVY)
        para(c, body, x + 12, y + 34, 140, size=7.1, leading=8.7, color=MUTED)
    footer(c, 5, "Operación y seguridad")


def evidence(c):
    section_label(c, "05 / Evidencia")
    page_title(c, "Validado con datos reales y controles de paridad",
               "Cifras documentadas en la certificación postactivación del 24 de julio de 2026.")
    metric_card(c, 42, 555, 158, 95, "7", "malls productivos",
                TEAL, "cierre comercial condicionado")
    metric_card(c, 218, 555, 158, 95, "0", "diferencia de paridad",
                INDIGO, "en los siete malls del alcance")
    metric_card(c, 394, 555, 158, 95, "310", "trabajos completados",
                SKY, "sin pendientes Big Data")

    rounded(c, 42, 292, 510, 236, fill=WHITE)
    para(c, "Matriz de evidencia", 60, 505, 200, size=12.5, bold=True, color=NAVY_DARK)
    rows = [
        ("Paridad comercial", "PASS", "Cero diferencias en siete malls productivos"),
        ("Incrementalidad", "PASS", "269 refrescos post-remediación sin error"),
        ("Aislamiento", "PASS", "Cero ventas cross-mall + guardrail"),
        ("Worker y cola", "PASS", "310 trabajos Big Data completados"),
        ("Regresión", "PASS", "122 pruebas backend + build frontend"),
        ("Evidencia visual", "PARCIAL", "Agora validado; paquete multi-mall pendiente"),
        ("Rendimiento", "PARCIAL", "Sin SLO ni telemetría postactivación completa"),
    ]
    y = 470
    for idx, (control, status, detail) in enumerate(rows):
        if idx % 2 == 0:
            c.setFillColor(PALE); c.rect(55, y - 16, 484, 27, fill=1, stroke=0)
        para(c, control, 63, y + 4, 120, size=7.8, bold=True, color=INK)
        scolor = TEAL if status == "PASS" else AMBER
        pill(c, status, 188, y - 11, fill=colors.HexColor("#EDF7F4") if status == "PASS" else colors.HexColor("#FFF6E8"),
             color=scolor, font_size=6.6)
        para(c, detail, 264, y + 4, 260, size=7.3, leading=9, color=MUTED)
        y -= 29

    rounded(c, 42, 106, 510, 160, fill=colors.HexColor("#FFF9EE"), stroke=colors.HexColor("#F4D9A7"))
    para(c, "Condición de lectura", 60, 243, 180, size=11, bold=True, color=colors.HexColor("#84510B"))
    para(c,
         "La certificación fue CONDITIONAL_GO: se aceptaron como riesgos residuales el histórico de Mall Demo, evidencia visual multi-mall incompleta y errores FTP/mapping de Agora. La interfaz conserva cobertura y errores para evitar conclusiones comerciales cuando faltan datos.",
         60, 218, 470, size=8.3, leading=11, color=colors.HexColor("#76541F"))
    footer(c, 6, "Certificación")


def close(c):
    section_label(c, "06 / Alcance completo")
    page_title(c, "Lo implementado, en una sola plataforma",
               "Inventario consolidado del código, contratos, migraciones, pruebas y documentación en develop.")

    columns = [
        ("Analítica", ["Resumen y evolución diaria", "Categorías y ranking", "Perfil 360° de local", "Benchmark por categoría", "Calidad y cobertura", "Calendario comercial"]),
        ("Inteligencia", ["Anomalías explicables", "Investigación y causas", "Pronóstico 7/30/90", "Escenarios comerciales", "Planes de acción", "Evaluación de resultados"]),
        ("Plataforma", ["Agregados incrementales", "Queue y watermarks", "API autenticada", "Flags por mall", "RLS y service role", "Operations + Copilot"]),
    ]
    for idx, (title, items) in enumerate(columns):
        x = 42 + idx * 173
        rounded(c, x, 390, 164, 250, fill=WHITE)
        c.setFillColor([INDIGO, TEAL, NAVY][idx]); c.roundRect(x, 596, 164, 44, 10, fill=1, stroke=0)
        para(c, title, x + 12, 624, 140, size=11, bold=True, align=TA_CENTER, color=WHITE)
        yy = 570
        for item in items:
            c.setFillColor([INDIGO, TEAL, NAVY][idx]); c.circle(x + 18, yy + 2, 3, fill=1, stroke=0)
            para(c, item, x + 28, yy + 8, 124, size=7.9, leading=9.8, color=INK)
            yy -= 31

    rounded(c, 42, 202, 510, 157, fill=NAVY_DARK, stroke=NAVY_DARK)
    para(c, "Propuesta de valor", 62, 333, 170, size=9, bold=True, color=TEAL)
    para(c, "Más contexto. Menos intuición. Decisiones trazables.", 62, 305, 450,
         size=19, leading=22, bold=True, color=WHITE)
    para(c,
         "MsMall Big Data convierte la operación diaria en una conversación verificable entre ventas, calidad de datos, calendario, predicción y ejecución comercial.",
         62, 257, 450, size=9.2, leading=12, color=colors.HexColor("#CBD7EA"))

    para(c, "Base documental", 42, 169, 120, size=8.5, bold=True, color=NAVY_DARK)
    para(c,
         "Sprint 1, Sprint 2, Fase 2 Diagnóstico, Fase 3A Predicción, Fase 3B Escenarios, semántica transaccional y certificaciones de despliegue.",
         42, 152, 510, size=7.2, leading=9.2, color=MUTED)
    para(c, "Documento informativo. Las cifras proyectadas no constituyen garantía de resultados.",
         42, 92, 510, size=7.4, bold=True, color=ROSE)
    footer(c, 7, "Resumen de capacidades")


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUTPUT), pagesize=A4, pageCompression=1)
    c.setTitle("MsMall Big Data - Brochure ejecutivo")
    c.setAuthor("MsMall")
    c.setSubject("Capacidades implementadas del módulo Big Data")
    for index, page in enumerate((cover, overview, intelligence, prediction, operations, evidence, close)):
        page(c)
        if index < 6:
            c.showPage()
    c.save()
    print(OUTPUT)


if __name__ == "__main__":
    build()
