"""Overview groups: the unit that reconciles FWD agencies, USAspending toptier agencies, OMB Table 5-1 rows,
and FEVS agency labels (PRD 5.8).

crosswalk/agency_groups.json is curated. `seed_groups()` builds a first draft by normalized-name matching plus
the hand-written OVERRIDES below, and writes anything it could not place to crosswalk/review.json.
"""
from __future__ import annotations

import json
import re

from pipeline.config import CROSSWALK, REFERENCE

GROUPS_PATH = CROSSWALK / "agency_groups.json"
REVIEW_PATH = CROSSWALK / "review.json"

ABBREV = {
    "NAT": "NATIONAL", "DEVELOPM": "DEVELOPMENT", "OFFENDR": "OFFENDER", "SUPERVSN": "SUPERVISION",
    "AGY": "AGENCY", "ADMIN": "ADMINISTRATION", "COMM": "COMMISSION", "CORP": "CORPORATION",
}
DROP_PREFIXES = ("DEPARTMENT OF THE ", "DEPARTMENT OF ", "UNITED STATES ", "US ", "THE ")


def normalize(name: str) -> str:
    s = name.upper().replace("&", " AND ").replace("--", " ").replace("-", " ")
    s = re.sub(r"\bU\.S\.\s*", "US ", s)
    s = re.sub(r"[.,'()*]", "", s)
    s = re.sub(r"\bU S\b", "US", s)
    s = " ".join(ABBREV.get(w, w) for w in s.split())
    for p in DROP_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    return s.strip()


