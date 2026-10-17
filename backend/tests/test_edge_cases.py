"""Edge-case tests (QA Stage 3): parser/detector corners + corrupt inputs.

Workbooks are generated once per session into a temp dir by
``tests/edge_cases/make_edge_cases.py``. Each case must either behave
correctly or fail with a clear, non-crashing error.
"""

import pytest

from app.core.graph.builder import build_graph
from app.core.graph.queries import dependents, precedents
from app.core.parser import reader as reader_mod
from app.core.parser.reader import read_workbook
from app.core.parser.refs import extract_refs
from app.core.detectors.base import run_all
from app.core.grouping.patterns import group_formulas
from tests.edge_cases.make_edge_cases import build_all

CASES: dict[str, str] = {}


@pytest.fixture(scope="module")
def edge_dir(tmp_path_factory):
    return build_all(tmp_path_factory.mktemp("edge"))


@pytest.fixture(scope="module")
def parsed(edge_dir):
    out = {}
    for name, path in edge_dir.items():
        if name.endswith("_cached"):
            continue
        wb = read_workbook(path)
        graph = build_graph(wb)
        groups = group_formulas(wb)
        out[name] = (wb, graph, groups, run_all(wb, graph, groups))
    return out


def _issues(entry, detector=None):
    _, _, _, issues = entry
    if detector is None:
        return {(i.detector, i.ref.sheet, i.ref.address) for i in issues}
    return {(i.ref.sheet, i.ref.address) for i in issues if i.detector == detector}


def test_empty_workbook(parsed):
    wb, _, _, issues = parsed["empty"]
    assert wb.cells == {} and issues == [] and wb.warnings == []


def test_blank_sheet(parsed):
    wb, _, _, issues = parsed["blank_sheet"]
    assert wb.cells["Notes!A1"].kind == "label"
    assert issues == []


def test_weird_names(parsed):
    wb, graph, _, issues = parsed["weird_names"]
    assert wb.cells["O'Brien!A1"].formula == "='My Sheet'!A1*2"
    assert "My Sheet!A1" in precedents(graph, "O'Brien!A1")
    assert wb.cells["Ünïcödé 日本語!A1"].value is None
    assert issues == []


def test_defined_names(parsed):
    wb, graph, _, issues = parsed["names"]
    assert "Rate" in wb.defined_names
    assert "Data!A1" in extract_refs("=Rate*2", "Data", wb.defined_names)
    assert set(dependents(graph, "Data!A1")) == {"Data!B1"}
    assert issues == []


def test_whole_column_collapses(parsed):
    wb, graph, _, issues = parsed["whole_col"]
    assert "S!A:A" in graph.nodes
    assert graph.nodes["S!A:A"]["kind"] == "range"
    assert issues == []


def test_tricky_literals_only_control_flagged(parsed):
    # B4's MATCH lookup value 9 is flaggable per spec (only the match-type
    # arg is excluded); B8's 1.15 is the planted control.
    assert _issues(parsed["tricky"], "hardcoded_constant") == {
        ("S", "B4"),
        ("S", "B8"),
    }
    assert _issues(parsed["tricky"]) == {
        ("hardcoded_constant", "S", "B4"),
        ("hardcoded_constant", "S", "B8"),
    }


def test_hidden_merged(parsed):
    wb, _, _, issues = parsed["hidden_merged"]
    assert wb.cells["S!C1"].kind == "formula"
    assert "S!D1" not in wb.cells  # merged-away cell stays empty
    assert "Meta!A1" in wb.cells  # hidden sheets still parse
    assert issues == []


def test_external_links_ignored(parsed):
    wb, graph, _, issues = parsed["external"]
    assert extract_refs("=[1]Sheet1!A1", "S") == []
    assert extract_refs("='C:\\dir\\[b.xlsx]S'!A1", "S") == []
    assert set(graph.nodes) == {"S!A1", "S!A2"}
    assert issues == []


def test_cached_values_present(edge_dir):
    wb = read_workbook(edge_dir["cached_ok"])
    assert wb.has_cached_values is True
    assert wb.warnings == []
    assert wb.cells["S!A2"].value == 10
    graph = build_graph(wb)
    groups = group_formulas(wb)
    assert run_all(wb, graph, groups) == []
    assert groups[0].sample_values == [10]


def test_error_values_cached_and_literal(edge_dir):
    wb = read_workbook(edge_dir["errors_cached"])
    assert wb.has_cached_values is True
    graph = build_graph(wb)
    groups = group_formulas(wb)
    got = {
        (i.detector, i.ref.sheet, i.ref.address)
        for i in run_all(wb, graph, groups)
        if i.detector == "error_values"
    }
    assert got == {("error_values", "S", "A2"), ("error_values", "S", "A3")}
    assert wb.cells["S!A4"].kind == "label"  # typed error text is not a cached value


def test_loops_all_sizes(parsed):
    got = _issues(parsed["loops"], "circular")
    assert got == {("S", "A1"), ("S", "B1"), ("S", "C1")}
    assert _issues(parsed["loops"]) == {
        ("circular", "S", "A1"),
        ("circular", "S", "B1"),
        ("circular", "S", "C1"),
    }


def test_sandwich_5k(parsed):
    # The constant is both a pattern break (inside a formula column) and a
    # labeled ("V" header), unreferenced numeric input. A bare constant is
    # not a formula literal, so hardcoded_constant stays silent here.
    assert _issues(parsed["sandwich_5k"]) == {
        ("pattern_break", "S", "A2502"),
        ("orphan_input", "S", "A2502"),
    }


def test_percent_scale(parsed):
    got = _issues(parsed["percent"], "unit_mismatch")
    assert got == {("S", "A2")}


def test_array_formula_is_formula(parsed):
    wb, _, _, _ = parsed["array"]
    rec = wb.cells["Data!B1"]
    assert rec.kind == "formula"
    assert rec.formula == "=SUM(A1:A2*2)"


def test_corrupt_files_raise_value_error(tmp_path):
    import shutil

    from conftest import DIRTY_XLSX

    garbage = tmp_path / "garbage.xlsx"
    garbage.write_bytes(b"\x00\x01not a zip" * 20)
    with pytest.raises(ValueError):
        read_workbook(garbage)
    zero = tmp_path / "zero.xlsx"
    zero.write_bytes(b"")
    with pytest.raises(ValueError):
        read_workbook(zero)
    renamed = tmp_path / "renamed.xlsx"
    renamed.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError):
        read_workbook(renamed)
    macro = tmp_path / "evil.xlsm"
    shutil.copy(DIRTY_XLSX, macro)
    with pytest.raises(ValueError, match="[Mm]acro"):
        read_workbook(macro)


def test_oversize_guard(tmp_path, monkeypatch):
    from conftest import DIRTY_XLSX

    monkeypatch.setattr(reader_mod, "MAX_FILE_MB", 0.000001)
    with pytest.raises(ValueError, match="[Ll]imit"):
        read_workbook(DIRTY_XLSX)
