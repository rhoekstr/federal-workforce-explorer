"""Money overview checks (PRD 5.8, RUNBOOK M4)."""
from __future__ import annotations

import json
from datetime import date

import pytest

from pipeline.config import SLICES, classify_object_class
from pipeline.money.groups import GROUPS_PATH, normalize
from pipeline.money.omb import load_table_5_1
from pipeline.money.overview import latest_closed_quarter, quarter_end_yyyymm


def test_object_class_buckets():
    assert classify_object_class("11.1") == "personnel"
    assert classify_object_class("12.1") == "personnel"
    assert classify_object_class("25.1") == "contracted"
    assert classify_object_class("25.2") == "contracted"
    assert classify_object_class("25.3") == "federal_services"
    assert classify_object_class("25.7") == "operations_other"
    assert classify_object_class("42.0") == "administered"
    assert classify_object_class("41.0") == "administered"
    assert classify_object_class("99.0") == "other"


def test_quarter_math():
    assert latest_closed_quarter(date(2026, 9, 9)) == (2026, 3)
    assert latest_closed_quarter(date(2026, 10, 15)) == (2026, 4)
    assert latest_closed_quarter(date(2027, 1, 5)) == (2027, 1)
    assert quarter_end_yyyymm(2026, 3) == "202606"
    assert quarter_end_yyyymm(2026, 1) == "202512"


def test_normalize_names():
    assert normalize("DEPARTMENT OF TREASURY") == normalize("Department of the Treasury")
    assert normalize("NAT AERONAUTICS AND SPACE ADMINISTRATION") == normalize("National Aeronautics and Space Administration")
    assert normalize("U.S.AGENCY FOR GLOBAL MEDIA") == normalize("U.S. Agency for Global Media")


def test_omb_table():
    rows = load_table_5_1()
    labor = {r["fy"]: r for r in rows if r["label"] == "Labor"}
    assert labor[2024]["fte"] == 15400 and labor[2024]["kind"] == "actual"
    assert labor[2027]["kind"] == "estimate"


def test_groups_cover_large_agencies():
    groups = json.loads(GROUPS_PATH.read_text())
    fwd_codes = {c for g in groups.values() for c in g["fwd_agency_codes"]}
    for code in ("VA", "HS", "NV", "AR", "AF", "DD", "DJ", "TR", "AG", "HE", "IN", "TD", "SZ", "CM", "NN", "DN", "EP", "ST", "DL", "GS"):
        assert code in fwd_codes, code
    assert all(len(set(g["usaspending_names"])) == len(g["usaspending_names"]) for g in groups.values())
    names = [n for g in groups.values() for n in g["usaspending_names"]]
    assert len(names) == len(set(names)), "a USAspending agency is in two groups"


@pytest.fixture(scope="module")
def overview():
    path = SLICES / "overview.json"
    if not path.exists():
        pytest.skip("overview not built")
    return json.loads(path.read_text())


def test_overview_labor(overview):
    dol = next(r for r in overview["rows"] if r["group"] == "dol")
    assert 0.8 * 2.4e9 < dol["personnel"] < 1.2 * 2.4e9
    assert 0.5 < dol["insourcing_ratio"] < 0.7
    assert dol["fte_omb"] in (13000, 14800)
    assert dol["headcount_latest"] and dol["headcount_latest"] > 9000


def test_overview_totals_add_up(overview):
    for r in overview["rows"]:
        if r["personnel"] is None:
            continue
        assert abs((r["administered"] + r["operations"] + r["other"]) - r["total_obligations"]) < 1.0
        if r["fte_omb"] is not None:
            assert r["headcount_latest"] is not None
