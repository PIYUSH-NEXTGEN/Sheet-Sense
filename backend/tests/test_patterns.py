"""Phase 2 grouping tests (spec sections 5.1 + 11.2)."""

from app.core.grouping.patterns import (
    group_formulas,
    group_id,
    normalize_formula,
)
from app.core.parser.reader import read_workbook
from conftest import CLEAN_XLSX, DIRTY_XLSX


def test_normalize_relative():
    # host C2 (row 2, col 3): B2 -> R[0]C[-1]
    assert normalize_formula("=B2*(1+A1)", 2, 3) == "=R[0]C[-1]*(1+R[-1]C[-2])"


def test_normalize_absolute_keeps_coordinates():
    # $B$1 is absolute wherever the host sits.
    assert normalize_formula("=B2*(1+Settings!$B$1)", 2, 3).endswith(
        "Settings!R1C2)"
    )
    assert "Settings!R1C2" in normalize_formula("=Settings!$B$1*2", 20, 10)


def test_normalize_mixed_absolute():
    # $B1: absolute col, relative row; B$1: relative col, absolute row.
    assert normalize_formula("=$B1+B$1", 5, 5) == "=R[-4]C2+R1C[-3]"


def test_normalize_range_both_endpoints():
    assert normalize_formula("=SUM(Pricing!B2:B21)", 2, 2) == (
        "=SUM(Pricing!R[0]C[0]:R[19]C[0])"
    )


def test_normalize_preserves_quote_and_locals():
    assert normalize_formula("='My Sheet'!A1+$A$1", 3, 3) == (
        "='My Sheet'!R[-2]C[-2]+R1C1"
    )


def test_normalize_keeps_names_and_literals_verbatim():
    assert normalize_formula("=Total*1.15", 1, 1) == "=Total*1.15"


def test_same_pattern_down_column():
    # Pricing!C2 and C3 share the pattern despite different rows.
    p2 = normalize_formula("=B2*(1+Settings!$B$1)", 2, 3)
    p3 = normalize_formula("=B3*(1+Settings!$B$1)", 3, 3)
    assert p2 == p3


def test_clean_pricing_c_collapses_to_one_group_of_20():
    groups = group_formulas(read_workbook(CLEAN_XLSX))
    col_c = [
        g
        for g in groups
        if g.sheet == "Pricing" and g.cells and g.cells[0].startswith("C")
    ]
    assert len(col_c) == 1
    assert col_c[0].cells == [f"C{r}" for r in range(2, 22)]


def test_clean_pricing_columns_each_one_group():
    groups = group_formulas(read_workbook(CLEAN_XLSX))
    pricing = [g for g in groups if g.sheet == "Pricing"]
    assert len(pricing) == 4
    assert all(len(g.cells) == 20 for g in pricing)


def test_clean_summary_groups_are_singles():
    groups = group_formulas(read_workbook(CLEAN_XLSX))
    summary = [g for g in groups if g.sheet == "Summary"]
    assert len(summary) == 4
    assert all(len(g.cells) == 1 for g in summary)


def test_dirty_break_splits_column():
    groups = group_formulas(read_workbook(DIRTY_XLSX))
    col_c = sorted(
        (
            g
            for g in groups
            if g.sheet == "Pricing" and g.cells and g.cells[0].startswith("C")
        ),
        key=lambda g: int(g.cells[0][1:]),
    )
    assert [g.cells for g in col_c] == [
        [f"C{r}" for r in range(2, 13)],
        [f"C{r}" for r in range(14, 22)],
    ]
    assert all("C13" not in g.cells for g in groups)


def test_group_ids_stable():
    wb = read_workbook(CLEAN_XLSX)
    first = [(g.id, g.cells) for g in group_formulas(wb)]
    second = [(g.id, g.cells) for g in group_formulas(wb)]
    assert first == second
    assert len({gid for gid, _ in first}) == len(first)


def test_group_id_hashes_sheet_pattern_first():
    assert group_id("S", "p", "A1") == group_id("S", "p", "A1")
    assert group_id("S", "p", "A1") != group_id("S", "p", "A2")
    assert group_id("S", "p", "A1") != group_id("T", "p", "A1")


def test_group_labels_and_sample():
    groups = group_formulas(read_workbook(CLEAN_XLSX))
    col_c = next(
        g
        for g in groups
        if g.sheet == "Pricing" and g.cells[0] == "C2"
    )
    assert col_c.sample_formula == "=B2*(1+Settings!$B$1)"
    assert col_c.labels.get("header") == "Price"
    assert col_c.pattern_r1c1 == normalize_formula(col_c.sample_formula, 2, 3)
