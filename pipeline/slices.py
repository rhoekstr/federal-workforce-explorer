"""Pre-computed JSON slices so the site paints before DuckDB-WASM loads (PRD 5.7).

Files (all under data/slices/):
  series/gov.json            government-wide monthly headcount, accessions, separations by category
  series/{org_code}.json     the same per org node (department, agency, sub-element)
  mix/{org_code}.json        grade, step, age, pay band, series mix for the latest month, plus disclosure share
  months.json                which months exist per dataset
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict

import duckdb

from pipeline import manifest as mf
from pipeline.config import NOT_DISCLOSED, SLICES, WORK
from pipeline.fwd.facts import fact_path
from pipeline.fwd.lookups import load_lookup

log = logging.getLogger(__name__)
SERIES_DIR = SLICES / "series"
MIX_DIR = SLICES / "mix"
MIX_DIMS = ("grade", "step_code", "age_bracket", "pay_band", "series_code", "supervisory_code", "work_schedule_code", "appointment_type_code")
TOP_N = 25


def _months(manifest: dict) -> dict[str, list[str]]:
    return {ds: sorted(v.keys()) for ds, v in manifest["datasets"].items()}


def _write(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")))


def _node_exprs() -> list[tuple[str, str]]:
    """(level, SQL expression producing the node code) for sub-element, agency, department, and government."""
    return [
        ("org", "org_code"),
        ("agency", "substr(org_code, 1, 2)"),
    ]


def build_series(con: duckdb.DuckDBPyConnection, months: dict[str, list[str]], org: dict) -> int:
    """Headcount per month and actions per effective month, for every node. Returns node count."""
    # node -> {yyyymm: headcount}
    headcount: dict[str, dict[str, int]] = defaultdict(dict)
    for m in months.get("employment", []):
        for level, expr in _node_exprs():
            for code, n in con.execute(f"SELECT {expr}, sum(n) FROM read_parquet('{fact_path('employment', m)}') GROUP BY 1").fetchall():
                headcount[code][m] = int(n)
        headcount["gov"][m] = int(con.execute(f"SELECT sum(n) FROM read_parquet('{fact_path('employment', m)}')").fetchone()[0])
    # department nodes: sum of agencies that belong to them (Defense is the only multi-agency department)
    agency_lookup = load_lookup("agency")
    dept_of = {code: v["department_code"] for code, v in agency_lookup.items()}
    for code in list(headcount):
        if len(code) == 2 and code in dept_of and dept_of[code] != code:
            for m, n in headcount[code].items():
                headcount[dept_of[code]][m] = headcount[dept_of[code]].get(m, 0) + n

    actions: dict[str, dict[str, dict[str, dict[str, int]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for dataset, cat in (("accessions", "accession_category_code"), ("separations", "separation_category_code")):
        for m in months.get(dataset, []):
            for level, expr in _node_exprs() + [("gov", "'gov'")]:
                rows = con.execute(
                    f"SELECT {expr}, effective_yyyymm, {cat}, sum(n) FROM read_parquet('{fact_path(dataset, m)}') GROUP BY 1, 2, 3"
                ).fetchall()
                for code, eff, c, n in rows:
                    node = actions[code][dataset]
                    node[eff][c] = node[eff].get(c, 0) + int(n)
            if dataset == "separations":
                for level, expr in _node_exprs() + [("gov", "'gov'")]:
                    rows = con.execute(
                        f"SELECT {expr}, effective_yyyymm, sum(n) FROM read_parquet('{fact_path(dataset, m)}') WHERE drp_indicator = 'Y' GROUP BY 1, 2"
                    ).fetchall()
                    for code, eff, n in rows:
                        node = actions[code]["separations"]
                        node[eff]["DRP"] = node[eff].get("DRP", 0) + int(n)
    for code in list(actions):
        if len(code) == 2 and code in dept_of and dept_of[code] != code:
            for dataset, by_eff in actions[code].items():
                for eff, cats in by_eff.items():
                    tgt = actions[dept_of[code]][dataset][eff]
                    for c, n in cats.items():
                        tgt[c] = tgt.get(c, 0) + n

    all_months = sorted(set(months.get("employment", [])))
    for code in set(headcount) | set(actions):
        _write(SERIES_DIR / f"{code}.json", {
            "code": code,
            "months": all_months,
            "headcount": headcount.get(code, {}),
            "accessions": actions.get(code, {}).get("accessions", {}),
            "separations": actions.get(code, {}).get("separations", {}),
        })
    return len(set(headcount) | set(actions))


def build_mix(con: duckdb.DuckDBPyConnection, latest: str) -> int:
    fact = fact_path("employment", latest)
    con.execute(f"CREATE OR REPLACE VIEW f AS SELECT * FROM read_parquet('{fact}')")
    nodes = 0
    for level, expr in _node_exprs() + [("gov", "'gov'")]:
        mixes: dict[str, dict] = defaultdict(dict)
        for dim in MIX_DIMS:
            rows = con.execute(f"SELECT {expr} AS node, {dim}, sum(n) AS n FROM f GROUP BY 1, 2").fetchall()
            per_node: dict[str, list] = defaultdict(list)
            for node, value, n in rows:
                per_node[node].append((value, int(n)))
            for node, items in per_node.items():
                items.sort(key=lambda t: -t[1])
                mixes[node][dim] = dict(items[:TOP_N]) | ({"_other": sum(n for _, n in items[TOP_N:])} if len(items) > TOP_N else {})
        disclosed = con.execute(
            f"SELECT {expr}, sum(n), sum(CASE WHEN duty_station_code <> '{NOT_DISCLOSED}' THEN n ELSE 0 END), sum(pay_sum), sum(pay_n), sum(los_sum) FROM f GROUP BY 1"
        ).fetchall()
        for node, n, disc, pay_sum, pay_n, los_sum in disclosed:
            mixes[node]["_summary"] = {
                "month": latest,
                "n": int(n),
                "disclosed_location_share": round(disc / n, 4) if n else None,
                "avg_pay": round(pay_sum / pay_n) if pay_n else None,
                "pay_disclosed_share": round(pay_n / n, 4) if n else None,
                "avg_los": round(los_sum / n, 1) if n else None,
            }
        for node, mix in mixes.items():
            _write(MIX_DIR / f"{node}.json", mix)
            nodes += 1
    return nodes


def build_slices() -> None:
    manifest = mf.load()
    months = _months(manifest)
    con = duckdb.connect()
    SLICES.mkdir(parents=True, exist_ok=True)
    org = load_lookup("org")
    n_series = build_series(con, months, org)
    latest = months["employment"][-1]
    n_mix = build_mix(con, latest)
    _write(SLICES / "months.json", {"datasets": months, "latest": latest})
    log.info("slices: %d series nodes, %d mix nodes, latest %s", n_series, n_mix, latest)
