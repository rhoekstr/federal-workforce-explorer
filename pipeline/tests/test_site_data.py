"""v0.4: the site reads measures, not the pre-measures slices."""
from __future__ import annotations

import json

import pytest

from pipeline.config import SLICES

MEAS = SLICES / "measures"


@pytest.fixture(scope="module")
def built():
    if not (MEAS / "periods.json").exists():
        pytest.skip("measure slices not built")
    return True


def test_retired_slices_are_gone(built):
    for stale in ("series", "mix", "trend", "overview.json"):
        assert not (SLICES / stale).exists(), f"{stale} came back; the site no longer reads it"


def test_period_axis_and_packing(built):
    axis = json.loads((MEAS / "periods.json").read_text())
    assert axis["month"] == sorted(axis["month"]) and len(axis["month"]) > 200
    gov = json.loads((MEAS / "gov.json").read_text())
    hc = gov["measures"]["headcount"]
    assert hc["t"] == "month" and isinstance(hc["v"], list)
    # positional encoding: the last non-null value lands on the last month OPM has published
    last = axis["month"][hc["i"] + len(hc["v"]) - 1]
    assert last == axis["month"][-1]
    assert sum(1 for v in hc["v"] if v is not None) > 200


def test_flows_components_sum_to_totals(built):
    """The flows chart builds its pies from named measures; they must add up to the totals it draws."""
    gov = json.loads((MEAS / "gov.json").read_text())["measures"]
    axis = json.loads((MEAS / "periods.json").read_text())["month"]

    def at(measure, period):
        s = gov[measure]
        k = axis.index(period) - s["i"]
        return s["v"][k] if 0 <= k < len(s["v"]) else None

    period = axis[-1]
    up = sum(at(m, period) or 0 for m in ("new_hires", "transfers_in"))
    down = sum(at(m, period) or 0 for m in ("quits", "retirements", "rifs", "transfers_out", "terminations"))
    assert abs(up - at("accessions", period)) < 0.5
    assert abs(down - at("separations", period)) < 0.5


def test_table_and_movers(built):
    table = json.loads((MEAS / "table.json").read_text())
    assert table["nodes"]["gov"]["headcount"]["v"] > 1_000_000
    assert "d12" in table["nodes"]["DL"]["headcount"]
    movers = json.loads((MEAS / "movers.json").read_text())
    twelve = movers["windows"]["12"]["measures"]["headcount"]
    assert len(twelve["down"]) and len(twelve["up"])
    assert twelve["down"][0]["d"] <= twelve["up"][0]["d"]


def test_composition_reaches_subelements(built):
    dl = json.loads((MEAS / "DLLS.json").read_text())
    assert "grade" in dl["dims_now"]["headcount"]
    assert sum(dl["dims_now"]["headcount"]["grade"].values()) > 1000
