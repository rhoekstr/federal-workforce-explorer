"""data/slices/orgtree.json: the organizational tree the site renders (PRD 5.5).

Nodes: government -> department (only when it holds more than one agency) -> agency -> sub-element.
Each node: code, name, level, parent, children, first_seen, last_seen, headcount by month, group id.
"""
from __future__ import annotations

import json
import logging

from pipeline.config import SLICES
from pipeline.fwd.lookups import load_lookup
from pipeline.money.groups import load_groups

log = logging.getLogger(__name__)
SMALL_AGENCY_MAX_SUBELEMENTS = 1


def _title(name: str) -> str:
    small = {"of", "and", "the", "for", "on", "in", "to", "at", "&"}
    words = []
    for i, w in enumerate(name.lower().split()):
        if w in ("u.s.", "us", "dc", "epa", "nasa", "fdic", "dfc", "osd"):
            words.append(w.upper())
        elif i and w in small:
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)


def build_orgtree() -> dict:
    org = load_lookup("org")
    agency = load_lookup("agency")
    department = load_lookup("department")
    groups = load_groups()
    group_of_agency = {code: gid for gid, g in groups.items() for code in g["fwd_agency_codes"]}
    group_of_org = {code: gid for gid, g in groups.items() for code in g.get("fwd_org_codes", [])}

    nodes: dict[str, dict] = {}
    root = {"code": "gov", "name": "Federal civilian workforce", "level": "government", "parent": None, "children": [], "headcount": {}}
    nodes["gov"] = root

    agencies_by_dept: dict[str, list[str]] = {}
    for code, a in agency.items():
        agencies_by_dept.setdefault(a["department_code"], []).append(code)

    for dept_code, agency_codes in agencies_by_dept.items():
        multi = len(agency_codes) > 1
        parent_for_agencies = "gov"
        if multi:
            d = department.get(dept_code, {})
            nodes[f"D:{dept_code}"] = {
                "code": f"D:{dept_code}", "name": _title(d.get("name", dept_code)), "level": "department", "parent": "gov", "children": [],
                "first_seen": d.get("first_seen"), "last_seen": d.get("last_seen"), "headcount": {},
            }
            root["children"].append(f"D:{dept_code}")
            parent_for_agencies = f"D:{dept_code}"
        for code in agency_codes:
            a = agency[code]
            nodes[code] = {
                "code": code, "name": _title(a["name"]), "level": "agency", "parent": parent_for_agencies, "children": [],
                "first_seen": a["first_seen"], "last_seen": a["last_seen"], "headcount": a.get("headcount", {}),
                "group": group_of_agency.get(code), "name_history": a.get("name_history", []),
            }
            nodes[parent_for_agencies]["children"].append(code)
            if multi:
                dn = nodes[parent_for_agencies]["headcount"]
                for m, n in a.get("headcount", {}).items():
                    dn[m] = dn.get(m, 0) + n

    for code, o in org.items():
        parent = o["agency_code"]
        if parent not in nodes:
            continue
        nodes[code] = {
            "code": code, "name": _title(o["name"]), "level": "subelement", "parent": parent, "children": [],
            "first_seen": o["first_seen"], "last_seen": o["last_seen"], "headcount": o.get("headcount", {}),
            "group": group_of_org.get(code), "name_history": o.get("name_history", []),
        }
        nodes[parent]["children"].append(code)

    # Government headcount by month = sum over agencies.
    for code in nodes:
        if nodes[code]["level"] == "agency":
            for m, n in nodes[code]["headcount"].items():
                root["headcount"][m] = root["headcount"].get(m, 0) + n

    latest = max(root["headcount"]) if root["headcount"] else None

    def latest_n(code: str) -> int:
        return nodes[code]["headcount"].get(latest, 0) if latest else 0

    for node in nodes.values():
        node["children"].sort(key=lambda c: -latest_n(c))
        node["latest"] = latest_n(node["code"])
        node["small"] = node["level"] == "agency" and len(node["children"]) <= SMALL_AGENCY_MAX_SUBELEMENTS
    tree = {"latest": latest, "root": "gov", "nodes": nodes, "groups": {gid: g["name"] for gid, g in groups.items()}}
    SLICES.mkdir(parents=True, exist_ok=True)
    (SLICES / "orgtree.json").write_text(json.dumps(tree, separators=(",", ":"), ensure_ascii=False))
    log.info("orgtree: %d nodes, latest %s", len(nodes), latest)
    return tree
