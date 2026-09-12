"""Sweep iCloud conflict copies before any pipeline step reads or writes the tree.

The repo lives in iCloud Drive, and when the pipeline rewrites hundreds of slice files quickly iCloud
races itself and leaves copies named "orgtree 2.json", "DL 3", "measures 2.parquet". They are byte-for-byte
stale, they get swept into commits, and one of them corrupted the git index. Moving the repo out of iCloud is
the real fix; until then every `pipeline.cli` command sweeps them first so they never reach a commit.

The pattern is a space, then digits, immediately before the extension or at the end of the name.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from pipeline.config import ROOT

log = logging.getLogger(__name__)
CONFLICT = re.compile(r" \d+(\.[A-Za-z0-9]+)?$")
SWEEP_DIRS = ("data", "site", "catalog", "crosswalk", "docs", "pipeline", ".git")


def is_conflict_copy(path: Path) -> bool:
    """True for 'name 2.json' and 'name 3'; false for legitimate names like 'ap_5_tables_1-3.xlsx'."""
    stem_and_ext = path.name
    return bool(CONFLICT.search(stem_and_ext))


def sweep(root: Path | None = None, dry_run: bool = False) -> list[Path]:
    """Delete every iCloud conflict copy under the sweep directories. Returns what was removed."""
    root = root or ROOT
    removed: list[Path] = []
    for name in SWEEP_DIRS:
        base = root / name
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and is_conflict_copy(path):
                if not dry_run:
                    try:
                        path.unlink()
                    except OSError as exc:  # noqa: PERF203 - one bad file must not stop the sweep
                        log.warning("could not remove %s: %s", path, exc)
                        continue
                removed.append(path)
    if removed:
        log.info("swept %d iCloud conflict copies", len(removed))
    return removed
