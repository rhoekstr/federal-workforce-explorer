"""PLUM outputs: leadership measures, the per-node leadership roster, and the executive directory.

Measures are dated to the month of the snapshot, so a later pull adds a point rather than restating one.
Only current positions (Filled, Vacant) count toward measures; Historical rows are past incumbencies and
belong to the person timeline, not to a headcount of today's leadership.
"""
from __future__ import annotations

import json
import logging

import duckdb

from pipeline.config import SLICES
from pipeline.measures.periods import month_start
from pipeline.plum.crosswalk import load_crosswalk
from pipeline.plum.load import APPOINTMENT_TYPES, POSITIONS, latest_snapshot

log = logging.getLogger(__name__)
PLUM_SLICES = SLICES / "plum"
POLITICAL = ("PAS", "PA", "SC", "NA", "TA")


def _register_crosswalk(con: duckdb.DuckDBPyConnection) -> None:
    rows = [(m["agency_name"], m["org_name"], m["node"], m["agency"]) for m in load_crosswalk().values()]
    con.execute("CREATE OR REPLACE TABLE plum_map (agency_name VARCHAR, org_name VARCHAR, node VARCHAR, agency VARCHAR)")
    con.executemany("INSERT INTO plum_map VALUES (?,?,?,?)", rows)


def plum_facts(con: duckdb.DuckDBPyConnection | None = None) -> list[tuple]:
    """Leadership measures per node per snapshot month, for the measures table."""
    con = con or duckdb.connect()
    con.execute(f"CREATE OR REPLACE VIEW plum AS SELECT * FROM read_parquet('{POSITIONS}')")
    _register_crosswalk(con)
    political = ", ".join(f"'{c}'" for c in POLITICAL)
    rows = con.execute(f"""
        SELECT m.agency AS node, p.last_snapshot AS snapshot,
               count(*) AS positions,
               sum(CASE WHEN p.status = 'Filled' THEN 1 ELSE 0 END) AS filled,
               sum(CASE WHEN p.status = 'Vacant' THEN 1 ELSE 0 END) AS vacant,
               sum(CASE WHEN p.status = 'Filled' AND p.appointment_type IN ({political}) THEN 1 ELSE 0 END) AS political,
               sum(CASE WHEN p.status = 'Filled' AND p.appointment_type NOT IN ({political}) THEN 1 ELSE 0 END) AS career
        FROM plum p JOIN plum_map m ON m.agency_name = p.agency_name AND m.org_name = p.org_name
        WHERE p.status <> 'Historical'
        GROUP BY 1, 2
    """).fetchall()
    facts: list[tuple] = []
    for node, snapshot, positions, filled, vacant, political_n, career_n in rows:
        period = month_start(snapshot.replace("-", "")[:6])
        ref = f"plum:{snapshot}"
        for measure, value in (
            ("plum_positions", positions), ("plum_filled", filled), ("plum_vacant", vacant),
            ("plum_political", political_n), ("plum_career", career_n),
        ):
            facts.append((measure, node, "month", period, None, None, float(value), None, None, ref))
    log.info("plum: %d facts", len(facts))
    return facts


