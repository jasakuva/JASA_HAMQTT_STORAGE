"""Generate the styled architecture Word document from docs/ARCHITECTURE.md."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "ARCHITECTURE.md"
OUTPUT = ROOT / "docs" / "HAMQTT_STORE_ARCHITECTURE.docx"
ASSET = ROOT / "docs" / "architecture_schema_overview.png"
ER_ASSET = ROOT / "docs" / "database_er_diagram.png"
NAVY, TEAL, BLUE = "15324B", "0F766E", "2563EB"
LIGHT_GRAY, MID_GRAY, WHITE = "F4F7FA", "64748B", "FFFFFF"


def shade(cell, fill: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    element = props.find(qn("w:shd"))
    if element is None:
        element = OxmlElement("w:shd")
        props.append(element)
    element.set(qn("w:fill"), fill)


def cell_text(cell, text: str, bold=False, color="1E293B") -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Aptos"
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def header_repeat(row) -> None:
    props = row._tr.get_or_add_trPr()
    element = OxmlElement("w:tblHeader")
    element.set(qn("w:val"), "true")
    props.append(element)


def page_number(paragraph) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, end])


def make_diagram() -> None:
    image = Image.new("RGB", (1600, 880), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    try:
        regular = ImageFont.truetype("segoeui.ttf", 18)
        title = ImageFont.truetype("segoeuib.ttf", 25)
        heading = ImageFont.truetype("segoeui.ttf", 24)
    except OSError:
        regular = title = heading = ImageFont.load_default()

    def box(x, y, w, h, name, lines, fill, outline):
        draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=fill, outline=outline, width=4)
        draw.text((x + 20, y + 16), name, font=title, fill="#15324B")
        for index, line in enumerate(lines):
            draw.text((x + 20, y + 58 + index * 27), line, font=regular, fill="#334155")

    def arrow(start, end, color="#64748B"):
        draw.line((*start, *end), fill=color, width=4)
        draw.polygon([(end[0], end[1]), (end[0] - 14, end[1] - 8), (end[0] - 14, end[1] + 8)], fill=color)

    box(55, 80, 330, 220, "Configuration", ["system_settings", "ha_connections", "mqtt_connections", "subscriptions"], "#EAF2FF", "#2563EB")
    box(470, 65, 300, 150, "Shared catalog", ["objects", "stable source identity"], "#E8F7F4", "#0F766E")
    box(870, 55, 310, 190, "Home Assistant", ["ha_entities", "ha_state_current", "ha_state_history"], "#FFF7ED", "#EA580C")
    box(870, 330, 360, 250, "MQTT raw + parsed", ["mqtt_topics", "mqtt_messages", "payload_fields", "observations", "current_values"], "#F5F3FF", "#7C3AED")
    box(470, 420, 300, 145, "Relationships", ["object_links", "confidence + source"], "#FDF2F8", "#DB2777")
    box(55, 640, 330, 150, "Semantic search", ["embeddings", "vector(1536)"], "#F0FDFA", "#0D9488")
    arrow((385, 170), (470, 140), "#2563EB")
    arrow((770, 140), (870, 145), "#0F766E")
    arrow((770, 180), (870, 425), "#0F766E")
    arrow((770, 490), (870, 480), "#DB2777")
    arrow((385, 715), (470, 510), "#0D9488")
    draw.text((55, 20), "HA MQTT Store — implemented database domains", font=heading, fill="#15324B")
    image.save(ASSET)


def make_er_diagram() -> None:
    """Draw the implemented relational schema without requiring Graphviz."""
    image = Image.new("RGB", (2400, 1750), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    try:
        regular = ImageFont.truetype("segoeui.ttf", 17)
        small = ImageFont.truetype("segoeui.ttf", 14)
        title = ImageFont.truetype("segoeuib.ttf", 23)
        heading = ImageFont.truetype("segoeuib.ttf", 30)
    except OSError:
        regular = small = title = heading = ImageFont.load_default()

    groups = {
        "config": ("#EAF2FF", "#2563EB"),
        "catalog": ("#E8F7F4", "#0F766E"),
        "ha": ("#FFF7ED", "#EA580C"),
        "mqtt": ("#F5F3FF", "#7C3AED"),
        "links": ("#FDF2F8", "#DB2777"),
    }

    tables = {
        "system_settings": (70, 120, 300, "config", ["PK id", "UQ setting_key", "setting_value JSON", "is_secret"]),
        "ha_connections": (70, 390, 300, "config", ["PK id", "name", "base_url", "enabled"]),
        "mqtt_connections": (70, 720, 300, "config", ["PK id", "name", "host / port", "tls_enabled", "enabled"]),
        "ingestion_subscriptions": (70, 1060, 300, "config", ["PK id", "FK mqtt_connection_id", "topic_filter", "qos", "enabled"]),
        "objects": (530, 580, 340, "catalog", ["PK id", "UQ source_type + source_identifier", "object_type", "display_name", "is_active"]),
        "ha_entities": (1030, 110, 350, "ha", ["PK id", "UQ/FK object_id", "FK ha_connection_id", "IDX entity_id", "domain", "raw_entity JSON"]),
        "ha_state_current": (1510, 80, 350, "ha", ["PK id", "UQ/FK ha_entity_id", "state_text / numeric / boolean", "attributes JSON", "last_updated_at"]),
        "ha_state_history": (1510, 390, 350, "ha", ["PK id", "FK ha_entity_id", "UQ entity_id + observed_at", "state values", "raw_state JSON"]),
        "mqtt_topics": (1030, 650, 350, "mqtt", ["PK id", "UQ/FK object_id", "FK mqtt_connection_id", "UQ topic per broker", "message_count"]),
        "mqtt_messages": (1510, 700, 350, "mqtt", ["PK id", "FK mqtt_topic_id", "FK mqtt_connection_id", "IDX received_at", "payload_*", "payload_hash"]),
        "mqtt_payload_fields": (1030, 1120, 350, "mqtt", ["PK id", "UQ/FK object_id", "FK mqtt_topic_id", "UQ topic + field_path", "data_type"]),
        "mqtt_observations": (1510, 1110, 350, "mqtt", ["PK id", "FK field/topic/object", "FK source_message_id", "IDX observed_at", "typed values"]),
        "mqtt_current_values": (1030, 1480, 350, "mqtt", ["PK id", "UQ/FK mqtt_payload_field_id", "FK object_id", "latest typed value"]),
        "mqtt_parse_events": (1980, 700, 330, "mqtt", ["PK id", "FK mqtt_message_id", "status", "error_message", "details JSON"]),
        "object_links": (530, 1100, 340, "links", ["PK id", "FK from_object_id", "FK to_object_id", "UQ link tuple", "confidence", "source"]),
        "embeddings": (530, 1450, 340, "links", ["PK id", "UQ/FK object_id", "embedding vector(1536)", "embedding_model", "content_hash"]),
    }

    def draw_table(name, x, y, width, group, fields):
        fill, outline = groups[group]
        row_height = 29
        height = 48 + row_height * len(fields)
        draw.rounded_rectangle((x, y, x + width, y + height), radius=12, fill=fill, outline=outline, width=4)
        draw.rectangle((x, y, x + width, y + 48), fill=outline)
        draw.text((x + 14, y + 11), name, font=title, fill="#FFFFFF")
        for i, field in enumerate(fields):
            draw.text((x + 14, y + 55 + i * row_height), field, font=small, fill="#1E293B")
        return (x, y, x + width, y + height)

    boxes = {name: draw_table(name, *data) for name, data in tables.items()}

    def point(name, side):
        x1, y1, x2, y2 = boxes[name]
        return ((x1 + x2) // 2, y1 if side == "top" else y2) if side in {"top", "bottom"} else (x1 if side == "left" else x2, (y1 + y2) // 2)

    def relation(source, target, source_side="right", target_side="left"):
        start, end = point(source, source_side), point(target, target_side)
        draw.line((*start, *end), fill="#94A3B8", width=3)
        # Small crow-foot-like endpoint marker.
        draw.ellipse((end[0] - 5, end[1] - 5, end[0] + 5, end[1] + 5), fill="#64748B")

    relations = [
        ("ha_connections", "ha_entities", "right", "left"),
        ("ha_entities", "ha_state_current", "right", "left"),
        ("ha_entities", "ha_state_history", "right", "left"),
        ("mqtt_connections", "ingestion_subscriptions", "bottom", "top"),
        ("mqtt_connections", "mqtt_topics", "right", "left"),
        ("mqtt_topics", "mqtt_messages", "right", "left"),
        ("mqtt_topics", "mqtt_payload_fields", "bottom", "top"),
        ("mqtt_messages", "mqtt_parse_events", "right", "left"),
        ("mqtt_payload_fields", "mqtt_observations", "right", "left"),
        ("mqtt_payload_fields", "mqtt_current_values", "bottom", "top"),
        ("mqtt_messages", "mqtt_observations", "bottom", "top"),
        ("objects", "ha_entities", "right", "left"),
        ("objects", "mqtt_topics", "right", "left"),
        ("objects", "mqtt_payload_fields", "right", "left"),
        ("objects", "object_links", "bottom", "top"),
        ("objects", "embeddings", "bottom", "top"),
    ]
    for relation_args in relations:
        relation(*relation_args)

    draw.text((70, 35), "HA MQTT Store — implemented database ER diagram", font=heading, fill="#15324B")
    draw.text((70, 78), "PK = primary key  •  FK = foreign key  •  UQ = unique constraint  •  IDX = index", font=regular, fill="#64748B")
    image.save(ER_ASSET)


def configure(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(9.5)
    normal.font.color.rgb = RGBColor.from_string("334155")
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.08
    for name, size, color in (("Title", 31, NAVY), ("Heading 1", 20, NAVY), ("Heading 2", 14, TEAL), ("Heading 3", 11, BLUE)):
        style = document.styles[name]
        style.font.name = "Aptos Display"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(12 if name != "Title" else 0)
        style.paragraph_format.space_after = Pt(6)
    code = document.styles.add_style("Code Block", WD_STYLE_TYPE.PARAGRAPH)
    code.font.name = "Cascadia Mono"
    code.font.size = Pt(8)
    code.font.color.rgb = RGBColor.from_string("E2E8F0")
    code.paragraph_format.left_indent = Inches(0.18)
    code.paragraph_format.right_indent = Inches(0.18)


def add_code(document, text: str) -> None:
    paragraph = document.add_paragraph(style="Code Block")
    props = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), NAVY)
    props.append(shading)
    paragraph.add_run(text.rstrip())


def add_table(document, rows: list[list[str]]) -> None:
    if len(rows) < 2:
        return
    separator = rows[1]
    body = rows[2:] if all(set(value.strip()) <= {"-", ":"} for value in separator) else rows[1:]
    table = document.add_table(rows=1, cols=len(rows[0]))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    header_repeat(table.rows[0])
    for index, value in enumerate(rows[0]):
        cell_text(table.rows[0].cells[index], value.strip(), True, WHITE)
        shade(table.rows[0].cells[index], NAVY)
    for row_index, row in enumerate(body):
        cells = table.add_row().cells
        for index in range(len(rows[0])):
            cell_text(cells[index], row[index].strip() if index < len(row) else "")
            shade(cells[index], WHITE if row_index % 2 == 0 else LIGHT_GRAY)


def render(document, markdown: str) -> None:
    lines = markdown.splitlines()
    index = 0
    in_code = False
    code_lines = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            if in_code:
                add_code(document, "\n".join(code_lines))
                code_lines = []
            in_code = not in_code
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].startswith("|"):
                rows.append([part.strip() for part in lines[index].strip().strip("|").split("|")])
                index += 1
            add_table(document, rows)
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            document.add_heading(heading.group(2), level=len(heading.group(1)))
        elif line.startswith("> "):
            document.add_paragraph(line[2:], style="Intense Quote")
        elif re.match(r"^[-*]\s+", line):
            document.add_paragraph(re.sub(r"^[-*]\s+", "", line), style="List Bullet")
        elif re.match(r"^\d+\.\s+", line):
            document.add_paragraph(re.sub(r"^\d+\.\s+", "", line), style="List Number")
        elif line.strip():
            document.add_paragraph(line)
        index += 1


def main() -> None:
    make_diagram()
    make_er_diagram()
    document = Document()
    configure(document)
    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.65)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)
    header = section.header.paragraphs[0]
    header.text = "HA MQTT STORE  /  ARCHITECTURE"
    header.runs[0].font.color.rgb = RGBColor.from_string(MID_GRAY)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run("HA MQTT Store  •  ")
    page_number(footer)
    title = document.add_paragraph(style="Title")
    title.add_run("HA MQTT Store")
    subtitle = document.add_paragraph("Architecture, database schema, lineage, SQL examples, and MCP access")
    subtitle.runs[0].font.size = Pt(15)
    subtitle.runs[0].font.color.rgb = RGBColor.from_string(TEAL)
    meta = document.add_paragraph("CURRENT IMPLEMENTATION REFERENCE  •  10 OCTOBER 2026\nPostgreSQL 17  |  SQLAlchemy 2.x  |  Alembic  |  pgvector")
    for run in meta.runs:
        run.font.color.rgb = RGBColor.from_string(MID_GRAY)
    document.add_picture(str(ASSET), width=Inches(6.9))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_page_break()
    document.add_heading("Implemented database ER diagram", level=1)
    document.add_paragraph("The diagram below reflects the tables and relationships implemented by the current SQLAlchemy models and Alembic migrations.")
    document.add_picture(str(ER_ASSET), width=Inches(7.0))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_page_break()
    render(document, SOURCE.read_text(encoding="utf-8"))
    document.core_properties.title = "HA MQTT Store — Architecture and Database Design"
    document.core_properties.subject = "PostgreSQL schema, lineage, SQL examples, and read-only MCP architecture"
    document.core_properties.author = "HA MQTT Store"
    document.save(OUTPUT)
    print(f"Generated {OUTPUT}")


if __name__ == "__main__":
    main()