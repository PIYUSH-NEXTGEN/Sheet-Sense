"""Analysis pipeline (Phases 3+4, spec sections 4 and 7).

Runs the deterministic stages in order — parse, references, graph, label,
group, detect — then the Gemma explainer (groups → sheets → workbook, cached
in SQLite), then persist. After each stage a progress event
``{stage, percent, detail}`` is emitted through the ``emit`` callback
(consumed by SSE in ``api/analysis.py``).

The explainer never decides facts; every item that the model cannot answer
gets a placeholder ("Explanation unavailable") and the pipeline continues.
Pass ``make_client`` in tests to inject a fake; by default a real
``OllamaClient`` is built when ``MODEL_NAME`` is configured, else every
explanation is a placeholder (and cache hits are still served).

Note: ``reader.read_workbook`` already attaches labels, so the label stage
reports the counts it produced rather than recomputing them.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import networkx as nx

from .. import config as app_config
from .detectors import run_all
from .graph.builder import build_graph
from .grouping.patterns import group_formulas, parse_address
from .llm.client import LLMClient, OllamaClient
from .llm.explainer import explain_groups, explain_sheets, explain_workbook
from .models import Explanation, FormulaGroup, Issue, ParsedWorkbook
from .parser.reader import read_workbook
from .parser.refs import extract_refs

Emit = Callable[[str, int, str], None]
MakeClient = Callable[[], LLMClient | None]


def default_client_factory() -> LLMClient | None:
    """Build the real client, or None when no model is configured."""
    if not app_config.MODEL_NAME:
        return None
    return OllamaClient()


def _count_refs(wb: ParsedWorkbook) -> int:
    total = 0
    for rec in wb.cells.values():
        if rec.kind == "formula" and rec.formula:
            total += len(extract_refs(rec.formula, rec.ref.sheet, wb.defined_names))
    return total


def _count_labeled(wb: ParsedWorkbook) -> int:
    return sum(
        1
        for rec in wb.cells.values()
        if rec.label_left or rec.label_above
    )


def _jsonable(value: Any) -> Any:
    """Make cached values JSON-safe (datetimes → ISO strings)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _sheet_stats(graph: nx.DiGraph) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for _node, data in graph.nodes(data=True):
        sheet = data.get("sheet", "?")
        info = stats.setdefault(sheet, {"n_inputs": 0, "n_outputs": 0})
        if data.get("kind") == "input":
            info["n_inputs"] += 1
        elif data.get("kind") == "output":
            info["n_outputs"] += 1
    return stats


def _sheet_edges(graph: nx.DiGraph) -> list[list[str]]:
    edges: set[tuple[str, str]] = set()
    for source, target in graph.edges:
        s_sheet = graph.nodes[source].get("sheet", "?")
        t_sheet = graph.nodes[target].get("sheet", "?")
        if s_sheet != t_sheet:
            edges.add((s_sheet, t_sheet))
    return [[s, t] for s, t in sorted(edges)]


def run_analysis(
    workbook_id: str,
    stored_path: str,
    filename: str,
    emit: Emit,
    make_client: MakeClient | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Run all stages; returns a JSON-serializable result payload.

    Raises the underlying error (e.g. ``ValueError`` from the reader for
    oversized/macro workbooks) so the caller can mark the analysis failed.
    Model failures never raise: they become placeholder explanations.
    """
    emit("parse", 10, f"reading {filename}")
    wb = read_workbook(stored_path)

    emit("references", 25, "extracting formula references")
    n_refs = _count_refs(wb)
    emit("references", 25, f"{n_refs} references extracted")

    emit("graph", 40, "building dependency graph")
    graph = build_graph(wb)

    emit("label", 52, f"{_count_labeled(wb)} cells labeled")

    emit("group", 65, "grouping repeated formulas")
    groups = group_formulas(wb)

    emit("detect", 78, "running detectors")
    issues = run_all(wb, graph, groups)

    emit("explain", 88, "explaining groups, sheets and workbook")
    factory = make_client or default_client_factory
    client = factory()
    sheet_names = sorted({rec.ref.sheet for rec in wb.cells.values()})
    group_expls = explain_groups(groups, wb, client)
    sheet_expls = explain_sheets(
        sheet_names, groups, group_expls, _sheet_stats(graph), client
    )
    workbook_expl = explain_workbook(
        sheet_names, sheet_expls, _sheet_edges(graph), client
    )
    emit("explain", 92, "explanations ready")
    explanations = {
        "workbook": workbook_expl.model_dump(),
        "sheets": {
            name: sheet_expls[name].model_dump() for name in sheet_names
        },
        "groups": {group.id: group_expls[group.id].model_dump() for group in groups},
    }

    n_formula = sum(1 for r in wb.cells.values() if r.kind == "formula")
    n_input = sum(1 for r in wb.cells.values() if r.kind == "input")
    n_output = sum(
        1 for _, data in graph.nodes(data=True) if data.get("kind") == "output"
    )
    by_severity: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for issue in issues:
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1

    result = {
        "workbook_id": workbook_id,
        "filename": filename,
        "warnings": list(wb.warnings) + list(extra_warnings or []),
        "stats": {
            "sheets": sheet_names,
            "n_cells": len(wb.cells),
            "n_formulas": n_formula,
            "n_inputs": n_input,
            "n_outputs": n_output,
            "n_groups": len(groups),
            "issues_by_severity": by_severity,
        },
        "groups": [
            {**group.model_dump(), "sample_values": [_jsonable(v) for v in group.sample_values]}
            for group in groups
        ],
        "inputs": sorted(
            (
                {
                    "sheet": rec.ref.sheet,
                    "address": rec.ref.address,
                    "label_left": rec.label_left,
                    "label_above": rec.label_above,
                    "value": _jsonable(rec.value),
                    "number_format": rec.number_format,
                }
                for rec in wb.cells.values()
                if rec.kind == "input"
            ),
            key=lambda item: (
                item["sheet"],
                (parse_address(item["address"]) or (0, 0))[1],
                (parse_address(item["address"]) or (0, 0))[0],
            ),
        ),
        "issues": [issue.model_dump() for issue in issues],
        "explanations": explanations,
    }
    emit("persist", 100, "analysis complete")
    return result


__all__ = [
    "Emit",
    "MakeClient",
    "default_client_factory",
    "run_analysis",
]
