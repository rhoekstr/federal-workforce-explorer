"""Measures model: catalog validation, evaluator patterns on synthetic series, cadence reconciliation, notation."""
from __future__ import annotations

import duckdb
import pytest

from pipeline.measures.catalog import Catalog, CatalogError
from pipeline.measures.evaluator import Evaluator
from pipeline.measures.periods import containing, label, shift

DIMS = {"dimensions": {}}


def _catalog(measures: dict) -> Catalog:
    return Catalog(measures, DIMS["dimensions"])


def _con(facts: list[tuple], nodes: list[tuple]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE TABLE facts (measure VARCHAR, node VARCHAR, period_type VARCHAR, period_start VARCHAR, dim VARCHAR, dim_value VARCHAR, value DOUBLE, n BIGINT, notation VARCHAR, source_ref VARCHAR)")
    con.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?)", facts)
    con.execute("CREATE TABLE nodes (code VARCHAR, kind VARCHAR, parent VARCHAR)")
    con.executemany("INSERT INTO nodes VALUES (?,?,?)", nodes)
    return con


BASE = {
    "headcount": {"title": "Headcount", "definition": "x", "kind": "base", "unit": "people", "aggregation": "latest", "extensiveness": "extensive", "category": "input", "cadence": "month", "since": "2020-01-01", "levels": ["agency"]},
    "quits": {"title": "Quits", "definition": "x", "kind": "base", "unit": "count", "aggregation": "sum", "extensiveness": "extensive", "category": "outcome", "cadence": "month", "since": "2020-01-01", "levels": ["agency"]},
    "spend": {"title": "Spend", "definition": "x", "kind": "base", "unit": "currency", "aggregation": "latest", "extensiveness": "intensive", "category": "input", "cadence": "quarter", "since": "2020-01-01", "levels": ["agency"]},
}


def test_periods():
    assert shift("month", "2025-12-01", 1) == "2026-01-01"
    assert shift("month", "2025-01-01", -1) == "2024-12-01"
    assert shift("quarter", "2025-10-01", 1) == "2026-01-01"
    assert containing("month", "2025-11-01")["quarter"] == "2025-10-01"
    assert containing("month", "2025-11-01")["fiscal_year"] == "2025-10-01"
    assert containing("month", "2025-03-01")["fiscal_year"] == "2024-10-01"
    assert label("quarter", "2025-10-01") == "FY2026 Q1"
    assert label("fiscal_year", "2025-10-01") == "FY2026"


def test_real_catalog_loads_and_generates_definitions():
    c = Catalog.load()
    assert c.measures["quit_rate"]["extensiveness"] == "intensive"
    assert "divided by" in c.measures["quit_rate"]["definition"]
    assert c.measures["accessions_trailing_12"]["extensiveness"] == "extensive"
    order = c.evaluation_order()
    assert order.index("headcount_prior_month") < order.index("quit_rate")
    assert order.index("accessions_trailing_12") < order.index("first_year_attrition_rate")


def test_catalog_rejects_cycles_and_undescribed():
    bad = dict(BASE)
    bad["a"] = {"title": "a", "kind": "derived", "unit": "count", "aggregation": "sum", "category": "output", "cadence": "month", "since": "2020-01-01", "levels": ["agency"], "calculation": {"pattern": "additive", "terms": [{"measure": "b"}]}}
    bad["b"] = {"title": "b", "kind": "derived", "unit": "count", "aggregation": "sum", "category": "output", "cadence": "month", "since": "2020-01-01", "levels": ["agency"], "calculation": {"pattern": "additive", "terms": [{"measure": "a"}]}}
    with pytest.raises(CatalogError, match="cycle"):
        _catalog(bad)
    with pytest.raises(CatalogError, match="not in the catalog"):
        _catalog({**BASE, "x": {"title": "x", "kind": "derived", "unit": "count", "aggregation": "sum", "category": "output", "cadence": "month", "since": "2020-01-01", "levels": ["agency"], "calculation": {"pattern": "ratio", "numerator": {"measure": "quits"}, "denominator": {"measure": "nope"}}}})
    with pytest.raises(CatalogError, match="operational definition"):
        _catalog({"h": {"title": "h", "kind": "base", "unit": "people", "aggregation": "latest", "extensiveness": "extensive", "category": "input", "cadence": "month", "since": "2020-01-01", "levels": ["agency"]}})


def _series(measure, node, values, start_month=1, year=2025, ptype="month"):
    return [(measure, node, ptype, f"{year}-{start_month + i:02d}-01", None, None, float(v), None, None, "t") for i, v in enumerate(values)]


