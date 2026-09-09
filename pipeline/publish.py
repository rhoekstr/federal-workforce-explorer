"""Publish fact parquet to GitHub Releases (one release per month, tag data-YYYYMM) and record URLs in the manifest.

Uses the `gh` CLI, which is authenticated locally and via GITHUB_TOKEN in Actions.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from pipeline import manifest as mf
from pipeline.config import DATASETS, RAW, ROOT, WORK

log = logging.getLogger(__name__)


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=ROOT, text=True, capture_output=True, check=check)


def current_repo(repo: str | None = None) -> str:
    if repo:
        return repo
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    out = _gh("repo", "view", "--json", "nameWithOwner").stdout
    return json.loads(out)["nameWithOwner"]


def release_exists(repo: str, tag: str) -> bool:
    return _gh("release", "view", tag, "--repo", repo, check=False).returncode == 0


def ensure_release(repo: str, tag: str, yyyymm: str) -> None:
    if release_exists(repo, tag):
        return
    title = f"Data {yyyymm[:4]}-{yyyymm[4:]}"
    notes = (
        f"Aggregated OPM Federal Workforce Data for {yyyymm[:4]}-{yyyymm[4:]}: employment snapshot, accessions, separations. "
        "Schema and definitions: see data.html on the site and PRD.md in the repo. Raw parquet (all source columns, no PII) is included for reproducibility."
    )
    _gh("release", "create", tag, "--repo", repo, "--title", title, "--notes", notes)
    log.info("created release %s", tag)


def upload(repo: str, tag: str, path: Path) -> str:
    _gh("release", "upload", tag, str(path), "--repo", repo, "--clobber")
    return f"https://github.com/{repo}/releases/download/{tag}/{path.name}"


def publish_releases(repo: str | None = None, include_raw: bool = True, only_missing: bool = True) -> dict:
    repo = current_repo(repo)
    manifest = mf.load()
    published = {}
    months = sorted({m for ds in manifest["datasets"].values() for m in ds})
    for yyyymm in months:
        tag = f"data-{yyyymm}"
        assets = []
        for dataset in DATASETS:
            entry = manifest["datasets"].get(dataset, {}).get(yyyymm)
            if not entry:
                continue
            path = WORK / entry["file"]
            if not path.exists():
                log.warning("missing %s, skipping", path)
                continue
            if only_missing and entry.get("release_url") and entry.get("release_sha256") == entry["sha256"]:
                continue
            assets.append((dataset, entry, path))
        raw_assets = []
        if include_raw:
            for dataset in DATASETS:
                entry = manifest["datasets"].get(dataset, {}).get(yyyymm)
                if not entry:
                    continue
                raw = RAW / f"{dataset}_{yyyymm}_{entry['version']}.parquet"
                if raw.exists() and not (only_missing and entry.get("raw_release_url")):
                    raw_assets.append((dataset, entry, raw))
        if not assets and not raw_assets:
            continue
        ensure_release(repo, tag, yyyymm)
        for dataset, entry, path in assets:
            entry["release_url"] = upload(repo, tag, path)
            entry["release_sha256"] = entry["sha256"]
            published[f"{dataset}/{yyyymm}"] = entry["release_url"]
            log.info("uploaded %s", path.name)
        for dataset, entry, raw in raw_assets:
            entry["raw_release_url"] = upload(repo, tag, raw)
            log.info("uploaded raw %s", raw.name)
        mf.save(manifest)
    manifest["releases"]["repo"] = repo
    mf.save(manifest)
    return published
