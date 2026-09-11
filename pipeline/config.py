"""Paths, endpoints, and the definitions that must not drift (see CLAUDE.md)."""
from __future__ import annotations

from pathlib import Path

import os

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
# Raw downloads and intermediate parquet live outside the repo when FEDPULSE_DATA is set, because the repo sits in
# an iCloud-synced folder and iCloud evicts and re-uploads large files (see CLAUDE.md, operational gotchas).
_DATA_ROOT = Path(os.environ["FEDPULSE_DATA"]).expanduser() if os.environ.get("FEDPULSE_DATA") else DATA
RAW = _DATA_ROOT / "raw"
WORK = _DATA_ROOT / "work"
LOOKUPS = DATA / "lookups"
SLICES = DATA / "slices"
REFERENCE = DATA / "reference"
CROSSWALK = ROOT / "crosswalk"
MANIFEST = ROOT / "manifest.json"

FWD_API = "https://data.opm.gov/api/v1/files"
FWD_BLOB = "https://data.opm.gov/data/blob/download/chunked/{filename}.txt"
PLUM_DOWNLOAD = "https://escs.opm.gov/escs-net/api/pbpub/download-data"
USASPENDING_API = "https://api.usaspending.gov/api/v2"

DATASETS = ("employment", "accessions", "separations")

NOT_DISCLOSED = "NDS"
REDACTED = "REDACTED"

# Fact-table dimensions common to all three datasets: source column -> fact column.
COMMON_DIMS = {
    "agency_subelement_code": "org_code",
    "duty_station_code": "duty_station_code",
    "occupational_series_code": "series_code",
    "pay_plan_code": "pay_plan_code",
    "grade": "grade",
    "step_or_rate_type_code": "step_code",
    "supervisory_status_code": "supervisory_code",
    "work_schedule_code": "work_schedule_code",
    "appointment_type_code": "appointment_type_code",
    "position_occupied_code": "position_occupied_code",
    "tenure_code": "tenure_code",
    "age_bracket": "age_bracket",
    "education_level_bracket": "education_bracket",
    "veteran_indicator": "veteran",
    "flsa_category_code": "flsa_code",
    "pay_basis_code": "pay_basis_code",
}

# Dataset-specific dimensions.
DATASET_DIMS = {
    "employment": {"snapshot_yyyymm": "snapshot_yyyymm"},
    "accessions": {
        "personnel_action_effective_date_yyyymm": "effective_yyyymm",
        "accession_category_code": "accession_category_code",
        "pathways_group": "pathways_group",
    },
    "separations": {
        "personnel_action_effective_date_yyyymm": "effective_yyyymm",
        "separation_category_code": "separation_category_code",
        "drp_indicator": "drp_indicator",
    },
}

# Small enumerated dimensions whose code -> label pairs go into lookups/codes.json.
CODE_TABLES = {
    "supervisory_status": ("supervisory_status_code", "supervisory_status"),
    "work_schedule": ("work_schedule_code", "work_schedule"),
    "appointment_type": ("appointment_type_code", "appointment_type"),
    "position_occupied": ("position_occupied_code", "position_occupied"),
    "tenure": ("tenure_code", "tenure"),
    "flsa_category": ("flsa_category_code", "flsa_category"),
    "pay_basis": ("pay_basis_code", "pay_basis"),
    "education_level": ("education_level_code", "education_level"),
    "separation_category": ("separation_category_code", "separation_category"),
    "accession_category": ("accession_category_code", "accession_category"),
}

# USAspending object class classification (PRD 5.8). Keys are the 2- or 4-char code prefixes.
PERSONNEL_CODES = {"11.1", "11.3", "11.5", "11.7", "11.8", "11.9", "12.1", "12.2", "13.0"}
CONTRACTED_CODES = {"25.1", "25.2"}
FEDERAL_SERVICES_CODES = {"25.3"}
ADMINISTERED_CODES = {"41.0", "42.0", "43.0", "44.0", "33.0", "94.0"}
OPERATIONS_PREFIXES = ("11", "12", "13", "21", "22", "23", "24", "25", "26", "31", "32")


def classify_object_class(code: str) -> str:
    """Bucket a File B object class code per PRD 5.8."""
    code = (code or "").strip()
    if code in PERSONNEL_CODES:
        return "personnel"
    if code in CONTRACTED_CODES:
        return "contracted"
    if code in FEDERAL_SERVICES_CODES:
        return "federal_services"
    if code in ADMINISTERED_CODES:
        return "administered"
    if code.startswith(OPERATIONS_PREFIXES):
        return "operations_other"
    return "other"
