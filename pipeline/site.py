"""Assemble the deployable static site in _site/: site/ plus the data the pages read."""
from __future__ import annotations

import logging
import shutil

import json

from pipeline.config import CROSSWALK, LOOKUPS, MANIFEST, ROOT, SLICES, WORK

log = logging.getLogger(__name__)
SITE_SRC = ROOT / "site"
SITE_OUT = ROOT / "_site"


def assemble() -> None:
    if SITE_OUT.exists():
        shutil.rmtree(SITE_OUT)
    shutil.copytree(SITE_SRC, SITE_OUT)
    data = SITE_OUT / "data"
    shutil.copytree(SLICES, data / "slices")
    shutil.copytree(LOOKUPS, data / "lookups")
    shutil.copytree(ROOT / "data" / "geo", data / "geo")
    (data / "crosswalk").mkdir(parents=True, exist_ok=True)
    for name in ("agency_groups.json", "review.json", "plum_org.json", "plum_review.json", "no_money.json"):
        src = CROSSWALK / name
        if src.exists():
            shutil.copy(src, data / "crosswalk" / name)
    # Fact parquet travels with the site so in-browser queries work even while the repo is private.
    manifest = json.loads(MANIFEST.read_text())
    facts = data / "facts"
    facts.mkdir(parents=True, exist_ok=True)
    for dataset, months in manifest.get("datasets", {}).items():
        for yyyymm, entry in months.items():
            src = WORK / entry["file"]
            if src.exists():
                shutil.copy(src, facts / entry["file"])
                entry["site_url"] = f"data/facts/{entry['file']}"
    # GitHub Release assets send no CORS header, so the browser reads the measures table from the site's own origin.
    from pipeline.measures.build import OUT as MEASURES_PARQUET
    if MEASURES_PARQUET.exists():
        shutil.copy(MEASURES_PARQUET, data / "measures.parquet")
        manifest.setdefault("measures", {})["site_url"] = "data/measures.parquet"
    (data / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    (SITE_OUT / ".nojekyll").write_text("")
    size = sum(p.stat().st_size for p in SITE_OUT.rglob("*") if p.is_file())
    log.info("assembled _site: %.1f MB", size / 1e6)
