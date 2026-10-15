"""Phase 1 reference-extraction tests.

Covers spec section 4 stage 2 via ``extract_refs``: cross-sheet refs,
absolute refs, ranges, quoted sheet names and defined names, plus the
> 5,000-cell range-node cap and whole-column collapsing.
"""

from app.core.parser.refs import (
    RANGE_EXPANSION_CAP,
    cell_key,
    extract_refs,
    is_range_key,
    split_key,
)


def test_cross_sheet_refs():
    assert extract_refs("=Inputs!B2*Inputs!C2", "Pricing") == [
        "Inputs!B2",
        "Inputs!C2",
    ]


def test_absolute_refs_use_host_sheet():
    assert extract_refs("=B2*(1+Settings!$B$1)", "Pricing") == [
        "Pricing!B2",
        "Settings!B1",
    ]


def test_range_expands_to_cells():
    refs = extract_refs("=SUM(Pricing!B2:B21)", "Summary")
    assert refs == [f"Pricing!B{r}" for r in range(2, 22)]


def test_range_sheet_prefix_on_first_endpoint_only():
    refs = extract_refs("=SUM(Sheet1!A1:B2)", "Other")
    assert refs == ["Sheet1!A1", "Sheet1!A2", "Sheet1!B1", "Sheet1!B2"]


def test_quoted_sheet_name():
    assert extract_refs("='My Sheet'!A1+$A$1", "Other") == [
        "My Sheet!A1",
        "Other!A1",
    ]


def test_quoted_sheet_range():
    refs = extract_refs("=SUM('My Sheet'!A1:A3)", "Other")
    assert refs == ["My Sheet!A1", "My Sheet!A2", "My Sheet!A3"]


def test_defined_name_single_cell():
    refs = extract_refs("=Total*2", "Summary", {"Total": "Settings!$B$1"})
    assert refs == ["Settings!B1"]


def test_defined_name_range():
    refs = extract_refs(
        "=SUM(Data)", "Summary", {"Data": "Pricing!$B$2:$B$4"}
    )
    assert refs == ["Pricing!B2", "Pricing!B3", "Pricing!B4"]


def test_defined_names_case_insensitive():
    refs = extract_refs("=total*2", "Summary", {"Total": "Settings!$B$1"})
    assert refs == ["Settings!B1"]


def test_unknown_name_ignored():
    assert extract_refs("=FooBarBaz*A1", "S") == ["S!A1"]


def test_literals_and_errors_ignored():
    assert extract_refs("=B4*1.15", "Summary") == ["Summary!B4"]
    assert extract_refs("=A1+#REF!", "S") == ["S!A1"]
    assert extract_refs('="hello"&A1', "S") == ["S!A1"]


def test_duplicates_removed_in_order():
    assert extract_refs("=C2+C2*Settings!$B$2", "Pricing") == [
        "Pricing!C2",
        "Settings!B2",
    ]


def test_non_formula_yields_no_refs():
    assert extract_refs(None, "S") == []
    assert extract_refs("", "S") == []
    assert extract_refs("just text", "S") == []


def test_whole_column_collapses_to_range_node():
    refs = extract_refs("=SUM(A:A)", "S")
    assert refs == ["S!A:A"]
    assert all(is_range_key(r) for r in refs)


def test_huge_range_collapses_to_single_node():
    refs = extract_refs("=SUM(A1:XFD1048576)", "S")
    assert len(refs) == 1 and is_range_key(refs[0])


def test_cap_boundary():
    assert RANGE_EXPANSION_CAP == 5000
    at_cap = extract_refs("=SUM(A1:E1000)", "S")  # exactly 5,000 cells
    assert len(at_cap) == 5000 and not any(is_range_key(k) for k in at_cap)
    over_cap = extract_refs("=SUM(A1:E1001)", "S")  # 5,005 cells
    assert len(over_cap) == 1 and is_range_key(over_cap[0])


def test_key_helpers():
    assert cell_key("Summary", "B4") == "Summary!B4"
    assert split_key("Summary!B4") == ("Summary", "B4")
    assert split_key("S!A1:B9") == ("S", "A1:B9")
    assert is_range_key("S!A1:B9") and not is_range_key("S!B9")
