"""OSHA federal agency injury and illness rates.

The only measure on the site of physical workplace health. OSHA publishes, per federal agency per fiscal year,
the number of recordable cases and lost-time cases and the rate of each per 100 employees. Two formats: HTML
tables for FY2004 through FY2017, spreadsheets for FY2018 and FY2019. **The series stops at FY2019** — OSHA has
published nothing newer on that page — so these measures carry an `until` and the site says so.

osha.gov refuses a bare client; it needs full browser headers and a referer.

The parse is gated, per docs/OVERNIGHT-v0.5.md: each agency's published rate is recomputed from its own case
count and employment, and the parse is rejected unless nearly every row agrees. That proves the columns are
aligned, which is the thing that actually goes wrong.
"""
from __future__ import annotations

import html
import logging
import re
import zipfile
from pathlib import Path

from pipeline.config import RAW, REFERENCE
from pipeline.measures.periods import fiscal_year_start
from pipeline.money.groups import normalize

log = logging.getLogger(__name__)
OSHA_DIR = RAW / "osha"
# Parsed values are committed, like the VA and FEVS tables: osha.gov refuses bare clients and the series is
# closed at FY2019, so re-scraping sixteen pages on every CI run would be all risk and no benefit.
FACTS_CSV = REFERENCE / "osha" / "osha.csv"
INDEX = "https://www.osha.gov/enforcement/fap/statistics"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": INDEX,
}
HTML_YEARS = range(2004, 2018)
XLSX_YEARS = {
    2018: "https://www.osha.gov/sites/default/files/2019-12/Q4_FY18_Statistics.xlsx",
    2019: "https://www.osha.gov/sites/default/files/2020-01/Q4CalculationsreworkedVAWebPosting.xlsx",
}
# Rate columns are cases per 100 employees, so a row is self-consistent when cases / employees * 100 = rate.
TOLERANCE = 0.05
MIN_AGREEMENT = 0.95

# OSHA names agencies its own way. Only unambiguous matches to a Fed Pulse agency are mapped.
ALIASES = {
    "DEPARTMENT OF HOMELAND SECURITY": "HS", "DEPARTMENT OF VETERANS AFFAIRS": "VA",
    "VETERANS AFFAIRS": "VA", "DEPARTMENT OF AGRICULTURE": "AG", "DEPARTMENT OF JUSTICE": "DJ",
    "DEPARTMENT OF TRANSPORTATION": "TD", "DEPARTMENT OF INTERIOR": "IN", "DEPARTMENT OF THE INTERIOR": "IN",
    "DEPARTMENT OF TREASURY": "TR", "DEPARTMENT OF THE TREASURY": "TR", "DEPARTMENT OF LABOR": "DL",
    "DEPARTMENT OF ENERGY": "DN", "DEPARTMENT OF COMMERCE": "CM", "DEPARTMENT OF STATE": "ST",
    "DEPARTMENT OF EDUCATION": "ED", "DEPARTMENT OF HEALTH AND HUMAN SERVICES": "HE",
    "DEPARTMENT OF HOUSING AND URBAN DEVELOPMENT": "HU", "SOCIAL SECURITY ADMINISTRATION": "SZ",
    "ENVIRONMENTAL PROTECTION AGENCY": "EP", "GENERAL SERVICES ADMINISTRATION": "GS",
    "NATIONAL AERONAUTICS AND SPACE ADMINISTRATION": "NN", "OFFICE OF PERSONNEL MANAGEMENT": "OM",
    "SMALL BUSINESS ADMINISTRATION": "SB", "NUCLEAR REGULATORY COMMISSION": "NU",
    "NATIONAL SCIENCE FOUNDATION": "NF", "SMITHSONIAN INSTITUTION": "SM",
    "NATIONAL ARCHIVES AND RECORDS ADMINISTRATION": "NQ", "DEPARTMENT OF THE ARMY": "AR",
    "DEPARTMENT OF THE NAVY": "NV", "DEPARTMENT OF THE AIR FORCE": "AF", "DEPARTMENT OF ARMY": "AR",
    "DEPARTMENT OF NAVY": "NV", "DEPARTMENT OF AIR FORCE": "AF",
}
PARENTHETICAL = re.compile(r"\s*\([^)]*\)")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text))).replace("\xa0", " ").strip()


