#!/usr/bin/env python3
"""Generate a concise two-page promotional Big Data brochure."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "big-data-promotional"
OUTPUT = ROOT / "output" / "pdf" / "msmall_big_data_brochure_promocional.pdf"
LOGO = ROOT / "public" / "msmall-icon-512.png"

W, H = landscape(A4)
NAVY = colors.HexColor("#081A3D")
NAVY_2 = colors.HexColor("#102A5E")
INDIGO = colors.HexColor("#4B4DE2")
TEAL = colors.HexColor("#00A884")
SKY = colors.HexColor("#2F80ED")
AMBER = colors.HexColor("#F3A83B")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#D8E0EB")
PALE = colors.HexColor("#F5F7FB")
WHITE = colors.white


def paragraph(c, text, x, y_top, width, size=10, leading=None, color=INK,
              bold=False, align=TA_LEFT):
    p = Paragraph(
        text,
        ParagraphStyle(
            name=f"p-{size}-{bold}",
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size,
            leading=leading or size * 1.25,
            textColor=color,
            alignment=align,
        ),
    )
    _, height = p.wrap(width, 500)
    p.drawOn(c, x, y_top - height)
    return height


def rounded(c, x, y, width, height, fill=WHITE, stroke=LINE, radius=12, line=0.8):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(line)
    c.roundRect(x, y, width, height, radius, fill=1, stroke=1)


def cropped_reader(filename, crop):
    with Image.open(ASSETS / filename) as image:
        image = image.convert("RGB").crop(crop)
        data = BytesIO()
        image.save(data, format="JPEG", quality=94, optimize=True)
        data.seek(0)
        return ImageReader(data)


def framed_image(c, reader, x, y, width, height, radius=13):
    image_width, image_height = reader.getSize()
    scale = max(width / image_width, height / image_height)
    draw_width = image_width * scale
    draw_height = image_height * scale
    draw_x = x + (width - draw_width) / 2
    draw_y = y + (height - draw_height) / 2
    c.saveState()
    path = c.beginPath()
    path.roundRect(x, y, width, height, radius)
    c.clipPath(path, stroke=0)
    c.drawImage(
        reader,
        draw_x,
        draw_y,
        draw_width,
        draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )
    c.restoreState()
    c.setStrokeColor(colors.HexColor("#C9D4E3"))
    c.setLineWidth(0.9)
    c.roundRect(x, y, width, height, radius, fill=0, stroke=1)


def chip(c, text, x, y, accent):
    width = c.stringWidth(text, "Helvetica-Bold", 7.5) + 24
    c.setFillColor(colors.HexColor("#EEF2F8"))
    c.roundRect(x, y, width, 23, 11.5, fill=1, stroke=0)
    c.setFillColor(accent)
    c.circle(x + 10, y + 11.5, 3, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x + 17, y + 8, text)
    return width


def footer(c, page):
    c.setStrokeColor(colors.HexColor("#D8E0EB"))
    c.setLineWidth(0.6)
    c.line(34, 24, W - 34, 24)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.8)
    c.drawString(34, 12, "MsMall Big Data  |  Inteligencia Comercial")
    c.drawRightString(W - 34, 12, f"{page}/2")


def cover_page(c):
    c.setFillColor(PALE)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.rect(0, 0, 265, H, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#173A77"))
    c.circle(245, H + 10, 145, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.circle(255, H + 18, 80, fill=1, stroke=0)

    if LOGO.exists():
        c.drawImage(ImageReader(str(LOGO)), 34, H - 90, 56, 56, mask="auto")
    paragraph(c, "BIG DATA", 104, H - 49, 125, 8, 10, colors.HexColor("#9EDDD2"), True)
    paragraph(c, "INTELIGENCIA COMERCIAL", 104, H - 64, 125, 7, 9,
              colors.HexColor("#B9C8DF"), True)

    paragraph(c, "De los datos a la decisión", 34, H - 150, 195, 28, 31, WHITE, True)
    paragraph(c,
              "Detecta patrones, anticipa resultados y convierte cada señal comercial en una acción verificable.",
              34, H - 256, 190, 11.2, 15.5, colors.HexColor("#D5E1F3"))

    y = 226
    for number, label, accent in [
        ("01", "Comprende el comportamiento", TEAL),
        ("02", "Prioriza lo que importa", SKY),
        ("03", "Decide con confianza", AMBER),
    ]:
        c.setFillColor(accent)
        c.circle(46, y + 5, 9, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(46, y + 3, number)
        paragraph(c, label, 64, y + 11, 160, 8.4, 10, WHITE, True)
        y -= 40

    screenshot = cropped_reader("summary.jpg", (210, 48, 1280, 720))
    framed_image(c, screenshot, 286, 138, 520, 327, 15)
    paragraph(c, "Lectura ejecutiva en una sola vista", 286, 118, 270, 12, 14, NAVY, True)
    paragraph(c,
              "Patrones semanales, feriados, confianza, cobertura y locales reportando.",
              286, 96, 485, 8, 10, MUTED)
    x = 286
    for text, accent in [
        ("Resumen ejecutivo", INDIGO),
        ("98.9% días cubiertos", TEAL),
        ("Contexto comercial", AMBER),
    ]:
        x += chip(c, text, x, 49, accent) + 8

    footer(c, 1)


def capability_card(c, x, y, width, height, title, subtitle, detail, image_reader, accent):
    rounded(c, x, y, width, height, fill=WHITE, stroke=LINE, radius=13)
    c.setFillColor(accent)
    c.roundRect(x, y + height - 6, width, 6, 3, fill=1, stroke=0)
    paragraph(c, title, x + 14, y + height - 20, width - 28, 10.5, 12.5, NAVY, True)
    paragraph(c, subtitle, x + 14, y + height - 39, width - 28, 7.2, 9, MUTED)
    framed_image(c, image_reader, x + 12, y + 140, width - 24, 128, 8)
    paragraph(c, detail, x + 14, y + 120, width - 28, 7.6, 10.5, INK, True)
    paragraph(c, "Datos visibles del sistema", x + 14, y + 83, width - 28,
              6.8, 8.5, MUTED)


def primary_capability_card(c, x, y, width, height, title, subtitle, image_reader, accent):
    rounded(c, x, y, width, height, fill=WHITE, stroke=LINE, radius=13)
    c.setFillColor(accent)
    c.roundRect(x, y + height - 6, width, 6, 3, fill=1, stroke=0)
    paragraph(c, title, x + 14, y + height - 20, width - 28, 11.5, 13.5, NAVY, True)
    paragraph(c, subtitle, x + 14, y + height - 41, width - 28, 7.6, 9.5, MUTED)
    framed_image(c, image_reader, x + 14, y + 14, width - 28, 271, 9)


def secondary_capability_card(c, x, y, width, height, title, image_reader, accent):
    rounded(c, x, y, width, height, fill=WHITE, stroke=LINE, radius=13)
    c.setFillColor(accent)
    c.roundRect(x, y + height - 6, width, 6, 3, fill=1, stroke=0)
    paragraph(c, title, x + 12, y + height - 18, width - 24, 9.2, 11, NAVY, True)
    framed_image(c, image_reader, x + 12, y + 12, width - 24, 126, 8)


def capabilities_page(c):
    c.setFillColor(PALE)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    paragraph(c, "BIG DATA EN ACCIÓN", 34, H - 31, 220, 7.5, 9, TEAL, True)
    paragraph(c, "Anticipa. Investiga. Simula.", 34, H - 52, 430, 24, 27, NAVY, True)
    paragraph(c,
              "Tres momentos de decisión conectados por una misma experiencia visual.",
              470, H - 49, 335, 9.2, 12, MUTED)

    prediction = cropped_reader("prediction.jpg", (210, 48, 1280, 650))
    anomalies = cropped_reader("anomalies.jpg", (210, 48, 1280, 650))
    simulator = cropped_reader("scenario-simulator.jpg", (95, 38, 1165, 640))

    primary_capability_card(
        c, 34, 164, 510, 350,
        "Pronósticos explicables",
        "Venta proyectada, rango esperado, confianza y trayectoria diaria en una sola vista.",
        prediction, TEAL,
    )
    secondary_capability_card(
        c, 560, 344, 248, 170,
        "Simulación comercial",
        simulator, INDIGO,
    )
    secondary_capability_card(
        c, 560, 164, 248, 170,
        "Anomalías accionables",
        anomalies, SKY,
    )

    rounded(c, 34, 50, 774, 93, fill=NAVY, stroke=NAVY, radius=13)
    paragraph(c, "UNA SOLA PLATAFORMA", 54, 121, 180, 7.2, 9, TEAL, True)
    paragraph(c, "Más contexto. Menos intuición.", 54, 98, 330, 16, 19, WHITE, True)
    paragraph(c,
              "Resumen, predicción, escenarios, calendario, anomalías y calidad trabajan juntos para que cada decisión sea trazable.",
              410, 111, 370, 8.5, 11.5, colors.HexColor("#D5E1F3"))
    paragraph(c,
              "MsMall Big Data no reemplaza la operación: la convierte en inteligencia comercial.",
              410, 74, 370, 7.5, 9.5, colors.HexColor("#9EDDD2"), True)

    footer(c, 2)


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUTPUT), pagesize=landscape(A4), pageCompression=1)
    c.setTitle("MsMall Big Data - Brochure promocional")
    c.setAuthor("MsMall")
    c.setSubject("Brochure promocional del módulo Big Data")
    cover_page(c)
    c.showPage()
    capabilities_page(c)
    c.save()
    print(OUTPUT)


if __name__ == "__main__":
    build()
