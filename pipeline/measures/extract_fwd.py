"""Era-aware extraction of base workforce measures from one OPM FWD file (text or raw parquet).

Emits long facts at the sub-element level (flat measures) and at the agency level (dimensioned headcount and
action categories). Roll-ups to department and government happen in build.py. A measure is emitted only when
every column it needs exists in the file, so 2005-era files yield the core set and 2010-era files the full set.
"""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from pipeline.fwd.raw import parse_filename, raw_source_sql
from pipeline.measures.periods import month_start

log = logging.getLogger(__name__)

CORE_EMPLOYMENT = {"agency_code", "agency_subelement_code", "count", "snapshot_yyyymm", "age_bracket", "grade", "pay_plan_code", "appointment_type_code", "supervisory_status_code", "work_schedule_code", "education_level_code", "length_of_service_years", "annualized_adjusted_basic_pay"}
CORE_ACTIONS = {"agency_code", "agency_subelement_code", "count", "personnel_action_effective_date_yyyymm", "length_of_service_years"}

NODE_SQL = "CASE WHEN agency_subelement_code IS NULL OR agency_subelement_code = '' THEN agency_code || '__' ELSE agency_subelement_code END"
AGE_LOWER_SQL = "CASE WHEN age_bracket = 'LESS THAN 20' THEN 15 WHEN age_bracket = '65 OR MORE' THEN 65 WHEN age_bracket = 'UNSPECIFIED' THEN NULL ELSE TRY_CAST(substr(age_bracket, 1, 2) AS INTEGER) END"
LOS_SQL = "TRY_CAST(length_of_service_years AS DOUBLE)"
PAY_SQL = "CASE WHEN annualized_adjusted_basic_pay IN ('REDACTED', '') THEN NULL ELSE TRY_CAST(annualized_adjusted_basic_pay AS DOUBLE) END"
N = "CAST(count AS INTEGER)"

# measure -> (sum expression, required columns beyond the core)
EMPLOYMENT_MEASURES: dict[str, tuple[str, set[str]]] = {
    "headcount": (f"sum({N})", set()),
    "supervisors": (f"sum(CASE WHEN supervisory_status_code IN ('2','4','5') THEN {N} ELSE 0 END)", set()),
    "permanent_employees": (f"sum(CASE WHEN appointment_type_code IN ('10','15','30','32','35','36','38','50','55','67') THEN {N} ELSE 0 END)", set()),
    "temporary_employees": (f"sum(CASE WHEN appointment_type_code IN ('20','40','42','44','45','46','48','60','65','68') THEN {N} ELSE 0 END)", set()),
    "fulltime_employees": (f"sum(CASE WHEN work_schedule_code IN ('F','G') THEN {N} ELSE 0 END)", set()),
    "gs_employees": (f"sum(CASE WHEN pay_plan_code = 'GS' THEN {N} ELSE 0 END)", set()),
    "gs13_plus_employees": (f"sum(CASE WHEN pay_plan_code = 'GS' AND grade IN ('13','14','15') THEN {N} ELSE 0 END)", set()),
    "under_30": (f"sum(CASE WHEN {AGE_LOWER_SQL} < 30 THEN {N} ELSE 0 END)", set()),
    "age_55_plus": (f"sum(CASE WHEN {AGE_LOWER_SQL} >= 55 THEN {N} ELSE 0 END)", set()),
    "retirement_eligible": (
        f"sum(CASE WHEN ({AGE_LOWER_SQL} >= 62 AND {LOS_SQL} >= 5) OR ({AGE_LOWER_SQL} >= 60 AND {LOS_SQL} >= 20) OR ({AGE_LOWER_SQL} >= 55 AND {LOS_SQL} >= 30) THEN {N} ELSE 0 END)", set()),
    "bachelors_plus": (f"sum(CASE WHEN education_level_code BETWEEN '13' AND '22' THEN {N} ELSE 0 END)", set()),
    "service_years_total": (f"sum({LOS_SQL} * {N})", set()),
    "pay_total": (f"sum({PAY_SQL} * {N})", set()),
    "pay_disclosed_employees": (f"sum(CASE WHEN {PAY_SQL} IS NOT NULL THEN {N} ELSE 0 END)", set()),
    "location_disclosed_employees": (f"sum(CASE WHEN duty_station_code NOT IN ('REDACTED', '') THEN {N} ELSE 0 END)", {"duty_station_code"}),
    "veterans": (f"sum(CASE WHEN veteran_indicator = 'Y' THEN {N} ELSE 0 END)", {"veteran_indicator"}),
    "stem_employees": (f"sum(CASE WHEN stem_occupation = 'STEM OCCUPATIONS' THEN {N} ELSE 0 END)", {"stem_occupation"}),
    "bargaining_unit_employees": (f"sum(CASE WHEN bargaining_unit_status = 'ELIGIBLE_IN_BU' THEN {N} ELSE 0 END)", {"bargaining_unit_status"}),
    "bargaining_disclosed_employees": (f"sum(CASE WHEN bargaining_unit_status NOT IN ('REDACTED', '') THEN {N} ELSE 0 END)", {"bargaining_unit_status"}),
}

