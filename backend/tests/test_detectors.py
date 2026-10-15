"""Phase 2 detector tests (spec sections 6 + 11.2).

Acceptance: ``clean.xlsx`` yields zero issues; ``dirty.xlsx`` yields exactly
the six entries in ``expected_issues.json``. Per-detector rules are covered
with small synthetic workbooks.
"""

import json

import pytest

from app.core.detectors import (
    circular,
    error_values,
    hardcoded_constant,
    orphan_input,
    pattern_break,
    range_gap,
    unit_mismatch,
)
from app.core.detectors.base import REGISTRY, run_all
from app.core.graph.builder import build_graph
from app.core.grouping.patterns import group_formulas
from app.core.models import CellRecord, CellRef, ParsedWorkbook
from app.core.parser.reader import read_workbook
from conftest import CLEAN_XLSX, DIRTY_XLSX, EXPECTED_ISSUES


def _rec(
    sheet: str,
    address: str,
    formula: str | None = None,
    value=None,
    kind: str | None = None,
    label_left: str | None = None,
    label_above: str | None = None,
    number_format: str | None = None,
):
    if kind is None:
        kind = "formula" if formula else ("input" if value is not None else "label")
    return CellRecord(
        ref=CellRef(sheet=sheet, address=address),
        formula=formula,
        value=value,
        number_format=number_format,
        label_left=label_left,
        label_above=label_above,
        kind=kind,
    )


def _wb(cells: dict[str, CellRecord], has_cached: bool = False) -> ParsedWorkbook:
    return ParsedWorkbook(cells=cells, has_cached_values=has_cached)


def _key_set(issues) -> set[tuple[str, str, str]]:
    return {(i.detector, i.ref.sheet, i.ref.address) for i in issues}


@pytest.fixture(scope="module")
def clean_result():
    wb = read_workbook(CLEAN_XLSX)
    graph = build_graph(wb)
    return wb, graph, group_formulas(wb), run_all(wb, graph, group_formulas(wb))


@pytest.fixture(scope="module")
def dirty_result():
    wb = read_workbook(DIRTY_XLSX)
    graph = build_graph(wb)
    return wb, graph, group_formulas(wb), run_all(wb, graph, group_formulas(wb))


def test_all_seven_detectors_registered():
    assert sorted(REGISTRY) == [
        "circular",
        "error_values",
        "hardcoded_constant",
        "orphan_input",
        "pattern_break",
        "range_gap",
        "unit_mismatch",
    ]


def test_clean_workbook_zero_issues(clean_result):
    _, _, _, issues = clean_result
    assert issues == []


def test_dirty_matches_expected_issues(dirty_result):
    _, _, _, issues = dirty_result
    with open(EXPECTED_ISSUES, encoding="utf-8") as fh:
        expected = {
            (e["detector"], e["sheet"], e["address"]) for e in json.load(fh)
        }
    assert _key_set(issues) == expected
    assert len(issues) == 6  # no duplicates


def test_dirty_severities(dirty_result):
    _, _, _, issues = dirty_result
    by_detector = {i.detector: i.severity for i in issues}
    assert by_detector["hardcoded_constant"] == "medium"
    assert by_detector["pattern_break"] == "high"
    assert by_detector["range_gap"] == "high"
    assert by_detector["circular"] == "high"
    for i in issues:
        if i.detector == "orphan_input":
            assert i.severity == "low"


def test_evidence_carries_formula_pattern_and_neighbors(dirty_result):
    _, _, _, issues = dirty_result
    for issue in issues:
        assert "formula" in issue.evidence
        assert "pattern" in issue.evidence
        assert issue.ref.address in issue.message or issue.ref.sheet in issue.message


def test_run_all_is_deterministic(dirty_result):
    wb, graph, groups, issues = dirty_result
    again = run_all(wb, graph, groups)
    assert [i.id for i in again] == [i.id for i in issues]


# --- hardcoded_constant ---


def _hc(formula: str):
    # Host the formula far from the cells it references so the circular
    # detector stays quiet; only hardcoded_constant should fire here.
    wb = _wb({"S!AA100": _rec("S", "AA100", formula=formula)})
    return run_all(wb, build_graph(wb), [])


