"""Resumable backfill: for every current OPM file, download (if needed), extract base measures, delete the raw text.

  python -m pipeline.measures.backfill --from 2005 --to 2024      # everything OPM lists in those years
  python -m pipeline.measures.backfill --dataset employment --from 2012

Extracts land in data/work/measures/{filename}.parquet; a file with an extract is skipped, so the run resumes.
Months with a raw parquet already in data/raw are extracted from it without downloading.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import duckdb
import requests

from pipeline.config import DATASETS, FWD_BLOB, RAW
from pipeline.fwd.discover import current_files
from pipeline.fwd.download import HEADERS, _stream
from pipeline.measures.build import EXTRACT_DIR
from pipeline.measures.extract_fwd import EraError, extract_actions, extract_employment, write_facts

log = logging.getLogger("backfill")


def extract_path(filename: str) -> Path:
    return EXTRACT_DIR / f"{filename}.parquet"


def raw_for(filename: str) -> Path | None:
    for ext in (".parquet", ".txt"):
        p = RAW / f"{filename}{ext}"
        if p.exists():
            return p
    return None


def download_text(filename: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    txt = RAW / f"{filename}.txt"
    url = FWD_BLOB.format(filename=filename)
    delay = 15
    for attempt in range(1, 6):
        try:
            _stream(url, txt)
            return txt
        except requests.RequestException as exc:
            log.warning("%s attempt %d: %s", filename, attempt, exc)
            time.sleep(delay)
            delay = min(delay * 2, 120)
    raise RuntimeError(f"could not download {filename}")


def process(f: dict, con: duckdb.DuckDBPyConnection, keep_raw: bool) -> str:
    filename, dataset = f["filename"], f["dataset"]
    out = extract_path(filename)
    if out.exists():
        return "skip"
    raw = raw_for(filename)
    downloaded = False
    if raw is None:
        raw = download_text(filename)
        downloaded = True
    try:
        facts = extract_employment(raw, con) if dataset == "employment" else extract_actions(raw, con)
    except EraError as exc:
        log.error("%s", exc)
        if downloaded:
            raw.unlink()
        return "era-error"
    write_facts(facts, out, con)
    if downloaded and not keep_raw:
        raw.unlink()
    return "done"


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", type=int, default=2005)
    p.add_argument("--to", dest="end", type=int, default=2026)
    p.add_argument("--dataset", action="append", choices=DATASETS)
    p.add_argument("--keep-raw", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args(argv)
    files = [f for f in current_files() if a.start <= int(f["year"]) <= a.end and (not a.dataset or f["dataset"] in a.dataset)]
    files.sort(key=lambda f: (f["yyyymm"], f["dataset"]))
    if a.limit:
        files = files[: a.limit]
    log.info("%d files in scope", len(files))
    con = duckdb.connect()
    counts = {"done": 0, "skip": 0, "era-error": 0, "failed": 0}
    t0 = time.time()
    for i, f in enumerate(files, 1):
        try:
            status = process(f, con, a.keep_raw)
        except Exception as exc:  # noqa: BLE001
            log.error("failed %s: %s", f["filename"], exc)
            status = "failed"
        counts[status] += 1
        if status != "skip":
            log.info("[%d/%d] %s %s (%.0f min elapsed)", i, len(files), f["filename"], status, (time.time() - t0) / 60)
    log.info("backfill finished: %s", counts)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
