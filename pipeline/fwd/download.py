"""Download one FWD file: stream text, validate header, convert to raw parquet, delete text."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from pipeline.config import FWD_BLOB, RAW
from pipeline.fwd.raw import text_to_parquet
from pipeline.fwd.schema import SchemaError, validate_header

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "federal-workforce-explorer (github.com/rhoekstr)"}
MAX_ATTEMPTS = 5


def _stream(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, headers=HEADERS, stream=True, timeout=(30, 600)) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    tmp.replace(dest)


def fetch(filename: str, dataset: str, keep_text: bool = False) -> Path:
    """Return the raw parquet path for an FWD filename like 'employment_202607_1'."""
    RAW.mkdir(parents=True, exist_ok=True)
    parquet = RAW / f"{filename}.parquet"
    if parquet.exists():
        return parquet
    txt = RAW / f"{filename}.txt"
    if not txt.exists():
        url = FWD_BLOB.format(filename=filename)
        delay = 15
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                log.info("downloading %s (attempt %d)", filename, attempt)
                _stream(url, txt)
                break
            except requests.RequestException as exc:
                log.warning("%s: %s", filename, exc)
                if attempt == MAX_ATTEMPTS:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 120)
    try:
        validate_header(txt, dataset)
    except SchemaError:
        txt.rename(txt.with_suffix(".rejected.txt"))
        raise
    rows = text_to_parquet(txt, parquet)
    log.info("%s: %d rows -> %s", filename, rows, parquet.name)
    if not keep_text:
        txt.unlink()
    return parquet