def _number(text: str) -> float | None:
    t = (text or "").replace(",", "").replace("$", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def fetch(year: int) -> Path | None:
    import requests

    OSHA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "xlsx" if year in XLSX_YEARS else "html"
    out = OSHA_DIR / f"osha_{year}.{suffix}"
    if out.exists():
        return out
    url = XLSX_YEARS.get(year) or f"{INDEX}/fy{year}-final-quarter"
    try:
        r = requests.get(url, headers=HEADERS, timeout=120)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.warning("OSHA FY%d unavailable: %s", year, exc)
        return None
    out.write_bytes(r.content)
    return out


def _rows_html(path: Path) -> list[list[str]]:
    s = path.read_text(errors="replace")
    out = []
    for raw in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S):
        cells = [_clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", raw, re.S)]
        if len(cells) >= 6 and cells[0] not in ("", " "):
            out.append(cells)
    return out


def _rows_xlsx(path: Path) -> list[list[str]]:
    z = zipfile.ZipFile(path)
    shared = [html.unescape(t) for t in re.findall(r"<t[^>]*>(.*?)</t>", z.read("xl/sharedStrings.xml").decode("utf8"), re.S)]
    sheet = next(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))
    out = []
    for raw in re.findall(r"<row[^>]*>(.*?)</row>", z.read(sheet).decode("utf8"), re.S):
        cells: dict[str, str] = {}
        for ref, attrs, body in re.findall(r'<c r="([A-Z]+)\d+"([^>]*)>(.*?)</c>', raw, re.S):
            v = re.search(r"<v>(.*?)</v>", body)
            if v:
                cells[ref] = shared[int(v.group(1))] if 't="s"' in attrs else v.group(1)
        row = [cells.get(c, "") for c in "ABCDEFG"]
        if row[0] and any(row[1:]):
            out.append(row)
    return out


def parse(path: Path) -> tuple[list[dict], dict]:
    """([{agency, employees, cases, rate, lt_cases, lt_rate}], validation). Columns are A..G in both formats."""
    rows = _rows_xlsx(path) if path.suffix == ".xlsx" else _rows_html(path)
    parsed, checked, agreed = [], 0, 0
    for cells in rows:
        name = _clean(cells[0])
        employees, cases, rate, lt_cases, lt_rate = (_number(cells[i]) if i < len(cells) else None for i in range(1, 6))
        if not name or employees is None or not employees or rate is None:
            continue
        if cases is not None:
            checked += 1
            if abs(cases / employees * 100 - rate) <= TOLERANCE:
                agreed += 1
        parsed.append({"agency": name, "employees": employees, "cases": cases, "rate": rate, "lt_cases": lt_cases, "lt_rate": lt_rate})
    validation = {"rows": len(parsed), "checked": checked, "agreed": agreed,
                  "share": round(agreed / checked, 3) if checked else 0.0}
    return parsed, validation


# normalize() strips "DEPARTMENT OF" and similar, so the alias keys must go through it too or nothing matches.
_ALIAS_INDEX = {normalize(k): v for k, v in ALIASES.items()}


FOOTNOTE = re.compile(r"\d+$")


def _node(name: str) -> str | None:
    """OSHA appends footnote digits to some names ("Department of Labor5"), and varies them by year."""
    cleaned = FOOTNOTE.sub("", PARENTHETICAL.sub("", name).strip()).strip()
    return _ALIAS_INDEX.get(normalize(cleaned))


def refresh_from_source(years: list[int] | None = None) -> dict:
    """Re-scrape and rewrite the committed CSV. Only needed if OSHA resumes publishing."""
    import csv

    facts, report = _scrape(years)
    FACTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(FACTS_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["measure", "node", "period_start", "value", "n", "source_ref"])
        for f in sorted(facts, key=lambda r: (r[3], r[0], r[1])):
            w.writerow([f[0], f[1], f[3], f[6], f[7], f[9]])
    log.info("osha: wrote %d facts to %s", len(facts), FACTS_CSV.name)
    return report


def osha_facts() -> list[tuple]:
    """Facts for the measures build, read from the committed CSV."""
    import csv

    if not FACTS_CSV.exists():
        log.warning("no committed OSHA table; run refresh_from_source() to build it")
        return []
    out: list[tuple] = []
    with open(FACTS_CSV, newline="") as fh:
        for r in csv.DictReader(fh):
            out.append((r["measure"], r["node"], "fiscal_year", r["period_start"], None, None,
                        float(r["value"]), int(r["n"]) if r["n"] else None, None, r["source_ref"]))
    log.info("osha: %d facts", len(out))
    return out


def _scrape(years: list[int] | None = None) -> tuple[list[tuple], dict]:
    years = years or sorted(set(HTML_YEARS) | set(XLSX_YEARS))
    facts: list[tuple] = []
    report: dict[str, dict] = {}
    for year in years:
        path = fetch(year)
        if path is None:
            continue
        try:
            rows, validation = parse(path)
        except Exception as exc:  # noqa: BLE001
            log.warning("OSHA FY%d parse failed: %s", year, exc)
            continue
        report[str(year)] = validation
        if validation["share"] < MIN_AGREEMENT:
            log.error("OSHA FY%d rejected: only %.0f%% of rows reproduce their own published rate",
                      year, 100 * validation["share"])
            continue
        period, ref = fiscal_year_start(year), f"osha:fy{year}"
        for r in rows:
            node = _node(r["agency"])
            if not node:
                continue
            facts.append(("osha_total_case_rate", node, "fiscal_year", period, None, None, r["rate"], int(r["employees"]), None, ref))
            if r["lt_rate"] is not None:
                facts.append(("osha_lost_time_case_rate", node, "fiscal_year", period, None, None, r["lt_rate"], int(r["employees"]), None, ref))
    log.info("osha: %d facts across %d years", len(facts), len({f[3] for f in facts}))
    return facts, report
