"""Restore raw parquet from GitHub Releases so a fresh runner can rebuild lookups and facts without hitting OPM.

  python -m pipeline.restore --since 202501
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import time

from pipeline import manifest as mf
from pipeline.config import DATASETS, RAW, ROOT, WORK
from pipeline.fwd.facts import fact_path

log = logging.getLogger("pipeline.restore")


def _download(url: str, dest) -> None:
    """Fetch a Release asset. Uses `gh` (authenticated) because assets on a private repo 404 anonymously."""
    tag, name = url.rstrip("/").split("/")[-2], url.rstrip("/").split("/")[-1]
    repo = "/".join(url.split("/")[3:5])
    cmd = ["gh", "release", "download", tag, "--repo", repo, "--pattern", name, "--dir", str(dest.parent), "--clobber"]
    for attempt in range(1, 5):
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if result.returncode == 0:
            break
        log.warning("attempt %d failed for %s: %s", attempt, name, result.stderr.strip()[-200:])
        if attempt == 4:
            raise RuntimeError(f"could not download {name} from {tag}")
        time.sleep(10 * attempt)
    downloaded = dest.parent / name
    if downloaded != dest:
        downloaded.replace(dest)


def restore_extracts() -> int:
    """Download the measure extracts archive from the rolling measures Release when the local extract dir is empty."""
    import tarfile
    from pipeline.measures.build import EXTRACT_DIR

    manifest = mf.load()
    url = manifest.get("measures", {}).get("extracts_url")
    if EXTRACT_DIR.exists() and any(EXTRACT_DIR.glob("*.parquet")):
        log.info("measure extracts already present; not restoring")
        return 0
    if not url:
        log.warning("manifest has no measures.extracts_url; the build will see only locally extracted months")
        return 0
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    archive = EXTRACT_DIR.parent / "extracts.tar.gz"
    _download(url, archive)
    with tarfile.open(archive) as tar:
        tar.extractall(EXTRACT_DIR, filter="data")
    archive.unlink()
    n = len(list(EXTRACT_DIR.glob("*.parquet")))
    log.info("restored %d measure extracts", n)
    return n


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
    restore_extracts()
