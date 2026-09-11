"""Base facts from the non-FWD sources: USAspending (rolling four quarters per group), OMB FTE, FEVS."""
from __future__ import annotations

import csv
import logging
from datetime import date

from pipeline.config import REFERENCE
from pipeline.measures.periods import fiscal_quarter_start, fiscal_year_start, survey_year_start
from pipeline.money.groups import load_groups
from pipeline.money.omb import fte_by_label
from pipeline.money.overview import latest_closed_quarter, rolling_four_quarters
from pipeline.money.usaspending import fileb_path

log = logging.getLogger(__name__)
MONEY_BUCKETS = {
    "personnel_obligations": ("personnel",),
    "contracted_services_obligations": ("contracted",),
    "federal_services_obligations": ("federal_services",),
    "administered_obligations": ("administered",),
    "operations_obligations": ("personnel", "contracted", "federal_services", "operations_other"),
}
FIRST_FILEB = (2017, 2)  # File B object class data begins FY2017 Q2


def money_facts(first_fy: int = 2018, first_quarter: int = 2, today: date | None = None, fetch: bool = True) -> list[tuple]:
    """Rolling-four-quarter obligations per group for every closed quarter since FY2018Q2.
    Requires File B for the three quarters behind each period; missing pulls are skipped (not fetched) unless fetch=True."""
    groups = load_groups()
    fy_end, q_end = latest_closed_quarter(today)
    facts: list[tuple] = []
    fy, q = first_fy, first_quarter
    while (fy, q) <= (fy_end, q_end):
        needed = [(fy, q), (fy - 1, 4), (fy - 1, q)]
        if not fetch and not all(fileb_path(f, qq).exists() for f, qq in needed):
            fy, q = (fy, q + 1) if q < 4 else (fy + 1, 1)
            continue
        try:
            money = rolling_four_quarters(fy, q)
        except Exception as exc:  # noqa: BLE001
            log.warning("money FY%dQ%d skipped: %s", fy, q, exc)
            fy, q = (fy, q + 1) if q < 4 else (fy + 1, 1)
            continue
        period = fiscal_quarter_start(fy, q)
        ref = f"fileb:FY{fy}Q{q}"
        for gid, g in groups.items():
            buckets: dict[str, float] = {}
            for name in g["usaspending_names"]:
                for b, v in money.get(name, {}).items():
                    buckets[b] = buckets.get(b, 0.0) + v
            if not buckets:
                continue
            for measure, parts in MONEY_BUCKETS.items():
                facts.append((measure, gid, "quarter", period, None, None, float(sum(buckets.get(p, 0.0) for p in parts)), None, None, ref))
        fy, q = (fy, q + 1) if q < 4 else (fy + 1, 1)
    log.info("money: %d facts", len(facts))
    return facts


def omb_facts() -> list[tuple]:
    groups = load_groups()
    fte = fte_by_label()
    facts: list[tuple] = []
    for gid, g in groups.items():
        by_fy: dict[int, dict] = {}
        for label in g["omb_labels"]:
            for y, v in fte.get(label, {}).items():
                by_fy.setdefault(y, {"fte": 0, "kind": v["kind"]})["fte"] += v["fte"]
        for y, v in by_fy.items():
            facts.append(("omb_fte", gid, "fiscal_year", fiscal_year_start(y), None, None, float(v["fte"]), None, "estimate" if v["kind"] == "estimate" else None, "omb:AP-FY2027-T5-1"))
    log.info("omb: %d facts", len(facts))
    return facts


FEVS_COLUMNS = {
    "fevs_engagement": "eei",
    "fevs_global_satisfaction": "gsi",
    "fevs_performance_confidence": "pci",
    "fevs_leave_any": "leave_any",
    "fevs_leave_outside": "leave_outside",
    "fevs_leave_within": "leave_within",
    "fevs_leave_other": "leave_other",
    "fevs_pay_satisfaction": "pp_pay_sat",
    "fevs_recommend": "pp_recommend",
    "fevs_workload_reasonable": "pp_workload",
}


def fevs_facts() -> list[tuple]:
    path = REFERENCE / "fevs" / "fevs_agency_year.csv"
    facts: list[tuple] = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            agency = row["agency"]
            if agency == "XX":
                continue
            if agency == "ALL":
                agency = "gov"
            year = int(row["year"])
            n = int(float(row["n_resp"])) if row.get("n_resp") else None
            for measure, col in FEVS_COLUMNS.items():
                raw = row.get(col, "")
                if raw in ("", None):
                    continue
                facts.append((measure, agency, "survey_year", survey_year_start(year), None, None, float(raw), n, None, f"fevs:{year}-prdf"))
    log.info("fevs: %d facts", len(facts))
    return facts
