"""USAspending File B (account breakdown by program activity and object class), by fiscal period.

Values are cumulative fiscal-year-to-date obligations at the submission period. We keep one small parquet per
(fy, quarter): agency name × object class code × obligations, then compute rolling four quarters in overview.py.
"""
from __future__ import annotations

import io
import logging
import time
import zipfile
from pathlib import Path

import duckdb
import requests

from pipeline.config import RAW, REFERENCE, USASPENDING_API, WORK, classify_object_class

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "federal-workforce-explorer (github.com/rhoekstr)", "Content-Type": "application/json"}
QUARTER_LAST_PERIOD = {1: 3, 2: 6, 3: 9, 4: 12}


FILEB_DIR = REFERENCE / "fileb"


def fileb_path(fy: int, quarter: int) -> Path:
    """Aggregated File B (agency × object class × funding source), ~30 KB per quarter, committed under data/reference."""
    FILEB_DIR.mkdir(parents=True, exist_ok=True)
    return FILEB_DIR / f"fileb_FY{fy}Q{quarter}.parquet"


def _post_with_retry(url: str, body: dict, attempts: int = 4) -> dict:
    """USAspending's download endpoint returns 500s and drops connections under load; back off and retry."""
    delay = 30
    for attempt in range(1, attempts + 1):
        try:
            r = requests.post(url, json=body, headers=HEADERS, timeout=120)
            if r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} from {url}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ConnectionError) as exc:
            log.warning("download request attempt %d failed: %s", attempt, exc)
            if attempt == attempts:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 240)


def request_download(fy: int, quarter: int) -> dict:
    body = {
        "account_level": "treasury_account",
        "filters": {"fy": str(fy), "quarter": str(quarter), "submission_types": ["object_class_program_activity"], "agency": "all"},
        "file_format": "csv",
    }
    return _post_with_retry(f"{USASPENDING_API}/download/accounts/", body)


def wait_for(status_url: str, timeout_s: int = 900) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(status_url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        d = r.json()
        if d["status"] == "finished":
            return d["file_url"]
        if d["status"] == "failed":
            raise RuntimeError(f"USAspending download failed: {d}")
        time.sleep(10)
    raise TimeoutError(status_url)


def _aggregate_csv(csv_path: Path, out: Path, fy: int, quarter: int) -> int:
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          SELECT '{fy}' AS fy, {quarter} AS quarter, submission_period,
                 owning_agency_name AS agency_name, object_class_code, object_class_name,
                 coalesce(direct_or_reimbursable_funding_source, 'D') AS funding_source,
                 sum(CAST(obligations_incurred AS DOUBLE)) AS obligations
          FROM read_csv('{csv_path}', header=true, all_varchar=true)
          GROUP BY ALL
        ) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    return con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]


def fetch_fileb(fy: int, quarter: int, force: bool = False) -> Path:
    """Ensure data/work/fileb_FY{fy}Q{q}.parquet exists; download from USAspending if needed."""
    out = fileb_path(fy, quarter)
    if out.exists() and not force:
        return out
    WORK.mkdir(parents=True, exist_ok=True)
    sample = RAW / f"usaspending_fileB_FY{fy}_P01-P{QUARTER_LAST_PERIOD[quarter]:02d}.csv"
    if sample.exists():
        log.info("using local File B sample %s", sample.name)
        _aggregate_csv(sample, out, fy, quarter)
        return out
    log.info("requesting File B FY%d Q%d", fy, quarter)
    time.sleep(20)  # pace requests; the download queue is shared
    file_url = wait_for(request_download(fy, quarter)["status_url"])
    log.info("downloading %s", file_url)
    r = requests.get(file_url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=600)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError(f"no csv in File B zip for FY{fy}Q{quarter}")
        tmp = WORK / f"fileb_FY{fy}Q{quarter}.csv"
        with z.open(names[0]) as src, open(tmp, "wb") as dst:
            dst.write(src.read())
    rows = _aggregate_csv(tmp, out, fy, quarter)
    tmp.unlink()
    log.info("File B FY%d Q%d: %d aggregated rows", fy, quarter, rows)
    return out


def classified(fy: int, quarter: int, direct_only: bool = True) -> list[tuple[str, str, float]]:
    """[(agency_name, bucket, obligations)] for one (fy, quarter). Direct obligations only by default:
    reimbursable obligations are funded by other agencies' orders and double count across government."""
    con = duckdb.connect()
    where = "WHERE funding_source = 'D'" if direct_only else ""
    rows = con.execute(f"SELECT agency_name, object_class_code, sum(obligations) FROM read_parquet('{fileb_path(fy, quarter)}') {where} GROUP BY 1, 2").fetchall()
    return [(a, classify_object_class(c), v or 0.0) for a, c, v in rows]
