"""manifest.json: what is published, at which OPM version, with sizes and checksums."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import MANIFEST, ROOT


def load() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"generated": None, "datasets": {}, "money": {}, "releases": {}}


def save(manifest: dict) -> None:
    manifest["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record_fact(manifest: dict, stats: dict, publish_date: str | None = None) -> None:
    ds = manifest["datasets"].setdefault(stats["dataset"], {})
    path = ROOT / stats["path"]
    ds[stats["yyyymm"]] = {
        "version": stats["version"],
        "source_file": stats["source_file"],
        "publish_date": publish_date,
        "rows_source": stats["rows_source"],
        "rows_fact": stats["rows_fact"],
        "n": stats["n"],
        "parquet_bytes": stats["parquet_bytes"],
        "sha256": sha256(path),
        "file": path.name,
        "release_url": ds.get(stats["yyyymm"], {}).get("release_url"),
        "incomplete_note": ds.get(stats["yyyymm"], {}).get("incomplete_note"),
    }


def published_versions(manifest: dict, dataset: str) -> dict[str, int]:
    return {m: v["version"] for m, v in manifest["datasets"].get(dataset, {}).items()}
