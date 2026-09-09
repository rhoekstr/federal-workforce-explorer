"""Lookups keyed by code, merged across months with first_seen / last_seen and name history.

Each lookup is a JSON object: {code: {...fields, "first_seen": yyyymm, "last_seen": yyyymm,
"name_history": [{"yyyymm": ..., "name": ...}]}}. Names are display attributes; codes are keys.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from pipeline.config import CODE_TABLES, LOOKUPS, NOT_DISCLOSED, REDACTED
from pipeline.fwd.raw import parse_filename, raw_source_sql

# lookup name -> (key expression, {field: source column}, name column, keep name history)
LOOKUP_SPECS = {
    "org": (
        "agency_subelement_code",
        {"agency_code": "agency_code", "department_code": "department_code", "cfo_act": "cfo_act_agency_indicator"},
        "agency_subelement",
        True,
    ),
    "agency": ("agency_code", {"department_code": "department_code"}, "agency", True),
    "department": ("department_code", {}, "department", True),
    # Duty station keeps codes only; labels for county, CBSA, and locality live in their own lookups.
    "duty_station": (
        "duty_station_code",
        {
            "st": "duty_station_state_abbreviation",
            "fips": "duty_station_state_country_territory_code || duty_station_county_code",
            "cc": "duty_station_country_code",
            "cbsa": "core_based_statistical_area_code",
            "csa": "consolidated_statistical_area_code",
            "loc": "locality_pay_area_code",
        },
        "duty_station_city",
        False,
    ),
    "county": (
        "duty_station_state_country_territory_code || duty_station_county_code",
        {"st": "duty_station_state_abbreviation"},
        "duty_station_county",
        False,
    ),
    "cbsa": ("core_based_statistical_area_code", {}, "core_based_statistical_area", False),
    "csa": ("consolidated_statistical_area_code", {}, "consolidated_statistical_area", False),
    "locality": ("locality_pay_area_code", {}, "locality_pay_area", False),
    "country": ("duty_station_country_code", {}, "duty_station_country", False),
    "series": (
        "occupational_series_code",
        {
            "group_code": "occupational_group_code",
            "group": "occupational_group",
            "category_code": "occupational_category_code",
            "category": "occupational_category",
            "stem": "stem_occupation",
            "stem_type": "stem_occupation_type",
        },
        "occupational_series",
        True,
    ),
    "pay_plan": ("pay_plan_code", {}, "pay_plan", True),
    "step": ("step_or_rate_type_code", {}, "step_or_rate_type", True),
}


def _load(name: str) -> dict:
    path = LOOKUPS / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save(name: str, data: dict) -> Path:
    LOOKUPS.mkdir(parents=True, exist_ok=True)
    path = LOOKUPS / f"{name}.json"
    path.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False, sort_keys=True))
    return path


def _upsert(table: dict, key: str, fields: dict, name: str | None, yyyymm: str, history: bool = True) -> None:
    entry = table.get(key)
    if entry is None:
        entry = {"first_seen": yyyymm, "last_seen": yyyymm}
        if history:
            entry["name_history"] = []
        table[key] = entry
    entry["first_seen"] = min(entry["first_seen"], yyyymm)
    entry["last_seen"] = max(entry["last_seen"], yyyymm)
    for k, v in fields.items():
        if v not in (None, "", REDACTED) or k not in entry:
            entry[k] = v
    if name is None:
        return
    if not history:
        if yyyymm >= entry["last_seen"] or "name" not in entry:
            entry["name"] = name
        return
    names = entry["name_history"]
    if (not names or names[-1]["name"] != name) and not any(h["yyyymm"] == yyyymm for h in names):
        names.append({"yyyymm": yyyymm, "name": name})
        names.sort(key=lambda h: h["yyyymm"])
    entry["name"] = max(names, key=lambda h: h["yyyymm"])["name"]


def _distinct_rows(con: duckdb.DuckDBPyConnection, raw: Path, key: str, fields: dict, name_col: str) -> list[tuple]:
    exprs = list(fields.values()) + ([name_col] if name_col not in fields.values() else [])
    # Most frequent value of each attribute per key, so a stray inconsistent row cannot flip a label.
    sql = f"""
    SELECT k, {", ".join(f"mode({e}) AS f{i}" for i, e in enumerate(exprs))}
    FROM (SELECT {key} AS k, * FROM {raw_source_sql(raw)})
    WHERE k IS NOT NULL AND k <> ''
    GROUP BY k
    """
    rows = con.execute(sql).fetchall()
    return [tuple(["k"] + exprs)] + rows


def update_lookups(raw: Path, con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """Upsert every lookup from one raw file. Returns {lookup: key count}."""
    dataset, yyyymm, _ = parse_filename(raw.name)
    con = con or duckdb.connect()
    counts = {}
    for lookup, (key, fields, name_col, history) in LOOKUP_SPECS.items():
        table = _load(lookup)
        header, *rows = _distinct_rows(con, raw, key, fields, name_col)
        idx = {c: i for i, c in enumerate(header)}
        for row in rows:
            code = row[0]
            if code == REDACTED or code == REDACTED + REDACTED:
                if lookup == "duty_station":
                    _upsert(table, NOT_DISCLOSED, {k: None for k in fields}, "Not disclosed", yyyymm, history)
                continue
            attrs = {field: row[idx[src]] for field, src in fields.items()}
            _upsert(table, code, attrs, row[idx[name_col]], yyyymm, history)
        if dataset == "employment" and lookup in ("org", "agency", "department"):
            _add_headcount(con, raw, table, key, yyyymm)
        _save(lookup, table)
        counts[lookup] = len(table)
    counts["codes"] = _update_codes(con, raw, yyyymm)
    return counts


def _add_headcount(con: duckdb.DuckDBPyConnection, raw: Path, table: dict, key: str, yyyymm: str) -> None:
    rows = con.execute(f"SELECT {key}, sum(CAST(count AS INTEGER)) FROM {raw_source_sql(raw)} GROUP BY 1").fetchall()
    for code, n in rows:
        if code in table:
            table[code].setdefault("headcount", {})[yyyymm] = int(n)


def _update_codes(con: duckdb.DuckDBPyConnection, raw: Path, yyyymm: str) -> int:
    codes = _load("codes")
    available = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {raw_source_sql(raw)}").fetchall()}
    for table_name, (code_col, label_col) in CODE_TABLES.items():
        if code_col not in available:
            continue
        rows = con.execute(
            f"SELECT {code_col}, mode({label_col}) FROM {raw_source_sql(raw)} WHERE {code_col} IS NOT NULL GROUP BY 1"
        ).fetchall()
        sub = codes.setdefault(table_name, {})
        for code, label in rows:
            _upsert(sub, code if code != "" else "_blank", {}, label, yyyymm, True)
    for bracket_col in ("age_bracket", "education_level_bracket"):
        if bracket_col not in available:
            continue
        rows = con.execute(f"SELECT DISTINCT {bracket_col} FROM {raw_source_sql(raw)} WHERE {bracket_col} IS NOT NULL").fetchall()
        sub = codes.setdefault(bracket_col, {})
        for (value,) in rows:
            _upsert(sub, value if value != "" else "_blank", {}, value, yyyymm, False)
    _save("codes", codes)
    return sum(len(v) for v in codes.values())


def load_lookup(name: str) -> dict:
    return _load(name)
