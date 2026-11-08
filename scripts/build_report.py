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
from reportlab.platypus import (Image, ListFlowable, ListItem, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "report" / "REPORT.md"
OUT = ROOT / "docs" / "report" / "GigBid_RnD_Report.pdf"

ss = getSampleStyleSheet()
BODY = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.2, leading=12.2, alignment=TA_LEFT, spaceAfter=4)
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, spaceBefore=6, spaceAfter=6, textColor=colors.HexColor("#1f6f5c"))
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#1f6f5c"))
H3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10, spaceBefore=6, spaceAfter=3)
CELL = ParagraphStyle("c", parent=BODY, fontSize=7.6, leading=9.4, spaceAfter=0)
CODE = ParagraphStyle("code", parent=ss["Code"], fontSize=7.2, leading=8.8, backColor=colors.HexColor("#f2f4f3"))


def inline(t: str) -> str:
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r"<font face='Courier'>\1</font>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<link href='\2' color='#1f6f5c'>\1</link>", t)
    return t


def table(lines: list[str]):
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines if not re.match(r"^\s*\|?\s*:?-{2,}", ln)]
    data = [[Paragraph(inline(c), CELL) for c in r] for r in rows]
    t = Table(data, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2f1ec")), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c9d3ce")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    return t


def build() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
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
            story.append(table(lines[i:j]))
            story.append(Spacer(1, 4))
            i = j - 1
        elif re.match(r"^\s*([-*]|\d+\.)\s+", ln):
            flush()
            j, items = i, []
            ordered = bool(re.match(r"^\s*\d+\.", ln))
            while j < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[j]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[j]))
                j += 1
            story.append(ListFlowable([ListItem(Paragraph(inline(x), BODY), leftIndent=10) for x in items],
                                      bulletType="1" if ordered else "bullet", leftIndent=12, bulletFontSize=7))
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
        c.setFillColor(colors.grey)
        c.drawString(1.6 * cm, 1 * cm, "GigBid - AI-4016 R&D report")
        c.drawRightString(A4[0] - 1.6 * cm, 1 * cm, f"page {d.page}")
    SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.4 * cm, bottomMargin=1.5 * cm,
                      title="GigBid R&D report").build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
