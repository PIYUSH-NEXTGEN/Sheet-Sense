"""Reference extraction from Excel formulas (Phase 1).

Uses ``openpyxl.formula.Tokenizer`` and reads only operands of subtype
``RANGE``. Handles cross-sheet refs (``'My Sheet'!A1``), absolute refs
(``$A$1``), ranges (``A1:B10``), whole-column/whole-row refs (collapsed to a
single range node), and defined names (resolved via the workbook's defined
names). Ranges expanding to more than ``RANGE_EXPANSION_CAP`` cells collapse
to a single range node (spec section 4, stage 2).

Public API:
- ``extract_refs(formula, host_sheet, defined_names)`` -> dependency keys in
  first-seen order: ``"Sheet!A1"`` cell keys, or ``"Sheet!A1:B999"`` /
  ``"Sheet!A:A"`` range-node keys for oversized ranges.
- ``cell_key(sheet, address)`` / ``split_key(key)`` / ``is_range_key(key)``.
"""

from __future__ import annotations

import re
from typing import Iterable

from openpyxl.formula import Tokenizer

# Expansion cap from spec section 4 stage 2.
RANGE_EXPANSION_CAP = 5000

MAX_COL = 16384  # XFD
MAX_ROW = 1048576

_CELL_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")
_COL_RANGE_RE = re.compile(r"^\$?([A-Za-z]{1,3}):\$?([A-Za-z]{1,3})$")
_ROW_RANGE_RE = re.compile(r"^\$?(\d{1,7}):\$?(\d{1,7})$")

# Internal defined names (print areas/titles) are never dependencies of user
# formulas in v1.
_INTERNAL_NAME_PREFIX = "_xlnm."


def cell_key(sheet: str, address: str) -> str:
    """Canonical dict/graph key for one cell: ``"Sheet!A1"``."""
    return f"{sheet}!{address}"


def split_key(key: str) -> tuple[str, str]:
    """Split ``"Sheet!A1"`` (or a range-node key) into ``(sheet, address)``.

    Splits at the last ``!`` so raw sheet names containing ``!`` survive.
    """
    sheet, _, address = key.rpartition("!")
    if not _:
        raise ValueError(f"Invalid cell key: {key!r}")
    return sheet, address


def is_range_key(key: str) -> bool:
    """True for collapsed range-node keys (``"Sheet!A1:B9"``, ``"S!A:A"``)."""
    try:
        _, address = split_key(key)
    except ValueError:
        return False
    return ":" in address


def _col_to_index(col: str) -> int:
    index = 0
    for ch in col.upper():
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index


def _index_to_col(index: int) -> str:
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(rem + ord("A")) + letters
    return letters


def _split_sheet(token: str) -> tuple[str | None, str] | None:
    """Split ``Sheet!rest`` into ``(sheet, rest)``; ``(None, token)`` if local.

    Returns None for external (``[book]``) and 3-D (``S1:S2!``) references,
    which are out of scope in v1 — they are skipped, never crash.
    """
    if "!" not in token:
        return None, token
    if token.startswith("'"):
        idx = token.rfind("'!")
        if idx < 0:
            return None
        sheet = token[1:idx].replace("''", "'")
        rest = token[idx + 2 :]
    else:
        sheet, _, rest = token.partition("!")
    if not rest:
        return None
    if "[" in sheet or "]" in sheet:
        return None  # external workbook reference
    if ":" in sheet:
        return None  # 3-D reference Sheet1:Sheet2!A1
    return sheet, rest


def _parse_single(ref: str) -> tuple[int, int] | None:
    """Parse ``B2``/``$B$2`` into ``(col, row)``; None when not a cell."""
    m = _CELL_RE.match(ref.strip())
    if not m:
        return None
    col = _col_to_index(m.group(1))
    row = int(m.group(2))
    if not (1 <= col <= MAX_COL and 1 <= row <= MAX_ROW):
        return None
    return col, row


