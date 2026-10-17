"""Analysis pipeline (Phases 3-5, spec sections 4 and 7).

Two phases: phase A runs the deterministic stages (parse → detect),
template explanations, and persists — afterwards the workbook is usable.
Phase B explains the remaining groups with the model, then sheets, then the
workbook overview. Phase B can fail or be interrupted without touching
phase A results. ``run_analysis`` runs both inline (kept for tests and
single-shot use); the API runs phase A, persists, then phase B.
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
from .llm.explainer import (
    explain_groups,
    explain_sheets,
    explain_workbook,
    placeholder,
)
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


def _stats_payload(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list, issues: list
) -> dict[str, Any]:
    n_output = sum(
        1 for _, data in graph.nodes(data=True) if data.get("kind") == "output"
    )
    by_severity: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for issue in issues:
        by_severity[issue.severity] = by_severity.get(issue.severity, 0) + 1
    return {
        "sheets": sorted({rec.ref.sheet for rec in wb.cells.values()}),
        "n_cells": len(wb.cells),
        "n_formulas": sum(1 for r in wb.cells.values() if r.kind == "formula"),
        "n_inputs": sum(1 for r in wb.cells.values() if r.kind == "input"),
        "n_outputs": n_output,
        "n_groups": len(groups),
        "issues_by_severity": by_severity,
    }


def run_phase_a(
    workbook_id: str,
    stored_path: str,
    filename: str,
    emit: Emit,
    extra_warnings: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Deterministic facts + templates. Returns (result, context for B).

    Never touches the model. Raises on parse errors like before.
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

    emit("explain", 88, "describing trivial groups")
    group_expls = explain_groups(groups, wb, None)
    pending = [
        gid for gid, expl in group_expls.items() if expl.source != "template"
    ]
    sheet_names = sorted({rec.ref.sheet for rec in wb.cells.values()})
    explanations = {
        "workbook": placeholder("workbook", workbook_id, "").model_dump(),
        "sheets": {
            name: placeholder("sheet", name, "").model_dump()
            for name in sheet_names
        },
        "groups": {gid: expl.model_dump() for gid, expl in group_expls.items()},
    }
    total = len(pending) + len(sheet_names) + 1

    result = {
        "workbook_id": workbook_id,
        "filename": filename,
        "warnings": list(wb.warnings) + list(extra_warnings or []),
        "stats": _stats_payload(wb, graph, groups, issues),
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
        "pending_groups": pending,
        "explanation_total": total,
    }
    emit("persist", 100, "facts ready")
    context = {
        "wb": wb,
        "graph": graph,
        "groups": groups,
        "sheet_names": sheet_names,
        "result": result,
    }
    return result, context


def run_phase_b(
    context: dict[str, Any],
    emit: Emit,
    make_client: MakeClient | None = None,
) -> dict[str, Any]:
    """Model explanations for everything phase A left pending.

    Never raises: every failure degrades to placeholders, and phase A
    results (issues, graph, formulas, templates) are never touched.
    Returns the updated result payload.
    """
    from .llm.explainer import (
        explain_groups,
        explain_sheets,
        explain_workbook,
        placeholder,
    )

    wb = context["wb"]
    graph = context["graph"]
    groups: list = context["groups"]
    sheet_names: list[str] = context["sheet_names"]
    result = context["result"]
    factory = make_client or default_client_factory
    try:
        client = factory()
    except Exception:
        client = None
    try:
        total = int(result.get("explanation_total", 0)) or 1
        done = total - len(result.get("pending_groups", []))
        emit("explaining", round(100 * done / total), f"{done} of {total}")

        group_expls = explain_groups(groups, wb, client)
        pending_now = [
            gid
            for gid, expl in group_expls.items()
            if expl.source != "template"
            and expl.text == placeholder("group", gid, "").text
            and gid in result.get("pending_groups", [])
        ]
        # Groups resolved this phase (templated earlier or explained now).
        done = total - len(pending_now) - len(sheet_names) - 1
        emit("explaining", round(100 * done / total), f"{done} of {total}")

        result["explanations"]["groups"] = {
            gid: expl.model_dump() for gid, expl in group_expls.items()
        }
        result["pending_groups"] = pending_now

        sheet_expls = explain_sheets(
            sheet_names, groups, group_expls, _sheet_stats(graph), client
        )
        done += len(sheet_names)
        emit("explaining", round(100 * done / total), f"{done} of {total}")
        result["explanations"]["sheets"] = {
            name: sheet_expls[name].model_dump() for name in sheet_names
        }

        workbook_expl = explain_workbook(
            sheet_names, sheet_expls, _sheet_edges(graph), client
        )
        done += 1
        emit("explaining", round(100 * done / total), f"{done} of {total}")
        result["explanations"]["workbook"] = workbook_expl.model_dump()
    except Exception:
        # Phase A results stand untouched; placeholders remain where the
        # model could not answer.
        pass
    emit("persist", 100, "analysis complete")
    return result


def run_analysis(
    workbook_id: str,
    stored_path: str,
    filename: str,
    emit: Emit,
    make_client: MakeClient | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Run phase A then phase B inline; returns the full result payload.

    Kept for tests and single-shot use. Raises on parse errors like before;
    model failures become placeholders, never exceptions.
    """
    result, context = run_phase_a(
        workbook_id, stored_path, filename, emit, extra_warnings
    )
    return run_phase_b(context, emit, make_client)


__all__ = [
    "Emit",
    "MakeClient",
    "default_client_factory",
    "run_analysis",
    "run_phase_a",
    "run_phase_b",
]
