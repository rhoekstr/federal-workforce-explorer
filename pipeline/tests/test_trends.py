"""E1 checks: trend slices sum to the node headcount and stay within budget."""
from __future__ import annotations

import json

import pytest

from pipeline.config import SLICES
from pipeline.trends import BUDGET_BYTES, TREND_DIR


@pytest.fixture(scope="module")
def built():
    if not TREND_DIR.exists() or not any(TREND_DIR.glob("*.json")):
        pytest.skip("trend slices not built")
    return True


def _series(code: str) -> dict:
    return json.loads((SLICES / "series" / f"{code}.json").read_text())


@pytest.mark.parametrize("code", ["gov", "DL", "DLLS", "D:DOD"])
def test_breakdowns_sum_to_headcount(built, code):
    path = TREND_DIR / f"{code}.json"
    if not path.exists():
        pytest.skip(f"{code} not in trend scope")
    t = json.loads(path.read_text())
    head = _series(code)["headcount"]
    for dim, values in t["by"].items():
        for m in t["months"]:
            total = sum(series.get(m, 0) for series in values.values())
            assert total == head[m], f"{code} {dim} {m}: {total} != {head[m]}"


def test_budget(built):
    total = sum(p.stat().st_size for p in TREND_DIR.glob("*.json"))
    assert total <= BUDGET_BYTES, f"{total / 1e6:.1f} MB over budget"
    assert max(p.stat().st_size for p in TREND_DIR.glob("*.json")) < 60 * 1024


def test_top_values_capped(built):
    t = json.loads((TREND_DIR / "DL.json").read_text())
    for dim, values in t["by"].items():
        assert len([v for v in values if v != "_other"]) <= 8
