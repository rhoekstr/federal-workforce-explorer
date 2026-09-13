"""FEVS at sub-agency level, 2019 only.

2019 is the one year of public FEVS data that carries a sub-agency field (`LEVEL1`, 238 units at a
300-respondent threshold). 2020 through 2023 have no such field and the 2024 file is corrupt as published,
so this does not generalise — it is one year, deliberately.

The join is by **name**, never by code. FEVS `LEVEL1` codes coincide with OPM sub-element codes for Defense,
Treasury and Transportation and diverge elsewhere, and where they collide they can name a different unit:
`IN01` is the Bureau of Land Management in FEVS and the Office of the Secretary in the workforce files. See
docs/FEVS-EXPLORATION.md section 10.

Results are emitted only for units that map. An unmapped unit is left out rather than folded into its agency,
because the agency already carries its own directly measured value and a partial roll-up would corrupt it.
"""
from __future__ import annotations

import json
import logging
import html
import re
import zipfile
from pathlib import Path

import duckdb

from pipeline.config import CROSSWALK, RAW
from pipeline.fwd.lookups import load_lookup
from pipeline.measures.periods import survey_year_start
from pipeline.money.groups import normalize

log = logging.getLogger(__name__)
YEAR = 2019
FEVS_2019 = RAW / "fevs" / "2019" / "2019"
MAP_PATH = CROSSWALK / "fevs_level1.json"
REVIEW_PATH = CROSSWALK / "fevs_review.json"
MIN_RESPONDENTS = 300
DROP_WORDS = re.compile(r"\b(OFFICE OF THE|OFFICE OF|BUREAU OF|DIVISION OF|THE|US|U S)\b")
PARENTHETICAL = re.compile(r"\s*\([^)]*\)")

# The index item lists validated in docs/FEVS-EXPLORATION.md, by 2019 item number.
EEI_ITEMS = {
    "leaders": ["Q53", "Q54", "Q56", "Q60", "Q61"],
    "supervisors": ["Q47", "Q48", "Q49", "Q51", "Q52"],
    "intrinsic": ["Q3", "Q4", "Q6", "Q11", "Q12"],
}
LEAVE_CODES = {"B": "within", "C": "outside", "D": "other"}  # 2019 coding; 2020+ differs


def _norm(name: str) -> str:
    s = normalize(PARENTHETICAL.sub("", name or ""))
    return " ".join(DROP_WORDS.sub(" ", s).split())


def _sheet_rows(z: zipfile.ZipFile, sheet: str) -> list[dict[str, str]]:
    """Cells of one worksheet as {column letter: value}, shared strings resolved."""
    shared = [html.unescape(t) for t in re.findall(r"<t[^>]*>(.*?)</t>", z.read("xl/sharedStrings.xml").decode("utf8"), re.S)]
    xml = z.read(f"xl/worksheets/{sheet}").decode("utf8")
    rows = []
    for raw in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
        cells: dict[str, str] = {}
        for ref, attrs, body in re.findall(r'<c r="([A-Z]+)\d+"([^>]*)>(.*?)</c>', raw, re.S):
            v = re.search(r"<v>(.*?)</v>", body)
            if v:
                cells[ref] = shared[int(v.group(1))] if 't="s"' in attrs else v.group(1)
        if cells:
            rows.append(cells)
    return rows


def codebook_names() -> dict[str, str]:
    """LEVEL1 code -> unit name, from the codebook's Work Unit Information sheet.

    That sheet holds agency codes first, then LEVEL1 codes under a section header, two columns wide. The
    shared-string pool is unordered, so the cells have to be read by row and column rather than pooled.
    """
    path = next(FEVS_2019.glob("*Codebook*.xlsx"))
    z = zipfile.ZipFile(path)
    rows = _sheet_rows(z, "sheet3.xml")
    start = next((i for i, r in enumerate(rows) if set(r) == {"A"} and "LEVEL1" in r["A"]), 0)
    out: dict[str, str] = {}
    for r in rows[start:]:
        code, name = r.get("A", ""), r.get("B", "")
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{2}", code or "") and name:
            out[code] = name.strip()
    return out


