"""orphan_input detector (Phase 2, severity low).

Flags a constant numeric input cell (int/float, not bool/date) that has a
label, has no dependents, and is not part of a live data column.

Interpretation of "not part of a data column where other cells in that
column are referenced": a cell is treated as part of a live series — and
skipped — only when **both** immediate vertical neighbors (same sheet, rows
r-1 and r+1) are themselves referenced numeric inputs. A hole inside a live
series is not an orphan; an unused setting next to other settings still is.
"""

from __future__ import annotations

import networkx as nx

from ..models import FormulaGroup, Issue, ParsedWorkbook
from ..grouping.patterns import parse_address
from .base import base_evidence, dependents_of, key_at, make_issue, register

NAME = "orphan_input"
SEVERITY = "low"


def _is_numeric_input(wb: ParsedWorkbook, key: str) -> bool:
    rec = wb.cells.get(key)
    return (
        rec is not None
        and rec.kind == "input"
        and isinstance(rec.value, (int, float))
        and not isinstance(rec.value, bool)
    )


def run(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list[FormulaGroup]
) -> list[Issue]:
    issues: list[Issue] = []
    for key in sorted(wb.cells):
        rec = wb.cells[key]
        if not _is_numeric_input(wb, key):
            continue
        if not (rec.label_left or rec.label_above):
            continue
        if dependents_of(graph, key):
            continue
        parsed = parse_address(rec.ref.address)
        if parsed is None:
            continue
        col, row = parsed
        above = key_at(rec.ref.sheet, col, row - 1) if row > 1 else ""
        below = key_at(rec.ref.sheet, col, row + 1)
        if (
            above
            and _is_numeric_input(wb, above)
            and dependents_of(graph, above)
            and _is_numeric_input(wb, below)
            and dependents_of(graph, below)
        ):
            continue  # hole inside a live data series, not an orphan
        label = rec.label_left or rec.label_above
        issues.append(
            make_issue(
                NAME,
                SEVERITY,
                rec.ref.sheet,
                rec.ref.address,
                f"Suspicious unused input at {rec.ref.address} ({label!r} = "
                f"{rec.value}): nothing references it. Check whether it "
                "should be wired into a formula or removed.",
                base_evidence(wb, key, label=label, value=rec.value),
            )
        )
    return issues


register(NAME, SEVERITY, run)
