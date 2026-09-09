"""FEVS agency-level index reports (Phase 2 data; the labels are used now for the crosswalk)."""
from __future__ import annotations

import openpyxl

from pipeline.config import REFERENCE

FEVS_DIR = REFERENCE / "fevs"
INDEX_FILES = {
    "engagement": ("2024-ee-report-excel.xlsx", "EEI"),
    "global_satisfaction": ("2024-gs-report-excel.xlsx", "Global Satisfaction"),
}


def _rows(filename: str, sheet: str) -> list[tuple]:
    path = FEVS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(path)
    ws = openpyxl.load_workbook(path, read_only=True)[sheet]
    return [r for r in ws.iter_rows(values_only=True) if r and r[0]]


def agency_labels() -> list[str]:
    header, *rows = _rows(*INDEX_FILES["engagement"])
    return [str(r[0]).strip() for r in rows if r[0] and "Overall" not in str(r[0]) and str(r[0]) != "Governmentwide"]


def index_by_label(index: str) -> dict[str, dict[int, float]]:
    """{label: {year: percentage}} for one index."""
    header, *rows = _rows(*INDEX_FILES[index])
    years = [int(str(h).split("_")[-1]) for h in header[2:] if h and str(h).startswith("percentage_")]
    out = {}
    for r in rows:
        label = str(r[0]).strip()
        vals = {}
        for y, v in zip(years, r[2 : 2 + len(years)]):
            try:
                vals[y] = round(float(v), 1)
            except (TypeError, ValueError):
                continue
        out[label] = vals
    return out
