"""Periods: month, fiscal quarter, fiscal year, survey year. Federal fiscal years start in October.

A period is (period_type, period_start) with period_start an ISO date string. Offsets move a period by whole
periods of its own type. A lagged result is dated to the period it describes (Evince decision 64).
"""
from __future__ import annotations

from datetime import date

PERIOD_TYPES = ("month", "quarter", "fiscal_year", "survey_year")


def month_start(yyyymm: str) -> str:
    return f"{yyyymm[:4]}-{yyyymm[4:6]}-01"


def yyyymm_of(period_start: str) -> str:
    return period_start[:4] + period_start[5:7]


def fiscal_year_of(d: date) -> int:
    return d.year + 1 if d.month >= 10 else d.year


def fiscal_year_start(fy: int) -> str:
    return f"{fy - 1}-10-01"


def fiscal_quarter_start(fy: int, quarter: int) -> str:
    month = {1: 10, 2: 1, 3: 4, 4: 7}[quarter]
    year = fy - 1 if quarter == 1 else fy
    return f"{year}-{month:02d}-01"


def survey_year_start(year: int) -> str:
    return f"{year}-01-01"


def shift(period_type: str, period_start: str, offset: int) -> str:
    """Move a period by `offset` periods of its type (negative = earlier)."""
    y, m = int(period_start[:4]), int(period_start[5:7])
    if period_type == "month":
        idx = y * 12 + (m - 1) + offset
        return f"{idx // 12}-{idx % 12 + 1:02d}-01"
    if period_type == "quarter":
        idx = y * 12 + (m - 1) + 3 * offset
        return f"{idx // 12}-{idx % 12 + 1:02d}-01"
    if period_type in ("fiscal_year", "survey_year"):
        return f"{y + offset}-{m:02d}-01"
    raise ValueError(period_type)


def containing(period_type: str, period_start: str) -> dict[str, str]:
    """The coarser periods that contain a period start: used to aggregate months to quarters and years."""
    d = date.fromisoformat(period_start)
    fy = fiscal_year_of(d)
    fq = ((d.month - 10) % 12) // 3 + 1
    return {"quarter": fiscal_quarter_start(fy, fq), "fiscal_year": fiscal_year_start(fy), "survey_year": survey_year_start(d.year)}


def label(period_type: str, period_start: str) -> str:
    d = date.fromisoformat(period_start)
    if period_type == "month":
        return d.strftime("%b %Y")
    if period_type == "quarter":
        fy = fiscal_year_of(d)
        fq = ((d.month - 10) % 12) // 3 + 1
        return f"FY{fy} Q{fq}"
    if period_type == "fiscal_year":
        return f"FY{fiscal_year_of(d)}"
    return str(d.year)


def periods_per_year(period_type: str) -> int:
    return {"month": 12, "quarter": 4, "fiscal_year": 1, "survey_year": 1}[period_type]