# Cases name matching cannot get right. Keys are group ids.
OVERRIDES = {
    "dod": {
        "name": "Department of Defense (War)",
        "fwd_agency_codes": ["DD", "AR", "NV", "AF"],
        "fwd_exclude_org_codes": ["ARCE"],
        "usaspending_names": ["Department of Defense"],
        "omb_labels": ["War--Military Programs"],
        "fevs_labels": ["Department of Defense, Overall"],
        "note": "FWD splits Army, Navy, Air Force, and defense-wide; the Corps of Engineers civil works (ARCE) is carved out into its own group.",
    },
    "usace": {
        "name": "Corps of Engineers, Civil Works",
        "fwd_agency_codes": [],
        "fwd_org_codes": ["ARCE"],
        "usaspending_names": ["Corps of Engineers - Civil Works"],
        "omb_labels": ["Corps of Engineers--Civil Works"],
        "fevs_labels": [],
        "note": "Headcount is the Army sub-element ARCE.",
    },
    "usaid": {
        "name": "International Assistance Programs",
        "fwd_agency_codes": ["AM"],
        "usaspending_names": ["Agency for International Development"],
        "omb_labels": ["International Assistance Programs"],
        "fevs_labels": ["U.S. Agency for International Development"],
        "note": "OMB's line pools USAID with other foreign assistance; USAID headcount is what FWD carries.",
    },
    "treasury": {"fwd_agency_codes": ["TR"], "usaspending_names": ["Department of the Treasury"], "omb_labels": ["Treasury"], "fevs_labels": ["Department of the Treasury"]},
    "interior": {"fwd_agency_codes": ["IN"], "usaspending_names": ["Department of the Interior"], "omb_labels": ["Interior"], "fevs_labels": ["Department of the Interior"]},
    "opm": {"fwd_agency_codes": ["OM"], "usaspending_names": ["Office of Personnel Management"], "omb_labels": ["Office of Personnel Management **"], "fevs_labels": ["Office of Personnel Management"]},
    "cfpb": {"fwd_agency_codes": [], "usaspending_names": ["Consumer Financial Protection Bureau"], "omb_labels": ["Bureau of Consumer Financial Protection"], "fevs_labels": []},
    "dfc": {"fwd_agency_codes": ["GB"], "usaspending_names": ["U.S. International Development Finance Corporation"], "omb_labels": [], "fevs_labels": ["U.S. International Development Finance Corporation"]},
    "csosa": {"fwd_agency_codes": ["FQ"], "usaspending_names": ["Court Services and Offender Supervision Agency"], "omb_labels": [], "fevs_labels": ["Court Services and Offender Supervision Agency"]},
    "usagm": {"fwd_agency_codes": ["IB"], "usaspending_names": ["U.S. Agency for Global Media"], "omb_labels": ["U.S. Agency for Global Media"], "fevs_labels": ["U.S. Agency for Global Media"]},
    "eop": {
        "name": "Executive Office of the President",
        "fwd_agency_codes": ["BO", "EC", "QQ", "NS", "TS", "CE", "EQ", "DO", "TN", "ZS"],
        "usaspending_names": ["Executive Office of the President"],
        "omb_labels": [],
        "fevs_labels": ["Office of Management and Budget", "Office of the U.S. Trade Representative"],
        "note": "FWD lists EOP components as separate agencies; USAspending reports them as one.",
    },
    "nea_neh": {"name": "National Endowments for the Arts and Humanities", "fwd_agency_codes": ["AH"], "usaspending_names": ["National Endowment for the Arts", "National Endowment for the Humanities"], "omb_labels": [], "fevs_labels": ["National Endowment for the Arts", "National Endowment for the Humanities"]},
    "fmcs": {"fwd_agency_codes": ["FM"], "usaspending_names": ["Federal Mediation and Conciliation Service"], "omb_labels": [], "fevs_labels": ["Federal Mediation and Conciliation Service"]},
    "oshrc": {"fwd_agency_codes": ["OS"], "usaspending_names": ["Occupational Safety and Health Review Commission"], "omb_labels": [], "fevs_labels": ["Occupational Safety and Health Review Commission"]},
    "csb": {"fwd_agency_codes": ["FJ"], "usaspending_names": ["United States Chemical Safety Board"], "omb_labels": [], "fevs_labels": ["U.S. Chemical Safety and Hazard Investigation Board"]},
    "achp": {"fwd_agency_codes": ["HP"], "usaspending_names": ["Advisory Council on Historic Preservation"], "omb_labels": [], "fevs_labels": ["Advisory Council on Historic Preservation"]},
    "abilityone": {"fwd_agency_codes": ["HB"], "usaspending_names": ["Committee for Purchase from People Who Are Blind or Severely Disabled"], "omb_labels": [], "fevs_labels": ["AbilityOne Commission"]},
    "udall": {"fwd_agency_codes": ["EO"], "usaspending_names": ["Morris K. Udall and Stewart L. Udall Foundation"], "omb_labels": [], "fevs_labels": []},
    "pclob": {"fwd_agency_codes": ["VD"], "usaspending_names": ["Privacy and Civil Liberties Oversight Board"], "omb_labels": [], "fevs_labels": ["Privacy and Civil Liberties Oversight Board"]},
    "fmshrc": {"fwd_agency_codes": ["RS"], "usaspending_names": ["Federal Mine Safety and Health Review Commission"], "omb_labels": [], "fevs_labels": []},
    "cigie": {"fwd_agency_codes": ["IG"], "usaspending_names": ["Council of the Inspectors General on Integrity and Efficiency"], "omb_labels": [], "fevs_labels": []},
    "fpisc": {"fwd_agency_codes": ["WK"], "usaspending_names": ["Federal Permitting Improvement Steering Council"], "omb_labels": [], "fevs_labels": ["Federal Permitting Improvement Steering Council"]},
    "heritage_abroad": {"fwd_agency_codes": ["BH"], "usaspending_names": ["Commission for the Preservation of America's Heritage Abroad"], "omb_labels": [], "fevs_labels": []},
    "ffiec": {"fwd_agency_codes": ["FI"], "usaspending_names": ["Federal Financial Institutions Examination Council"], "omb_labels": [], "fevs_labels": []},
    "acus": {"fwd_agency_codes": ["AA"], "usaspending_names": ["Administrative Conference of the U.S."], "omb_labels": [], "fevs_labels": []},
    "jusfc": {"fwd_agency_codes": ["UJ"], "usaspending_names": ["Japan-United States Friendship Commission"], "omb_labels": [], "fevs_labels": []},
    "access_board": {"fwd_agency_codes": ["BT"], "usaspending_names": ["Access Board"], "omb_labels": [], "fevs_labels": ["U.S. Access Board"]},
    "truman": {"fwd_agency_codes": ["HT"], "usaspending_names": ["Harry S Truman Scholarship Foundation"], "omb_labels": [], "fevs_labels": []},
    "madison": {"fwd_agency_codes": ["BK"], "usaspending_names": ["James Madison Memorial Fellowship Foundation"], "omb_labels": [], "fevs_labels": []},
    "goldwater": {"fwd_agency_codes": ["GE"], "usaspending_names": ["Barry Goldwater Scholarship and Excellence In Education Foundation"], "omb_labels": [], "fevs_labels": []},
    "frtib": {"name": "Federal Retirement Thrift Investment Board", "fwd_agency_codes": ["RF"], "usaspending_names": [], "omb_labels": [], "fevs_labels": ["Federal Retirement Thrift Investment Board"]},
    "ibwc": {"name": "International Boundary and Water Commission", "fwd_agency_codes": ["GW"], "usaspending_names": [], "omb_labels": [], "fevs_labels": ["International Boundary and Water Commission"]},
    "smithsonian": {"fwd_agency_codes": ["SM"], "usaspending_names": [], "omb_labels": ["Smithsonian Institution"], "fevs_labels": [], "note": "Trust instrumentality; not in USAspending account data."},
}


def _fwd_agencies() -> list[dict]:
    return json.loads((REFERENCE / "fwd_agencies_202607.json").read_text())


