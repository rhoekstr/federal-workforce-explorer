"""Derived-measure evaluator: three patterns over a DuckDB facts table (Evince A17, simplified).

Facts live in a table `facts(measure, node, period_type, period_start, dim, dim_value, value, n, notation, source_ref)`.
Derived measures are evaluated in dependency order; each result is inserted into the same table so later measures
can use it. Only flat facts (dim IS NULL) participate in calculations.

Cadence reconciliation: a component at a finer cadence than the derived measure is aggregated to the derived cadence
by the component's own aggregation rule (sum, latest, average). Periods with fewer sub-periods than expected are
notated `incomplete`. A component at a coarser cadence than the derived measure is not spread downward; the derived
value is `not_available` there (disaggregation deliberately dropped from Evince).
"""
from __future__ import annotations

import logging

import duckdb

from pipeline.measures.catalog import Catalog
from pipeline.measures.periods import periods_per_year

log = logging.getLogger(__name__)
ORDER = {"month": 0, "quarter": 1, "fiscal_year": 2, "survey_year": 2}
SCALE = {"percentage": 100.0, "rate": 1000.0}


def _containing_sql(target: str) -> str:
    """SQL mapping a period_start (ISO string) to the start of its containing target period."""
    if target == "quarter":
        return (
            "CASE WHEN CAST(substr(period_start,6,2) AS INTEGER) IN (10,11,12) THEN substr(period_start,1,4) || '-10-01' "
            "WHEN CAST(substr(period_start,6,2) AS INTEGER) <= 3 THEN substr(period_start,1,4) || '-01-01' "
            "WHEN CAST(substr(period_start,6,2) AS INTEGER) <= 6 THEN substr(period_start,1,4) || '-04-01' "
            "ELSE substr(period_start,1,4) || '-07-01' END"
        )
    if target == "fiscal_year":
        return "CASE WHEN CAST(substr(period_start,6,2) AS INTEGER) >= 10 THEN substr(period_start,1,4) || '-10-01' ELSE CAST(CAST(substr(period_start,1,4) AS INTEGER) - 1 AS VARCHAR) || '-10-01' END"
    if target == "survey_year":
        return "substr(period_start,1,4) || '-01-01'"
    raise ValueError(target)


def _shift_sql(period_type: str, offset: int) -> str:
    """SQL shifting period_start by `offset` periods of `period_type`."""
    if offset == 0:
        return "period_start"
    months = {"month": 1, "quarter": 3, "fiscal_year": 12, "survey_year": 12}[period_type] * offset
    return f"strftime(CAST(period_start AS DATE) + INTERVAL ({months}) MONTH, '%Y-%m-%d')"


