"""Restore raw parquet from GitHub Releases so a fresh runner can rebuild lookups and facts without hitting OPM.

  python -m pipeline.restore --since 202501
"""
from __future__ import annotations

import argparse
import logging
import subprocess

import requests

from pipeline import manifest as mf
from pipeline.config import DATASETS, RAW, ROOT, WORK
from pipeline.fwd.facts import fact_path

log = logging.getLogger("pipeline.restore")


def _download(url: str, dest) -> None:
    with requests.get(url, stream=True, timeout=(30, 600)) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)


def restore(since: str, include_raw: bool = False) -> int:
    """Facts are always restored for every published month (the site needs all of them); `since` bounds raw parquet."""
    manifest = mf.load()
    RAW.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    n = 0
    for dataset in DATASETS:
        for yyyymm, entry in sorted(manifest["datasets"].get(dataset, {}).items()):
            fact = fact_path(dataset, yyyymm)
            if entry.get("release_url") and not fact.exists():
                _download(entry["release_url"], fact)
                n += 1
            if yyyymm < since:
                continue
            raw = RAW / f"{dataset}_{yyyymm}_{entry['version']}.parquet"
            if include_raw and entry.get("raw_release_url") and not raw.exists():
                _download(entry["raw_release_url"], raw)
                n += 1
    log.info("restored %d files", n)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument("--since", default="202501")
    p.add_argument("--raw", action="store_true", help="also restore raw parquet (needed only to rebuild lookups from scratch)")
    a = p.parse_args()
    restore(a.since, a.raw)
