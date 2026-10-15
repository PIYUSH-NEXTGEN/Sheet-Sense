"""Detector registry and shared helpers (Phase 2).

Every detector is deterministic Python; issue messages come from code
templates, never from a model (golden rule 1). Every ``Issue.evidence``
includes the cell's formula, its normalized pattern, and the neighbor
formulas used for the comparison (spec section 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import networkx as nx
from openpyxl.formula import Tokenizer

from ..grouping.patterns import cell_key_for, parse_address, pattern_of
from ..models import FormulaGroup, Issue, ParsedWorkbook

IssueRun = Callable[
    [ParsedWorkbook, nx.DiGraph, list[FormulaGroup]], list[Issue]
]


class Detector(Protocol):
    name: str
    severity: str

    def run(
        self,
        wb: ParsedWorkbook,
        graph: nx.DiGraph,
        groups: list[FormulaGroup],
    ) -> list[Issue]: ...


@dataclass(frozen=True)
class _Entry:
    name: str
    severity: str
    run: IssueRun


REGISTRY: dict[str, _Entry] = {}


def register(name: str, severity: str, run: IssueRun) -> IssueRun:
    """Register a detector; the pipeline runs all registered ones."""
    REGISTRY[name] = _Entry(name=name, severity=severity, run=run)
    return run


def make_issue(
    detector: str,
    severity: str,
    sheet: str,
    address: str,
    message: str,
    evidence: dict | None = None,
) -> Issue:
    """Build an Issue with a stable ``detector:Sheet!A1`` id."""
    from ..models import CellRef

    return Issue(
        id=f"{detector}:{sheet}!{address}",
        detector=detector,
        severity=severity,  # type: ignore[arg-type]
        ref=CellRef(sheet=sheet, address=address),
        message=message,
        evidence=evidence or {},
    )


def base_evidence(
    wb: ParsedWorkbook, key: str, **extra: object
) -> dict[str, object]:
    """Evidence every issue carries: formula + normalized pattern + neighbors."""
    rec = wb.cells.get(key)
    evidence: dict[str, object] = {
        "ref": key,
        "formula": rec.formula if rec else None,
        "pattern": pattern_of(wb, key),
    }
    evidence.update(extra)
    return evidence


def neighbor_formulas(
    wb: ParsedWorkbook, keys: list[str]
) -> dict[str, str | None]:
    """Map cell keys to their formulas for evidence."""
    out: dict[str, str | None] = {}
    for key in keys:
        rec = wb.cells.get(key)
        out[key] = rec.formula if rec else None
    return out


@dataclass(frozen=True)
class TokenFrame:
    """One function-call (or plain-paren) level around a token."""

    name: str | None  # upper-cased function name; None for plain parens
    arg: int  # 1-based argument position within this level


def function_frames(formula: str) -> list[tuple[object, list[TokenFrame]]]:
    """Pair each token with the stack of enclosing function frames.

    ``SEP / ARG`` increments the current level's arg counter; closes pop.
    Returns ``(token, frames)`` with innermost frame last. Unparseable
    formulas yield no pairs.
    """
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        return []
    stack: list[TokenFrame] = []
    paired: list[tuple[object, list[TokenFrame]]] = []
    for tok in tokens:
        if tok.type == "FUNC" and tok.subtype == "OPEN":
            name = tok.value[:-1].upper() if tok.value.endswith("(") else tok.value.upper()
            stack.append(TokenFrame(name=name, arg=1))
            paired.append((tok, list(stack)))
        elif tok.type == "PAREN" and tok.subtype == "OPEN":
            stack.append(TokenFrame(name=None, arg=1))
            paired.append((tok, list(stack)))
        elif tok.type in ("FUNC", "PAREN") and tok.subtype == "CLOSE":
            paired.append((tok, list(stack)))
            if stack:
                stack.pop()
        elif tok.type == "SEP":
            paired.append((tok, list(stack)))
            if stack and tok.subtype == "ARG":
                top = stack[-1]
                # Frames are frozen: replace so earlier snapshots keep
                # the arg value that was current when they were taken.
                stack[-1] = TokenFrame(name=top.name, arg=top.arg + 1)
        else:
            paired.append((tok, list(stack)))
    return paired


def enclosing_named_frames(frames: list[TokenFrame]) -> list[TokenFrame]:
    """Innermost-first named (non-paren) frames."""
    return [f for f in reversed(frames) if f.name is not None]


def run_all(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list[FormulaGroup]
) -> list[Issue]:
    """Run every registered detector; deterministic sheet/row/col order."""
    found: list[Issue] = []
    seen: set[str] = set()
    for name in sorted(REGISTRY):
        for issue in REGISTRY[name].run(wb, graph, groups) or []:
            if issue.id in seen:
                continue
            seen.add(issue.id)
            found.append(issue)

    def _sort_key(issue: Issue) -> tuple[str, int, int, str]:
        parsed = parse_address(issue.ref.address)
        row, col = (parsed[1], parsed[0]) if parsed else (0, 0)
        return (issue.ref.sheet, row, col, issue.detector)

    return sorted(found, key=_sort_key)


def dependents_of(graph: nx.DiGraph, key: str) -> list[str]:
    """Direct dependents; [] when the cell is not in the graph."""
    if key not in graph:
        return []
    return sorted(graph.successors(key))


def key_at(sheet: str, col: int, row: int) -> str:
    """``Sheet!A1`` key for 1-based (col, row)."""
    return cell_key_for(sheet, col, row)
