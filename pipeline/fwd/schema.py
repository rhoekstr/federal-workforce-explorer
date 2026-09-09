"""Header validation against the reference headers captured on 2026-09-09."""
from __future__ import annotations

from pathlib import Path

from pipeline.config import DATASETS, REFERENCE


class SchemaError(RuntimeError):
    """Raised when a downloaded file's header does not match the reference."""


def expected_columns(dataset: str) -> list[str]:
    if dataset not in DATASETS:
        raise ValueError(f"unknown dataset {dataset!r}")
    text = (REFERENCE / f"fwd_{dataset}_header.txt").read_text(encoding="utf-8-sig")
    return text.strip().split("|")


def read_header(path: Path) -> list[str]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return fh.readline().rstrip("\r\n").split("|")


def validate_header(path: Path, dataset: str) -> list[str]:
    """Return the columns if they match the reference exactly; raise SchemaError otherwise."""
    expected = expected_columns(dataset)
    actual = read_header(path)
    if actual == expected:
        return actual
    missing = sorted(set(expected) - set(actual))
    added = sorted(set(actual) - set(expected))
    reordered = not missing and not added
    detail = f"missing={missing} added={added}" if not reordered else "same columns, different order"
    raise SchemaError(f"{path.name}: header differs from reference for {dataset}: {detail}")