def test_hardcoded_flags_plain_literal():
    assert {(i.detector, i.ref.address) for i in _hc("=B4*1.15")} == {
        ("hardcoded_constant", "AA100")
    }


def test_hardcoded_allows_0_1_2_100():
    assert _hc("=A1*(1+2)+100*A2+0") == []


def test_hardcoded_exclusions():
    assert _hc("=ROUND(A1*B2,2)") == []
    assert _hc("=ROUNDUP(A1,1.5)") == []
    assert _hc("=MATCH(A1,A1:A9,0)") == []
    assert _hc("=VLOOKUP(A1,X1:Z9,3,FALSE)") == []
    assert _hc("=HLOOKUP(A1,X1:Z2,2,TRUE)") == []
    assert _hc("=INDEX(A1:B9,2,1)") == []
    assert _hc("=IF(A1>0,1,0)") == []


def test_hardcoded_if_other_literals_still_flagged():
    assert len(_hc("=IF(A1,1.5,0)")) == 1
    assert len(_hc("=VLOOKUP(A1*1.5,X1:Z9,2,TRUE)")) == 1
    assert len(_hc("=MATCH(5,A1:A9,0)")) == 1  # lookup value is not excluded


# --- pattern_break ---


def _column_wb(values: dict[int, CellRecord]) -> ParsedWorkbook:
    cells = {f"S!A{r}": rec for r, rec in values.items()}
    return _wb(cells)


def test_pattern_break_sandwiched_constant():
    cells = {
        r: _rec("S", f"A{r}", formula="=B{r}*2", value=None)
        for r in (1, 2, 4, 5)
    }
    cells[3] = _rec("S", "A3", value=99.5, kind="input")
    issues = run_all(_column_wb(cells), build_graph(_column_wb(cells)), [])
    assert _key_set(issues) == {("pattern_break", "S", "A3")}


def test_pattern_break_sandwiched_formula():
    cells = {
        r: _rec("S", f"A{r}", formula="=B{r}*2", value=None)
        for r in (1, 2, 4, 5)
    }
    cells[3] = _rec("S", "A3", formula="=B3*1", value=None)
    issues = run_all(_column_wb(cells), build_graph(_column_wb(cells)), [])
    assert _key_set(issues) == {("pattern_break", "S", "A3")}


def test_pattern_break_ignores_ties_and_labels():
    cells = {
        1: _rec("S", "A1", formula="=B1*2"),
        2: _rec("S", "A2", formula="=B2*2"),
        3: _rec("S", "A3", value="note", kind="label"),
        4: _rec("S", "A4", formula="=B4*3"),
        5: _rec("S", "A5", formula="=B5*3"),
    }
    wb = _column_wb(cells)
    flagged = [i for i in pattern_break.run(wb, build_graph(wb), [])]
    assert flagged == []


# --- range_gap ---


def test_range_gap_flags_skipped_row():
    wb = _wb(
        {
            "S!B1": _rec("S", "B1", formula="=SUM(A1:A3)"),
            "S!A4": _rec("S", "A4", formula="=A3*2"),
        }
    )
    assert _key_set(run_all(wb, build_graph(wb), [])) == {("range_gap", "S", "B1")}


def test_range_gap_host_below_range_is_fine():
    wb = _wb({"S!A4": _rec("S", "A4", formula="=SUM(A1:A3)")})
    assert range_gap.run(wb, build_graph(wb), []) == []


def test_range_gap_ignores_non_target_functions():
    wb = _wb(
        {
            "S!B1": _rec("S", "B1", formula="=PRODUCT(A1:A3)"),
            "S!A4": _rec("S", "A4", value=5, kind="input"),
        }
    )
    assert range_gap.run(wb, build_graph(wb), []) == []


# --- orphan_input ---


def test_orphan_flags_labeled_unused_input():
    wb = _wb(
        {"S!B3": _rec("S", "B3", value=0.10, kind="input", label_left="Discount")}
    )
    assert _key_set(run_all(wb, build_graph(wb), [])) == {
        ("orphan_input", "S", "B3")
    }


