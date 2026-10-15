"""range_gap detector (Phase 2, severity high).

Flags ``SUM``/``AVERAGE``/``MIN``/``MAX``/``COUNT`` calls whose range ends
while the cell immediately after the range end (same column for a vertical
range, same row for a horizontal one) still holds a numeric value or a
formula result that looks like part of the same data block. The host cell
itself is excluded (a total directly below its range is normal).

Only single-column / single-row ranges are considered; 2-D blocks and
whole-column refs are skipped. A formula candidate counts as a "result"
regardless of cached values, since the tool must work without them.
"""

from __future__ import annotations

import networkx as nx

from ..models import FormulaGroup, Issue, ParsedWorkbook
from ..grouping.patterns import MAX_COL, MAX_ROW, parse_address
from .base import (
    base_evidence,
    enclosing_named_frames,
    function_frames,
    key_at,
    make_issue,
    neighbor_formulas,
    register,
)

NAME = "range_gap"
SEVERITY = "high"

TARGETS = frozenset({"SUM", "AVERAGE", "MIN", "MAX", "COUNT"})


def _range_endpoints(token_value: str) -> tuple[str, str] | None:
    """Split a range token into endpoints, dropping sheet/external prefixes."""
    text = token_value
    if text.startswith("'"):
        idx = text.rfind("'!")
        if idx < 0:
            return None
        text = text[idx + 2 :]
    else:
        _, _, rest = text.partition("!")
        text = rest if rest else text
        if "[" in text.split(":")[0]:
            return None
    first, sep, second = text.partition(":")
    if not sep or not first.strip() or not second.strip():
        return None
    if "!" in second:  # qualified second endpoint: out of scope
        return None
    return first.strip(), second.strip()


def _candidate_after(
    sheet: str, first: str, second: str
) -> tuple[str, str] | None:
    """Cell key + range text immediately after the range end, if 1-D."""
    start = parse_address(first)
    end = parse_address(second)
    if start is None or end is None:
        return None
    (c1, r1), (c2, r2) = start, end
    lo_c, hi_c = min(c1, c2), max(c1, c2)
    lo_r, hi_r = min(r1, r2), max(r1, r2)
    if lo_c == hi_c and lo_r != hi_r:  # vertical range
        if hi_r + 1 > MAX_ROW:
            return None
        return key_at(sheet, lo_c, hi_r + 1), f"{first}:{second}"
    if lo_r == hi_r and lo_c != hi_c:  # horizontal range
        if hi_c + 1 > MAX_COL:
            return None
        return key_at(sheet, hi_c + 1, lo_r), f"{first}:{second}"
    return None  # single cell or 2-D block


def run(
    wb: ParsedWorkbook, graph: nx.DiGraph, groups: list[FormulaGroup]
) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    for key in sorted(wb.cells):
        rec = wb.cells[key]
        if rec.kind != "formula" or not rec.formula:
            continue
        for tok, frames in function_frames(rec.formula):
            if tok.type != "OPERAND" or tok.subtype != "RANGE":
                continue
            if ":" not in (tok.value or ""):
                continue
            named = enclosing_named_frames(frames)
            if not named or named[0].name not in TARGETS:
                continue  # only direct args of SUM/AVERAGE/MIN/MAX/COUNT
            sheet = rec.ref.sheet
            raw = tok.value
            if raw.startswith("'"):
                idx = raw.rfind("'!")
                sheet = raw[1:idx].replace("''", "'") if idx > 0 else sheet
            elif "!" in raw and not raw.startswith("="):
                maybe_sheet, _, _ = raw.partition("!")
                if maybe_sheet and "[" not in maybe_sheet and ":" not in maybe_sheet:
                    sheet = maybe_sheet
            endpoints = _range_endpoints(raw)
            if endpoints is None:
                continue
            found = _candidate_after(sheet, *endpoints)
            if found is None:
                continue
            candidate, _ = found
            if candidate == key:
                continue  # host cell itself: a total below its range is fine
            target = wb.cells.get(candidate)
            if target is None:
                continue
            looks_like_data = target.kind == "formula" or (
                target.kind == "input"
                and isinstance(target.value, (int, float))
                and not isinstance(target.value, bool)
            )
            if not looks_like_data:
                continue
            issue_id = f"{NAME}:{key}"
            if issue_id in seen:
                continue
            seen.add(issue_id)
            issues.append(
                make_issue(
                    NAME,
                    SEVERITY,
                    rec.ref.sheet,
                    rec.ref.address,
                    f"Suspicious range in {rec.ref.address} ({rec.formula}): "
                    f"{candidate} right after the range end looks like part of "
                    "the same data block and may have been left out.",
                    base_evidence(
                        wb,
                        key,
                        range=raw,
                        next_cell=neighbor_formulas(wb, [candidate]),
                    ),
                )
            )
    return issues


register(NAME, SEVERITY, run)
