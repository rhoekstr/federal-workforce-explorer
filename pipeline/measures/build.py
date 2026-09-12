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
from pipeline.plum.build import plum_facts
from pipeline.money.groups import load_groups

log = logging.getLogger(__name__)
EXTRACT_DIR = WORK / "measures"
TOP_DIM = 8
TOP_DIM_NOW = 14
DIM_MONTHS = 72
DIM_TREND = ("grade", "age_bracket", "supervisory", "appointment_type", "work_schedule", "pay_band")
MOVER_WINDOWS = {"3": 3, "12": 12, "60": 60, "all": None}
MOVER_ROWS = 12
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


def _load_extracts(con: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    """Returns (fact rows, extract files). The file count is the regression guard: a run that sees far
    fewer extracts than the last published build is reading a partial history and must not overwrite it."""
    files = sorted(EXTRACT_DIR.glob("*.parquet"))
    if not files:
        raise RuntimeError(f"no extracts in {EXTRACT_DIR}")
    prior = mf.load().get("measures", {}).get("extract_files")
    if prior and len(files) < prior * 0.8:
        raise RuntimeError(
            f"only {len(files)} extracts in {EXTRACT_DIR}, but the last published build used {prior}. "
            "The extract archive was probably not restored from the measures Release; refusing to "
            "replace the published table with a partial history."
        )
    con.execute(f"CREATE OR REPLACE TABLE raw_facts AS SELECT * FROM read_parquet({[str(f) for f in files]}, union_by_name=true)")
    return con.execute("SELECT count(*) FROM raw_facts").fetchone()[0], len(files)


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


def _latest_subelement_dims(con: duckdb.DuckDBPyConnection) -> int:
    """Dimensioned headcount for sub-elements, latest month only.

    Monthly dimension series stop at agency level (v0.3 design: the full history would triple the table).
    Composition needs one month at every level, and the latest fact table already has it.
    """
    from pipeline.fwd.facts import fact_path

    latest = con.execute("SELECT max(period_start) FROM facts WHERE measure = 'headcount' AND dim IS NULL AND period_type = 'month'").fetchone()[0]
    fact = fact_path("employment", latest[:4] + latest[5:7])
    if not fact.exists():
        log.warning("no fact table for %s; sub-element composition will be unavailable", latest)
        return 0
    dims = {"grade": "grade", "age_bracket": "age_bracket", "supervisory": "supervisory_code", "appointment_type": "appointment_type_code",
            "pay_band": "pay_band", "work_schedule": "work_schedule_code", "series": "series_code", "step": "step_code"}
    before = con.execute("SELECT count(*) FROM facts").fetchone()[0]
    for dim, col in dims.items():
        con.execute(f"""
        INSERT INTO facts
        SELECT 'headcount', org_code, 'month', '{latest}', '{dim}',
               CASE WHEN {col} IS NULL OR {col} = '' THEN '_blank' ELSE {col} END AS dim_value,
               sum(n), NULL, NULL, 'fact:{fact.stem}'
        FROM read_parquet('{fact}')
        WHERE org_code IN (SELECT code FROM nodes WHERE kind = 'subelement')
        GROUP BY org_code, dim_value
        """)
    added = con.execute("SELECT count(*) FROM facts").fetchone()[0] - before
    log.info("sub-element composition: %d dimensioned rows for %s", added, latest)
    return added


def _plum_or_none(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """PLUM is optional: a clone without a snapshot still builds every other measure."""
    from pipeline.plum.load import POSITIONS

    if not POSITIONS.exists():
        log.warning("no PLUM positions table; leadership measures will be absent")
        return []
    return plum_facts(con)


def _insert(con: duckdb.DuckDBPyConnection, facts: list[tuple]) -> None:
    if facts:
        con.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?)", facts)


def _write_slices(con: duckdb.DuckDBPyConnection, catalog: Catalog, nodes: dict) -> None:
    """Per-node slices for instant paint.

    Series are stored positionally against a shared period axis (periods.json) rather than keyed by date:
    a date key costs more than the value it labels. Each series is {t: period_type, i: index of first
    period, v: values, n?: counts, z?: {index: notation}}.

    Three shapes per node:
      measures   flat series for every shown measure, full history
      dims       dimension series for the trend breakdown: DIM_TREND dims, last DIM_MONTHS months
      dims_now   every dimension at the latest period, for Composition (also emitted for sub-elements)
    """
    SLICE_DIR.mkdir(parents=True, exist_ok=True)
    for stale in SLICE_DIR.glob("*.json"):
        stale.unlink()
    write_public_catalog(catalog, SLICE_DIR / "catalog.json")
    (SLICE_DIR / "nodes.json").write_text(json.dumps({"nodes": nodes}, separators=(",", ":"), ensure_ascii=False))

    axis = {pt: [r[0] for r in con.execute(f"SELECT DISTINCT period_start FROM facts WHERE period_type = '{pt}' ORDER BY 1").fetchall()]
            for pt in ("month", "quarter", "fiscal_year", "survey_year")}
    index = {pt: {p: i for i, p in enumerate(ps)} for pt, ps in axis.items()}
    (SLICE_DIR / "periods.json").write_text(json.dumps(axis, separators=(",", ":")))

    def pack(points: list[tuple]) -> dict:
        """points = [(period_type, period_start, value, n, notation)] for one series."""
        pt = points[0][0]
        idx = sorted((index[pt][p], v, n, z) for _, p, v, n, z in points if p in index[pt])
        if not idx:
            return {}
        i0, i1 = idx[0][0], idx[-1][0]
        span = i1 - i0 + 1
        v: list = [None] * span
        n_arr: list = [None] * span
        z: dict = {}
        for i, val, n, note in idx:
            v[i - i0] = round(val, 2 if abs(val) >= 100 else 4)
            n_arr[i - i0] = n
            if note:
                z[str(i - i0)] = note
        out = {"t": pt, "i": i0, "v": v}
        if any(x is not None for x in n_arr):
            out["n"] = n_arr
        if z:
            out["z"] = z
        return out

    shown = [c for c, m in catalog.measures.items() if m.get("display", True)]
    con.execute("CREATE OR REPLACE TABLE shown_measures AS SELECT unnest(?) AS measure", [shown])
    rows = con.execute("""
        SELECT f.node, f.measure, f.period_type, f.period_start, f.value, f.n, f.notation
        FROM facts f JOIN nodes k ON k.code = f.node JOIN shown_measures s ON s.measure = f.measure
        WHERE f.dim IS NULL AND k.kind IN ('gov', 'department', 'agency', 'group') AND f.value IS NOT NULL
        ORDER BY f.node, f.measure, f.period_start
    """).fetchall()
    raw: dict[str, dict[str, list]] = {}
    for node, measure, pt, ps, value, n, notation in rows:
        raw.setdefault(node, {}).setdefault(measure, []).append((pt, ps, value, n, notation))
    per_node = {node: {m: pack(pts) for m, pts in ms.items()} for node, ms in raw.items()}

    # "Latest" is the newest month the workforce snapshot covers, not the newest month any source touches.
    # PLUM publishes continuously and lands a month or two ahead of OPM; anchoring on headcount keeps the
    # site's as-of date, its vitals, and its composition on the month that actually has a workforce behind it.
    months = axis["month"]
    latest = con.execute("SELECT max(period_start) FROM facts WHERE measure = 'headcount' AND dim IS NULL AND period_type = 'month'").fetchone()[0] or (months[-1] if months else None)
    cutoff = months[max(0, len(months) - DIM_MONTHS)] if months else None
    dim_rows = con.execute(f"""
        SELECT node, measure, dim, dim_value, period_start, value FROM facts
        WHERE dim IS NOT NULL AND value IS NOT NULL AND measure IN (SELECT measure FROM shown_measures)
          AND (period_start >= '{cutoff}' OR period_start = '{latest}')
        ORDER BY node, measure, dim, period_start
    """).fetchall()
    trend_dims: dict[str, dict] = {}
    now_dims: dict[str, dict] = {}
    for node, measure, dim, dv, ps, value in dim_rows:
        if dim in DIM_TREND and ps >= cutoff:
            trend_dims.setdefault(node, {}).setdefault(measure, {}).setdefault(dim, {}).setdefault(dv, {})[ps] = round(value, 2)
        if ps == latest:
            now_dims.setdefault(node, {}).setdefault(measure, {}).setdefault(dim, {})[dv] = round(value, 2)

    def top_only(values: dict) -> dict:
        last = max((p for series in values.values() for p in series), default=None)
        ranked = sorted(values.items(), key=lambda kv: -(kv[1].get(last) or 0))
        keep, rest = ranked[:TOP_DIM], ranked[TOP_DIM:]
        merged: dict[str, float] = {}
        for _, series in rest:
            for p, val in series.items():
                merged[p] = merged.get(p, 0) + val
        packed = {k: pack([("month", p, val, None, None) for p, val in series.items()]) for k, series in keep}
        if merged:
            packed["_other"] = pack([("month", p, val, None, None) for p, val in merged.items()])
        return packed

    for node, ms in trend_dims.items():
        for measure, dims in ms.items():
            for dim, values in dims.items():
                dims[dim] = top_only(values)
    for node, ms in now_dims.items():
        for measure, dims in ms.items():
            for dim, values in dims.items():
                ranked = sorted(values.items(), key=lambda kv: -kv[1])
                keep, rest = ranked[:TOP_DIM_NOW], ranked[TOP_DIM_NOW:]
                dims[dim] = dict(keep) | ({"_other": round(sum(v for _, v in rest), 2)} if rest else {})

    written = 0
    for node in set(per_node) | set(trend_dims) | set(now_dims):
        payload: dict = {"node": node}
        if per_node.get(node):
            payload["measures"] = per_node[node]
        if trend_dims.get(node):
            payload["dims"] = trend_dims[node]
        if now_dims.get(node):
            payload["dims_now"] = now_dims[node]
        fname = f"group-{node}.json" if nodes.get(node, {}).get("kind") == "group" else f"{node}.json"
        (SLICE_DIR / fname).write_text(json.dumps(payload, separators=(",", ":")))
        written += 1

    current = con.execute("""
        SELECT node, measure, period_type, period_start, value, n, notation FROM (
          SELECT *, row_number() OVER (PARTITION BY node, measure ORDER BY period_start DESC) AS rn
          FROM facts WHERE dim IS NULL AND value IS NOT NULL AND measure IN (SELECT measure FROM shown_measures)
        ) WHERE rn = 1
    """).fetchall()
    snap: dict[str, dict] = {}
    for node, measure, pt, ps, value, n, notation in current:
        snap.setdefault(node, {})[measure] = {"p": ps, "t": pt, "v": round(value, 4), **({"n": n} if n is not None else {}), **({"note": notation} if notation else {})}
    (SLICE_DIR / "current.json").write_text(json.dumps(snap, separators=(",", ":")))
    _write_movers(con, catalog, nodes, snap)
    total = sum(p.stat().st_size for p in SLICE_DIR.glob("*.json"))
    log.info("measure slices: %d node files, %.1f MB", written, total / 1e6)


def _write_movers(con: duckdb.DuckDBPyConnection, catalog: Catalog, nodes: dict, snap: dict) -> None:
    """movers.json: for each monthly measure and window, the agencies that rose and fell most.

    Compared across agencies only, and only where both endpoints exist and the unit had at least
    MIN_HEADCOUNT people at the start, so a 30-person office does not dominate a percentage ranking.
    """
    MIN_HEADCOUNT = 250
    monthly = [c for c, m in catalog.measures.items() if m.get("display", True) and m["cadence"] == "month"]
    # Anchored on headcount for the same reason the slices are: PLUM runs ahead of the workforce snapshot.
    latest = con.execute("SELECT max(period_start) FROM facts WHERE measure = 'headcount' AND period_type = 'month' AND dim IS NULL").fetchone()[0]
    out: dict[str, dict] = {"latest": latest, "windows": {}}
    for label, months in MOVER_WINDOWS.items():
        start = con.execute(
            "SELECT min(period_start) FROM facts WHERE period_type = 'month' AND dim IS NULL" if months is None
            else f"SELECT min(period_start) FROM facts WHERE period_type = 'month' AND dim IS NULL AND period_start >= strftime(CAST('{latest}' AS DATE) - INTERVAL {months} MONTH, '%Y-%m-%d')"
        ).fetchone()[0]
        if not start or start >= latest:
            continue
        rows = con.execute(f"""
        WITH agencies AS (SELECT code FROM nodes WHERE kind = 'agency'),
        size AS (SELECT node, value AS hc FROM facts WHERE measure = 'headcount' AND dim IS NULL AND period_start = '{start}'),
        a AS (SELECT measure, node, value AS v0 FROM facts WHERE period_type = 'month' AND dim IS NULL AND period_start = '{start}' AND value IS NOT NULL),
        b AS (SELECT measure, node, value AS v1 FROM facts WHERE period_type = 'month' AND dim IS NULL AND period_start = '{latest}' AND value IS NOT NULL)
        SELECT a.measure, a.node, a.v0, b.v1, b.v1 - a.v0 AS delta,
               CASE WHEN a.v0 = 0 THEN NULL ELSE 100.0 * (b.v1 - a.v0) / abs(a.v0) END AS pct
        FROM a JOIN b ON a.measure = b.measure AND a.node = b.node
        JOIN agencies g ON g.code = a.node
        JOIN size s ON s.node = a.node AND s.hc >= {MIN_HEADCOUNT}
        WHERE a.measure IN (SELECT unnest(?))
        """, [monthly]).fetchall()
        by_measure: dict[str, list] = {}
        for measure, node, v0, v1, delta, pct in rows:
            by_measure.setdefault(measure, []).append({"node": node, "v0": round(v0, 3), "v1": round(v1, 3), "d": round(delta, 3), "p": None if pct is None else round(pct, 1)})
        window = {}
        for measure, items in by_measure.items():
            items.sort(key=lambda r: r["d"])
            if len(items) < 4:
                continue
            window[measure] = {"down": items[:MOVER_ROWS], "up": list(reversed(items[-MOVER_ROWS:]))}
        out["windows"][label] = {"start": start, "measures": window}
    (SLICE_DIR / "movers.json").write_text(json.dumps(out, separators=(",", ":")))
    log.info("movers: %d windows", len(out["windows"]))

    # table.json: latest value plus 12- and 60-month change for every agency and measure, so the landing
    # table can rank on any measure without reading 132 node slices.
    starts = {}
    for label, months in (("12", 12), ("60", 60)):
        starts[label] = con.execute(
            f"SELECT min(period_start) FROM facts WHERE period_type = 'month' AND dim IS NULL AND period_start >= strftime(CAST('{latest}' AS DATE) - INTERVAL {months} MONTH, '%Y-%m-%d')"
        ).fetchone()[0]
    rows = con.execute("""
        SELECT f.node, f.measure, f.period_type, f.period_start, f.value FROM facts f
        JOIN nodes k ON k.code = f.node JOIN shown_measures s ON s.measure = f.measure
        WHERE f.dim IS NULL AND f.value IS NOT NULL AND k.kind IN ('gov', 'agency', 'group')
          AND (f.period_start = ? OR f.period_start = ? OR f.period_type <> 'month')
    """, [starts["12"], starts["60"]]).fetchall()
    past: dict[tuple, dict] = {}
    for node, measure, pt, ps, value in rows:
        if pt == "month":
            past.setdefault((node, measure), {})[ps] = value
    table: dict[str, dict] = {}
    for node, ms in snap.items():
        if nodes.get(node, {}).get("kind") not in ("gov", "agency", "group"):
            continue
        entry = {}
        for measure, v in ms.items():
            cell = {"v": v["v"], "p": v["p"], "t": v["t"]}
            if v.get("note"):
                cell["note"] = v["note"]
            hist = past.get((node, measure), {})
            for label in ("12", "60"):
                base = hist.get(starts[label])
                if base is not None and v["t"] == "month":
                    cell["d" + label] = round(v["v"] - base, 3)
                    if base:
                        cell["p" + label] = round(100.0 * (v["v"] - base) / abs(base), 2)
            entry[measure] = cell
        table[node] = entry
    (SLICE_DIR / "table.json").write_text(json.dumps({"latest": latest, "starts": starts, "nodes": table}, separators=(",", ":")))
    log.info("table: %d nodes", len(table))


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
    n_raw, n_files = _load_extracts(con)
    _add_historical_nodes(con, nodes)
    _register_nodes(con, nodes)
    _base_facts(con, catalog)
    _insert(con, money_facts(fetch=fetch_money))
    _insert(con, omb_facts())
    _insert(con, fevs_facts())
    _insert(con, _plum_or_none(con))
    _latest_subelement_dims(con)
    unknown = con.execute("SELECT DISTINCT measure FROM facts WHERE measure NOT IN (SELECT unnest(?))", [list(catalog.measures)]).fetchall()
    if unknown:
        raise RuntimeError(f"facts reference measures not in the catalog: {[u[0] for u in unknown]}")
    Evaluator(con, catalog).evaluate_all()
    con.execute(f"COPY (SELECT * FROM facts ORDER BY node, measure, period_type, period_start, dim, dim_value) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    stats = con.execute("SELECT count(*), count(DISTINCT node), count(DISTINCT measure), min(period_start), max(period_start) FROM facts").fetchone()
    _write_slices(con, catalog, nodes)
    manifest = mf.load()
    manifest.setdefault("measures", {}).update({
        "rows": stats[0], "nodes": stats[1], "measures": stats[2], "first_period": stats[3], "last_period": stats[4],
        "parquet_bytes": OUT.stat().st_size, "extracts": n_raw, "extract_files": n_files,
    })
    mf.save(manifest)
    log.info("measures.parquet: %s rows, %s nodes, %s measures, %s to %s, %.1f MB", *stats, OUT.stat().st_size / 1e6)
    return manifest["measures"]
