"""Cross-source reconciliation: a standing report, not a gate.

Fed Pulse now carries six sources and ninety-odd measures, and nothing compares them to each other. These
sources measure genuinely different things — full-time equivalents are not people, a survey respondent is not
an employee, an appropriation is not a payroll — so disagreement is expected and is not an error. The value is
that an *unexplained* divergence becomes visible instead of sitting in the data unnoticed.

One check is a real invariant and is treated as one: agency headcount must sum to the government total.
"""
from __future__ import annotations

import json
import logging

import duckdb

from pipeline.config import ROOT
from pipeline.measures.build import OUT
from pipeline.measures.periods import label as period_label

log = logging.getLogger(__name__)
REPORT = ROOT / "docs" / "RECONCILIATION.md"
# Plausible band for personnel obligations per employee, in dollars. Outside this, something is mismatched.
PAY_BAND = (40_000, 400_000)

# Divergences with a known cause. A flag with an entry here is understood; a flag without one is not, and is
# what this report exists to surface.
EXPLAINED = {
    "state": "The workforce files exclude Foreign Service personnel, so State's payroll covers people its headcount does not.",
    "usaid": "The workforce files exclude Foreign Service personnel, and the group pools foreign assistance entities.",
    "gsa": "Most GSA staff are paid from revolving funds through reimbursable obligations, which this site excludes to avoid double counting across government.",
    "opm": "OPM's obligations under object class 25.2 are largely health-benefit payments to carriers rather than contracted labour, so its in-sourcing ratio reads far lower than its staffing implies.",
    "dod": "Defense's civilian headcount excludes service members, who are counted and paid separately.",
    "va": "VA's obligations include medical care purchased for veterans, which is programme spending rather than staff cost.",
}


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"CREATE OR REPLACE VIEW f AS SELECT * FROM read_parquet('{OUT}')")
    con.execute("CREATE OR REPLACE VIEW flat AS SELECT * FROM f WHERE dim IS NULL AND value IS NOT NULL")
    return con


def agency_sum_invariant(con) -> list[dict]:
    """Agency headcount must sum to the government total, every month. This one is exact."""
    rows = con.execute("""
        WITH agencies AS (
          SELECT period_start, sum(value) AS total FROM flat
          WHERE measure = 'headcount' AND node IN (SELECT code FROM nodes_t WHERE kind = 'agency')
          GROUP BY period_start),
        govt AS (SELECT period_start, value FROM flat WHERE measure = 'headcount' AND node = 'gov')
        SELECT g.period_start, g.value, a.total FROM govt g JOIN agencies a USING (period_start)
        WHERE abs(g.value - a.total) > 0.5 ORDER BY 1
    """).fetchall()
    return [{"period": p, "gov": int(g), "agency_sum": int(a), "diff": int(g - a)} for p, g, a in rows]


def omb_vs_headcount(con) -> list[dict]:
    """OMB full-time equivalents against September headcount for the same fiscal year."""
    rows = con.execute("""
        WITH fte AS (SELECT node, period_start, value FROM flat WHERE measure = 'omb_fte'),
        sept AS (SELECT node, period_start, value FROM flat WHERE measure = 'headcount' AND period_start LIKE '%-09-01')
        SELECT f.node, f.period_start, f.value,
               (SELECT s.value FROM sept s WHERE s.node = f.node
                 AND substr(s.period_start,1,4) = substr(f.period_start,1,4) LIMIT 1) AS head
        FROM fte f ORDER BY f.node, f.period_start
    """).fetchall()
    out = []
    for node, period, fte, head in rows:
        if head is None or not fte:
            continue
        ratio = head / fte
        if ratio < 0.75 or ratio > 1.35:
            out.append({"node": node, "fy": period[:4], "omb_fte": int(fte), "headcount": int(head), "ratio": round(ratio, 2)})
    return out


def plum_vs_ses(con) -> list[dict]:
    """PLUM leadership positions against the SES-grade workforce, per agency."""
    rows = con.execute("""
        SELECT p.node, p.value AS plum, h.value AS headcount
        FROM flat p JOIN flat h ON h.node = p.node AND h.measure = 'headcount'
          AND h.period_start = (SELECT max(period_start) FROM flat WHERE measure = 'headcount')
        WHERE p.measure = 'plum_positions'
          AND p.period_start = (SELECT max(period_start) FROM flat WHERE measure = 'plum_positions')
        ORDER BY p.value DESC
    """).fetchall()
    return [{"node": n, "plum_positions": int(p), "headcount": int(h), "per_1000": round(1000 * p / h, 1)}
            for n, p, h in rows if h and (1000 * p / h) > 40]


def pay_per_employee(con) -> list[dict]:
    """Personnel obligations divided by headcount, flagged outside a plausible band."""
    rows = con.execute("""
        SELECT node, period_start, value FROM flat WHERE measure = 'personnel_per_head'
          AND period_start = (SELECT max(period_start) FROM flat WHERE measure = 'personnel_per_head')
        ORDER BY value
    """).fetchall()
    return [{"node": n, "period": p, "per_employee": int(v)} for n, p, v in rows if v < PAY_BAND[0] or v > PAY_BAND[1]]