class Evaluator:
    def __init__(self, con: duckdb.DuckDBPyConnection, catalog: Catalog):
        self.con = con
        self.catalog = catalog

    def component_view(self, name: str, comp: dict, target_cadence: str) -> None:
        """Create a temp view `name` with (node, period_start, value, notation) for a component at the target cadence, shifted."""
        m = self.catalog.measures[comp["measure"]]
        src_cadence = m["cadence"]
        offset = comp.get("offset", 0)
        carry = comp.get("carry_forward", 0)
        if ORDER[src_cadence] == ORDER[target_cadence] and carry:
            # Carry the last observed value forward up to `carry` periods (quarterly snapshots serving monthly rates).
            step = {"month": 1, "quarter": 3, "fiscal_year": 12, "survey_year": 12}[src_cadence]
            base = f"""
            WITH obs AS (SELECT node, CAST(period_start AS DATE) AS d, value, notation FROM facts WHERE measure = '{comp['measure']}' AND dim IS NULL AND period_type = '{src_cadence}'),
            spans AS (SELECT node, min(d) AS lo, max(d) AS hi FROM obs GROUP BY node),
            grid AS (SELECT node, unnest(generate_series(lo, hi, INTERVAL {step} MONTH)) AS d FROM spans),
            filled AS (SELECT g.node, g.d, o.value, o.notation, o.d AS od FROM grid g ASOF LEFT JOIN obs o ON g.node = o.node AND g.d >= o.d)
            SELECT node, strftime(d, '%Y-%m-%d') AS period_start, value, notation FROM filled WHERE od IS NOT NULL AND d <= od + INTERVAL {carry * step} MONTH
            """
        elif ORDER[src_cadence] == ORDER[target_cadence]:
            base = f"SELECT node, period_start, value, notation FROM facts WHERE measure = '{comp['measure']}' AND dim IS NULL AND period_type = '{src_cadence}'"
        elif ORDER[src_cadence] < ORDER[target_cadence]:
            agg = m["aggregation"]
            expected = periods_per_year(src_cadence) // periods_per_year(target_cadence)
            if agg == "sum":
                val = "sum(value)"
            elif agg == "average":
                val = "avg(value)"
            else:  # latest
                val = "arg_max(value, period_start)"
            base = f"""
            SELECT node, {_containing_sql(target_cadence)} AS period_start, {val} AS value,
                   CASE WHEN count(*) < {expected} THEN 'incomplete' WHEN bool_or(notation IS NOT NULL) THEN max(notation) ELSE NULL END AS notation
            FROM facts WHERE measure = '{comp['measure']}' AND dim IS NULL AND period_type = '{src_cadence}'
            GROUP BY node, {_containing_sql(target_cadence)}
            """
        else:
            base = "SELECT NULL::VARCHAR AS node, NULL::VARCHAR AS period_start, NULL::DOUBLE AS value, NULL::VARCHAR AS notation WHERE FALSE"
        shifted = f"SELECT node, {_shift_sql(target_cadence, -offset)} AS period_start, value, notation FROM ({base}) s"
        # A value observed at period p with offset k serves the derived period p - k: shift by -offset.
        self.con.execute(f"CREATE OR REPLACE TEMP VIEW {name} AS {shifted}")

    def evaluate(self, code: str) -> int:
        m = self.catalog.measures[code]
        calc = m["calculation"]
        cadence = m["cadence"]
        comps = self.catalog.components(code)
        levels_sql = ", ".join(f"'{l}'" for l in m["levels"])
        self.con.execute(f"DELETE FROM facts WHERE measure = '{code}'")
        scale = SCALE.get(m["unit"], 1.0)
        pattern = calc["pattern"]
        if pattern == "ratio":
            self.component_view("num", comps[0], cadence)
            self.component_view("den", comps[1], cadence)
            sql = f"""
            INSERT INTO facts
            SELECT '{code}', n.node, '{cadence}', n.period_start, NULL, NULL,
                   CASE WHEN d.value IS NULL OR d.value = 0 THEN NULL ELSE n.value / d.value * {scale} END,
                   CAST(round(d.value) AS BIGINT),
                   CASE WHEN d.value IS NULL OR d.value = 0 THEN 'not_available' ELSE coalesce(n.notation, d.notation{", '" + m['notation_default'] + "'" if m.get('notation_default') else ''}) END,
                   'derived'
            FROM num n LEFT JOIN den d ON n.node = d.node AND n.period_start = d.period_start
            JOIN nodes k ON k.code = n.node AND k.kind IN ({levels_sql})
            """
        elif pattern == "additive":
            terms = calc["terms"]
            for i, t in enumerate(terms):
                self.component_view(f"t{i}", {"measure": t["measure"], "offset": t.get("offset", 0)}, cadence)
            union = " UNION ALL ".join(f"SELECT node, period_start, value * ({t.get('sign', 1)}) AS value, notation, {i} AS term FROM t{i}" for i, t in enumerate(terms))
            sql = f"""
            INSERT INTO facts
            SELECT '{code}', u.node, '{cadence}', u.period_start, NULL, NULL,
                   CASE WHEN count(DISTINCT term) < {len(terms)} THEN NULL ELSE sum(value) * {scale if m['unit'] in SCALE else 1.0} END,
                   NULL,
                   CASE WHEN count(DISTINCT term) < {len(terms)} THEN 'not_available' WHEN bool_or(notation IS NOT NULL) THEN max(notation) ELSE NULL END,
                   'derived'
            FROM ({union}) u JOIN nodes k ON k.code = u.node AND k.kind IN ({levels_sql})
            GROUP BY u.node, u.period_start
            """
        else:  # time_offset
            self.component_view("src", comps[0], cadence)
            sql = f"""
            INSERT INTO facts
            SELECT '{code}', s.node, '{cadence}', s.period_start, NULL, NULL, s.value, NULL, s.notation, 'derived'
            FROM src s JOIN nodes k ON k.code = s.node AND k.kind IN ({levels_sql})
            """
        self.con.execute(sql)
        # Offsets can project a derived period past the data; keep derived periods within the observed base range.
        self.con.execute(
            f"DELETE FROM facts WHERE measure = '{code}' AND period_start > (SELECT coalesce(max(period_start), '9999') FROM facts WHERE source_ref <> 'derived' AND period_type = '{cadence}')"
        )
        n = self.con.execute(f"SELECT count(*) FROM facts WHERE measure = '{code}'").fetchone()[0]
        return n

    def evaluate_all(self) -> dict[str, int]:
        out = {}
        for code in self.catalog.evaluation_order():
            out[code] = self.evaluate(code)
            log.info("derived %s: %d rows", code, out[code])
        return out
