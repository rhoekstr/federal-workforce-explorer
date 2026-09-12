"""Map PLUM (agency, organization) pairs onto Fed Pulse org nodes.

PLUM names its organizations in its own words, and about a third of them are offices that sit below the level
OPM's workforce files report. Per the PRD, an organization that cannot be placed rolls up to its agency node
rather than inventing a node: a leadership box always attaches to a unit that has headcount behind it.

The mapping lives in crosswalk/plum_org.json and is curated. This module seeds it by name matching, keeps
every hand edit, and writes what it could not place to crosswalk/plum_review.json so drift is visible.
"""
from __future__ import annotations

import json
import logging
import re

import duckdb

from pipeline.config import CROSSWALK
from pipeline.fwd.lookups import load_lookup
from pipeline.money.groups import normalize
from pipeline.plum.load import POSITIONS

log = logging.getLogger(__name__)
MAP_PATH = CROSSWALK / "plum_org.json"
REVIEW_PATH = CROSSWALK / "plum_review.json"

# PLUM writes agency names its own way; these are the ones normalization alone does not reach.
AGENCY_ALIASES = {
    "EXECUTIVE OFFICE OF PRESIDENT": "EOP",
    "OFFICE OF MANAGEMENT AND BUDGET": "BO",
    "AGENCY FOR INTERNATIONAL DEVELOPMENT": "AM",
    "ENVIRONMENTAL PROTECTION AGENCY": "EP",
    "SOCIAL SECURITY ADMINISTRATION": "SZ",
    "GENERAL SERVICES ADMINISTRATION": "GS",
    "OFFICE OF PERSONNEL MANAGEMENT": "OM",
    "SMALL BUSINESS ADMINISTRATION": "SB",
    "NATIONAL AERONAUTICS AND SPACE ADMINISTRATION": "NN",
    "NATIONAL ARCHIVES AND RECORDS ADMINISTRATION": "NQ",
    "NUCLEAR REGULATORY COMMISSION": "NU",
    "SECURITIES AND EXCHANGE COMMISSION": "SE",
    "FEDERAL COMMUNICATIONS COMMISSION": "FC",
    "FEDERAL TRADE COMMISSION": "FT",
    "EQUAL EMPLOYMENT OPPORTUNITY COMMISSION": "EE",
    "NATIONAL LABOR RELATIONS BOARD": "NL",
    "NATIONAL SCIENCE FOUNDATION": "NF",
    "RAILROAD RETIREMENT BOARD": "RR",
    "PEACE CORPS": "PU",
    "COMMODITY FUTURES TRADING COMMISSION": "CT",
    "CONSUMER PRODUCT SAFETY COMMISSION": "SK",
    "FEDERAL DEPOSIT INSURANCE CORPORATION": "FD",
    "PENSION BENEFIT GUARANTY CORPORATION": "BG",
    "SMITHSONIAN INSTITUTION": "SM",
    "MERIT SYSTEMS PROTECTION BOARD": "BD",
    "FEDERAL LABOR RELATIONS AUTHORITY": "AU",
    "FEDERAL MARITIME COMMISSION": "MC",
    "NATIONAL TRANSPORTATION SAFETY BOARD": "TB",
    "SELECTIVE SERVICE SYSTEM": "SS",
    "OFFICE OF SPECIAL COUNSEL": "FW",
    "FEDERAL ELECTION COMMISSION": "LF",
    "NATIONAL CREDIT UNION ADMINISTRATION": "CU",
    "FEDERAL HOUSING FINANCE AGENCY": "HF",
    "EXPORT IMPORT BANK OF THE UNITED STATES": "EB",
    "MILLENNIUM CHALLENGE CORPORATION": "MI",
    "CORPORATION FOR NATIONAL AND COMMUNITY SERVICE": "KS",
    "US INTERNATIONAL TRADE COMMISSION": "TC",
    "INTERNATIONAL TRADE COMMISSION": "TC",
    "ARMED FORCES RETIREMENT HOME": "RH",
    "DEFENSE NUCLEAR FACILITIES SAFETY BOARD": "BF",
    "FARM CREDIT ADMINISTRATION": "FL",
}
# PLUM's department-level names for agencies the workforce files split (Defense) or name differently.
DEPARTMENT_HINT = {"DEFENSE": "DD", "ARMY": "AR", "NAVY": "NV", "AIR FORCE": "AF", "WAR": "DD"}
# Agencies PLUM lists that the workforce files fold into a parent, or do not cover at all.
FOLDED_INTO = {
    "FEDERAL ENERGY REGULATORY COMMISSION": "DN",
    "US PATENT AND TRADEMARK OFFICE": "CM",
    "PATENT AND TRADEMARK OFFICE": "CM",
    "BUREAU OF INDUSTRY AND SECURITY": "CM",
    "INTERNATIONAL DEVELOPMENT FINANCE CORPORATION": "GB",
    "US INTERNATIONAL DEVELOPMENT FINANCE CORPORATION": "GB",
    "NATIONAL ENDOWMENT FOR ARTS": "AH",
    "NATIONAL ENDOWMENT FOR HUMANITIES": "AH",
    "INSTITUTE OF MUSEUM AND LIBRARY SERVICES": "AH",
    "US AGENCY FOR GLOBAL MEDIA": "IB",
    "AGENCY FOR GLOBAL MEDIA": "IB",
    "COURT SERVICES AND OFFENDER SUPERVISION AGENCY": "FQ",
    "US TRADE AND DEVELOPMENT AGENCY": "EW",
    "TRADE AND DEVELOPMENT AGENCY": "EW",
    "INTER AMERICAN FOUNDATION": "IF",
    "US AFRICAN DEVELOPMENT FOUNDATION": "AN",
    "AFRICAN DEVELOPMENT FOUNDATION": "AN",
    "APPALACHIAN REGIONAL COMMISSION": "AP",
    "DENALI COMMISSION": "DQ",
    "DELTA REGIONAL AUTHORITY": "DA",
    "NORTHERN BORDER REGIONAL COMMISSION": "DG",
    "US COMMISSION ON CIVIL RIGHTS": "CC",
    "COMMISSION ON CIVIL RIGHTS": "CC",
    "US HOLOCAUST MEMORIAL MUSEUM": "HD",
    "HOLOCAUST MEMORIAL MUSEUM": "HD",
    "MARINE MAMMAL COMMISSION": "MA",
    "NATIONAL CAPITAL PLANNING COMMISSION": "NP",
    "NATIONAL MEDIATION BOARD": "NM",
    "NATIONAL COUNCIL ON DISABILITY": "NK",
    "OCCUPATIONAL SAFETY AND HEALTH REVIEW COMMISSION": "OS",
    "FEDERAL MINE SAFETY AND HEALTH REVIEW COMMISSION": "RS",
    "FEDERAL MEDIATION AND CONCILIATION SERVICE": "FM",
    "FEDERAL RETIREMENT THRIFT INVESTMENT BOARD": "RF",
    "ADVISORY COUNCIL ON HISTORIC PRESERVATION": "HP",
    "AMERICAN BATTLE MONUMENTS COMMISSION": "AB",
    "ADMINISTRATIVE CONFERENCE OF US": "AA",
    "PRIVACY AND CIVIL LIBERTIES OVERSIGHT BOARD": "VD",
    "ELECTION ASSISTANCE COMMISSION": "GQ",
    "OFFICE OF GOVERNMENT ETHICS": "GG",
    "US ACCESS BOARD": "BT",
    "ACCESS BOARD": "BT",
    "SURFACE TRANSPORTATION BOARD": "TW",
    "CHEMICAL SAFETY AND HAZARD INVESTIGATION BOARD": "FJ",
    "NUCLEAR WASTE TECHNICAL REVIEW BOARD": "BW",
    "PRESIDIO TRUST": "GJ",
    "GULF COAST ECOSYSTEM RESTORATION COUNCIL": "GC",
    "US INTERAGENCY COUNCIL ON HOMELESSNESS": "HW",
    "MEDICAID AND CHIP PAYMENT AND ACCESS COMMISSION": "RO",
    "CONSUMER FINANCIAL PROTECTION BUREAU": "FZ",
    "BUREAU OF CONSUMER FINANCIAL PROTECTION": "FZ",
}
# PLUM writes Executive Office of the President components as "EXECUTIVE OFFICE OF THE PRESIDENT - X".
EOP_COMPONENTS = {
    "OFFICE OF MANAGEMENT AND BUDGET": "BO",
    "WHITE HOUSE OFFICE": "EC",
    "OFFICE OF ADMINISTRATION": "EC",
    "OFFICE OF THE UNITED STATES TRADE REPRESENTATIVE": "TN",
    "OFFICE OF THE US TRADE REPRESENTATIVE": "TN",
    "OFFICE OF NATIONAL DRUG CONTROL POLICY": "QQ",
    "NATIONAL SECURITY COUNCIL": "NS",
    "OFFICE OF SCIENCE AND TECHNOLOGY POLICY": "TS",
    "COUNCIL OF ECONOMIC ADVISERS": "CE",
    "COUNCIL ON ENVIRONMENTAL QUALITY": "EQ",
    "OFFICE OF THE NATIONAL CYBER DIRECTOR": "DO",
    "OFFICE OF THE VICE PRESIDENT": "EC",
}
DROP_WORDS = re.compile(r"\b(OFFICE OF THE|OFFICE OF|BUREAU OF|DIVISION OF|ADMINISTRATION FOR|THE)\b")


