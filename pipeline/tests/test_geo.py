"""E2 checks: geo slices reconcile to headcount and to the TopoJSON."""
from __future__ import annotations

import json

import pytest

from pipeline.config import ROOT, SLICES
from pipeline.geo import GEO_DIR


@pytest.fixture(scope="module")
def built():
    if not GEO_DIR.exists() or not (GEO_DIR / "DL.json").exists():
        pytest.skip("geo slices not built")
    return True


@pytest.fixture(scope="module")
def county_ids():
    topo = json.loads((ROOT / "data" / "geo" / "counties-10m.json").read_text())
    return {g["id"] for g in topo["objects"]["counties"]["geometries"]}


@pytest.mark.parametrize("code", ["gov", "DL", "VA", "D:DOD"])
def test_geo_reconciles(built, code):
    g = json.loads((GEO_DIR / f"{code}.json").read_text())
    counties = sum(g["counties"].values())
    nds = g["n"] - g["disclosed"] - g["invalid"]
    assert counties + g["abroad"] + g["territory"] + g["invalid"] + nds == g["n"]
    assert sum(g["states"].values()) == counties
    mix = json.loads((SLICES / "mix" / f"{code}.json").read_text())["_summary"]
    assert abs(g["disclosed_share"] - mix["disclosed_location_share"]) < 0.02  # invalid codes are the only gap


def test_labor_disclosed(built):
    g = json.loads((GEO_DIR / "DL.json").read_text())
    assert g["n"] > 10000 and g["disclosed_share"] > 0.85


def test_fips_known(built, county_ids):
    g = json.loads((GEO_DIR / "gov.json").read_text())
    unknown = {f: n for f, n in g["counties"].items() if f not in county_ids}
    share = sum(unknown.values()) / sum(g["counties"].values())
    assert share < 0.01, f"{len(unknown)} unknown FIPS holding {share:.2%}: {sorted(unknown)[:10]}"
