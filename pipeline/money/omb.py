"""OMB Analytical Perspectives Table 5-1: executive branch civilian FTE by agency, in thousands."""
from __future__ import annotations

import re

import openpyxl

from pipeline.config import REFERENCE

TABLE_FILE = REFERENCE / "omb_ap_fy2027_tables_5-1_to_5-3.xlsx"
SHEET = "Table 5-1"


def load_table_5_1() -> list[dict]:
    """Rows of {label, fy, fte, kind} with fte in persons (thousands × 1000) and kind actual|estimate."""
    ws = openpyxl.load_workbook(TABLE_FILE, read_only=True)[SHEET]
    years: list[int] = []
    kinds: list[str] = []
    out = []
    for row in ws.iter_rows(values_only=True):
        cells = [c for c in row if c is not None]
        if not cells:
            continue
        if not years and all(isinstance(c, int) and 2000 < c < 2100 for c in cells[:4]):
            years = list(cells[:4])
            continue
        if not kinds and isinstance(cells[0], str) and cells[0] == "Agency":
            # header row: 'Agency', 'Actual', 'Estimate', ...; actual covers the first two years
            kinds = ["actual", "actual", "estimate", "estimate"]
            continue
        if years and isinstance(cells[0], str) and len(cells) >= 5 and all(isinstance(c, (int, float)) for c in cells[1:5]):
            label = re.sub(r"\s+", " ", cells[0]).strip()
            for fy, kind, value in zip(years, kinds or ["actual"] * 4, cells[1:5]):
                out.append({"label": label, "fy": fy, "fte": int(round(value * 1000)), "kind": kind})
    if not out:
        raise RuntimeError(f"no FTE rows parsed from {TABLE_FILE.name}")
    return out


def fte_by_label() -> dict[str, dict[int, dict]]:
    """{label: {fy: {fte, kind}}}"""
    table: dict[str, dict[int, dict]] = {}
    for r in load_table_5_1():
        table.setdefault(r["label"], {})[r["fy"]] = {"fte": r["fte"], "kind": r["kind"]}
    return table