def _usaspending() -> list[dict]:
    return json.loads((REFERENCE / "usaspending_toptier_agencies.json").read_text())


def _omb_labels() -> list[str]:
    from pipeline.money.omb import load_table_5_1

    return sorted({r["label"] for r in load_table_5_1()})


def _fevs_labels() -> list[str]:
    from pipeline.money.fevs import agency_labels

    try:
        return agency_labels()
    except FileNotFoundError:
        return []


def seed_groups() -> tuple[dict, dict]:
    """Build crosswalk/agency_groups.json and crosswalk/review.json. Returns (groups, review)."""
    fwd = _fwd_agencies()
    usa = _usaspending()
    omb = _omb_labels()
    fevs = _fevs_labels()
    groups: dict[str, dict] = {}
    used = {"fwd": set(), "usa": set(), "omb": set(), "fevs": set()}

    for gid, spec in OVERRIDES.items():
        g = {
            "name": spec.get("name") or (spec.get("usaspending_names") or [None])[0] or next((r["agency"].title() for r in fwd if r["agency_code"] in spec["fwd_agency_codes"]), gid),
            "fwd_agency_codes": spec.get("fwd_agency_codes", []),
            "fwd_org_codes": spec.get("fwd_org_codes", []),
            "fwd_exclude_org_codes": spec.get("fwd_exclude_org_codes", []),
            "usaspending_names": spec.get("usaspending_names", []),
            "omb_labels": spec.get("omb_labels", []),
            "fevs_labels": spec.get("fevs_labels", []),
            "method": "manual",
        }
        if "note" in spec:
            g["note"] = spec["note"]
        groups[gid] = g
        used["fwd"].update(g["fwd_agency_codes"])
        used["usa"].update(g["usaspending_names"])
        used["omb"].update(g["omb_labels"])
        used["fevs"].update(g["fevs_labels"])

    usa_by_norm = {normalize(r["agency_name"]): r for r in usa}
    omb_by_norm = {normalize(l): l for l in omb}
    fevs_by_norm = {normalize(l): l for l in fevs}

    for r in sorted(fwd, key=lambda r: -r["headcount_202607"]):
        code = r["agency_code"]
        if code in used["fwd"]:
            continue
        key = normalize(r["agency"])
        u = usa_by_norm.get(key)
        gid = (u["abbreviation"].lower().replace(" ", "_") if u else code.lower())
        if gid in groups:
            gid = f"{gid}_{code.lower()}"
        g = {
            "name": (u["agency_name"] if u else r["agency"].title()),
            "fwd_agency_codes": [code],
            "fwd_org_codes": [],
            "fwd_exclude_org_codes": [],
            "usaspending_names": [u["agency_name"]] if u else [],
            "omb_labels": [omb_by_norm[key]] if key in omb_by_norm else [],
            "fevs_labels": [fevs_by_norm[key]] if key in fevs_by_norm else [],
            "method": "normalized" if u else "fwd_only",
        }
        groups[gid] = g
        used["fwd"].add(code)
        used["usa"].update(g["usaspending_names"])
        used["omb"].update(g["omb_labels"])
        used["fevs"].update(g["fevs_labels"])

    no_money = json.loads((CROSSWALK / "no_money.json").read_text())["agencies"] if (CROSSWALK / "no_money.json").exists() else {}
    review = {
        "_about": (
            "Seeding leftovers, not a defect list. Agencies under fwd_agencies_unmapped_to_usaspending that appear "
            "in no_money.json are funded outside annual appropriations or sit outside the executive branch, and the "
            "unit page explains each one. FEVS labels are informational: survey measures attach by FWD agency code "
            "directly, not through these groups, so an unmatched label here does not mean missing survey data."
        ),
        "fwd_agencies_unmapped_to_usaspending_explained": sorted(no_money),
        "fwd_agencies_unmapped_to_usaspending": [
            {"code": r["agency_code"], "name": r["agency"], "headcount": r["headcount_202607"]}
            for r in fwd if not any(r["agency_code"] in g["fwd_agency_codes"] and g["usaspending_names"] for g in groups.values())
        ],
        "usaspending_agencies_without_group": sorted(r["agency_name"] for r in usa if r["agency_name"] not in used["usa"]),
        "omb_labels_without_group": sorted(l for l in omb if l not in used["omb"] and not l.startswith(("Total", "Other War"))),
        "fevs_labels_without_group": sorted(l for l in fevs if l not in used["fevs"]),
    }
    CROSSWALK.mkdir(exist_ok=True)
    GROUPS_PATH.write_text(json.dumps(groups, indent=1, ensure_ascii=False))
    REVIEW_PATH.write_text(json.dumps(review, indent=1, ensure_ascii=False))
    return groups, review


def load_groups() -> dict:
    return json.loads(GROUPS_PATH.read_text())
