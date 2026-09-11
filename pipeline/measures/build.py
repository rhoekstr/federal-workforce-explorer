"""Assemble measures.parquet: union extracts, roll nodes up, add group headcount, evaluate derived, write slices."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

from pipeline import manifest as mf
from pipeline.config import SLICES, WORK
from pipeline.fwd.lookups import load_lookup
from pipeline.measures.catalog import Catalog, write_public_catalog
from pipeline.measures.evaluator import Evaluator
from pipeline.measures.extract_other import fevs_facts, money_facts, omb_facts
from pipeline.money.groups import load_groups

log = logging.getLogger(__name__)
EXTRACT_DIR = WORK / "measures"
OUT = WORK / "measures.parquet"
SLICE_DIR = SLICES / "measures"
NODES_PATH = Path("catalog") / "nodes.json"


def build_nodes() -> dict[str, dict]:
    """catalog/nodes.json from the lookups and the overview groups."""
    agency = load_lookup("agency")
    org = load_lookup("org")
    department = load_lookup("department")
    groups = load_groups()
    nodes: dict[str, dict] = {"gov": {"code": "gov", "kind": "gov", "name": "Federal civilian workforce", "parent": None}}
    by_dept: dict[str, list[str]] = {}
    for code, a in agency.items():
        by_dept.setdefault(a["department_code"], []).append(code)
    for dept, codes in by_dept.items():
        multi = len(codes) > 1
        if multi:
            d = department.get(dept, {})
            nodes[f"D:{dept}"] = {"code": f"D:{dept}", "kind": "department", "name": d.get("name", dept).title(), "parent": "gov", "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen")}
        for code in codes:
            a = agency[code]
            nodes[code] = {"code": code, "kind": "agency", "name": a["name"].title(), "parent": f"D:{dept}" if multi else "gov", "first_seen": a["first_seen"], "last_seen": a["last_seen"]}
    for code, o in org.items():
        nodes[code] = {"code": code, "kind": "subelement", "name": o["name"].title(), "parent": o["agency_code"], "first_seen": o["first_seen"], "last_seen": o["last_seen"]}
    for gid, g in groups.items():
        nodes[gid] = {"code": gid, "kind": "group", "name": g["name"], "parent": None, "members": {"agencies": g["fwd_agency_codes"], "orgs": g.get("fwd_org_codes", []), "exclude_orgs": g.get("fwd_exclude_org_codes", [])}}
    NODES_PATH.parent.mkdir(exist_ok=True)
    NODES_PATH.write_text(json.dumps({"nodes": nodes}, indent=0, ensure_ascii=False))
    return nodes


def _load_extracts(con: duckdb.DuckDBPyConnection) -> int:
    files = sorted(EXTRACT_DIR.glob("*.parquet"))
    if not files:
        raise RuntimeError(f"no extracts in {EXTRACT_DIR}")
    con.execute(f"CREATE OR REPLACE TABLE raw_facts AS SELECT * FROM read_parquet({[str(f) for f in files]}, union_by_name=true)")
    return con.execute("SELECT count(*) FROM raw_facts").fetchone()[0]


def _register_nodes(con: duckdb.DuckDBPyConnection, nodes: dict) -> None:
    con.execute("CREATE OR REPLACE TABLE nodes (code VARCHAR, kind VARCHAR, parent VARCHAR)")
    con.executemany("INSERT INTO nodes VALUES (?,?,?)", [(n["code"], n["kind"], n.get("parent")) for n in nodes.values()])
    agency = load_lookup("agency")
    con.execute("CREATE OR REPLACE TABLE agency_dept (agency VARCHAR, dept VARCHAR)")
    con.executemany("INSERT INTO agency_dept VALUES (?,?)", [(c, f"D:{a['department_code']}") for c, a in agency.items() if nodes.get(f"D:{a['department_code']}")])
    groups = load_groups()
    rows = []
    for gid, g in groups.items():
        for a in g["fwd_agency_codes"]:
            rows.append((gid, "agency", a, 1))
        for o in g.get("fwd_org_codes", []):
            rows.append((gid, "org", o, 1))
        for o in g.get("fwd_exclude_org_codes", []):
            rows.append((gid, "org", o, -1))
    con.execute("CREATE OR REPLACE TABLE group_members (gid VARCHAR, kind VARCHAR, code VARCHAR, sign INTEGER)")
    con.executemany("INSERT INTO group_members VALUES (?,?,?,?)", rows)


def _base_facts(con: duckdb.DuckDBPyConnection, catalog: Catalog) -> None:
    """From raw extracts to base facts at every level: dedupe stock by latest source, sum flows across sources, roll up."""
    sums = [c for c, m in catalog.measures.items() if m["kind"] == "base" and m["aggregation"] == "sum"]
    sums_sql = ", ".join(f"'{c}'" for c in sums) or "''"
    # Flat sub-element (or agency-level dimensioned) facts, one row per key.
    con.execute(f"""
    CREATE OR REPLACE TABLE leaf AS
    SELECT measure, node, period_type, period_start, dim, dim_value,
           CASE WHEN measure IN ({sums_sql}) THEN sum(value) ELSE arg_max(value, source_ref) END AS value,
           NULL::BIGINT AS n, max(notation) AS notation, max(source_ref) AS source_ref
    FROM raw_facts GROUP BY measure, node, period_type, period_start, dim, dim_value
    """)
    # Level of each leaf node: sub-element rows have 4-char codes (or agency + '__'); dimensioned rows are agency-level.
    con.execute("""
    CREATE OR REPLACE TABLE facts AS
    WITH sub AS (
      SELECT * FROM leaf WHERE dim IS NULL AND node IN (SELECT code FROM nodes WHERE kind = 'subelement')
    ), orphan AS (
      SELECT * FROM leaf WHERE dim IS NULL AND node NOT IN (SELECT code FROM nodes WHERE kind = 'subelement')
    ), agency_flat AS (
      SELECT measure, substr(node, 1, 2) AS node, period_type, period_start, dim, dim_value, sum(value) AS value, n, max(notation) AS notation, max(source_ref) AS source_ref
      FROM (SELECT * FROM sub UNION ALL SELECT * FROM orphan) GROUP BY measure, substr(node, 1, 2), period_type, period_start, dim, dim_value, n
    ), agency_dim AS (
      SELECT * FROM leaf WHERE dim IS NOT NULL
    ), agency_all AS (
      SELECT * FROM agency_flat UNION ALL SELECT * FROM agency_dim
    ), dept AS (
      SELECT a.measure, d.dept AS node, a.period_type, a.period_start, a.dim, a.dim_value, sum(a.value) AS value, a.n, max(a.notation) AS notation, max(a.source_ref) AS source_ref
      FROM agency_all a JOIN agency_dept d ON d.agency = a.node
      GROUP BY a.measure, d.dept, a.period_type, a.period_start, a.dim, a.dim_value, a.n
    ), gov AS (
      SELECT measure, 'gov' AS node, period_type, period_start, dim, dim_value, sum(value) AS value, n, max(notation) AS notation, max(source_ref) AS source_ref
      FROM agency_all GROUP BY measure, period_type, period_start, dim, dim_value, n
    )
    SELECT * FROM sub UNION ALL SELECT * FROM orphan UNION ALL SELECT * FROM agency_all UNION ALL SELECT * FROM dept UNION ALL SELECT * FROM gov
    """)
    # A unit that exists (has a headcount) but recorded no actions of a kind that month had zero of them, not an unknown number.
    flows = [(c, m["since"]) for c, m in catalog.measures.items() if m["kind"] == "base" and m["aggregation"] == "sum" and m["cadence"] == "month"]
    for code, since in flows:
        con.execute(f"""
        INSERT INTO facts
        SELECT '{code}', h.node, 'month', h.period_start, NULL, NULL, 0.0, NULL, NULL, 'zero-fill'
        FROM (SELECT DISTINCT node, period_start FROM facts WHERE measure = 'headcount' AND dim IS NULL AND period_type = 'month' AND period_start >= '{since}'
              AND period_start <= (SELECT max(period_start) FROM facts WHERE measure = '{code}' AND dim IS NULL)) h
        WHERE NOT EXISTS (SELECT 1 FROM facts f WHERE f.measure = '{code}' AND f.node = h.node AND f.period_start = h.period_start AND f.dim IS NULL)
        """)
    # Group headcount for money ratios: members' agencies plus/minus org codes.
    con.execute("""
    INSERT INTO facts
    SELECT 'headcount', g.gid, f.period_type, f.period_start, NULL, NULL, sum(f.value * g.sign), NULL, NULL, max(f.source_ref)
    FROM group_members g JOIN facts f ON f.node = g.code AND f.measure = 'headcount' AND f.dim IS NULL
     AND f.node IN (SELECT code FROM nodes WHERE kind IN ('agency', 'subelement'))
    GROUP BY g.gid, f.period_type, f.period_start
    """)


def _insert(con: duckdb.DuckDBPyConnection, facts: list[tuple]) -> None:
    if facts:
        con.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?)", facts)


def _write_slices(con: duckdb.DuckDBPyConnection, catalog: Catalog, nodes: dict) -> None:
    SLICE_DIR.mkdir(parents=True, exist_ok=True)
    for stale in SLICE_DIR.glob("*.json"):
        stale.unlink()
    write_public_catalog(catalog, SLICE_DIR / "catalog.json")
    (SLICE_DIR / "nodes.json").write_text(json.dumps({"nodes": nodes}, separators=(",", ":"), ensure_ascii=False))
    # Government-wide series for every flat measure, plus per-node series for departments, agencies, and groups.
    shown = [c for c, m in catalog.measures.items() if m.get("display", True)]
    con.execute("CREATE OR REPLACE TABLE shown_measures AS SELECT unnest(?) AS measure", [shown])
    rows = con.execute("""
        SELECT f.node, f.measure, f.period_type, f.period_start, f.value, f.n, f.notation
        FROM facts f JOIN nodes k ON k.code = f.node JOIN shown_measures s ON s.measure = f.measure
        WHERE f.dim IS NULL AND k.kind IN ('gov', 'department', 'agency', 'group') AND f.value IS NOT NULL
        ORDER BY f.node, f.measure, f.period_start
    """).fetchall()
    per_node: dict[str, dict] = {}
    for node, measure, pt, ps, value, n, notation in rows:
        entry = per_node.setdefault(node, {}).setdefault(measure, {"period_type": pt, "values": {}})
        v = round(value, 2 if abs(value) >= 100 else 4)
        entry["values"][ps] = [v, n, notation] if notation else ([v, n] if n is not None else [v])
    for node, measures in per_node.items():
        (SLICE_DIR / f"{node}.json").write_text(json.dumps({"node": node, "measures": measures}, separators=(",", ":")))
    # Latest current snapshot for every node and measure (all levels), for vitals strips.
    current = con.execute("""
        SELECT node, measure, period_type, period_start, value, n, notation FROM (
          SELECT *, row_number() OVER (PARTITION BY node, measure ORDER BY period_start DESC) AS rn FROM facts WHERE dim IS NULL AND value IS NOT NULL AND measure IN (SELECT measure FROM shown_measures)
        ) WHERE rn = 1
    """).fetchall()
    snap: dict[str, dict] = {}
    for node, measure, pt, ps, value, n, notation in current:
        snap.setdefault(node, {})[measure] = {"p": ps, "t": pt, "v": round(value, 4), **({"n": n} if n is not None else {}), **({"note": notation} if notation else {})}
    (SLICE_DIR / "current.json").write_text(json.dumps(snap, separators=(",", ":")))
    total = sum(p.stat().st_size for p in SLICE_DIR.glob("*.json"))
    log.info("measure slices: %d node files, %.1f MB", len(per_node), total / 1e6)


def _add_historical_nodes(con: duckdb.DuckDBPyConnection, nodes: dict[str, dict]) -> int:
    """Agencies and sub-elements that appear in the history but not in the current OPM lookups get code-named nodes."""
    rows = con.execute("""
        SELECT node, min(period_start), max(period_start) FROM raw_facts
        WHERE measure = 'headcount' AND dim IS NULL AND (length(node) = 4 OR (length(node) = 2 AND node = upper(node)))
        GROUP BY node
    """).fetchall()
    added = 0
    for code, first, last in rows:
        if code in nodes:
            continue
        if len(code) == 2:
            nodes[code] = {"code": code, "kind": "agency", "name": f"Agency {code} (historical; not in current OPM files)", "parent": "gov", "first_seen": first[:7].replace("-", ""), "last_seen": last[:7].replace("-", ""), "historical": True}
        else:
            parent = code[:2]
            if parent not in nodes:
                nodes[parent] = {"code": parent, "kind": "agency", "name": f"Agency {parent} (historical; not in current OPM files)", "parent": "gov", "first_seen": first[:7].replace("-", ""), "last_seen": last[:7].replace("-", ""), "historical": True}
            nodes[code] = {"code": code, "kind": "subelement", "name": f"{code} (historical sub-element; name not in current OPM files)", "parent": parent, "first_seen": first[:7].replace("-", ""), "last_seen": last[:7].replace("-", ""), "historical": True}
        added += 1
    NODES_PATH.write_text(json.dumps({"nodes": nodes}, indent=0, ensure_ascii=False))
    log.info("added %d historical nodes", added)
    return added


def build_measures(fetch_money: bool = False) -> dict:
    catalog = Catalog.load()
    nodes = build_nodes()
    con = duckdb.connect()
    n_raw = _load_extracts(con)
    _add_historical_nodes(con, nodes)
    _register_nodes(con, nodes)
    _base_facts(con, catalog)
    _insert(con, money_facts(fetch=fetch_money))
    _insert(con, omb_facts())
    _insert(con, fevs_facts())
    unknown = con.execute("SELECT DISTINCT measure FROM facts WHERE measure NOT IN (SELECT unnest(?))", [list(catalog.measures)]).fetchall()
    if unknown:
        raise RuntimeError(f"facts reference measures not in the catalog: {[u[0] for u in unknown]}")
    Evaluator(con, catalog).evaluate_all()
    con.execute(f"COPY (SELECT * FROM facts ORDER BY node, measure, period_type, period_start, dim, dim_value) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    stats = con.execute("SELECT count(*), count(DISTINCT node), count(DISTINCT measure), min(period_start), max(period_start) FROM facts").fetchone()
    _write_slices(con, catalog, nodes)
    manifest = mf.load()
    manifest["measures"] = {"rows": stats[0], "nodes": stats[1], "measures": stats[2], "first_period": stats[3], "last_period": stats[4], "parquet_bytes": OUT.stat().st_size, "extracts": n_raw}
    mf.save(manifest)
    log.info("measures.parquet: %s rows, %s nodes, %s measures, %s to %s, %.1f MB", *stats, OUT.stat().st_size / 1e6)
    return manifest["measures"]
