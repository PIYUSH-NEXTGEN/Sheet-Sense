"""error_values detector (Phase 2, severity high).

Flags formula cells whose cached value is an Excel error
(``#REF!``, ``#DIV/0!``, ``#N/A``, ``#NAME?``, ``#VALUE!``, ``#NUM!``,
``#NULL!``) and formulas containing the literal ``#REF!``. When the workbook
has no cached values (``has_cached_values`` is False, e.g. openpyxl-written
files), value checks are skipped gracefully — the parser-level
``cached_values_missing`` warning already covers it — but ``#REF!`` text in
formulas is still reported.
"""

from __future__ import annotations

import networkx as nx

from ..models import FormulaGroup, Issue, ParsedWorkbook
from .base import base_evidence, make_issue, neighbor_formulas, register

NAME = "error_values"
SEVERITY = "high"

ERRORS = frozenset(
    {"#REF!", "#DIV/0!", "#N/A", "#NAME?", "#VALUE!", "#NUM!", "#NULL!"}
)


def run(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list[FormulaGroup]
) -> list[Issue]:
    issues: list[Issue] = []
    for key in sorted(wb.cells):
        rec = wb.cells[key]
        if rec.kind != "formula" or not rec.formula:
            continue
        if "#REF!" in rec.formula.upper():
            issues.append(
                make_issue(
                    NAME,
                    SEVERITY,
                    rec.ref.sheet,
                    rec.ref.address,
                    f"Suspicious broken reference at {rec.ref.address}: the "
                    f"formula ({rec.formula}) contains #REF!.",
                    base_evidence(wb, key),
                )
            )
            continue
        if not wb.has_cached_values:
            continue
        if (
            isinstance(rec.value, str)
            and rec.value.strip().upper() in ERRORS
        ):
            issues.append(
                make_issue(
                    NAME,
                    SEVERITY,
                    rec.ref.sheet,
                    rec.ref.address,
                    f"Suspicious error value at {rec.ref.address}: cached "
                    f"result is {rec.value.strip()} for {rec.formula}.",
                    base_evidence(
                        wb, key, cached_value=rec.value,
                        neighbors=neighbor_formulas(wb, []),
                    ),
                )
            )
    return issues


register(NAME, SEVERITY, run)
