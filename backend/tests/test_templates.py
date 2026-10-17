"""Template explanations for trivial groups (no model call)."""

from app.core.grouping.patterns import group_formulas
from app.core.llm.explainer import explain_groups
from app.core.llm.templates import render_group
from app.core.models import CellRecord, CellRef, FormulaGroup, ParsedWorkbook
from app.core.parser.reader import read_workbook
from conftest import CLEAN_XLSX, FakeLLMClient


def _by_cell(sheet):
    wb = read_workbook(CLEAN_XLSX)
    groups = group_formulas(wb)
    return wb, {(g.sheet, g.cells[0]): g for g in groups}


def test_plain_link_template():
    wb, groups = _by_cell("Pricing")
    out = render_group(groups[("Pricing", "A2")], wb)
    # The referenced cell is itself text, so its own value is the label.
    assert out == {
        "summary": "Pulls Copy Paper A4 Rim from Inputs.",
        "plain_formula": "Copy Paper A4 Rim",
    }


def test_aggregate_template():
    wb, groups = _by_cell("Summary")
    out = render_group(groups[("Summary", "B2")], wb)
    assert out is not None
    assert out["summary"] == "Adds up Cost Total from rows 2 to 21 of Pricing."
    assert out["plain_formula"] == "Sum of Cost Total"


def test_binary_operator_template():
    wb, groups = _by_cell("Pricing")
    out = render_group(groups[("Pricing", "B2")], wb)
    assert out is not None
    assert "Unit Cost" in out["summary"] and "Qty" in out["summary"]


def test_missing_label_falls_through():
    wb = ParsedWorkbook(
        cells={
            "S!A1": CellRecord(
                ref=CellRef(sheet="S", address="A1"), value=5, kind="input"
            ),
            "S!B1": CellRecord(
                ref=CellRef(sheet="S", address="B1"),
                formula="=A1*2",
                kind="formula",
            ),
        }
    )
    group = FormulaGroup(
        id="g", sheet="S", pattern_r1c1="p", cells=["B1"],
        sample_formula="=A1*2", labels={},
    )
    assert render_group(group, wb) is None  # A1 has no label at all


def test_templated_groups_make_no_model_calls():
    wb = read_workbook(CLEAN_XLSX)
    groups = group_formulas(wb)
    templatable = [
        g for g in groups
        if (g.sheet, g.cells[0]) in {("Pricing", "A2"), ("Pricing", "B2")}
    ]
    assert len(templatable) == 2
    fake = FakeLLMClient()
    out = explain_groups(templatable, wb, fake)
    assert fake.calls == []
    assert all(e.source == "template" for e in out.values())
    assert all(e.text for e in out.values())


def test_mixed_groups_use_model_for_rest():
    wb = read_workbook(CLEAN_XLSX)
    groups = group_formulas(wb)
    fake = FakeLLMClient()
    out = explain_groups(groups, wb, fake)
    sources = {e.source for e in out.values()}
    assert "template" in sources and "model" in sources