def survey_vs_headcount(con) -> list[dict]:
    """FEVS respondents against agency headcount in the survey year; a rate above 100% is impossible."""
    rows = con.execute("""
        SELECT s.node, s.period_start, s.n,
               (SELECT h.value FROM flat h WHERE h.node = s.node AND h.measure = 'headcount'
                 AND substr(h.period_start,1,4) = substr(s.period_start,1,4) ORDER BY h.period_start DESC LIMIT 1)
        FROM f s WHERE s.measure = 'fevs_engagement' AND s.n IS NOT NULL AND s.dim IS NULL
    """).fetchall()
    out = []
    for node, period, n, head in rows:
        if not head or not n:
            continue
        rate = n / head
        if rate > 1.0 or rate < 0.02:
            out.append({"node": node, "year": period[:4], "respondents": int(n), "headcount": int(head), "response_share": round(rate, 2)})
    return out


def build_report() -> dict:
    con = _con()
    nodes = json.loads((ROOT / "catalog" / "nodes.json").read_text())["nodes"]
    con.execute("CREATE OR REPLACE TABLE nodes_t (code VARCHAR, kind VARCHAR)")
    con.executemany("INSERT INTO nodes_t VALUES (?,?)", [(c, v["kind"]) for c, v in nodes.items()])
    name = lambda c: nodes.get(c, {}).get("name", c)  # noqa: E731

    checks = {
        "agency_sum": agency_sum_invariant(con),
        "omb": omb_vs_headcount(con),
        "plum": plum_vs_ses(con),
        "pay": pay_per_employee(con),
        "survey": survey_vs_headcount(con),
    }
    lines = [
        "# Cross-source reconciliation",
        "",
        "Regenerated by `python -m pipeline.cli reconcile`. **This is a report, not a gate.** Fed Pulse carries six",
        "sources that measure different things: full-time equivalents are not people, a survey respondent is not an",
        "employee, and an appropriation is not a payroll. Divergence is expected. What matters is that a divergence",
        "nobody can explain becomes visible here rather than sitting unnoticed in a chart.",
        "",
        "One check below is a true invariant and is treated as one.",
        "",
        "## 1. Agency headcount sums to the government total (invariant)",
        "",
    ]
    if checks["agency_sum"]:
        lines += ["**Failing.** Every month below should be exact and is not.", "",
                  "| Month | Government | Sum of agencies | Difference |", "|---|---|---|---|"]
        lines += [f"| {period_label('month', r['period'])} | {r['gov']:,} | {r['agency_sum']:,} | {r['diff']:+,} |" for r in checks["agency_sum"][:20]]
    else:
        lines.append("Exact for every month in the table. No agency headcount is double counted or dropped.")

    lines += ["", "## 2. OMB full-time equivalents against September headcount", "",
              "FTE counts paid hours; headcount counts people on the rolls. A part-time or seasonal workforce makes FTE",
              "lower than headcount, and OMB's agency coverage differs from OPM's. Rows outside 0.75 to 1.35 are listed.", ""]
    if checks["omb"]:
        lines += ["| Agency | FY | OMB FTE | Headcount | Headcount ÷ FTE |", "|---|---|---|---|---|"]
        lines += [f"| {name(r['node'])} | {r['fy']} | {r['omb_fte']:,} | {r['headcount']:,} | {r['ratio']} |" for r in checks["omb"][:25]]
    else:
        lines.append("Every agency falls inside the band.")

    lines += ["", "## 3. PLUM leadership positions per 1,000 employees", "",
              "Listed where a unit reports more than 40 leadership positions per 1,000 employees. A high rate is normal",
              "for a small policy office and worth a look for a large operating agency.", ""]
    if checks["plum"]:
        lines += ["| Unit | PLUM positions | Headcount | Per 1,000 |", "|---|---|---|---|"]
        lines += [f"| {name(r['node'])} | {r['plum_positions']:,} | {r['headcount']:,} | {r['per_1000']} |" for r in checks["plum"][:25]]
    else:
        lines.append("No unit exceeds the threshold.")

    lines += ["", "## 4. Personnel obligations per employee", "",
              f"Flagged outside ${PAY_BAND[0]:,} to ${PAY_BAND[1]:,}. Outside that band the money and the headcount are",
              "probably not describing the same population.", ""]
    if checks["pay"]:
        lines += ["| Group | Period | Per employee | Known cause |", "|---|---|---|---|"]
        lines += [f"| {name(r['node'])} | {period_label('quarter', r['period'])} | ${r['per_employee']:,} | {EXPLAINED.get(r['node'], '**unexplained**')} |" for r in checks["pay"][:25]]
    else:
        lines.append("Every group falls inside the band.")

    lines += ["", "## 5. FEVS respondents against headcount", "",
              "A response share above 100% is impossible and means the survey unit and the workforce unit are not the",
              "same population. Below 2% suggests a mismatch too.", ""]
    if checks["survey"]:
        lines += ["| Unit | Year | Respondents | Headcount | Share |", "|---|---|---|---|---|"]
        lines += [f"| {name(r['node'])} | {r['year']} | {r['respondents']:,} | {r['headcount']:,} | {r['response_share']} |" for r in checks["survey"][:25]]
    else:
        lines.append("Every surveyed unit falls inside the plausible range.")

    counts = {k: len(v) for k, v in checks.items()}
    unexplained = [r["node"] for r in checks["pay"] if r["node"] not in EXPLAINED]
    lines += ["", "## Summary", "",
              f"Flags by check: {json.dumps(counts)}",
              "",
              (f"Spending-per-employee flags without a known cause: {', '.join(name(n) for n in unexplained)}."
               if unexplained else "Every spending-per-employee flag has a known cause."),
              "",
              "This report found the defect that split military pay and retiree annuities out of the personnel measure:",
              "before that change, spending per employee read $1.2M at Defense and $2.6M at OPM.",
              ""]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")
    log.info("reconciliation: %s", counts)
    return counts