# dimension code -> (value expression, required columns)
DIMENSIONS: dict[str, tuple[str, set[str]]] = {
    "grade": ("grade", set()),
    "age_bracket": ("age_bracket", set()),
    "supervisory": ("supervisory_status_code", set()),
    "appointment_type": ("appointment_type_code", set()),
    "pay_band": (f"CASE WHEN {PAY_SQL} IS NULL THEN 'R' ELSE CAST(CAST(floor({PAY_SQL} / 10000) * 10 AS INTEGER) AS VARCHAR) END", set()),
    "work_schedule": ("work_schedule_code", set()),
    "series": ("occupational_series_code", {"occupational_series_code"}),
    "step": ("step_or_rate_type_code", {"step_or_rate_type_code"}),
}

ACTION_MEASURES: dict[str, dict[str, tuple[str, set[str]]]] = {
    "accessions": {
        "accessions": (f"sum({N})", set()),
        "new_hires": (f"sum(CASE WHEN accession_category_code IN ('AC','AD','AE') THEN {N} ELSE 0 END)", {"accession_category_code"}),
        "transfers_in": (f"sum(CASE WHEN accession_category_code IN ('AA','AB') THEN {N} ELSE 0 END)", {"accession_category_code"}),
    },
    "separations": {
        "separations": (f"sum({N})", set()),
        "quits": (f"sum(CASE WHEN separation_category_code = 'SC' THEN {N} ELSE 0 END)", {"separation_category_code"}),
        "retirements": (f"sum(CASE WHEN separation_category_code IN ('SD','SE','SG') THEN {N} ELSE 0 END)", {"separation_category_code"}),
        "rifs": (f"sum(CASE WHEN separation_category_code = 'SH' THEN {N} ELSE 0 END)", {"separation_category_code"}),
        "transfers_out": (f"sum(CASE WHEN separation_category_code IN ('SA','SB') THEN {N} ELSE 0 END)", {"separation_category_code"}),
        "terminations": (f"sum(CASE WHEN separation_category_code IN ('SJ','SL') THEN {N} ELSE 0 END)", {"separation_category_code"}),
        "deferred_resignations": (f"sum(CASE WHEN drp_indicator = 'Y' THEN {N} ELSE 0 END)", {"drp_indicator"}),
        "first_year_separations": (f"sum(CASE WHEN {LOS_SQL} < 1 THEN {N} ELSE 0 END)", set()),
    },
}
ACTION_DIMENSION = {"accessions": ("accession_category", "accession_category_code"), "separations": ("separation_category", "separation_category_code")}

FACT_COLUMNS = ["measure", "node", "period_type", "period_start", "dim", "dim_value", "value", "n", "notation", "source_ref"]


class EraError(RuntimeError):
    pass