def build_slices(con: duckdb.DuckDBPyConnection | None = None) -> dict:
    """Per-node leadership rosters, the searchable directory, and person timelines."""
    con = con or duckdb.connect()
    con.execute(f"CREATE OR REPLACE VIEW plum AS SELECT * FROM read_parquet('{POSITIONS}')")
    _register_crosswalk(con)
    snapshot = latest_snapshot(con)
    PLUM_SLICES.mkdir(parents=True, exist_ok=True)
    for stale in PLUM_SLICES.glob("*.json"):
        stale.unlink()

    # Rank so a roster reads top-down: the secretary before the deputies before the rest.
    rank_sql = """
    CASE
      WHEN upper(title) LIKE 'SECRETARY%' OR upper(title) LIKE 'ATTORNEY GENERAL%' OR upper(title) LIKE 'ADMINISTRATOR' OR upper(title) LIKE 'DIRECTOR' AND appointment_type = 'PAS' THEN 0
      WHEN upper(title) LIKE 'DEPUTY SECRETARY%' OR upper(title) LIKE 'DEPUTY ATTORNEY GENERAL%' OR upper(title) LIKE 'DEPUTY ADMINISTRATOR%' THEN 1
      WHEN upper(title) LIKE 'UNDER SECRETARY%' OR upper(title) LIKE 'ASSOCIATE ATTORNEY GENERAL%' THEN 2
      WHEN upper(title) LIKE 'ASSISTANT SECRETARY%' OR upper(title) LIKE 'GENERAL COUNSEL%' OR upper(title) LIKE 'INSPECTOR GENERAL%' OR upper(title) LIKE 'CHIEF%' THEN 3
      WHEN appointment_type = 'PAS' THEN 4
      WHEN appointment_type IN ('PA', 'NA') THEN 5
      ELSE 6
    END"""
    rows = con.execute(f"""
        SELECT m.node, p.title, p.status, p.appointment_type, p.appointment_label, p.appointment_class,
               p.first_name, p.last_name, p.individual_id, p.begin_date, p.level_grade_pay, p.org_name,
               {rank_sql} AS rank
        FROM plum p JOIN plum_map m ON m.agency_name = p.agency_name AND m.org_name = p.org_name
        WHERE p.status <> 'Historical'
        ORDER BY m.node, rank, p.last_name
    """).fetchall()
    rosters: dict[str, list[dict]] = {}
    for node, title, status, appt, appt_label, appt_class, first, last, pid, begin, level, org, rank in rows:
        entry = {"title": title, "status": status, "appt": appt, "appt_label": appt_label, "class": appt_class, "org": org}
        if first or last:
            entry["name"] = " ".join(x for x in (first, last) if x)
        if pid:
            entry["id"] = pid
        if begin:
            entry["since"] = begin
        if level:
            entry["level"] = level
        rosters.setdefault(node, []).append(entry)
    for node, roster in rosters.items():
        (PLUM_SLICES / f"node-{node}.json").write_text(json.dumps({"node": node, "snapshot": snapshot, "positions": roster}, separators=(",", ":"), ensure_ascii=False))

    # Directory: one row per current position with a person, small enough to search in the browser.
    directory = con.execute(f"""
        SELECT p.first_name, p.last_name, p.individual_id, p.title, p.agency_name, p.org_name,
               p.appointment_type, p.appointment_label, p.appointment_class, p.pay_plan, p.level_grade_pay,
               p.duty_location, p.begin_date, m.node
        FROM plum p LEFT JOIN plum_map m ON m.agency_name = p.agency_name AND m.org_name = p.org_name
        WHERE p.status = 'Filled' AND (p.first_name IS NOT NULL OR p.last_name IS NOT NULL)
        ORDER BY p.last_name, p.first_name
    """).fetchall()
    # Appointment label and class are derivable from the code, so ship the code and the key, not both per row.
    people = [
        {"n": " ".join(x for x in (r[0], r[1]) if x), "id": r[2], "t": r[3], "a": r[4], "o": r[5],
         "at": r[6], "pp": r[9], "lv": r[10], "loc": r[11], "since": r[12], "node": r[13]}
        for r in directory
    ]
    appointments = {code: {"label": label, "class": kind} for code, (label, kind) in APPOINTMENT_TYPES.items()}
    (PLUM_SLICES / "directory.json").write_text(json.dumps({"snapshot": snapshot, "appointments": appointments, "people": people}, separators=(",", ":"), ensure_ascii=False))

    # Timelines: every position a person has held, including the historical rows.
    hist = con.execute("""
        SELECT individual_id, first_name, last_name, title, agency_name, org_name, status,
               appointment_type, appointment_label, appointment_class, begin_date, vacate_date, level_grade_pay
        FROM plum WHERE individual_id IS NOT NULL ORDER BY individual_id, coalesce(begin_date, '0000')
    """).fetchall()
    timelines: dict[str, dict] = {}
    for pid, first, last, title, agency, org, status, appt, appt_label, appt_class, begin, vacate, level in hist:
        person = timelines.setdefault(pid, {"id": pid, "name": " ".join(x for x in (first, last) if x), "positions": []})
        person["positions"].append({"t": title, "a": agency, "o": org, "s": status, "at": appt, "b": begin, "v": vacate, "lv": level})
    # A person with one position already has it in full on their directory row; only careers with more than
    # one position need a timeline file, which is the difference between a 3.4 MB download and a 1 MB one.
    multi = {pid: p for pid, p in timelines.items() if len(p["positions"]) > 1}
    (PLUM_SLICES / "timelines.json").write_text(json.dumps({"snapshot": snapshot, "people": multi}, separators=(",", ":"), ensure_ascii=False))

    stats = {
        "snapshot": snapshot, "nodes_with_roster": len(rosters), "directory": len(people),
        "people": len(timelines), "people_multi_position": len(multi),
        "bytes": sum(p.stat().st_size for p in PLUM_SLICES.glob("*.json")),
    }
    log.info("plum slices: %(nodes_with_roster)d rosters, %(directory)d in the directory, %(people)d people, %(bytes).0f bytes", stats)
    return stats
