"""Aggregate a raw FWD file to the fact grain defined in PRD 5.2 and 5.3."""
from __future__ import annotations

from pathlib import Path

import duckdb

from pipeline.config import COMMON_DIMS, DATASET_DIMS, NOT_DISCLOSED, REDACTED, WORK
from pipeline.fwd.raw import parse_filename, raw_source_sql

PAY_BAND_SQL = (
    f"CASE WHEN annualized_adjusted_basic_pay = '{REDACTED}' THEN 'R' "
    "ELSE CAST(CAST(floor(TRY_CAST(annualized_adjusted_basic_pay AS DOUBLE) / 10000) * 10 AS INTEGER) AS VARCHAR) END"
)
DUTY_STATION_SQL = f"CASE WHEN duty_station_code = '{REDACTED}' THEN '{NOT_DISCLOSED}' ELSE duty_station_code END"

MEASURES_SQL = """
    sum(CAST(count AS INTEGER)) AS n,
    sum(TRY_CAST(annualized_adjusted_basic_pay AS DOUBLE)) AS pay_sum,
    sum(CASE WHEN annualized_adjusted_basic_pay <> '{redacted}' AND annualized_adjusted_basic_pay <> '' THEN CAST(count AS INTEGER) ELSE 0 END) AS pay_n,
    sum(TRY_CAST(length_of_service_years AS DOUBLE)) AS los_sum
""".format(redacted=REDACTED)


def fact_columns(dataset: str) -> list[str]:
    """Fact dimension names in order, then measures."""
    dims = list(DATASET_DIMS[dataset].values())
    if dataset != "employment":
        dims.insert(0, "file_yyyymm")
    dims += [c for c in COMMON_DIMS.values()] + ["pay_band"]
    return dims + ["n", "pay_sum", "pay_n", "los_sum"]


def _select_dims_sql(dataset: str, file_yyyymm: str) -> str:
    parts = []
    if dataset != "employment":
        parts.append(f"'{file_yyyymm}' AS file_yyyymm")
    for src, dst in DATASET_DIMS[dataset].items():
        parts.append(f"{src} AS {dst}")
    for src, dst in COMMON_DIMS.items():
        if src == "duty_station_code":
            parts.append(f"{DUTY_STATION_SQL} AS {dst}")
        else:
            parts.append(f"{src} AS {dst}")
    parts.append(f"{PAY_BAND_SQL} AS pay_band")
    return ",\n    ".join(parts)


def fact_path(dataset: str, yyyymm: str) -> Path:
    return WORK / f"fact_{dataset}_{yyyymm}.parquet"


def build_fact(raw: Path, con: duckdb.DuckDBPyConnection | None = None) -> dict:
    """Write fact_{dataset}_{yyyymm}.parquet from a raw file. Returns a small stats dict."""
    dataset, yyyymm, version = parse_filename(raw.name)
    con = con or duckdb.connect()
    out = fact_path(dataset, yyyymm)
    out.parent.mkdir(parents=True, exist_ok=True)
    sql = f"""
    COPY (
      SELECT
        {_select_dims_sql(dataset, yyyymm)},
        {MEASURES_SQL}
      FROM {raw_source_sql(raw)}
      GROUP BY ALL
      ORDER BY ALL
    ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """
    con.execute(sql)
    rows_source = con.execute(f"SELECT count(*) FROM {raw_source_sql(raw)}").fetchone()[0]
    rows_fact, n = con.execute(f"SELECT count(*), sum(n) FROM read_parquet('{out}')").fetchone()
    return {
        "dataset": dataset,
        "yyyymm": yyyymm,
        "version": version,
        "source_file": raw.name,
        "rows_source": rows_source,
        "rows_fact": rows_fact,
        "n": int(n),
        "parquet_bytes": out.stat().st_size,
        "path": str(out.relative_to(WORK.parent.parent)),
    }
