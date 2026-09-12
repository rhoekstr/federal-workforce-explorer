"""PLUM: the statutory list of policy and supporting positions (5 U.S.C. 3330f).

Unlike the workforce files, PLUM names people. That is the point of the statute: it exists so the public can
see who holds the leadership positions of the executive branch. Fed Pulse shows it as published and never
joins it to workforce records (PRD Non-Goal 2) — the directory stands alone.

The endpoint refuses a bare client; it needs a browser user agent. Snapshots are dated by the "as of" the
site advertises, falling back to the fetch date, and stored one file per snapshot so a later pull adds a point
to the position history rather than replacing it.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import duckdb
import requests

from pipeline.config import PLUM_DOWNLOAD, RAW, REFERENCE

log = logging.getLogger(__name__)
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Referer": "https://www.opm.gov/",
    "Origin": "https://www.opm.gov",
}
# The accumulated position history is committed (about 350 KB), not derived: PLUM publishes only a current
# snapshot, so the record of what it said last time exists nowhere else. CI fetches today's snapshot, merges
# it into this file, and commits it back.
PLUM_DIR = REFERENCE / "plum"
POSITIONS = PLUM_DIR / "positions.parquet"

# Appointment types, as PLUM codes them. "Political" is the set a new administration replaces.
APPOINTMENT_TYPES = {
    "PAS": ("Presidential appointment with Senate confirmation", "political"),
    "PA": ("Presidential appointment", "political"),
    "SC": ("Schedule C", "political"),
    "NA": ("Noncareer SES", "political"),
    "TA": ("Time-limited SES", "political"),
    "CA": ("Career", "career"),
    "XS": ("Excepted service", "career"),
    "CG": ("Career SES, general", "career"),
    "DA": ("Other", "career"),
}
STATUSES = ("Filled", "Vacant", "Historical")


def fetch(snapshot: str | None = None) -> Path:
    """Download the PLUM CSV. Returns the raw path; skips the download when that snapshot is already here."""
    snapshot = snapshot or date.today().isoformat()
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / f"plum_{snapshot}.csv"
    if out.exists():
        log.info("plum snapshot %s already downloaded", snapshot)
        return out
    r = requests.get(PLUM_DOWNLOAD, headers=HEADERS, data="{}", timeout=180)
    r.raise_for_status()
    if not r.content.lstrip(b"\xef\xbb\xbf").startswith(b"Agency,"):
        raise RuntimeError(f"PLUM download did not return the expected CSV header: {r.content[:120]!r}")
    out.write_bytes(r.content)
    log.info("plum snapshot %s: %.1f MB", snapshot, len(r.content) / 1e6)
    return out


def _clean(col: str) -> str:
    """PLUM serves HTML entities in free text: &#039; for an apostrophe, &amp; for an ampersand."""
    inner = f"trim({col})"
    for entity, literal in (("&#039;", "''"), ("&amp;", "&"), ("&quot;", '"'), ("&nbsp;", " ")):
        inner = f"replace({inner}, '{entity}', '{literal}')"
    return inner


def _date_sql(col: str) -> str:
    """PLUM dates are mm/dd/yyyy, sometimes blank."""
    return f"CASE WHEN {col} IS NULL OR {col} = '' THEN NULL ELSE strftime(strptime({col}, '%m/%d/%Y'), '%Y-%m-%d') END"


def build_positions(snapshots: list[Path] | None = None, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Union every downloaded snapshot into one positions table, deduplicated across snapshots.

    A position is identified by (agency, organization, title, individual id, begin date); the same row seen in
    two snapshots collapses to one with first_snapshot and last_snapshot recording the span we observed it.
    """
    con = con or duckdb.connect()
    files = snapshots or sorted(RAW.glob("plum_*.csv"))
    if not files and not POSITIONS.exists():
        raise RuntimeError(f"no PLUM snapshots in {RAW} and no committed history")
    PLUM_DIR.mkdir(parents=True, exist_ok=True)
    parts = []
    carried = ""
    if POSITIONS.exists():
        # Carry the committed history forward. Its span is already collapsed, so contribute both endpoints and
        # let the min/max below re-derive the same span when no new snapshot touches the row.
        cols = "agency_name, org_name, title, status, appointment_type, pay_plan, level_grade_pay, duty_location, first_name, last_name, individual_id, begin_date, vacate_date, expiration_date, tenure"
        carried = f"""
        SELECT first_snapshot AS snapshot, {cols} FROM read_parquet('{POSITIONS}')
        UNION ALL
        SELECT last_snapshot AS snapshot, {cols} FROM read_parquet('{POSITIONS}')
        UNION ALL
        """
    for f in files:
        snap = re.search(r"plum_(\d{4}-\d{2}-\d{2})", f.name).group(1)
        parts.append(f"""
        SELECT '{snap}' AS snapshot, {_clean("Agency")} AS agency_name, {_clean("Organization")} AS org_name,
               {_clean('"Position Title"')} AS title,
               "Position Status" AS status, "Appointment Type" AS appointment_type, "Pay Plan" AS pay_plan,
               {_clean('"Level, Grade, or Pay"')} AS level_grade_pay, {_clean('"Duty Location"')} AS duty_location,
               nullif({_clean('"First Name"')}, '') AS first_name, nullif({_clean('"Last Name"')}, '') AS last_name,
               nullif("Individual Unique ID", '') AS individual_id,
               {_date_sql('"Begin Date"')} AS begin_date, {_date_sql('"Vacate Date"')} AS vacate_date,
               {_date_sql('"Expiration Date"')} AS expiration_date, nullif(Tenure, '') AS tenure
        FROM read_csv('{f}', header=true, all_varchar=true)
        """)
    types_sql = " ".join(f"WHEN '{c}' THEN '{kind}'" for c, (_, kind) in APPOINTMENT_TYPES.items())
    labels_sql = " ".join(f"WHEN '{c}' THEN '{label}'" for c, (label, _) in APPOINTMENT_TYPES.items())
    con.execute(f"""
    CREATE OR REPLACE TABLE plum AS
    WITH raw AS ({carried}{" UNION ALL ".join(parts)})
    SELECT agency_name, org_name, title, status, appointment_type,
           CASE appointment_type {labels_sql} ELSE appointment_type END AS appointment_label,
           CASE appointment_type {types_sql} ELSE 'career' END AS appointment_class,
           pay_plan, level_grade_pay, duty_location, first_name, last_name, individual_id,
           begin_date, vacate_date, expiration_date, tenure,
           min(snapshot) AS first_snapshot, max(snapshot) AS last_snapshot
    FROM raw
    GROUP BY ALL
    """)
    con.execute(f"COPY (SELECT * FROM plum ORDER BY agency_name, org_name, title) TO '{POSITIONS}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n = con.execute("SELECT count(*) FROM plum").fetchone()[0]
    log.info("plum positions: %d rows from %d snapshot(s)", n, len(files))
    return n


def latest_snapshot(con: duckdb.DuckDBPyConnection | None = None) -> str:
    con = con or duckdb.connect()
    return con.execute(f"SELECT max(last_snapshot) FROM read_parquet('{POSITIONS}')").fetchone()[0]
