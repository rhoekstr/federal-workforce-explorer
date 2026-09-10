"""overview/agency_period: people beside money per overview group (PRD 5.8)."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date

import duckdb

from pipeline import manifest as mf
from pipeline.config import SLICES, WORK
from pipeline.fwd.lookups import load_lookup
from pipeline.money.groups import load_groups
from pipeline.money.omb import fte_by_label
from pipeline.money.usaspending import fetch_fileb, classified

log = logging.getLogger(__name__)
OVERVIEW_DIR = WORK.parent / "overview"


def latest_closed_quarter(today: date | None = None) -> tuple[int, int]:
    """(fiscal year, quarter) of the most recent quarter that has ended."""
    today = today or date.today()
    fy = today.year + (1 if today.month >= 10 else 0)
    fq = ((today.month - 10) % 12) // 3 + 1  # current fiscal quarter
    if fq == 1:
        return fy - 1, 4
    return fy, fq - 1


def quarter_end_yyyymm(fy: int, quarter: int) -> str:
    month = {1: 12, 2: 3, 3: 6, 4: 9}[quarter]
    year = fy - 1 if quarter == 1 else fy
    return f"{year}{month:02d}"


def _sum_buckets(rows) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for agency, bucket, value in rows:
        out[agency][bucket] += value
    return out


def rolling_four_quarters(fy: int, quarter: int, force: bool = False) -> dict[str, dict[str, float]]:
    """rolling(Y,P) = YTD(Y,P) + YTD(Y-1,12) - YTD(Y-1,P), per agency name and bucket."""
    for f, q in ((fy, quarter), (fy - 1, 4), (fy - 1, quarter)):
        fetch_fileb(f, q, force=force)
    cur = _sum_buckets(classified(fy, quarter))
    prior_full = _sum_buckets(classified(fy - 1, 4))
    prior_same = _sum_buckets(classified(fy - 1, quarter))
    out: dict[str, dict[str, float]] = {}
    for agency in set(cur) | set(prior_full) | set(prior_same):
        buckets = set(cur.get(agency, {})) | set(prior_full.get(agency, {})) | set(prior_same.get(agency, {}))
        out[agency] = {
            b: cur.get(agency, {}).get(b, 0.0) + prior_full.get(agency, {}).get(b, 0.0) - prior_same.get(agency, {}).get(b, 0.0)
            for b in buckets
        }
    return out


def _group_headcount(group: dict, org: dict, agency: dict, yyyymm: str) -> int | None:
    total = 0
    found = False
    for code in group["fwd_agency_codes"]:
        n = agency.get(code, {}).get("headcount", {}).get(yyyymm)
        if n is not None:
            total += n
            found = True
    for code in group.get("fwd_org_codes", []):
        n = org.get(code, {}).get("headcount", {}).get(yyyymm)
        if n is not None:
            total += n
            found = True
    for code in group.get("fwd_exclude_org_codes", []):
        n = org.get(code, {}).get("headcount", {}).get(yyyymm)
        if n is not None:
            total -= n
    return total if found else None


def _months_available(agency: dict) -> list[str]:
    months = set()
    for v in agency.values():
        months.update(v.get("headcount", {}).keys())
    return sorted(months)


def _shift_12(yyyymm: str) -> str:
    return f"{int(yyyymm[:4]) - 1}{yyyymm[4:]}"


def build_overview(force: bool = False, today: date | None = None) -> list[dict]:
    fy, quarter = latest_closed_quarter(today)
    period = f"FY{fy}Q{quarter}"
    log.info("overview period %s", period)
    money = rolling_four_quarters(fy, quarter, force=force)
    fte = fte_by_label()
    groups = load_groups()
    org, agency = load_lookup("org"), load_lookup("agency")
    months = _months_available(agency)
    latest = months[-1] if months else None
    qend = quarter_end_yyyymm(fy, quarter)
    if qend not in months and months:
        qend = max(m for m in months if m <= qend) if any(m <= qend for m in months) else months[0]

    rows = []
    for gid, g in groups.items():
        buckets: dict[str, float] = defaultdict(float)
        for name in g["usaspending_names"]:
            for b, v in money.get(name, {}).items():
                buckets[b] += v
        personnel = buckets.get("personnel", 0.0)
        contracted = buckets.get("contracted", 0.0)
        federal_services = buckets.get("federal_services", 0.0)
        administered = buckets.get("administered", 0.0)
        operations = personnel + contracted + federal_services + buckets.get("operations_other", 0.0)
        other = buckets.get("other", 0.0)
        has_money = bool(g["usaspending_names"]) and any(buckets.values())
        headcount = _group_headcount(g, org, agency, qend) if qend else None
        headcount_latest = _group_headcount(g, org, agency, latest) if latest else None
        prior = _group_headcount(g, org, agency, _shift_12(latest)) if latest else None
        fte_rows = {}
        for label in g["omb_labels"]:
            for y, v in fte.get(label, {}).items():
                fte_rows[y] = {"fte": fte_rows.get(y, {}).get("fte", 0) + v["fte"], "kind": v["kind"]}
        fte_fy = fte_rows.get(fy) or fte_rows.get(fy - 1)
        rows.append({
            "group": gid,
            "name": g["name"],
            "period": period,
            "quarter_end_yyyymm": qend,
            "latest_yyyymm": latest,
            "headcount": headcount,
            "headcount_latest": headcount_latest,
            "headcount_change_12m": (headcount_latest - prior) if (headcount_latest is not None and prior is not None) else None,
            "fte_omb": fte_fy["fte"] if fte_fy else None,
            "fte_omb_kind": fte_fy["kind"] if fte_fy else None,
            "fte_omb_fy": fy if fy in fte_rows else (fy - 1 if (fy - 1) in fte_rows else None),
            "fte_series": {str(y): v for y, v in sorted(fte_rows.items())},
            "personnel": personnel if has_money else None,
            "contracted_services": contracted if has_money else None,
            "federal_services": federal_services if has_money else None,
            "insourcing_ratio": (personnel / (personnel + contracted)) if has_money and (personnel + contracted) > 0 else None,
            "administered": administered if has_money else None,
            "operations": operations if has_money else None,
            "other": other if has_money else None,
            "total_obligations": (administered + operations + other) if has_money else None,
            "personnel_per_head": (personnel / headcount) if has_money and headcount else None,
            "money_reason": None if has_money else ("no USAspending agency mapped" if not g["usaspending_names"] else "no obligations reported"),
        })
    rows.sort(key=lambda r: -(r["headcount_latest"] or 0))
    OVERVIEW_DIR.mkdir(parents=True, exist_ok=True)
    SLICES.mkdir(parents=True, exist_ok=True)
    tmp = OVERVIEW_DIR / "agency_period.jsonl"
    with open(tmp, "w") as fh:
        for r in rows:
            fh.write(json.dumps({**r, "fte_series": json.dumps(r["fte_series"])}) + "\n")
    duckdb.connect().execute(f"COPY (SELECT * FROM read_json_auto('{tmp}')) TO '{OVERVIEW_DIR / 'agency_period.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    tmp.unlink()
    (SLICES / "overview.json").write_text(json.dumps({"period": period, "quarter_end_yyyymm": qend, "latest_yyyymm": latest, "rows": rows}, separators=(",", ":")))
    manifest = mf.load()
    manifest["money"] = {"period": period, "fy": fy, "quarter": quarter, "fileb_periods": [f"FY{fy}Q{quarter}", f"FY{fy-1}Q4", f"FY{fy-1}Q{quarter}"], "omb_table": "AP FY2027 Table 5-1", "groups": len(rows)}
    mf.save(manifest)
    log.info("overview: %d groups, %d with money", len(rows), sum(1 for r in rows if r["personnel"] is not None))
    return rows
