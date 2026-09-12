"""The iCloud conflict sweep must catch copies and spare legitimate names."""
from pipeline.hygiene import is_conflict_copy, sweep
from pathlib import Path


def test_recognizes_conflict_copies():
    for name in ("orgtree 2.json", "DL 3", "measures 2.parquet", "index 10.html"):
        assert is_conflict_copy(Path(name)), name


def test_spares_legitimate_names():
    for name in ("ap_5_tables_1-3.xlsx", "counties-10m.json", "fileb_FY2026Q3.parquet",
                 "2024-ee-report-excel.xlsx", "employment_202607_1.parquet", "measures.json"):
        assert not is_conflict_copy(Path(name)), name


def test_sweep_removes_only_copies(tmp_path):
    (tmp_path / "data").mkdir()
    keep = tmp_path / "data" / "orgtree.json"
    drop = tmp_path / "data" / "orgtree 2.json"
    keep.write_text("{}")
    drop.write_text("{}")
    removed = sweep(tmp_path)
    assert removed == [drop]
    assert keep.exists() and not drop.exists()
