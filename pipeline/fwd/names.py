"""Harvest sub-element names from historical employment files.

The org lookup learns names only from months the fact pipeline processes, which is 2025 onward. The measures
history runs to 2005, so units that were abolished before 2025 appear on real charts with no name — 165 of
them at the time of writing, including an Army command carrying 16,000 people.

The names are in the files themselves. This walks the smallest set of months that covers the nameless units,
reads two columns out of each, and merges the result into the lookup as name history dated to the month it
came from. Files are large; each is deleted as soon as it is read.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict

import duckdb

from pipeline.config import RAW, REFERENCE, ROOT
from pipeline.fwd.discover import current_files
from pipeline.measures.backfill import download_text
from pipeline.fwd.facts import ORG_CODE_SQL
from pipeline.fwd.lookups import LOOKUPS, load_lookup
from pipeline.fwd.raw import raw_source_sql
from pipeline.measures.build import EXTRACT_DIR

log = logging.getLogger(__name__)
MAX_FILES = 30
# Committed, because these units vanished before the current files and their names exist nowhere else the
# pipeline can reach. CI reads this; re-harvesting is a local step.
NAMES_PATH = REFERENCE / "historical_names.json"


def nameless_nodes() -> set[str]:
    """Sub-element codes whose display name is still a placeholder."""
    nodes = json.loads((ROOT / "catalog" / "nodes.json").read_text())["nodes"]
    return {c for c, v in nodes.items() if "historical sub-element" in v.get("name", "") or v["name"] == c}


def covering_months(targets: set[str], con: duckdb.DuckDBPyConnection | None = None) -> list[str]:
    """Fewest months whose employment files name every target, greedily, preferring later months."""
    if not targets:
        return []
    con = con or duckdb.connect()
    files = sorted(str(p) for p in EXTRACT_DIR.glob("employment_*.parquet"))
    rows = con.execute(
        f"SELECT node, period_start FROM read_parquet({files!r}, union_by_name=true) "
        f"WHERE measure = 'headcount' AND dim IS NULL AND value > 0 AND node IN ({','.join(repr(c) for c in targets)})"
    ).fetchall()
    by_month: dict[str, set[str]] = defaultdict(set)
    for node, period in rows:
        by_month[period].add(node)
    uncovered, chosen = set(targets), []
    while uncovered and len(chosen) < MAX_FILES:
        best = max(by_month, key=lambda m: (len(by_month[m] & uncovered), m))
        gain = by_month[best] & uncovered
        if not gain:
            break
        chosen.append(best)
        uncovered -= gain
    if uncovered:
        log.warning("%d units are not named by any month in the covering set", len(uncovered))
    return chosen


def harvest(months: list[str], con: duckdb.DuckDBPyConnection | None = None) -> dict[str, dict[str, str]]:
    """{month: {org_code: name}} — one download at a time, deleted as soon as it is read."""
    con = con or duckdb.connect()
    wanted = {f["yyyymm"]: f for f in current_files() if f["dataset"] == "employment"}
    out: dict[str, dict[str, str]] = {}
    for period in months:
        yyyymm = period[:4] + period[5:7]
        meta = wanted.get(yyyymm)
        if not meta:
            log.warning("OPM lists no employment file for %s", yyyymm)
            continue
        txt = RAW / f"{meta['filename']}.txt"
        downloaded = not txt.exists()
        try:
            if downloaded:
                txt = download_text(meta["filename"])
            pairs = con.execute(
                f"SELECT {ORG_CODE_SQL} AS code, mode(agency_subelement) AS name FROM {raw_source_sql(txt)} "
                f"WHERE agency_subelement IS NOT NULL AND agency_subelement NOT IN ('', 'NO DATA REPORTED') GROUP BY 1"
            ).fetchall()
            out[yyyymm] = {c: n for c, n in pairs if c and n}
            log.info("%s: %d sub-element names", yyyymm, len(out[yyyymm]))
        except Exception as exc:  # noqa: BLE001 - one bad month must not stop the harvest
            log.error("%s: %s", yyyymm, exc)
        finally:
            if downloaded and txt.exists():
                txt.unlink()
    return out


def write_reference(harvested: dict[str, dict[str, str]], targets: set[str] | None = None) -> dict[str, dict]:
    """Write data/reference/historical_names.json: code -> {name, from}.

    These units are not in the org lookup at all — they were abolished before the months the fact pipeline
    processes, which is why they had no name. So this is a new source of truth rather than a merge, and it is
    committed so CI has it. The latest month a name was seen wins, matching the lookup's own rule.
    """
    existing = json.loads(NAMES_PATH.read_text()) if NAMES_PATH.exists() else {}
    out = dict(existing)
    for yyyymm in sorted(harvested):
        for code, name in harvested[yyyymm].items():
            if targets is not None and code not in targets:
                continue
            prior = out.get(code)
            if prior is None or yyyymm >= prior.get("from", ""):
                out[code] = {"name": name, "from": yyyymm}
    NAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NAMES_PATH.write_text(json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True))
    log.info("wrote %d historical names to %s", len(out), NAMES_PATH.name)
    return out


def run() -> dict:
    targets = nameless_nodes()
    log.info("%d units need a name", len(targets))
    if not targets:
        return {"targets": 0, "months": 0, "named": 0}
    months = covering_months(targets)
    log.info("covering set: %d months (%s)", len(months), ", ".join(m[:7] for m in months))
    harvested = harvest(months)
    written = write_reference(harvested, targets)
    named = sum(1 for c in targets if c in written)
    return {"targets": len(targets), "months": len(months), "named": named}