def _expand_cells(
    sheet: str, first: str, second: str
) -> tuple[list[str], str | None]:
    """Expand ``first:second`` into cell keys, or a single range-node key.

    Returns ``(cells, range_node)`` where exactly one side is populated:
    ranges of more than ``RANGE_EXPANSION_CAP`` cells (including whole-column
    and whole-row refs) collapse to one range-node key.
    """
    start = _parse_single(first)
    end = _parse_single(second)
    if start is None or end is None:
        # Whole-column (A:A) or whole-row (1:3) refs always collapse: they
        # would otherwise expand to ~1M cells.
        pair = f"{first.strip()}:{second.strip()}"
        if _COL_RANGE_RE.match(pair) or _ROW_RANGE_RE.match(pair):
            node = cell_key(sheet, pair.replace("$", ""))
            return [], node
        return [], ""  # unparseable endpoint: ignore (caller drops "")
    (c1, r1), (c2, r2) = start, end
    lo_c, hi_c = min(c1, c2), max(c1, c2)
    lo_r, hi_r = min(r1, r2), max(r1, r2)
    count = (hi_c - lo_c + 1) * (hi_r - lo_r + 1)
    if count > RANGE_EXPANSION_CAP:
        node = cell_key(
            sheet,
            f"{_index_to_col(lo_c)}{lo_r}:{_index_to_col(hi_c)}{hi_r}",
        )
        return [], node
    cells = [
        cell_key(sheet, f"{_index_to_col(c)}{r}")
        for c in range(lo_c, hi_c + 1)
        for r in range(lo_r, hi_r + 1)
    ]
    return cells, None


def _index_names(defined_names: dict[str, str] | None) -> dict[str, str]:
    """Lower-cased name -> target text, skipping internal ``_xlnm.*`` names."""
    index: dict[str, str] = {}
    for name, target in (defined_names or {}).items():
        if not name or name.lower().startswith(_INTERNAL_NAME_PREFIX):
            continue
        index.setdefault(name.lower(), target)
    return index


def _refs_from_text(
    text: str,
    host_sheet: str,
    names: dict[str, str],
    seen_names: frozenset[str],
    out: list[str],
) -> None:
    """Append dependency keys found in one formula/target string to ``out``."""
    try:
        tokens = Tokenizer(text).items
    except Exception:
        return  # unparseable formula: no refs, never crash
    for tok in tokens:
        if tok.type != "OPERAND" or tok.subtype != "RANGE":
            continue  # numbers, strings, errors (#REF!), logicals ignored
        raw = tok.value
        if not raw:
            continue
        parts = _split_sheet(raw)
        if parts is None:
            continue
        sheet, rest = parts
        sheet = host_sheet if sheet is None else sheet
        if ":" in rest:
            first, _, second = rest.partition(":")
            first, second = first.strip(), second.strip()
            if not first or not second:
                continue
            # An endpoint may itself carry a sheet (rare); inherit otherwise.
            sheet2 = sheet
            for ep in (first, second):
                sub = _split_sheet(ep)
                if sub is not None and sub[0] is not None:
                    sheet2 = sub[0]
            cells, node = _expand_cells(sheet2, first, second)
            out.extend(cells)
            if node:
                out.append(node)
            continue
        single = _parse_single(rest)
        if single is not None:
            col, row = single
            out.append(cell_key(sheet, f"{_index_to_col(col)}{row}"))
            continue
        # Not a cell address: maybe a defined name (optionally sheet-scoped).
        name = rest.strip()
        sub = _split_sheet(name)
        if sub is not None and sub[0] is not None:
            name = sub[1]
        target = names.get(name.lower())
        if target is None or name.lower() in seen_names:
            continue  # unknown name or cycle: ignore
        _refs_from_text(
            target if target.startswith("=") else "=" + target,
            sheet,
            names,
            seen_names | {name.lower()},
            out,
        )


def extract_refs(
    formula: str | None,
    host_sheet: str,
    defined_names: dict[str, str] | None = None,
) -> list[str]:
    """Return dependency keys for ``formula``, deduplicated in first-seen order."""
    if not formula or not formula.startswith("="):
        return []
    names = _index_names(defined_names)
    found: list[str] = []
    _refs_from_text(formula, host_sheet, names, frozenset(), found)
    # Drop the "" sentinel for ignored endpoints, dedupe preserving order.
    seen: set[str] = set()
    refs: list[str] = []
    for key in found:
        if not key or key in seen:
            continue
        seen.add(key)
        refs.append(key)
    return refs


def iter_range_cells(key: str) -> Iterable[str]:
    """Yield cell keys covered by a range-node key (bounded by the cap)."""
    sheet, address = split_key(key)
    first, _, second = address.partition(":")
    cells, _ = _expand_cells(sheet, first, second)
    return cells
