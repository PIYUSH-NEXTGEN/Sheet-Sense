"""Template explanations for trivial formula groups (no model call).

A group is templatable only when every label it needs exists; anything
else falls through to the model (``None``). Templates never touch the
network, the cache, or a client — deterministic text from code facts.
"""

from __future__ import annotations

import re
from typing import Any

from openpyxl.formula import Tokenizer

from ..models import FormulaGroup, ParsedWorkbook

_CELL_RE = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)(\d{1,7})$")
_AGGREGATES = {
    "SUM": ("Adds up", "Sum"),
    "AVERAGE": ("Averages", "Average"),
    "MIN": ("Takes the minimum of", "Minimum"),
    "MAX": ("Takes the maximum of", "Maximum"),
    "COUNT": ("Counts", "Count"),
}
_OPERATORS = {
    "+": ("Adds", "plus"),
    "-": ("Subtracts", "minus"),
    "*": ("Multiplies", "times"),
    "/": ("Divides", "divided by"),
}


def _split_sheet(token: str) -> tuple[str | None, str] | None:
    """Split ``Sheet!rest``; None for external/3-D refs (out of scope)."""
    if "!" not in token:
        return None, token
    if token.startswith("'"):
        idx = token.rfind("'!")
        if idx < 0:
            return None
        return token[1:idx].replace("''", "'"), token[idx + 2 :]
    sheet, _, rest = token.partition("!")
    if not rest or "[" in sheet or "]" in sheet or ":" in sheet:
        return None
    return sheet, rest


def _parse_cell(ref: str) -> tuple[str, int] | None:
    """Parse ``B2``/``$B$2`` into ``(letters, row)``; None if not a cell."""
    match = _CELL_RE.match(ref.strip())
    if not match:
        return None
    return match.group(2).upper(), int(match.group(4))


def label_of(wb: ParsedWorkbook, sheet: str, address: str) -> str:
    """Human label for a cell: header first, then row label, then its text."""
    rec = wb.cells.get(f"{sheet}!{address}")
    if rec is None:
        return ""
    if rec.label_above:
        return rec.label_above
    if rec.label_left:
        return rec.label_left
    if isinstance(rec.value, str) and rec.value.strip():
        return rec.value.strip()
    return ""


def _tokens(formula: str) -> list[Any] | None:
    try:
        return [t for t in Tokenizer(formula).items if t.value]
    except Exception:
        return None


def _aggregate(
    group: FormulaGroup, wb: ParsedWorkbook, func: str, token: str
) -> dict[str, str] | None:
    split = _split_sheet(token)
    if split is None:
        return None
    sheet, rest = split
    sheet = sheet or group.sheet
    first, sep, second = rest.partition(":")
    if not sep:
        return None
    start = _parse_cell(first)
    end = _parse_cell(second)
    if start is None or end is None or start[0] != end[0]:
        return None  # single-column blocks only
    col = start[0]
    rows = sorted([start[1], end[1]])
    column_label = label_of(wb, sheet, f"{col}{rows[0]}")
    if not column_label:
        return None
    verb, noun = _AGGREGATES[func]
    return {
        "summary": (
            f"{verb} {column_label} from rows {rows[0]} to {rows[1]} "
            f"of {sheet}."
        ),
        "plain_formula": f"{noun} of {column_label}",
    }


def render_group(
    group: FormulaGroup, wb: ParsedWorkbook
) -> dict[str, str] | None:
    """Return ``{"summary", "plain_formula"}`` or None (use the model)."""
    if not group.sample_formula or not group.sample_formula.startswith("="):
        return None
    tokens = _tokens(group.sample_formula)
    if not tokens:
        return None
    ranges = [t for t in tokens if t.type == "OPERAND" and t.subtype == "RANGE"]
    ops = [t for t in tokens if t.type.startswith("OPERATOR")]
    funcs = [t for t in tokens if t.type == "FUNC"]
    numbers = [
        t for t in tokens if t.type == "OPERAND" and t.subtype == "NUMBER"
    ]

    # Single aggregate over one range: =SUM(Sheet!B2:B21).
    if (
        len(tokens) == 3
        and len(funcs) == 2
        and len(ranges) == 1
        and not ops
        and not numbers
        and funcs[0].subtype == "OPEN"
        and funcs[1].subtype == "CLOSE"
    ):
        name = funcs[0].value[:-1].upper() if funcs[0].value.endswith("(") else ""
        if name in _AGGREGATES:
            return _aggregate(group, wb, name, ranges[0].value)

    # Plain link: =Sheet!A1 (one reference, no operators).
    if len(ranges) == 1 and not ops and not funcs and not numbers:
        split = _split_sheet(ranges[0].value)
        if split is None:
            return None
        sheet, rest = split
        sheet = sheet or group.sheet
        if ":" in rest or _parse_cell(rest) is None:
            return None
        label = label_of(wb, sheet, _parse_cell(rest)[0] + str(_parse_cell(rest)[1]))
        if not label:
            return None
        return {"summary": f"Pulls {label} from {sheet}.", "plain_formula": label}

    # One operator between exactly two labeled references. Note: the
    # Tokenizer leaves OPERATOR-INFIX with an empty subtype.
    if (
        len(tokens) == 3
        and len(ranges) == 2
        and len(ops) == 1
        and not funcs
        and not numbers
        and ops[0].type == "OPERATOR-INFIX"
        and ops[0].value in _OPERATORS
    ):
        parts = []
        for token in (ranges[0].value, ranges[1].value):
            split = _split_sheet(token)
            if split is None:
                return None
            sheet, rest = split
            sheet = sheet or group.sheet
            parsed = _parse_cell(rest)
            if parsed is None or ":" in rest:
                return None
            label = label_of(wb, sheet, parsed[0] + str(parsed[1]))
            if not label:
                return None
            parts.append(label)
        verb, _opword = _OPERATORS[ops[0].value]
        first, second = parts
        if ops[0].value == "+":
            summary = f"Adds {first} and {second}."
        elif ops[0].value == "-":
            summary = f"Subtracts {second} from {first}."
        elif ops[0].value == "*":
            summary = f"Multiplies {first} by {second}."
        else:
            summary = f"Divides {first} by {second}."
        return {"summary": summary, "plain_formula": f"{first} {_opword} {second}"}

    return None
