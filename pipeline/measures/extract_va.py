"""VA All Employee Survey: the FEVS-comparable items, parsed from OPM-format tables VA publishes as PDFs.

The Department of Veterans Affairs is the largest federal agency and has never appeared in a public FEVS
respondent file, so 446,000 people are missing from every survey measure on the site. VA runs its own census
survey and publishes the subset of items that also appear on FEVS, per administration, as
"AES {year} FEVS Percents" on data.va.gov.

Those files are PDFs of response distributions. Each item carries its full FEVS wording, which is what makes
them usable: items are matched to Fed Pulse measures by text, not by position or by an item number whose
meaning is not published. Percent positive follows the FEVS convention validated in docs/FEVS-EXPLORATION.md —
the top two response options over a base that excludes "Missing or Do not Know".

Precision: the PDFs round to whole percents, so these values carry about half a point of rounding error and
are notated `estimate`. That is the honest limit of the published form.
"""
from __future__ import annotations

import logging
import re
import zlib
from pathlib import Path

from pipeline.config import RAW
from pipeline.measures.periods import survey_year_start

log = logging.getLogger(__name__)
VA_DIR = RAW / "va"
# data.va.gov dataset ids, one per survey year. 2024 exists only as a tabular file keyed by unpublished item
# numbers, so it is deliberately absent: see PRD section 8.
DATASETS = {2018: "isnh-negm", 2020: "5bqz-r7ak", 2022: "4cvs-huag", 2023: "y9gb-p7uj"}
DOWNLOAD = "https://www.data.va.gov/download/{id}/application%2Fvnd.openxmlformats-officedocument.spreadsheetml.sheet"

# VA's reporting units, mapped to Fed Pulse nodes. VA's sub-element codes come from the org lookup.
ADMINISTRATIONS = {
    "All VA": "VA",
    "VHA": "VATA",   # Veterans Health Administration
    "VBA": "VALA",   # Veterans Benefits Administration
    "NCA": "VAPA",   # National Cemetery Administration
}

# Item wording -> the measure it feeds. Only items whose Fed Pulse counterpart is unambiguous are mapped;
# the rest are parsed and ignored rather than forced onto an index they do not belong to.
ITEM_MEASURES = {
    "i recommend my organization as a good place to work": "va_aes_recommend",
    "considering everything, how satisfied are you with your job": "va_aes_job_satisfaction",
    "considering everything, how satisfied are you with your pay": "va_aes_pay_satisfaction",
    "considering everything, how satisfied are you with your organization": "va_aes_org_satisfaction",
    "my workload is reasonable": "va_aes_workload_reasonable",
    "i feel encouraged to come up with new and better ways of doing things": "va_aes_encouraged",
    "my work gives me a feeling of personal accomplishment": "va_aes_accomplishment",
    "my talents are used well in the workplace": "va_aes_talents_used",
}
ROW = re.compile(r"\b(All VA|VHA|VBA|NCA|VACO)\b((?:\s+\d+%){5,7})")
# VA uses three response scales; an item's name ends where its scale begins.
SCALE_STARTS = ("Strongly Disagree", "Very Dissatisfied", "Very Poor")

# OPM's Employee Engagement Index is the mean of three subindices, each the mean of its items' percent
# positive. VA asks all fifteen, so the index is comparable to the FEVS figure validated for other agencies.
EEI_SUBINDICES = {
    "intrinsic": [
        "i feel encouraged to come up with new and better ways of doing things",
        "my work gives me a feeling of personal accomplishment",
        "i know what is expected of me on the job",
        "my talents are used well in the workplace",
        "i know how my work relates to the agency's goals",
    ],
    "supervisors": [
        "supervisors in my work unit support employee development",
        "my supervisor listens to what i have to say",
        "my supervisor treats me with respect",
        "i have trust and confidence in my supervisor",
        "overall, how good a job do you feel is being done by your immediate supervisor",
    ],
    "leaders": [
        "in my organization, senior leaders generate high levels of motivation and commitment in the workforce",
        "my organization's senior leaders maintain high standards of honesty and integrity",
        "managers communicate the goals of the organization",
        "i have a high level of respect for my organization's senior leaders",
        "how satisfied are you with the information you receive from management on what's going on in your organization",
    ],
}