def test_orphan_skips_referenced_unlabeled_and_series_holes():
    wb = _wb(
        {
            # referenced: kept
            "S!B1": _rec("S", "B1", value=1, kind="input", label_left="A"),
            "S!C1": _rec("S", "C1", formula="=B1*2"),
            # unlabeled: kept
            "S!B2": _rec("S", "B2", value=2, kind="input"),
            # hole inside a live series (B3/B5 referenced, B4 not): kept
            "S!B3": _rec("S", "B3", value=3, kind="input", label_left="x"),
            "S!B4": _rec("S", "B4", value=4, kind="input", label_left="x"),
            "S!B5": _rec("S", "B5", value=5, kind="input", label_left="x"),
            "S!C3": _rec("S", "C3", formula="=B3*2"),
            "S!C5": _rec("S", "C5", formula="=B5*2"),
            # bool constant: kept
            "S!B6": _rec("S", "B6", value=True, kind="input", label_left="flag"),
        }
    )
    assert orphan_input.run(wb, build_graph(wb), []) == []


# --- error_values ---


def test_error_values_from_cache():
    wb = _wb(
        {
            "S!A1": _rec("S", "A1", formula="=B1/0", value="#DIV/0!"),
            "S!A2": _rec("S", "A2", formula="=B2+1", value=3),
        },
        has_cached=True,
    )
    assert _key_set(error_values.run(wb, build_graph(wb), [])) == {
        ("error_values", "S", "A1")
    }


def test_error_values_ref_literal_without_cache():
    wb = _wb({"S!A1": _rec("S", "A1", formula="=SUM(#REF!)")})
    assert _key_set(error_values.run(wb, build_graph(wb), [])) == {
        ("error_values", "S", "A1")
    }


def test_error_values_silent_without_cache():
    wb = _wb({"S!A1": _rec("S", "A1", formula="=B1/0")})
    assert error_values.run(wb, build_graph(wb), []) == []


# --- circular ---


def test_circular_two_cycle_single_issue():
    wb = _wb(
        {
            "S!A1": _rec("S", "A1", formula="=A2+1"),
            "S!A2": _rec("S", "A2", formula="=A1*2"),
        }
    )
    issues = circular.run(wb, build_graph(wb), [])
    assert [(i.detector, i.ref.address) for i in issues] == [("circular", "A1")]


def test_circular_self_loop():
    wb = _wb({"S!A1": _rec("S", "A1", formula="=A1+1")})
    assert len(circular.run(wb, build_graph(wb), [])) == 1


def test_circular_acyclic_is_clean():
    wb = _wb(
        {
            "S!A1": _rec("S", "A1", formula="=A2+1"),
            "S!A2": _rec("S", "A2", value=5, kind="input"),
        }
    )
    assert circular.run(wb, build_graph(wb), []) == []


# --- unit_mismatch ---


def test_unit_mismatch_percent_over_one():
    wb = _wb(
        {"S!A1": _rec("S", "A1", value=25, kind="input", number_format="0%")},
        has_cached=True,
    )
    assert _key_set(unit_mismatch.run(wb, build_graph(wb), [])) == {
        ("unit_mismatch", "S", "A1")
    }


def test_unit_mismatch_fraction_and_plain_are_fine():
    wb = _wb(
        {
            "S!A1": _rec(
                "S", "A1", value=0.25, kind="input", number_format="0%"
            ),
            "S!A2": _rec("S", "A2", value=25, kind="input"),
        },
        has_cached=True,
    )
    assert unit_mismatch.run(wb, build_graph(wb), []) == []


def test_unit_mismatch_mixed_scales_in_column():
    wb = _wb(
        {
            "S!A1": _rec(
                "S", "A1", value=0.25, kind="input", number_format="0%"
            ),
            "S!A2": _rec(
                "S", "A2", value=25.0, kind="input", number_format="0%"
            ),
        },
        has_cached=True,
    )
    assert _key_set(unit_mismatch.run(wb, build_graph(wb), [])) == {
        ("unit_mismatch", "S", "A2")
    }