def columns_of(con: duckdb.DuckDBPyConnection, raw: Path) -> set[str]:
    return {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {raw_source_sql(raw)}").fetchall()}


def _select_measures(specs: dict, available: set[str]) -> dict[str, str]:
    return {m: expr for m, (expr, needs) in specs.items() if needs <= available}


def extract_employment(raw: Path, con: duckdb.DuckDBPyConnection | None = None) -> list[tuple]:
    """Base stock facts for one employment file: flat at sub-element level, dimensioned at agency level."""
    con = con or duckdb.connect()
    dataset, yyyymm, version = parse_filename(raw.name)
    assert dataset == "employment"
    available = columns_of(con, raw)
    missing = CORE_EMPLOYMENT - available
    if missing:
        raise EraError(f"{raw.name}: missing core columns {sorted(missing)}")
    source_ref = f"fwd:{raw.stem}"
    period = month_start(yyyymm)
    con.execute(f"CREATE OR REPLACE VIEW src AS SELECT * FROM {raw_source_sql(raw)}")
    measures = _select_measures(EMPLOYMENT_MEASURES, available)
    cols = ", ".join(f"{expr} AS \"{m}\"" for m, expr in measures.items())
    rows = con.execute(f"SELECT {NODE_SQL} AS node, {cols} FROM src GROUP BY 1").fetchall()
    names = list(measures)
    facts: list[tuple] = []
    for r in rows:
        node = r[0]
        for i, m in enumerate(names):
            v = r[i + 1]
            if v is None:
                continue
            facts.append((m, node, "month", period, None, None, float(v), None, None, source_ref))
    for dim, (expr, needs) in DIMENSIONS.items():
        if not needs <= available:
            continue
        drows = con.execute(f"SELECT agency_code, {expr} AS v, sum({N}) FROM src GROUP BY 1, 2").fetchall()
        for agency, v, n in drows:
            facts.append(("headcount", agency, "month", period, dim, v if v not in (None, "") else "_blank", float(n), None, None, source_ref))
    log.info("%s: %d flat measures, %d facts", raw.name, len(names), len(facts))
    return facts


def extract_actions(raw: Path, con: duckdb.DuckDBPyConnection | None = None) -> list[tuple]:
    """Base flow facts for one accessions or separations file, by effective month."""
    con = con or duckdb.connect()
    dataset, yyyymm, version = parse_filename(raw.name)
    assert dataset in ACTION_MEASURES
    available = columns_of(con, raw)
    missing = CORE_ACTIONS - available
    if missing:
        raise EraError(f"{raw.name}: missing core columns {sorted(missing)}")
    source_ref = f"fwd:{raw.stem}"
    con.execute(f"CREATE OR REPLACE VIEW src AS SELECT * FROM {raw_source_sql(raw)}")
    measures = _select_measures(ACTION_MEASURES[dataset], available)
    cols = ", ".join(f"{expr} AS \"{m}\"" for m, expr in measures.items())
    rows = con.execute(
        f"SELECT {NODE_SQL} AS node, personnel_action_effective_date_yyyymm AS eff, {cols} FROM src WHERE length(personnel_action_effective_date_yyyymm) = 6 GROUP BY 1, 2"
    ).fetchall()
    names = list(measures)
    facts: list[tuple] = []
    for r in rows:
        node, eff = r[0], r[1]
        period = month_start(eff)
        for i, m in enumerate(names):
            v = r[i + 2]
            if v is None:
                continue
            facts.append((m, node, "month", period, None, None, float(v), None, None, source_ref))
    dim, col = ACTION_DIMENSION[dataset]
    if col in available:
        drows = con.execute(
            f"SELECT agency_code, personnel_action_effective_date_yyyymm, {col}, sum({N}) FROM src WHERE length(personnel_action_effective_date_yyyymm) = 6 GROUP BY 1, 2, 3"
        ).fetchall()
        for agency, eff, v, n in drows:
            facts.append((dataset, agency, "month", month_start(eff), dim, v if v not in (None, "") else "_blank", float(n), None, None, source_ref))
    log.info("%s: %d flow measures, %d facts", raw.name, len(names), len(facts))
    return facts


def write_facts(facts: list[tuple], out: Path, con: duckdb.DuckDBPyConnection | None = None) -> int:
    con = con or duckdb.connect()
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute("CREATE OR REPLACE TABLE f (measure VARCHAR, node VARCHAR, period_type VARCHAR, period_start VARCHAR, dim VARCHAR, dim_value VARCHAR, value DOUBLE, n BIGINT, notation VARCHAR, source_ref VARCHAR)")
    con.executemany("INSERT INTO f VALUES (?,?,?,?,?,?,?,?,?,?)", facts)
    con.execute(f"COPY f TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    return len(facts)
