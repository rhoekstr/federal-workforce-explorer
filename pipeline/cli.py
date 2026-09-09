"""Command line entry point.

  python -m pipeline.cli build 202607            # facts + lookups from data/raw for one month
  python -m pipeline.cli sync --year 2026        # discover, download, build every missing month
  python -m pipeline.cli money                   # USAspending + OMB -> overview
  python -m pipeline.cli slices                  # pre-computed JSON + org tree for the site
  python -m pipeline.cli site                    # assemble _site/ for local preview or Pages
  python -m pipeline.cli publish                 # upload parquet to GitHub Releases, fill manifest URLs
"""
from __future__ import annotations

import argparse
import logging
import sys

import duckdb

from pipeline import manifest as mf
from pipeline.config import DATASETS
from pipeline.fwd.discover import missing_files
from pipeline.fwd.download import fetch
from pipeline.fwd.facts import build_fact
from pipeline.fwd.lookups import update_lookups
from pipeline.fwd.raw import find_raw
from pipeline.fwd.schema import SchemaError

log = logging.getLogger("pipeline")


def build_month(yyyymm: str, datasets=DATASETS, publish_dates: dict | None = None) -> list[dict]:
    """Build facts and lookups for one month from whatever is in data/raw. Returns stats per dataset."""
    con = duckdb.connect()
    manifest = mf.load()
    out = []
    for dataset in datasets:
        raw = find_raw(dataset, yyyymm)
        if raw is None:
            log.warning("no raw %s file for %s", dataset, yyyymm)
            continue
        stats = build_fact(raw, con)
        update_lookups(raw, con)
        mf.record_fact(manifest, stats, (publish_dates or {}).get(dataset))
        log.info("%s %s: %s rows -> %s fact rows, %.1f MB", dataset, yyyymm, stats["rows_source"], stats["rows_fact"], stats["parquet_bytes"] / 1e6)
        out.append(stats)
    mf.save(manifest)
    return out


def cmd_build(args) -> int:
    build_month(args.yyyymm, args.dataset or DATASETS)
    return 0


def cmd_sync(args) -> int:
    manifest = mf.load()
    todo = missing_files(manifest, args.year)
    if args.limit:
        todo = todo[: args.limit]
    log.info("%d files to fetch", len(todo))
    failures = []
    for f in todo:
        try:
            fetch(f["filename"], f["dataset"])
            build_month(f["yyyymm"], [f["dataset"]], {f["dataset"]: f.get("publishDate")})
        except SchemaError as exc:
            log.error("schema drift, skipping dataset: %s", exc)
            failures.append((f["filename"], str(exc)))
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            log.error("failed %s: %s", f["filename"], exc)
            failures.append((f["filename"], str(exc)))
    for name, why in failures:
        log.error("FAILED %s: %s", name, why)
    return 1 if failures else 0


def cmd_money(args) -> int:
    from pipeline.money.overview import build_overview

    build_overview(force=args.force)
    return 0


def cmd_slices(args) -> int:
    from pipeline.orgtree import build_orgtree
    from pipeline.slices import build_slices

    build_slices()
    build_orgtree()
    return 0


def cmd_site(args) -> int:
    from pipeline.site import assemble

    assemble()
    return 0


def cmd_publish(args) -> int:
    from pipeline.publish import publish_releases

    publish_releases(repo=args.repo)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("yyyymm")
    b.add_argument("--dataset", action="append", choices=DATASETS)
    b.set_defaults(fn=cmd_build)
    s = sub.add_parser("sync")
    s.add_argument("--year", type=int, default=None)
    s.add_argument("--limit", type=int, default=0)
    s.set_defaults(fn=cmd_sync)
    m = sub.add_parser("money")
    m.add_argument("--force", action="store_true")
    m.set_defaults(fn=cmd_money)
    sub.add_parser("slices").set_defaults(fn=cmd_slices)
    sub.add_parser("site").set_defaults(fn=cmd_site)
    pub = sub.add_parser("publish")
    pub.add_argument("--repo", default=None)
    pub.set_defaults(fn=cmd_publish)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
