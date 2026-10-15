"""Phase 1 parser tests: formulas, kinds and labels on both fixtures."""

import pytest

from app.core.parser.reader import CACHED_VALUES_MISSING, read_workbook
from conftest import CLEAN_XLSX, DIRTY_XLSX


@pytest.fixture(scope="module")
def clean():
    return read_workbook(CLEAN_XLSX)


@pytest.fixture(scope="module")
def dirty():
    return read_workbook(DIRTY_XLSX)


def test_pricing_formulas_clean(clean):
    assert clean.cells["Pricing!B2"].formula == "=Inputs!B2*Inputs!C2"
    assert clean.cells["Pricing!C2"].formula == "=B2*(1+Settings!$B$1)"
    assert clean.cells["Pricing!D2"].formula == "=C2+C2*Settings!$B$2"
    assert clean.cells["Pricing!A2"].formula == "=Inputs!A2"
    assert clean.cells["Pricing!C21"].formula == "=B21*(1+Settings!$B$1)"


def test_summary_formulas_clean(clean):
    assert clean.cells["Summary!B2"].formula == "=SUM(Pricing!B2:B21)"
    assert clean.cells["Summary!B3"].formula == "=SUM(Pricing!C2:C21)"
    assert clean.cells["Summary!B4"].formula == "=SUM(Pricing!D2:D21)"
    assert clean.cells["Summary!B5"].formula == "=B4*(1+Settings!B4)"


def test_kinds_clean(clean):
    assert clean.cells["Pricing!B2"].kind == "formula"
    assert clean.cells["Summary!B4"].kind == "formula"
    assert clean.cells["Inputs!B2"].kind == "input"  # numeric constant
    assert clean.cells["Settings!B1"].kind == "input"
    assert clean.cells["Inputs!A2"].kind == "label"  # text "Item-01"
    assert clean.cells["Pricing!B1"].kind == "label"  # header "Cost Total"
    assert clean.cells["Summary!A2"].kind == "label"
    assert "Pricing!Z99" not in clean.cells  # empty cells are absent


def test_labels_clean(clean):
    assert clean.cells["Pricing!B2"].label_above == "Cost Total"
    assert clean.cells["Pricing!C2"].label_above == "Price"
    assert clean.cells["Pricing!D2"].label_above == "With Tax"
    # Pricing!A2 is a formula, not text, so no text sits left of B2.
    assert clean.cells["Pricing!B2"].label_left is None
    assert clean.cells["Inputs!B2"].label_above == "Unit Cost"
    assert clean.cells["Inputs!B2"].label_left == "Item-01"
    assert clean.cells["Inputs!C5"].label_above == "Qty"
    assert clean.cells["Summary!B2"].label_left == "Total cost"
    assert clean.cells["Summary!B4"].label_left == "Total with tax"
    assert clean.cells["Summary!B5"].label_left == "Total with surcharge"


def test_cached_values_missing_warning(clean, dirty):
    # openpyxl-written fixtures carry no cached values; the tool must say so.
    for wb in (clean, dirty):
        assert wb.has_cached_values is False
        assert CACHED_VALUES_MISSING in wb.warnings
        assert clean.cells["Pricing!B2"].value is None


def test_number_format_present(clean):
    assert clean.cells["Inputs!B2"].number_format == "General"


def test_no_defined_names_in_fixtures(clean):
    assert clean.defined_names == {}


def test_dirty_planted_differences(dirty):
    assert dirty.cells["Summary!B5"].formula == "=B4*1.15"
    c13 = dirty.cells["Pricing!C13"]
    assert c13.formula is None and c13.value == 99.5 and c13.kind == "input"
    assert dirty.cells["Summary!B3"].formula == "=SUM(Pricing!C2:C20)"
    assert dirty.cells["Settings!A3"].value == "Unused discount"
    assert dirty.cells["Settings!B3"].value == 0.10
    assert dirty.cells["Summary!B7"].formula == "=B8+1"
    assert dirty.cells["Summary!B8"].formula == "=B7*2"
    assert dirty.cells["Summary!A7"].value == "Loop A"


def test_clean_lacks_dirty_cells(clean):
    assert "Summary!B7" not in clean.cells
    assert "Settings!A3" not in clean.cells
    assert clean.cells["Pricing!C13"].formula == "=B13*(1+Settings!$B$1)"


def test_xlsm_rejected(tmp_path):
    import shutil

    fake = tmp_path / "copy.xlsm"
    shutil.copy(CLEAN_XLSX, fake)
    with pytest.raises(ValueError, match="[Mm]acro"):
        read_workbook(fake)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(ValueError, match="[Cc]annot read|[Nn]o such"):
        read_workbook(tmp_path / "nope.xlsx")
