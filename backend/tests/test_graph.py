"""Phase 1 graph tests: precedents/dependents of Summary!B4 and node kinds."""

import pytest

from app.core.graph.builder import build_graph
from app.core.graph.queries import (
    ancestors,
    dependents,
    descendants,
    precedents,
    trace_chain,
)
from app.core.models import CellRecord, CellRef, ParsedWorkbook
from app.core.parser.reader import read_workbook
from conftest import CLEAN_XLSX, DIRTY_XLSX


@pytest.fixture(scope="module")
def clean_graph():
    return build_graph(read_workbook(CLEAN_XLSX))


@pytest.fixture(scope="module")
def dirty_graph():
    return build_graph(read_workbook(DIRTY_XLSX))


def test_summary_b4_precedents_clean(clean_graph):
    expected = {f"Pricing!D{r}" for r in range(2, 22)}
    assert set(precedents(clean_graph, "Summary!B4")) == expected


def test_summary_b4_dependents_clean(clean_graph):
    assert dependents(clean_graph, "Summary!B4") == ["Summary!B5"]


def test_summary_b4_precedents_dirty(dirty_graph):
    expected = {f"Pricing!D{r}" for r in range(2, 22)}
    assert set(precedents(dirty_graph, "Summary!B4")) == expected


def test_summary_b4_dependents_dirty(dirty_graph):
    assert dependents(dirty_graph, "Summary!B4") == ["Summary!B5"]


def test_edge_direction_precedent_to_dependent(clean_graph):
    assert ("Pricing!D2", "Summary!B4") in clean_graph.edges
    assert ("Summary!B4", "Pricing!D2") not in clean_graph.edges


def test_node_kinds_clean(clean_graph):
    assert clean_graph.nodes["Summary!B4"]["kind"] == "formula"  # has dependent B5
    assert clean_graph.nodes["Summary!B5"]["kind"] == "output"  # no dependents
    assert clean_graph.nodes["Inputs!B2"]["kind"] == "input"
    assert clean_graph.nodes["Settings!B1"]["kind"] == "input"
    assert clean_graph.nodes["Summary!B4"]["formula"] == "=SUM(Pricing!D2:D21)"


def test_chain_through_pricing(clean_graph):
    ups = ancestors(clean_graph, "Summary!B4")
    assert "Pricing!D2" in ups and "Pricing!C2" in ups  # D2 via C2
    assert "Settings!B2" in ups  # tax rate feeds column D
    assert "Summary!B4" not in ups


def test_ancestors_depth_limit(clean_graph):
    deep = ancestors(clean_graph, "Summary!B5", depth=1)
    # Clean B5 =B4*(1+Settings!B4): two direct precedents.
    assert deep == ["Settings!B4", "Summary!B4"]
    full = ancestors(clean_graph, "Summary!B5")
    assert len(full) > len(deep)
    assert "Settings!B4" in full  # clean B5 references the surcharge


def test_circular_loop_edges_dirty(dirty_graph):
    assert "Summary!B8" in precedents(dirty_graph, "Summary!B7")
    assert "Summary!B7" in precedents(dirty_graph, "Summary!B8")
    assert "Summary!B7" in dependents(dirty_graph, "Summary!B8")
    assert "Summary!B8" in dependents(dirty_graph, "Summary!B7")


def test_unknown_cell_raises(clean_graph):
    with pytest.raises(KeyError):
        precedents(clean_graph, "Nope!Z99")


def _mini_workbook() -> ParsedWorkbook:
    cells = {
        "S!A1": CellRecord(ref=CellRef(sheet="S", address="A1"), value=1, kind="input"),
        "S!B1": CellRecord(
            ref=CellRef(sheet="S", address="B1"), formula="=SUM(A:A)", kind="formula"
        ),
    }
    return ParsedWorkbook(cells=cells)


def test_whole_column_creates_range_node():
    graph = build_graph(_mini_workbook())
    assert "S!A:A" in graph.nodes
    assert graph.nodes["S!A:A"]["kind"] == "range"
    assert ("S!A:A", "S!B1") in graph.edges


def test_trace_chain_shape(clean_graph):
    chain = trace_chain(clean_graph, "Summary!B4")
    assert chain["target"] == ["Summary!B4"]
    assert f"Pricing!D2" in chain["ancestors"]
    assert len(chain["formulas"]) == len(chain["ancestors"]) + 1


def test_descendants_flow_down(clean_graph):
    downs = descendants(clean_graph, "Pricing!D2")
    assert "Summary!B4" in downs and "Summary!B5" in downs
