"""Sweep iCloud conflict copies before the suite reads the tree.

The repo lives in iCloud Drive by explicit decision, and iCloud leaves stale duplicates ("node-NL00 2.json")
when the pipeline rewrites hundreds of slice files. Those files are not what the pipeline wrote, so a suite
that sees them is testing iCloud, not Fed Pulse. `pipeline.cli` sweeps on every command; pytest does not go
through the CLI, so it sweeps here.
"""
import pytest

from pipeline.hygiene import sweep


@pytest.fixture(scope="session", autouse=True)
def _sweep_icloud_conflicts():
    removed = sweep()
    if removed:
        print(f"\nswept {len(removed)} iCloud conflict copies before the suite")
    return removed
