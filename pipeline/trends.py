"""data/slices/trend/{code}.json: monthly headcount broken down by dimension, per node (ENHANCEMENT-PLAN E1).

Scope: government, departments, agencies, and sub-elements with at least MIN_HEADCOUNT employees in the latest
month. Top TOP_VALUES values per dimension by latest-month headcount, the rest summed into "_other".
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict

import duckdb

from pipeline import manifest as mf
from pipeline.config import SLICES
from pipeline.fwd.facts import fact_path
from pipeline.fwd.lookups import load_lookup

log = logging.getLogger(__name__)
TREND_DIR = SLICES / "trend"
DIMS = ("grade", "age_bracket", "supervisory_code", "appointment_type_code", "pay_band", "work_schedule_code", "series_code", "step_code")
SUBELEMENT_DIMS = ("grade", "age_bracket", "supervisory_code", "appointment_type_code", "pay_band", "work_schedule_code")
MIN_HEADCOUNT = 500
TOP_VALUES = 8
BUDGET_BYTES = 15 * 1024 * 1024


def _months() -> list[str]:
    return sorted(mf.load()["datasets"].get("employment", {}))


def _nodes_in_scope(latest: str) -> tuple[set[str], set[str], dict[str, str]]:
    """(agency codes, sub-element codes in scope, department of each agency)."""
    agency = load_lookup("agency")
    org = load_lookup("org")
    dept_of = {code: v["department_code"] for code, v in agency.items()}
    subs = {code for code, v in org.items() if v.get("headcount", {}).get(latest, 0) >= MIN_HEADCOUNT}
    return set(agency), subs, dept_of


def _collect(con: duckdb.DuckDBPyConnection, months: list[str], subs: set[str], dept_of: dict[str, str]) -> dict:
    """{node: {dim: {value: {month: n}}}} for every node in scope."""
    data: dict[str, dict[str, dict[str, dict[str, int]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for m in months:
        fact = fact_path("employment", m)
        for dim in DIMS:
            rows = con.execute(f"SELECT org_code, {dim}, sum(n) FROM read_parquet('{fact}') GROUP BY 1, 2").fetchall()
            for org_code, value, n in rows:
                n = int(n)
                value = value if value not in (None, "") else "_blank"
                agency_code = org_code[:2]
                targets = ["gov", agency_code]
                dept = dept_of.get(agency_code)
                if dept and dept != agency_code:
                    targets.append(f"D:{dept}")
                if org_code in subs and dim in SUBELEMENT_DIMS:
                    targets.append(org_code)
                for t in targets:
                    slot = data[t][dim][value]
                    slot[m] = slot.get(m, 0) + n
    return data


def _top_values(by_value: dict[str, dict[str, int]], latest: str) -> dict[str, dict[str, int]]:
    ranked = sorted(by_value.items(), key=lambda kv: -kv[1].get(latest, 0))
    keep, other = ranked[:TOP_VALUES], ranked[TOP_VALUES:]
    out = {v: dict(sorted(series.items())) for v, series in keep}
    if other:
        merged: dict[str, int] = defaultdict(int)
        for _, series in other:
            for m, n in series.items():
                merged[m] += n
        out["_other"] = dict(sorted(merged.items()))
    return out


def build_trends() -> dict:
    months = _months()
    if not months:
        raise RuntimeError("no employment months in manifest")
    latest = months[-1]
    agencies, subs, dept_of = _nodes_in_scope(latest)
    con = duckdb.connect()
    data = _collect(con, months, subs, dept_of)
    TREND_DIR.mkdir(parents=True, exist_ok=True)
    for stale in TREND_DIR.glob("*.json"):
        stale.unlink()
    total = 0
    written = 0
    for node, dims in data.items():
        payload = {"code": node, "months": months, "latest": latest, "by": {dim: _top_values(values, latest) for dim, values in dims.items()}}
        path = TREND_DIR / f"{node}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")))
        total += path.stat().st_size
        written += 1
    log.info("trends: %d nodes (%d sub-elements >= %d), %.1f MB", written, len(subs), MIN_HEADCOUNT, total / 1e6)
    if total > BUDGET_BYTES:
        log.warning("trend slices exceed the %.0f MB budget: %.1f MB", BUDGET_BYTES / 1e6, total / 1e6)
    return {"nodes": written, "bytes": total, "subelements": len(subs)}