PARENTHETICAL = re.compile(r"\s*\([^)]*\)")


def _norm_org(name: str) -> str:
    """Normalized for matching: parentheticals dropped, then the filler words agencies vary on."""
    s = normalize(PARENTHETICAL.sub("", name or ""))
    s = DROP_WORDS.sub(" ", s)
    return " ".join(s.split())


def _agency_index() -> dict[str, str]:
    """Normalized agency name (and alias) -> FWD agency code."""
    index: dict[str, str] = {}
    for code, a in load_lookup("agency").items():
        index.setdefault(normalize(a["name"]), code)
    for alias, code in AGENCY_ALIASES.items():
        index.setdefault(alias, code)
    return index


def _org_index() -> dict[str, list[tuple[str, str]]]:
    """Agency code -> [(normalized sub-element name, node code)]."""
    index: dict[str, list[tuple[str, str]]] = {}
    for code, o in load_lookup("org").items():
        index.setdefault(o["agency_code"], []).append((_norm_org(o["name"]), code))
    return index


def _load_existing() -> dict:
    return json.loads(MAP_PATH.read_text()) if MAP_PATH.exists() else {}


def build_crosswalk(con: duckdb.DuckDBPyConnection | None = None) -> tuple[dict, dict]:
    """Seed or refresh crosswalk/plum_org.json. Hand edits (method 'manual') are never overwritten."""
    con = con or duckdb.connect()
    pairs = con.execute(f"""
        SELECT agency_name, org_name, count(*) AS n,
               sum(CASE WHEN status = 'Filled' THEN 1 ELSE 0 END) AS filled
        FROM read_parquet('{POSITIONS}') WHERE status <> 'Historical' GROUP BY 1, 2 ORDER BY 3 DESC
    """).fetchall()
    agencies, orgs = _agency_index(), _org_index()
    existing = _load_existing()
    mapping: dict[str, dict] = {}
    unplaced_agency: dict[str, int] = {}
    rolled_up: list[dict] = []

    for agency_name, org_name, n, filled in pairs:
        key = f"{agency_name}|{org_name}"
        if existing.get(key, {}).get("method") == "manual":
            mapping[key] = existing[key]
            continue
        na = normalize(agency_name)
        agency_code = agencies.get(na)
        if agency_code is None and " - " in agency_name:
            # "EXECUTIVE OFFICE OF THE PRESIDENT - OFFICE OF MANAGEMENT AND BUDGET"
            head, _, tail = agency_name.partition(" - ")
            nt = normalize(tail)
            if "EXECUTIVE OFFICE" in normalize(head):
                agency_code = EOP_COMPONENTS.get(nt) or EOP_COMPONENTS.get(_norm_org(tail))
            agency_code = agency_code or agencies.get(nt) or FOLDED_INTO.get(nt) or FOLDED_INTO.get(_norm_org(tail))
        if agency_code is None:
            agency_code = FOLDED_INTO.get(na) or EOP_COMPONENTS.get(na) or FOLDED_INTO.get(_norm_org(agency_name))
        if agency_code is None:
            for hint, code in DEPARTMENT_HINT.items():
                if hint in na:
                    agency_code = code
                    break
        # An alias is only useful if the workforce files actually carry that agency. CFPB, the Postal Service
        # and the legislative branch appear in PLUM and never in FWD, so they stay unplaced rather than
        # hanging a leadership roster on a node that does not exist.
        if agency_code is not None and agency_code not in orgs and agency_code not in agencies.values():
            agency_code = None
        if agency_code is None:
            unplaced_agency[agency_name] = unplaced_agency.get(agency_name, 0) + n
            continue
        node, method = agency_code, "agency"
        target = _norm_org(org_name)
        for cand_name, cand_code in orgs.get(agency_code, []):
            if cand_name == target:
                node, method = cand_code, "normalized"
                break
        if method == "agency" and target:
            hits = [c for name, c in orgs.get(agency_code, []) if name and (name in target or target in name)]
            if len(hits) == 1:
                node, method = hits[0], "contains"
        mapping[key] = {"agency_name": agency_name, "org_name": org_name, "node": node, "agency": agency_code, "method": method, "positions": n, "filled": filled}
        if method == "agency":
            rolled_up.append({"agency": agency_code, "agency_name": agency_name, "org_name": org_name, "positions": n})

    review = {
        "_about": "PLUM organizations Fed Pulse could not place on an org node. Rolled-up entries are shown at their agency, which is correct for offices below the level OPM reports. Set \"method\": \"manual\" on an entry in plum_org.json to pin it and the seeder will leave it alone.",
        "agencies_unmatched": [{"agency_name": k, "positions": v} for k, v in sorted(unplaced_agency.items(), key=lambda kv: -kv[1])],
        "organizations_rolled_up_to_agency": sorted(rolled_up, key=lambda r: -r["positions"])[:120],
        "counts": {"pairs": len(pairs), "mapped": len(mapping), "to_subelement": sum(1 for m in mapping.values() if m["method"] != "agency"), "rolled_up": len(rolled_up), "agencies_unmatched": len(unplaced_agency)},
    }
    CROSSWALK.mkdir(exist_ok=True)
    MAP_PATH.write_text(json.dumps(mapping, indent=1, ensure_ascii=False, sort_keys=True))
    REVIEW_PATH.write_text(json.dumps(review, indent=1, ensure_ascii=False))
    log.info("plum crosswalk: %(mapped)d pairs mapped, %(to_subelement)d to a sub-element, %(rolled_up)d rolled up, %(agencies_unmatched)d agencies unmatched", review["counts"])
    return mapping, review


def load_crosswalk() -> dict:
    return _load_existing()
