"""Relative-formula normalization and grouping (Phase 2, spec section 5.1).

For each formula cell at host position (row r, col c), every reference is
converted to relative notation:

- relative ref at (r2, c2) -> ``R[r2-r]C[c2-c]``
- absolute parts (``$``) keep absolute coordinates, e.g. ``R5C2``
- sheet qualifiers are preserved (with their original quoting)
- both endpoints of a range are converted

Two cells share a pattern iff their normalized strings are equal. A
``FormulaGroup`` is formed from each contiguous run (same column, or same
row) of cells with the same pattern; single-cell formulas become their own
group of size 1. Group IDs are stable: sha256 of sheet + pattern + first
address.

Notes / interpretations:
- Unparseable references (defined names, whole-column refs, external/3-D
  refs) are kept verbatim, so only textually identical ones merge. This is
  conservative: it may split groups, never wrongly merge them.
- Vertical runs take priority: every cell first joins a same-column run;
  leftover single cells may then join a same-row run.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from openpyxl.formula import Tokenizer

from ..models import FormulaGroup, ParsedWorkbook
from ..parser.refs import cell_key, extract_refs

_CELL_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")
_ADDR_SPLIT_RE = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)(\d{1,7})$")

MAX_COL = 16384
MAX_ROW = 1048576


def parse_address(address: str) -> tuple[int, int] | None:
    """Parse ``B2``/``$B$2`` into ``(col, row)``; None when not a cell."""
    m = _CELL_RE.match(address.strip())
    if not m:
        return None
    col = 0
    for ch in m.group(1).upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    row = int(m.group(2))
    if not (1 <= col <= MAX_COL and 1 <= row <= MAX_ROW):
        return None
    return col, row


def make_address(col: int, row: int) -> str:
    """Inverse of :func:`parse_address` (1-based)."""
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(rem + ord("A")) + letters
    return f"{letters}{row}"


def _split_prefix(token: str) -> tuple[str, str] | None:
    """Split ``Sheet!rest`` into ``(prefix, rest)`` (prefix keeps the ``!``).

    Returns ``("", token)`` for local refs and None for external/3-D refs.
    """
    if "!" not in token:
        return "", token
    if token.startswith("'"):
        idx = token.rfind("'!")
        if idx < 0:
            return None
        return token[: idx + 2], token[idx + 2 :]
    prefix, _, rest = token.partition("!")
    if not rest or "[" in prefix or "]" in prefix or ":" in prefix:
        return None
    return prefix + "!", rest


def _normalize_endpoint(ref: str, host_row: int, host_col: int) -> str | None:
    """Normalize one cell ref; None when it is not a plain cell address."""
    m = _ADDR_SPLIT_RE.match(ref.strip())
    if not m:
        return None
    col_dollar, col_letters, row_dollar, row_digits = m.groups()
    col = row = 0
    for ch in col_letters.upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    row = int(row_digits)
    if not (1 <= col <= MAX_COL and 1 <= row <= MAX_ROW):
        return None
    row_part = f"R{row}" if row_dollar else f"R[{row - host_row}]"
    col_part = f"C{col}" if col_dollar else f"C[{col - host_col}]"
    return f"{row_part}{col_part}"


def _normalize_token(token: str, host_row: int, host_col: int) -> str:
    """Normalize one RANGE token; verbatim when not a plain ref/range."""
    split = _split_prefix(token)
    if split is None:
        return token
    prefix, rest = split
    if ":" in rest:
        first, _, second = rest.partition(":")
        n1 = _normalize_endpoint(first, host_row, host_col)
        # A second endpoint never carries its own sheet in valid input; if it
        # looks qualified, bail out to verbatim (conservative, no merge).
        n2 = _normalize_endpoint(second, host_row, host_col)
        if n1 is None or n2 is None or "!" in second:
            return token
        return f"{prefix}{n1}:{n2}"
    single = _normalize_endpoint(rest, host_row, host_col)
    if single is None:
        return token  # defined name or whole-column ref: keep verbatim
    return f"{prefix}{single}"


def normalize_formula(formula: str, host_row: int, host_col: int) -> str:
    """Return the relative-notation pattern for one formula cell.

    Non-reference tokens (functions, operators, literals, strings) pass
    through untouched. Unparseable formulas return their own text, so they
    form single-cell groups instead of crashing.
    """
    if not formula or not formula.startswith("="):
        return formula or ""
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        return formula
    # The Tokenizer consumes the leading "="; restore it so patterns still
    # read as formulas.
    return "=" + "".join(
        _normalize_token(tok.value, host_row, host_col)
        if tok.type == "OPERAND" and tok.subtype == "RANGE"
        else tok.value
        for tok in tokens
        if tok.value
    )


@dataclass
class _CellPattern:
    key: str
    address: str
    row: int
    col: int
    pattern: str
    formula: str


def _collect_patterns(wb: ParsedWorkbook) -> dict[str, list[_CellPattern]]:
    """Map sheet -> formula cells with their normalized patterns."""
    by_sheet: dict[str, list[_CellPattern]] = {}
    for key, rec in wb.cells.items():
        if rec.kind != "formula" or not rec.formula:
            continue
        parsed = parse_address(rec.ref.address)
        if parsed is None:
            continue
        col, row = parsed
        by_sheet.setdefault(rec.ref.sheet, []).append(
            _CellPattern(
                key=key,
                address=rec.ref.address,
                row=row,
                col=col,
                pattern=normalize_formula(rec.formula, row, col),
                formula=rec.formula,
            )
        )
    return by_sheet


def group_id(sheet: str, pattern: str, first_address: str) -> str:
    """Stable group ID: sha256 of sheet + pattern + first address."""
    digest = hashlib.sha256(
        f"{sheet}\x00{pattern}\x00{first_address}".encode("utf-8")
    ).hexdigest()
    return digest[:16]


def group_formulas(wb: ParsedWorkbook) -> list[FormulaGroup]:
    """Partition formula cells into contiguous same-pattern runs."""
    groups: list[FormulaGroup] = []
    by_sheet = _collect_patterns(wb)
    for sheet in sorted(by_sheet.keys()):
        members = by_sheet[sheet]
        assigned: set[str] = set()

        def emit(run: list[_CellPattern]) -> None:
            first = run[0]
            sample = wb.cells[first.key]
            labels: dict[str, str] = {}
            if sample.label_above:
                labels["header"] = sample.label_above
            for ref in extract_refs(sample.formula, sheet, wb.defined_names):
                target = wb.cells.get(ref)
                if target is None:
                    continue
                tag = target.label_left or target.label_above
                if tag:
                    labels[ref] = tag
            groups.append(
                FormulaGroup(
                    id=group_id(sheet, first.pattern, first.address),
                    sheet=sheet,
                    pattern_r1c1=first.pattern,
                    cells=[m.address for m in run],
                    sample_formula=first.formula,
                    labels=labels,
                    sample_values=[
                        wb.cells[m.key].value for m in run[:3]
                    ],
                )
            )
            assigned.update(m.key for m in run)

        # Vertical runs first: same column + same pattern, consecutive rows.
        by_col: dict[tuple[int, str], list[_CellPattern]] = {}
        for m in members:
            by_col.setdefault((m.col, m.pattern), []).append(m)
        vertical_runs: list[list[_CellPattern]] = []
        for members_in_col in by_col.values():
            ordered = sorted(members_in_col, key=lambda m: m.row)
            run = [ordered[0]]
            for prev, cur in zip(ordered, ordered[1:]):
                if cur.row == prev.row + 1:
                    run.append(cur)
                else:
                    vertical_runs.append(run)
                    run = [cur]
            vertical_runs.append(run)
        for run in sorted(vertical_runs, key=lambda r: (r[0].col, r[0].row)):
            if len(run) > 1:
                emit(run)

        # Leftover singles: horizontal runs in the same row.
        leftover = sorted(
            (m for m in members if m.key not in assigned),
            key=lambda m: (m.row, m.col),
        )
        by_row: dict[tuple[int, str], list[_CellPattern]] = {}
        for m in leftover:
            by_row.setdefault((m.row, m.pattern), []).append(m)
        horizontal: list[list[_CellPattern]] = []
        for members_in_row in by_row.values():
            ordered = sorted(members_in_row, key=lambda m: m.col)
            run = [ordered[0]]
            for prev, cur in zip(ordered, ordered[1:]):
                if cur.col == prev.col + 1:
                    run.append(cur)
                else:
                    horizontal.append(run)
                    run = [cur]
            horizontal.append(run)
        for run in sorted(horizontal, key=lambda r: (r[0].row, r[0].col)):
            emit(run)

    def _group_sort_key(g: FormulaGroup) -> tuple[str, int, int]:
        parsed = parse_address(g.cells[0]) if g.cells else None
        row, col = (parsed[1], parsed[0]) if parsed else (0, 0)
        return (g.sheet, row, col)

    groups.sort(key=_group_sort_key)
    return groups


def pattern_of(wb: ParsedWorkbook, key: str) -> str | None:
    """Normalized pattern for one cell key; None for non-formula cells."""
    rec = wb.cells.get(key)
    if rec is None or rec.kind != "formula" or not rec.formula:
        return None
    parsed = parse_address(rec.ref.address)
    if parsed is None:
        return None
    col, row = parsed
    return normalize_formula(rec.formula, row, col)


def cell_key_for(sheet: str, col: int, row: int) -> str:
    """``Sheet!A1`` key for 1-based (col, row)."""
    return cell_key(sheet, make_address(col, row))
