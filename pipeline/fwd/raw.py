"""Reading raw FWD files (pipe-delimited text or the raw parquet we keep) with DuckDB."""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

from pipeline.config import RAW

FILENAME_RE = re.compile(r"^(employment|accessions|separations)_(\d{6})_(\d+)$")


def parse_filename(name: str) -> tuple[str, str, int]:
    """'employment_202607_1' -> ('employment', '202607', 1)."""
    stem = Path(name).stem if name.endswith((".txt", ".parquet")) else name
    m = FILENAME_RE.match(stem)
    if not m:
        raise ValueError(f"not an FWD filename: {name!r}")
    return m.group(1), m.group(2), int(m.group(3))


def raw_source_sql(path: Path) -> str:
    """A DuckDB FROM-clause expression for a raw file, text or parquet."""
    p = str(path)
    if path.suffix == ".parquet":
        return f"read_parquet('{p}')"
    return f"read_csv('{p}', delim='|', header=true, quote='', all_varchar=true)"


def text_to_parquet(txt: Path, parquet: Path) -> int:
    """Convert a raw text file to ZSTD parquet, all columns as strings. Returns row count."""
    parquet.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM {raw_source_sql(txt)}) TO '{parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    return con.execute(f"SELECT count(*) FROM read_parquet('{parquet}')").fetchone()[0]


def find_raw(dataset: str, yyyymm: str) -> Path | None:
    """Prefer the raw parquet, fall back to text, highest version wins."""
    candidates = sorted(RAW.glob(f"{dataset}_{yyyymm}_*.parquet")) + sorted(RAW.glob(f"{dataset}_{yyyymm}_*.txt"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: (parse_filename(p.name)[2], p.suffix == ".parquet"))