def test_ratio_with_offset_and_scaling():
    cat = _catalog({**BASE,
        "hc_prior": {"title": "prior", "kind": "derived", "unit": "people", "aggregation": "latest", "category": "input", "cadence": "month", "since": "2020-01-01", "levels": ["agency"], "calculation": {"pattern": "time_offset", "source": {"measure": "headcount", "offset": -1}}},
        "quit_rate": {"title": "qr", "kind": "derived", "unit": "percentage", "aggregation": "sum", "category": "outcome", "cadence": "month", "since": "2020-01-01", "levels": ["agency"], "calculation": {"pattern": "ratio", "numerator": {"measure": "quits"}, "denominator": {"measure": "hc_prior"}}},
    })
    con = _con(_series("headcount", "A", [1000, 1100, 1200]) + _series("quits", "A", [10, 22, 36]), [("A", "agency", "gov")])
    Evaluator(con, cat).evaluate_all()
    rows = dict(con.execute("SELECT period_start, value FROM facts WHERE measure='quit_rate' ORDER BY 1").fetchall())
    assert rows["2025-02-01"] == pytest.approx(2.2)   # 22 / 1000 * 100
    assert rows["2025-03-01"] == pytest.approx(36 / 1100 * 100)
    assert "2025-01-01" not in rows or rows["2025-01-01"] is None
    n = con.execute("SELECT n FROM facts WHERE measure='quit_rate' AND period_start='2025-02-01'").fetchone()[0]
    assert n == 1000
    assert con.execute("SELECT count(*) FROM facts WHERE measure='quit_rate' AND period_start > '2025-03-01'").fetchone()[0] == 0


def test_additive_requires_all_terms():
    cat = _catalog({**BASE, "trail2": {"title": "t", "kind": "derived", "unit": "count", "aggregation": "sum", "category": "output", "cadence": "month", "since": "2020-01-01", "levels": ["agency"], "calculation": {"pattern": "additive", "terms": [{"measure": "quits", "offset": -1}, {"measure": "quits", "offset": -2}]}}})
    con = _con(_series("quits", "A", [5, 7, 11, 13]), [("A", "agency", "gov")])
    Evaluator(con, cat).evaluate_all()
    rows = {r[0]: (r[1], r[2]) for r in con.execute("SELECT period_start, value, notation FROM facts WHERE measure='trail2' ORDER BY 1").fetchall()}
    assert rows["2025-03-01"] == (12.0, None)   # 7 + 5
    assert rows["2025-04-01"] == (18.0, None)   # 11 + 7
    assert rows["2025-02-01"][1] == "not_available"


def test_cadence_reconciliation_latest_and_incomplete():
    cat = _catalog({**BASE, "spend_per_head": {"title": "s", "kind": "derived", "unit": "dollars_per_person", "aggregation": "latest", "category": "input", "cadence": "quarter", "since": "2020-01-01", "levels": ["agency"], "calculation": {"pattern": "ratio", "numerator": {"measure": "spend"}, "denominator": {"measure": "headcount"}}}})
    # FY2025 Q2 = Jan-Mar 2025; give all three months. Q3 = Apr-Jun; give only April (incomplete).
    facts = _series("headcount", "A", [100, 110, 120], start_month=1) + _series("headcount", "A", [130], start_month=4)
    facts += [("spend", "A", "quarter", "2025-01-01", None, None, 1200.0, None, None, "t"), ("spend", "A", "quarter", "2025-04-01", None, None, 1300.0, None, None, "t")]
    con = _con(facts, [("A", "agency", "gov")])
    Evaluator(con, cat).evaluate_all()
    rows = {r[0]: (r[1], r[2]) for r in con.execute("SELECT period_start, value, notation FROM facts WHERE measure='spend_per_head' ORDER BY 1").fetchall()}
    assert rows["2025-01-01"] == (pytest.approx(10.0), None)      # 1200 / latest headcount in quarter (120)
    assert rows["2025-04-01"][1] == "incomplete"                     # only April present


def test_extensiveness_rules():
    with pytest.raises(CatalogError, match="share extensiveness"):
        _catalog({**BASE, "bad": {"title": "b", "kind": "derived", "unit": "count", "aggregation": "sum", "category": "output", "cadence": "month", "since": "2020-01-01", "levels": ["agency"], "calculation": {"pattern": "additive", "terms": [{"measure": "quits"}, {"measure": "spend"}]}}})