def build_crosswalk(names: dict[str, str] | None = None) -> tuple[dict, dict]:
    """Seed crosswalk/fevs_level1.json by name. Entries marked manual are preserved."""
    names = names or codebook_names()
    org = load_lookup("org")
    by_agency: dict[str, list[tuple[str, str]]] = {}
    for code, o in org.items():
        by_agency.setdefault(o["agency_code"], []).append((_norm(o["name"]), code))
    existing = json.loads(MAP_PATH.read_text()) if MAP_PATH.exists() else {}
    mapping, unmatched = {}, []
    for level1, name in sorted(names.items()):
        if existing.get(level1, {}).get("method") == "manual":
            mapping[level1] = existing[level1]
            continue
        agency = level1[:2]
        if level1.endswith("ZZ"):
            unmatched.append({"level1": level1, "name": name, "why": "residual 'all other' unit, not a real org node"})
            continue
        target = _norm(name)
        node, method = None, None
        for cand_name, cand_code in by_agency.get(agency, []):
            if cand_name == target:
                node, method = cand_code, "name"
                break
        if node is None:
            hits = [c for n, c in by_agency.get(agency, []) if n and (n in target or target in n)]
            if len(hits) == 1:
                node, method = hits[0], "name_contains"
        if node is None:
            unmatched.append({"level1": level1, "name": name, "why": "no sub-element of this agency matches by name"})
            continue
        mapping[level1] = {"level1": level1, "fevs_name": name, "node": node, "node_name": org[node]["name"], "method": method}
    review = {
        "_about": (
            "FEVS 2019 sub-agency units that could not be placed on an org node by name. Codes are never used "
            "to join: FEVS LEVEL1 codes coincide with OPM sub-element codes only for Defense, Treasury and "
            "Transportation, and a colliding code can name a different unit. Set \"method\": \"manual\" on an "
            "entry in fevs_level1.json to pin it."
        ),
        "counts": {"units": len(names), "mapped": len(mapping), "unmatched": len(unmatched)},
        "unmatched": unmatched,
    }
    CROSSWALK.mkdir(exist_ok=True)
    MAP_PATH.write_text(json.dumps(mapping, indent=1, ensure_ascii=False, sort_keys=True))
    REVIEW_PATH.write_text(json.dumps(review, indent=1, ensure_ascii=False))
    log.info("fevs level1 crosswalk: %(mapped)d of %(units)d units mapped", review["counts"])
    return mapping, review


def _positive_sql(item: str) -> str:
    """Weighted percent positive: top two options over a base excluding Do Not Know (X) and blanks."""
    return (
        f"100.0 * sum(CASE WHEN {item} IN ('4','5') THEN POSTWT::DOUBLE ELSE 0 END) / "
        f"nullif(sum(CASE WHEN {item} IN ('1','2','3','4','5') THEN POSTWT::DOUBLE ELSE 0 END), 0)"
    )


def level1_facts(con: duckdb.DuckDBPyConnection | None = None) -> list[tuple]:
    csv = next(FEVS_2019.glob("*PRDF*.csv"), None)
    if csv is None:
        log.warning("2019 FEVS respondent file not present; sub-agency measures skipped")
        return []
    mapping = json.loads(MAP_PATH.read_text()) if MAP_PATH.exists() else build_crosswalk()[0]
    con = con or duckdb.connect()
    con.execute(f"CREATE OR REPLACE VIEW p AS SELECT * FROM read_csv('{csv}', header=true, all_varchar=true, ignore_errors=true)")
    items = [i for sub in EEI_ITEMS.values() for i in sub]
    selects = ", ".join(f"{_positive_sql(item)} AS {item.lower()}" for item in items)
    leave = ", ".join(
        f"100.0 * sum(CASE WHEN DLEAVING = '{code}' THEN POSTWT::DOUBLE ELSE 0 END) / "
        f"nullif(sum(CASE WHEN DLEAVING IN ('A','B','C','D') THEN POSTWT::DOUBLE ELSE 0 END), 0) AS leave_{label}"
        for code, label in LEAVE_CODES.items()
    )
    rows = con.execute(
        f"SELECT LEVEL1, count(*) AS n, {selects}, {leave} FROM p "
        f"WHERE LEVEL1 IS NOT NULL AND LEVEL1 <> '' GROUP BY LEVEL1 HAVING count(*) >= {MIN_RESPONDENTS}"
    ).fetchall()
    cols = ["level1", "n"] + [i.lower() for i in items] + [f"leave_{l}" for l in LEAVE_CODES.values()]
    facts: list[tuple] = []
    period, ref = survey_year_start(YEAR), f"fevs:{YEAR}-prdf-level1"
    for row in rows:
        r = dict(zip(cols, row))
        entry = mapping.get(r["level1"])
        if not entry:
            continue
        node, n = entry["node"], int(r["n"])
        subindices = []
        for sub, sub_items in EEI_ITEMS.items():
            vals = [r[i.lower()] for i in sub_items if r[i.lower()] is not None]
            if len(vals) < len(sub_items):
                subindices = []
                break
            subindices.append(sum(vals) / len(vals))
        if subindices:
            facts.append(("fevs_engagement", node, "survey_year", period, None, None, round(sum(subindices) / len(subindices), 1), n, None, ref))
        leave_any = sum(r[f"leave_{l}"] for l in LEAVE_CODES.values() if r[f"leave_{l}"] is not None)
        for label, measure in (("outside", "fevs_leave_outside"), ("within", "fevs_leave_within"), ("other", "fevs_leave_other")):
            v = r[f"leave_{label}"]
            if v is not None:
                facts.append((measure, node, "survey_year", period, None, None, round(v, 1), n, None, ref))
        if leave_any:
            facts.append(("fevs_leave_any", node, "survey_year", period, None, None, round(leave_any, 1), n, None, ref))
    log.info("fevs 2019 sub-agency: %d facts across %d units", len(facts), len({f[1] for f in facts}))
    return facts
