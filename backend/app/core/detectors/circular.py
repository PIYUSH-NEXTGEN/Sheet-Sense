"""circular detector (Phase 2, severity high).

Reports strongly connected components with size > 1 and self-loops via
``nx.strongly_connected_components`` (never ``simple_cycles``, which blows up
on large graphs). One issue per cycle, anchored at the sorted-first member
so ids are stable.
"""

from __future__ import annotations

import networkx as nx

from ..models import FormulaGroup, Issue, ParsedWorkbook
from .base import base_evidence, make_issue, neighbor_formulas, register

NAME = "circular"
SEVERITY = "high"


def run(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list[FormulaGroup]
) -> list[Issue]:
    issues: list[Issue] = []
    for component in nx.strongly_connected_components(graph):
        members = sorted(component)
        if len(members) == 1 and not graph.has_edge(members[0], members[0]):
            continue
        anchor = members[0]
        sheet, _, address = anchor.rpartition("!")
        others = ", ".join(members[1:])
        if others:
            message = (
                f"Suspicious circular reference: {anchor} depends on itself "
                f"through {others}. Review the chain before trusting results."
            )
        else:
            message = (
                f"Suspicious circular reference: {anchor} refers to itself."
            )
        issues.append(
            make_issue(
                NAME,
                SEVERITY,
                sheet,
                address,
                message,
                base_evidence(
                    wb, anchor, members=neighbor_formulas(wb, members)
                ),
            )
        )
    return issues


register(NAME, SEVERITY, run)
