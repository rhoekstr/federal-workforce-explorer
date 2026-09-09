"""Golden checks against the July 2026 files in data/raw (skipped when absent)."""
from __future__ import annotations

import json

import duckdb
import pytest

from pipeline.config import LOOKUPS, NOT_DISCLOSED, RAW, WORK
from pipeline.fwd.facts import build_fact, fact_columns, fact_path
from pipeline.fwd.lookups import update_lookups
from pipeline.fwd.raw import find_raw, raw_source_sql
from pipeline.fwd.schema import SchemaError, expected_columns, validate_header

JULY = "202607"
GOLDEN = {"employment": 2_020_230, "accessions": 19_024, "separations": 16_681}


def _raw(dataset):
    path = find_raw(dataset, JULY)
    if path is None:
        pytest.skip(f"no raw {dataset} {JULY} in data/raw")
    return path


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


@pytest.fixture(scope="module")
def july_facts(con):
    stats = {}
    for dataset in GOLDEN:
        raw = _raw(dataset)
        stats[dataset] = build_fact(raw, con)
        update_lookups(raw, con)
    return stats


def test_reference_headers_match_raw_text():
    for dataset in ("accessions", "separations"):
        raw = _raw(dataset)
        if raw.suffix == ".txt":
            assert validate_header(raw, dataset) == expected_columns(dataset)


def test_schema_error_on_drift(tmp_path):
    bad = tmp_path / "employment_209901_1.txt"
    bad.write_text("a|b|c\n1|2|3\n")
    with pytest.raises(SchemaError):
        validate_header(bad, "employment")


@pytest.mark.parametrize("dataset", list(GOLDEN))
def test_headcount_is_preserved(july_facts, dataset):
    assert july_facts[dataset]["n"] == GOLDEN[dataset]
    assert july_facts[dataset]["rows_source"] == GOLDEN[dataset]


def test_employment_grain_and_size(july_facts):
    s = july_facts["employment"]
    assert 1_400_000 < s["rows_fact"] < 1_750_000
    assert s["parquet_bytes"] < 25 * 1024 * 1024


def test_fact_columns(con, july_facts):
    for dataset in GOLDEN:
        cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{fact_path(dataset, JULY)}')").fetchall()]
        assert cols == fact_columns(dataset)


def test_pay_measures_consistent(con, july_facts):
    bad = con.execute(f"SELECT count(*) FROM read_parquet('{fact_path('employment', JULY)}') WHERE pay_n > n").fetchone()[0]
    assert bad == 0
    redacted = con.execute(
        f"SELECT sum(n) FROM read_parquet('{fact_path('employment', JULY)}') WHERE pay_band = 'R'"
    ).fetchone()[0]
    assert 0.4 * GOLDEN["employment"] < redacted < 0.55 * GOLDEN["employment"]


def test_every_code_resolves(con, july_facts):
    org = json.loads((LOOKUPS / "org.json").read_text())
    ds = json.loads((LOOKUPS / "duty_station.json").read_text())
    facts = con.execute(
        f"SELECT DISTINCT org_code, duty_station_code FROM read_parquet('{fact_path('employment', JULY)}')"
    ).fetchall()
    assert all(o in org for o, _ in facts)
    assert all(d in ds for _, d in facts)
    assert NOT_DISCLOSED in ds and ds[NOT_DISCLOSED]["name"] == "Not disclosed"


def test_org_codes_prefix_agency(july_facts):
    org = json.loads((LOOKUPS / "org.json").read_text())
    assert all(code.startswith(v["agency_code"]) for code, v in org.items())
    assert 400 < len(org) < 700


def test_functional_dependencies_hold(con, july_facts):
    raw = _raw("employment")
    checks = {
        "agency_subelement_code": ["agency_code", "department_code"],
        "duty_station_code": ["duty_station_state_abbreviation", "duty_station_county_code", "core_based_statistical_area_code"],
        "occupational_series_code": ["occupational_group_code", "occupational_category_code"],
    }
    for key, deps in checks.items():
        for dep in deps:
            violations = con.execute(
                f"SELECT count(*) FROM (SELECT {key}, count(DISTINCT {dep}) c FROM {raw_source_sql(raw)} GROUP BY 1) WHERE c > 1"
            ).fetchone()[0]
            assert violations == 0, f"{key} -> {dep} violated {violations} times"


def test_actions_keep_both_months(con, july_facts):
    months = con.execute(
        f"SELECT count(DISTINCT effective_yyyymm), count(DISTINCT file_yyyymm) FROM read_parquet('{fact_path('separations', JULY)}')"
    ).fetchone()
    assert months[0] > 1 and months[1] == 1


def test_lookups_are_small(july_facts):
    total = sum(p.stat().st_size for p in LOOKUPS.glob("*.json"))
    assert total < 5 * 1024 * 1024
