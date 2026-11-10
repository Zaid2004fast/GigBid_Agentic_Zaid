"""Spreadsheet version of the blind pairwise panel (easier for classmates than a CSV).

    python -m evals.runners.panel_sheet make    # -> evals/datasets/pairwise_panel.xlsx
    python -m evals.runners.panel_sheet read <file1.xlsx> [file2.xlsx ...]   # -> pairwise_panel_votes.csv, then `panel score`
"""
from __future__ import annotations

import csv
import sys

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from evals.runners.harness import ROOT

DS = ROOT / "evals" / "datasets"


def make() -> None:
    rows = list(csv.DictReader((DS / "pairwise_panel.csv").open(encoding="utf-8")))
    wb = Workbook()
    ws = wb.active
    ws.title = "Vote here"
    ws.append(["ID", "Job", "Proposal A", "Proposal B", "YOUR VOTE (A or B)"])
    for r in rows:
        ws.append([r["id"], r["job"], r["proposal_A"], r["proposal_B"], None])
    for col, w in zip("ABCDE", [6, 45, 60, 60, 16]):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for c in ws[1]:
        c.font = Font(bold=True)
    dv = DataValidation(type="list", formula1='"A,B"', showErrorMessage=True)
    ws.add_data_validation(dv)
    dv.add(f"E2:E{len(rows) + 1}")
    for i in range(2, len(rows) + 2):
        ws[f"E{i}"].fill = PatternFill("solid", fgColor="FFF2CC")
    h = wb.create_sheet("Instructions")
    h.column_dimensions["A"].width = 120
    for t in ["For each row, read the job, then both proposals.",
              "Pick the proposal you would be more likely to reply to if you were the client. Write A or B in the yellow column.",
              "The two proposals were written by two different systems, in random order.",
              "Save the file and send it back. Thank you!"]:
        h.append([t])
    wb.save(DS / "pairwise_panel.xlsx")
    print(f"wrote {DS / 'pairwise_panel.xlsx'} ({len(rows)} pairs)")


def read(files: list[str]) -> None:
    out = []
    for f in files:
        for row in load_workbook(f)["Vote here"].iter_rows(min_row=2, values_only=True):
            if row[0] and row[4] and str(row[4]).strip().upper() in ("A", "B"):
                out.append({"id": row[0], "vote": str(row[4]).strip().upper(), "rater": f})
    with (DS / "pairwise_panel_votes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "vote", "rater"])
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} votes from {len(files)} rater(s)")


if __name__ == "__main__":
    make() if sys.argv[1:2] in (["make"], []) else read(sys.argv[2:])