def fetch(year: int) -> Path:
    import requests

    VA_DIR.mkdir(parents=True, exist_ok=True)
    out = VA_DIR / f"aes_{year}.pdf"
    if out.exists():
        return out
    r = requests.get(DOWNLOAD.format(id=DATASETS[year]), headers={"User-Agent": "Mozilla/5.0"}, timeout=180)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise RuntimeError(f"VA {year}: expected a PDF, got {r.content[:60]!r}")
    out.write_bytes(r.content)
    return out


def pdf_text(path: Path) -> str:
    """Flate-decoded text of a PDF, good enough for these machine-generated tables."""
    raw = path.read_bytes()
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        try:
            data = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        text = b" ".join(re.findall(rb"\((?:[^()\\]|\\.)*\)", data))
        if len(text) > 60:
            chunks.append(re.sub(rb"[()]", b" ", text).decode("latin-1"))
    return re.sub(r"\s+", " ", " ".join(chunks))


SMART = {"\x80": "'", "\x92": "'", "\x91": "'", "‘": "'", "’": "'", "\x93": '"', "\x94": '"', "“": '"', "”": '"', "\x96": "-", "\x97": "-"}


def normalize_item(text: str) -> str:
    """Item text as a stable key: smart punctuation folded to ASCII, case and trailing marks dropped."""
    for bad, good in SMART.items():
        text = text.replace(bad, good)
    return " ".join(text.split()).lower().rstrip("?. ")


def parse(path: Path) -> list[dict]:
    """[{item, unit, positive, base_excludes_dk}] for every item and reporting unit in one year's tables."""
    text = pdf_text(path)
    blocks = re.split(r"Survey Item=", text)[1:]
    out: list[dict] = []
    for block in blocks:
        cut = min((block.find(s) for s in SCALE_STARTS if block.find(s) >= 0), default=-1)
        if cut < 0:
            continue
        item = normalize_item(block[:cut])
        if not item:
            continue
        for unit, nums in ROW.findall(block):
            pct = [int(x) for x in re.findall(r"(\d+)%", nums)]
            if len(pct) < 6:
                continue
            # Five response options then "Missing or Do not Know"; positive is the top two.
            options, missing = pct[:5], pct[5]
            base = sum(options)
            if base <= 0:
                continue
            out.append({"item": item, "unit": unit, "positive": 100.0 * (options[3] + options[4]) / base, "missing": missing})
    return out


def va_facts(fetch_missing: bool = True) -> list[tuple]:
    facts: list[tuple] = []
    for year in sorted(DATASETS):
        path = VA_DIR / f"aes_{year}.pdf"
        if not path.exists():
            if not fetch_missing:
                continue
            try:
                path = fetch(year)
            except Exception as exc:  # noqa: BLE001
                log.warning("VA AES %d unavailable: %s", year, exc)
                continue
        rows = parse(path)
        period = survey_year_start(year)
        ref = f"va-aes:{year}"
        by_unit: dict[str, dict[str, float]] = {}
        for r in rows:
            key = r["item"]
            by_unit.setdefault(r["unit"], {})[key] = r["positive"]
            measure = ITEM_MEASURES.get(key)
            node = ADMINISTRATIONS.get(r["unit"])
            if measure and node:
                facts.append((measure, node, "survey_year", period, None, None, round(r["positive"], 1), None, "estimate", ref))
        for unit, items in by_unit.items():
            node = ADMINISTRATIONS.get(unit)
            if not node:
                continue
            subindices = []
            for name, wanted in EEI_SUBINDICES.items():
                have = [items[k] for k in wanted if k in items]
                if len(have) < len(wanted):
                    log.warning("VA %d %s: %s subindex has %d of %d items; index skipped", year, unit, name, len(have), len(wanted))
                    subindices = []
                    break
                subindices.append(sum(have) / len(have))
            if subindices:
                facts.append(("va_aes_engagement", node, "survey_year", period, None, None, round(sum(subindices) / len(subindices), 1), None, "estimate", ref))
    log.info("va aes: %d facts across %d years", len(facts), len(DATASETS))
    return facts
