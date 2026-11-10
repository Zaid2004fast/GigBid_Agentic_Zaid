"""Spreadsheet workflow for the human labels used to calibrate the LLM judge.

    python -m evals.runners.label_sheet make     # -> evals/datasets/judge_labels.xlsx (score column empty)
    python -m evals.runners.label_sheet read     # reads your scores -> evals/datasets/human_labels.jsonl
Then: python -m evals.runners.judge_calibration report
"""
from __future__ import annotations

import json
import sys
import time

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from evals.runners.harness import ROOT

DS = ROOT / "evals" / "datasets"
XLSX = DS / "judge_labels.xlsx"
RUBRIC = [
    ("5", "Excellent: specific to this client's problem, concrete past work, answers the questions, good length, ends with a question"),
    ("4", "Good: one clear weakness"),
    ("3", "Acceptable: fine, but generic in places"),
    ("2", "Weak: mostly generic or padded"),
    ("1", "Bad: irrelevant, spammy or unsafe"),
]


def make() -> None:
    items = [json.loads(x) for x in (DS / "judge_items.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    wb = Workbook()
    ws = wb.active
    ws.title = "Score here"
    ws.append(["ID", "Job (what the client asked)", "Proposal (what GigBid wrote)", "YOUR SCORE (1-5)"])
    for it in items:
        ws.append([it["id"], it["job"], it["proposal"], None])
    widths = {"A": 6, "B": 55, "C": 80, "D": 16}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[1]:
        cell.font = Font(bold=True)
    yellow = PatternFill("solid", fgColor="FFF2CC")
    for r in range(2, len(items) + 2):
        ws[f"D{r}"].fill = yellow
        ws[f"D{r}"].alignment = Alignment(horizontal="center", vertical="center")
    dv = DataValidation(type="whole", operator="between", formula1="1", formula2="5", showErrorMessage=True,
                        error="Enter a whole number from 1 to 5", errorTitle="Score 1-5")
    ws.add_data_validation(dv)
    dv.add(f"D2:D{len(items) + 1}")
    ws.freeze_panes = "B2"
    rub = wb.create_sheet("How to score")
    rub.append(["Score", "Meaning"])
    for s, m in RUBRIC:
        rub.append([s, m])
    rub.append([])
    rub.append(["Tip", "Read the job first, then the proposal. Judge only the text. Do not look at what the AI judge said."])
    rub.column_dimensions["A"].width = 8
    rub.column_dimensions["B"].width = 110
    wb.save(XLSX)
    print(f"wrote {XLSX}")


def read() -> None:
    ws = load_workbook(XLSX)["Score here"]
    out, missing = [], []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:
            continue
        if row[3] in (None, ""):
            missing.append(row[0])
            continue
        s = int(row[3])
        if not 1 <= s <= 5:
            raise SystemExit(f"{row[0]}: score must be 1-5")
        out.append({"id": row[0], "score": s, "ts": time.time(), "source": "judge_labels.xlsx"})
    (DS / "human_labels.jsonl").write_text("\n".join(json.dumps(o) for o in out), encoding="utf-8")
    print(f"{len(out)} labels saved; missing: {missing or 'none'}")


if __name__ == "__main__":
    {"make": make, "read": read}[sys.argv[1] if len(sys.argv) > 1 else "make"]()
