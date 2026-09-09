"""Discover FWD files through the metadata API and compare with the manifest."""
from __future__ import annotations

import requests

from pipeline.config import DATASETS, FWD_API
from pipeline.manifest import published_versions

HEADERS = {"User-Agent": "federal-workforce-explorer (github.com/rhoekstr)", "Accept": "application/json"}


def list_files(dataset: str, year: int | None = None) -> list[dict]:
    """Every file OPM lists for a dataset: filename, version, current, month, year, publishDate."""
    params = {"year": year} if year else {}
    r = requests.get(f"{FWD_API}/{dataset}", params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    if r.status_code == 204 or not r.content:
        return []
    files = r.json()
    for f in files:
        f["yyyymm"] = f"{f['year']}{int(f['month']):02d}"
        f["dataset"] = dataset
    return sorted(files, key=lambda f: (f["yyyymm"], f["version"]))


def current_files(year: int | None = None) -> list[dict]:
    """The current version of every month for every dataset."""
    out = []
    for dataset in DATASETS:
        by_month: dict[str, dict] = {}
        for f in list_files(dataset, year):
            if f.get("current", True) and f["version"] >= by_month.get(f["yyyymm"], {}).get("version", -1):
                by_month[f["yyyymm"]] = f
        out.extend(by_month.values())
    return out


def missing_files(manifest: dict, year: int | None = None) -> list[dict]:
    """Files whose (dataset, month, version) is not in the manifest yet."""
    todo = []
    for f in current_files(year):
        have = published_versions(manifest, f["dataset"]).get(f["yyyymm"])
        if have is None or have < f["version"]:
            todo.append(f)
    return todo
