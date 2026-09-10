"""data/slices/geo/{code}.json: where a node's employees are, by county FIPS and state (ENHANCEMENT-PLAN E2).

Precomputed for government, departments, and agencies. Sub-elements are computed in the browser with DuckDB
from the same fact table and the same duty station lookup, so the two paths agree by construction.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict

import duckdb

from pipeline import manifest as mf
from pipeline.config import NOT_DISCLOSED, SLICES
from pipeline.fwd.facts import fact_path
from pipeline.fwd.lookups import load_lookup

log = logging.getLogger(__name__)
GEO_DIR = SLICES / "geo"


def classify(ds: dict | None) -> tuple[str, str | None, str | None]:
    """(bucket, fips, state) for one duty station lookup entry: bucket is county | abroad | invalid | nds."""
    if ds is None:
        return "invalid", None, None
    if ds.get("name") == "Not disclosed":
        return "nds", None, None
    cc, fips, st = ds.get("cc"), ds.get("fips"), ds.get("st")
    if cc and cc != "US":
        return "abroad", None, None
    if fips and len(fips) == 5 and fips.isdigit() and st and st != "*":
        return "county", fips, st
    if cc == "US" and ds.get("name") and ds.get("name") != "INVALID":
        return "territory", None, None  # Puerto Rico, Guam, and similar: disclosed, but OPM gives no county FIPS
    return "invalid", None, st


def build_geo() -> dict:
    months = sorted(mf.load()["datasets"].get("employment", {}))
    latest = months[-1]
    duty = load_lookup("duty_station")
    agency = load_lookup("agency")
    dept_of = {code: v["department_code"] for code, v in agency.items()}
    con = duckdb.connect()
    rows = con.execute(
        f"SELECT substr(org_code, 1, 2) AS agency_code, duty_station_code, sum(n) FROM read_parquet('{fact_path('employment', latest)}') GROUP BY 1, 2"
    ).fetchall()
    nodes: dict[str, dict] = defaultdict(lambda: {"n": 0, "disclosed": 0, "abroad": 0, "territory": 0, "invalid": 0, "counties": defaultdict(int), "states": defaultdict(int)})
    for agency_code, code, n in rows:
        n = int(n)
        bucket, fips, st = classify(duty.get(code)) if code != NOT_DISCLOSED else ("nds", None, None)
        targets = ["gov", agency_code]
        dept = dept_of.get(agency_code)
        if dept and dept != agency_code:
            targets.append(f"D:{dept}")
        for t in targets:
            node = nodes[t]
            node["n"] += n
            if bucket == "county":
                node["disclosed"] += n
                node["counties"][fips] += n
                node["states"][st] += n
            elif bucket == "abroad":
                node["disclosed"] += n
                node["abroad"] += n
            elif bucket == "territory":
                node["disclosed"] += n
                node["territory"] += n
            elif bucket == "invalid":
                node["invalid"] += n
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    for stale in GEO_DIR.glob("*.json"):
        stale.unlink()
    total = 0
    for code, node in nodes.items():
        payload = {
            "code": code,
            "month": latest,
            "n": node["n"],
            "disclosed": node["disclosed"],
            "disclosed_share": round(node["disclosed"] / node["n"], 4) if node["n"] else None,
            "abroad": node["abroad"],
            "territory": node["territory"],
            "invalid": node["invalid"],
            "counties": dict(sorted(node["counties"].items())),
            "states": dict(sorted(node["states"].items())),
        }
        path = GEO_DIR / f"{code}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")))
        total += path.stat().st_size
    log.info("geo: %d nodes, %.1f MB, latest %s", len(nodes), total / 1e6, latest)
    return {"nodes": len(nodes), "bytes": total}
