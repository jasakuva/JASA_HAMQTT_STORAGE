from pathlib import Path
from zipfile import ZipFile


root = Path(__file__).resolve().parents[1]
plan = root / "IMPLEMENTATION_PLAN.md"
architecture = root / "docs" / "ARCHITECTURE.md"
docx = root / "docs" / "HAMQTT_STORE_ARCHITECTURE.docx"

assert plan.exists() and plan.stat().st_size > 0
assert architecture.exists() and architecture.stat().st_size > 0
assert docx.exists() and docx.stat().st_size > 1000

required_parts = {
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/styles.xml",
    "word/_rels/document.xml.rels",
}

with ZipFile(docx) as package:
    names = set(package.namelist())
    assert required_parts.issubset(names), required_parts - names
    document_xml = package.read("word/document.xml").decode("utf-8")

for expected in (
    "Detailed database schema",
    "mqtt_observations",
    "mqtt_parse_events",
    "object_links",
    "pgvector",
    "MCP read-only access",
    "Trace a value to its raw message",
):
    assert expected in architecture.read_text(encoding="utf-8")
    assert expected in document_xml

print("Documentation validation passed")
print(f"Plan: {plan.stat().st_size} bytes")
print(f"Architecture Markdown: {architecture.stat().st_size} bytes")
print(f"Architecture Word document: {docx.stat().st_size} bytes")