"""Dependency graph builder (Phase 1).

Builds a ``networkx.DiGraph`` with edge direction precedent -> dependent.
Node attributes: ``sheet``, ``address``, ``kind``
(``input``/``formula``/``output``/``range``), ``formula``.

- ``input``: a constant (numeric, text, date, bool) referenced by something —
  including referenced-but-empty cells, which get a placeholder node — and
  unreferenced label/value cells kept for map completeness.
- ``formula``: a formula cell with at least one dependent.
- ``output``: a formula cell with no dependents.
- ``range``: a collapsed node for an oversized range (see ``refs``); its key
  is ``"Sheet!A1:B9999"`` (or ``"Sheet!A:A"`` for whole-column refs).
"""

from __future__ import annotations

import networkx as nx

from ..models import ParsedWorkbook
from ..parser.refs import extract_refs, is_range_key, split_key


def build_graph(wb: ParsedWorkbook) -> nx.DiGraph:
    """Build the precedent -> dependent graph for a parsed workbook."""
    graph: nx.DiGraph = nx.DiGraph()
    for key, rec in wb.cells.items():
        kind = "formula" if rec.formula else "input"
        graph.add_node(
            key,
            sheet=rec.ref.sheet,
            address=rec.ref.address,
            kind=kind,
            formula=rec.formula,
        )
    for key, rec in wb.cells.items():
        if not rec.formula:
            continue
        for dep in extract_refs(rec.formula, rec.ref.sheet, wb.defined_names):
            if dep not in graph:
                sheet, address = split_key(dep)
                graph.add_node(
                    dep,
                    sheet=sheet,
                    address=address,
                    kind="range" if is_range_key(dep) else "input",
                    formula=None,
                )
            graph.add_edge(dep, key)
    for node, data in graph.nodes(data=True):
        if data.get("kind") == "formula" and graph.out_degree(node) == 0:
            data["kind"] = "output"
    return graph
