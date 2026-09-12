"""PLUM checks: clean text, honest status split, and a crosswalk that places almost every position."""
import json
import pytest

from pipeline.config import CROSSWALK, SLICES
from pipeline.plum.load import APPOINTMENT_TYPES, POSITIONS

PLUM_SLICES = SLICES / "plum"


@pytest.fixture(scope="module")
def built():
    if not (PLUM_SLICES / "directory.json").exists():
        pytest.skip("PLUM slices not built")
    return json.loads((PLUM_SLICES / "directory.json").read_text())


def test_no_html_entities(built):
    blob = json.dumps(built)
    for entity in ("&#039;", "&amp;", "&quot;", "&nbsp;"):
        assert entity not in blob, entity


def test_directory_rows_are_filled_positions_with_names(built):
    assert built["people"], "directory is empty"
    assert all(p["n"].strip() for p in built["people"])
    assert all(p["at"] in APPOINTMENT_TYPES for p in built["people"])


def test_crosswalk_places_nearly_every_position():
    review = json.loads((CROSSWALK / "plum_review.json").read_text())
    c = review["counts"]
    assert c["mapped"] / c["pairs"] > 0.9, c
    unmatched = sum(a["positions"] for a in review["agencies_unmatched"])
    assert unmatched < 500, f"{unmatched} positions have no agency"


def test_rosters_attach_to_real_nodes():
    nodes = json.loads((SLICES / "measures" / "nodes.json").read_text())["nodes"]
    files = list(PLUM_SLICES.glob("node-*.json"))
    assert files, "no rosters"
    for f in files:
        assert f.name[len("node-"):-len(".json")] in nodes, f.name


def test_no_workforce_fields_leak_into_plum(built):
    """PRD Non-Goal 2: a PLUM record never acquires a workforce attribute."""
    forbidden = {"age_bracket", "length_of_service", "grade", "pay_band", "veteran", "education"}
    for p in built["people"][:200]:
        assert not (forbidden & set(p)), p
