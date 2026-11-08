"""Build the R&D report PDF from docs/report/REPORT.md (reportlab, no LaTeX needed).

    python scripts/build_report.py   ->  docs/report/GigBid_RnD_Report.pdf
Supports: # headings, paragraphs, - bullets, 1. lists, | tables |, ``` code ```, **bold**, `code`, images ![](path).
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "report" / "REPORT.md"
OUT = ROOT / "docs" / "report" / "GigBid_RnD_Report.pdf"

ss = getSampleStyleSheet()
# Plain, readable style: one font family, black text, generous spacing, no colours or underlines.
BODY = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=10.5, leading=15.5, alignment=TA_LEFT,
                      spaceAfter=8, textColor=colors.black)
H1 = ParagraphStyle("h1", parent=BODY, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceBefore=4, spaceAfter=10)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=16, spaceAfter=8)
H3 = ParagraphStyle("h3", parent=BODY, fontName="Helvetica-Bold", fontSize=11, leading=15, spaceBefore=10, spaceAfter=5)
CELL = ParagraphStyle("c", parent=BODY, fontSize=9, leading=12, spaceAfter=0)
CODE = ParagraphStyle("code", parent=ss["Code"], fontName="Courier", fontSize=8.5, leading=11)


def inline(t: str) -> str:
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r"<font face='Courier'>\1</font>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", t)   # plain text, no coloured/underlined links
    return t


def table(lines: list[str]):
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines if not re.match(r"^\s*\|?\s*:?-{2,}", ln)]
    data = [[Paragraph(("<b>%s</b>" % inline(c)) if i == 0 else inline(c), CELL) for c in r] for i, r in enumerate(rows)]
    t = Table(data, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]))
    return t


RESULTS = ROOT / "evals" / "results"
_REF = re.compile(r"\{\{([\w.-]+\.json):([^}|]+)(?:\|(\w+))?\}\}")


def fill(text: str) -> str:
    """{{file.json:a.b.0.c|fmt}} -> value from evals/results/file.json (fmt: pct, int, 1, 2, 4, raw)."""
    cache: dict = {}

    def rep(m):
        f, path, fmt = m.group(1), m.group(2), m.group(3) or "3"
        if f not in cache:
            p = RESULTS / f
            cache[f] = __import__("json").loads(p.read_text()) if p.exists() else None
        v = cache[f]
        for k in path.split("."):
            if v is None:
                break
            v = v[int(k)] if isinstance(v, list) and k.isdigit() else (v.get(k) if isinstance(v, dict) else None)
        if v is None:
            return "n/a"
        if fmt == "pct":
            return f"{float(v) * 100:.1f}%"
        if fmt == "int":
            return str(int(v))
        if fmt == "raw" or not isinstance(v, (int, float)):
            return str(v)
        return f"{float(v):.{int(fmt)}f}"
    return _REF.sub(rep, text)


def build() -> None:
    filled = fill(SRC.read_text(encoding="utf-8"))
    (SRC.parent / "REPORT.filled.md").write_text(filled, encoding="utf-8")
    lines = filled.splitlines()
    story, i, para = [], 0, []

    def flush():
        if para:
            story.append(Paragraph(inline(" ".join(para)), BODY))
            para.clear()
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "<!-- pagebreak -->":
            flush()
            story.append(PageBreak())
        elif ln.startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            story.append(Preformatted("\n".join(lines[i + 1:j]), CODE))
            i = j
        elif ln.startswith("#"):
            flush()
            lvl = len(ln) - len(ln.lstrip("#"))
            story.append(Paragraph(inline(ln.lstrip("#").strip()), {1: H1, 2: H2}.get(lvl, H3)))
        elif ln.strip().startswith("|"):
            flush()
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            story.append(Spacer(1, 4))
            story.append(table(lines[i:j]))
            story.append(Spacer(1, 12))
            i = j - 1
        elif re.match(r"^\s*([-*]|\d+\.)\s+", ln):
            flush()
            j, items = i, []
            ordered = bool(re.match(r"^\s*\d+\.", ln))
            while j < len(lines):
                if re.match(r"^\s*([-*]|\d+\.)\s+", lines[j]):
                    items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[j]))
                elif lines[j].startswith((" ", "\t")) and lines[j].strip() and items:
                    items[-1] += " " + lines[j].strip()      # wrapped continuation of the same item
                else:
                    break
                j += 1
            story.append(ListFlowable([ListItem(Paragraph(inline(x), BODY), leftIndent=10) for x in items],
                                      bulletType="1" if ordered else "bullet", leftIndent=14, bulletFontSize=8, spaceAfter=6))
            i = j - 1
        elif m := re.match(r"!\[[^\]]*\]\(([^)]+)\)", ln.strip()):
            flush()
            p = (SRC.parent / m.group(1)).resolve()
            if p.exists():
                img = Image(str(p))
                ratio = min(16 * cm / img.imageWidth, 9 * cm / img.imageHeight, 1)
                img.drawWidth, img.drawHeight = img.imageWidth * ratio, img.imageHeight * ratio
                story.append(img)
        elif not ln.strip():
            flush()
        else:
            para.append(ln.strip())
        i += 1
    flush()

    def footer(c, d):
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        c.drawString(1.6 * cm, 1 * cm, "GigBid - AI-4016 R&D report")
        c.drawRightString(A4[0] - 1.6 * cm, 1 * cm, f"page {d.page}")
    SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                      title="GigBid R&D report").build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
