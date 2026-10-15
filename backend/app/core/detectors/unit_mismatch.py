"""unit_mismatch detector (Phase 2, severity low).

Conservative percent-scale checks; low false-positive rate matters more than
recall, so cells without cached values are skipped silently:

- a percent-formatted cell holding a value > 1 (e.g. ``25`` formatted as
  ``25%`` instead of ``0.25``);
- a percent-formatted cell holding a whole number while the same column holds
  a percent-formatted value exactly 100x smaller (``0.25`` vs ``25``) — the
  whole-number side is flagged.
"""

from __future__ import annotations

import math

import networkx as nx

from ..models import FormulaGroup, Issue, ParsedWorkbook
from ..grouping.patterns import parse_address
from .base import base_evidence, make_issue, neighbor_formulas, register

NAME = "unit_mismatch"
SEVERITY = "low"


def _is_percent(number_format: str | None) -> bool:
    return bool(number_format) and "%" in number_format


def _numeric_value(wb: ParsedWorkbook, key: str) -> float | None:
    rec = wb.cells.get(key)
    if rec is None or isinstance(rec.value, bool):
        return None
    if isinstance(rec.value, (int, float)):
        return float(rec.value)
    return None


def run(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list[FormulaGroup]
) -> list[Issue]:
    issues: list[Issue] = []
    percent_cells: dict[tuple[str, int], list[tuple[int, str, float]]] = {}
    for key, rec in wb.cells.items():
        if not _is_percent(rec.number_format):
            continue
        value = _numeric_value(wb, key)
        if value is None:
            continue
        parsed = parse_address(rec.ref.address)
        if parsed is None:
            continue
        col, row = parsed
        percent_cells.setdefault((rec.ref.sheet, col), []).append(
            (row, key, value)
        )

    for (sheet, _col), members in percent_cells.items():
        small = [v for _, _, v in members if 0 < abs(v) < 1]
        for _, key, value in sorted(members):
            rec = wb.cells[key]
            if value > 1 and not any(
                math.isclose(value, s * 100, rel_tol=1e-9) for s in small
            ):
                issues.append(
                    make_issue(
                        NAME,
                        SEVERITY,
                        rec.ref.sheet,
                        rec.ref.address,
                        f"Suspicious percent scale at {rec.ref.address}: "
                        f"percent-formatted but holding {rec.value} (> 1) — "
                        "did you mean a fraction like "
                        f"{value / 100:g}?",
                        base_evidence(wb, key, value=rec.value),
                    )
                )
            elif value >= 1 and any(
                math.isclose(value, s * 100, rel_tol=1e-9) for s in small
            ):
                peers = sorted(k for _, k, _ in members if k != key)
                issues.append(
                    make_issue(
                        NAME,
                        SEVERITY,
                        rec.ref.sheet,
                        rec.ref.address,
                        f"Suspicious mixed percent scales in this column: "
                        f"{rec.ref.address} holds {rec.value} while a sibling "
                        "cell holds a value 100x smaller — one side is "
                        "likely off by 100x.",
                        base_evidence(
                            wb, key, value=rec.value,
                            neighbors=neighbor_formulas(wb, peers),
                        ),
                    )
                )
    return issues


register(NAME, SEVERITY, run)
