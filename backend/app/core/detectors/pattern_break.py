"""pattern_break detector (Phase 2, severity high).

Per column and per row: the dominant normalized pattern is the strictly most
frequent formula pattern (needs at least 2 cells; ties mean no dominant
pattern). A cell is flagged when both immediate neighbors (before and after
it in that column/row) carry the dominant pattern while it is itself a
different formula pattern or a hardcoded (numeric) constant. Text labels and
empty cells never flag.
"""

from __future__ import annotations

from collections import Counter

import networkx as nx

from ..models import FormulaGroup, Issue, ParsedWorkbook
from ..grouping.patterns import parse_address, pattern_of
from .base import base_evidence, make_issue, neighbor_formulas, register

NAME = "pattern_break"
SEVERITY = "high"


def _dominant(patterns: list[str | None]) -> str | None:
    counts = Counter(p for p in patterns if p is not None)
    if not counts:
        return None
    top = counts.most_common(2)
    if len(top) > 1 and top[0][1] == top[1][1]:
        return None  # tie: no dominant pattern
    if top[0][1] < 2:
        return None
    return top[0][0]


def _scan_line(
    wb: ParsedWorkbook, keys: list[str | None]
) -> list[tuple[str, list[str]]]:
    """Flag sandwiched cells in one ordered column/row line.

    ``keys`` parallels the line's cells (None for empty). Returns
    ``(flagged_key, [neighbor_keys])`` pairs.
    """
    pats = [pattern_of(wb, k) if k else None for k in keys]
    dom = _dominant(pats)
    if dom is None:
        return []
    hits: list[tuple[str, list[str]]] = []
    for i in range(1, len(keys) - 1):
        key = keys[i]
        if key is None or pats[i] == dom:
            continue
        before, after = keys[i - 1], keys[i + 1]
        if before is None or after is None:
            continue
        if pats[i - 1] != dom or pats[i + 1] != dom:
            continue
        rec = wb.cells.get(key)
        if rec is None:
            continue
        if rec.kind == "formula":
            hits.append((key, [before, after]))  # different formula pattern
        elif (
            rec.kind == "input"
            and isinstance(rec.value, (int, float))
            and not isinstance(rec.value, bool)
        ):
            hits.append((key, [before, after]))  # hardcoded constant
        # labels / empties: never flag
    return hits


def run(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list[FormulaGroup]
) -> list[Issue]:
    flagged: dict[str, list[str]] = {}
    sheets: dict[str, list[tuple[int, int, str]]] = {}
    for key, rec in wb.cells.items():
        parsed = parse_address(rec.ref.address)
        if parsed is None:
            continue
        col, row = parsed
        sheets.setdefault(rec.ref.sheet, []).append((col, row, key))

    for sheet, members in sheets.items():
        cols: dict[int, dict[int, str]] = {}
        rows: dict[int, dict[int, str]] = {}
        for col, row, key in members:
            cols.setdefault(col, {})[row] = key
            rows.setdefault(row, {})[col] = key
        for by_row in cols.values():
            lo, hi = min(by_row), max(by_row)
            line = [by_row.get(r) for r in range(lo, hi + 1)]
            for key, neighbors in _scan_line(wb, line):
                flagged.setdefault(key, []).extend(neighbors)
        for by_col in rows.values():
            lo, hi = min(by_col), max(by_col)
            line = [by_col.get(c) for c in range(lo, hi + 1)]
            for key, neighbors in _scan_line(wb, line):
                flagged.setdefault(key, []).extend(neighbors)

    issues: list[Issue] = []
    for key in sorted(flagged):
        rec = wb.cells[key]
        neighbors = sorted(set(flagged[key]))
        if rec.kind == "formula":
            detail = f"formula {rec.formula} differs from the column/row pattern"
        else:
            detail = f"constant {rec.value} sits inside a formula column/row"
        issues.append(
            make_issue(
                NAME,
                SEVERITY,
                rec.ref.sheet,
                rec.ref.address,
                f"Suspicious pattern break at {rec.ref.address}: {detail}; "
                "neighbors use the dominant pattern.",
                base_evidence(
                    wb, key, neighbors=neighbor_formulas(wb, neighbors)
                ),
            )
        )
    return issues


register(NAME, SEVERITY, run)
