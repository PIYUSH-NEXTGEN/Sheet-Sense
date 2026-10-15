"""hardcoded_constant detector (Phase 2, severity medium).

Flags a formula containing a numeric literal outside the allow-list
(default ``{0, 1, 2, 100}``). Ignored positions (spec section 6):

- 2nd arg of ``ROUND``/``ROUNDUP``/``ROUNDDOWN``
- match-type arg (3rd) of ``MATCH``
- column-index (3rd) / range_lookup (4th) args of ``VLOOKUP``/``HLOOKUP``
- row (2nd) / col (3rd) args of ``INDEX``
- ``IF`` branch results (2nd/3rd args) of exactly 0/1

The exclusion applies at every enclosing function level (a literal nested
inside an excluded slot is also excluded): false positives are worse than
misses. A trailing ``%`` postfix does not exempt the literal.
"""

from __future__ import annotations

import networkx as nx

from ..models import FormulaGroup, Issue, ParsedWorkbook
from .base import base_evidence, enclosing_named_frames, function_frames, make_issue, register

NAME = "hardcoded_constant"
SEVERITY = "medium"

ALLOW_LIST = frozenset({0.0, 1.0, 2.0, 100.0})

_ROUND = frozenset({"ROUND", "ROUNDUP", "ROUNDDOWN"})
_LOOKUP = frozenset({"VLOOKUP", "HLOOKUP"})


def _excluded(name: str, arg: int, value: float) -> bool:
    if name in _ROUND and arg == 2:
        return True
    if name == "MATCH" and arg == 3:
        return True
    if name in _LOOKUP and arg in (3, 4):
        return True
    if name == "INDEX" and arg in (2, 3):
        return True
    if name == "IF" and arg in (2, 3) and value in (0.0, 1.0):
        return True
    return False


def _literals(formula: str) -> list[float]:
    """Non-allowed numeric literals with no excluded function context."""
    hits: list[float] = []
    for tok, frames in function_frames(formula):
        if tok.type != "OPERAND" or tok.subtype != "NUMBER":
            continue
        try:
            value = float(tok.value)
        except (TypeError, ValueError):
            continue
        if value in ALLOW_LIST:
            continue
        if any(
            _excluded(frame.name, frame.arg, value)
            for frame in enclosing_named_frames(frames)
        ):
            continue
        hits.append(value)
    return hits


def run(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list[FormulaGroup]
) -> list[Issue]:
    issues: list[Issue] = []
    for key in sorted(wb.cells):
        rec = wb.cells[key]
        if rec.kind != "formula" or not rec.formula:
            continue
        for value in _literals(rec.formula):
            number = int(value) if value.is_integer() else value
            issues.append(
                make_issue(
                    NAME,
                    SEVERITY,
                    rec.ref.sheet,
                    rec.ref.address,
                    f"Suspicious hardcoded number {number} in {rec.ref.address} "
                    f"({rec.formula}). Consider moving it to a labeled input cell.",
                    base_evidence(wb, key, literal=number),
                )
            )
            break  # one issue per cell, even with several literals
    return issues


register(NAME, SEVERITY, run)
