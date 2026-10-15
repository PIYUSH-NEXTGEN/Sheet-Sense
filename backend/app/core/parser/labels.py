"""Human-facing labels for cells (Phase 1).

Attaches ``label_left`` (nearest text cell to the left in the same row) and
``label_above`` (nearest text cell above in the same column, i.e. the column
header) so later phases can show "Unit Cost x Qty" instead of ``B5*C5``.
Only non-formula text cells (``kind == "label"``) serve as labels.
"""

from __future__ import annotations

import re

from ..models import CellRecord

_ADDRESS_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")


def _split_address(address: str) -> tuple[int, int]:
    """Parse ``B2``/``$B$2`` into ``(col, row)``; raises ValueError if bad."""
    m = _ADDRESS_RE.match(address.strip())
    if not m:
        raise ValueError(f"Invalid cell address: {address!r}")
    col = 0
    for ch in m.group(1).upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return col, int(m.group(2))


def attach_labels(cells: dict[str, CellRecord]) -> None:
    """Mutate ``cells`` in place, filling ``label_left``/``label_above``."""
    # Index label text per sheet: row -> {col: text}, col -> {row: text}.
    by_row: dict[tuple[str, int], dict[int, str]] = {}
    by_col: dict[tuple[str, int], dict[int, str]] = {}
    positions: dict[str, tuple[str, int, int]] = {}
    for key, rec in cells.items():
        if rec.kind != "label" or not (rec.value or "").strip():
            continue
        try:
            col, row = _split_address(rec.ref.address)
        except ValueError:
            continue
        by_row.setdefault((rec.ref.sheet, row), {})[col] = rec.value.strip()
        by_col.setdefault((rec.ref.sheet, col), {})[row] = rec.value.strip()
        positions[key] = (rec.ref.sheet, col, row)

    for key, rec in cells.items():
        if rec.kind == "label":
            continue  # labels do not label themselves
        try:
            col, row = _split_address(rec.ref.address)
        except ValueError:
            continue
        row_labels = by_row.get((rec.ref.sheet, row), {})
        left_cols = [c for c in row_labels if c < col]
        rec.label_left = row_labels[max(left_cols)] if left_cols else None
        col_labels = by_col.get((rec.ref.sheet, col), {})
        above_rows = [r for r in col_labels if r < row]
        rec.label_above = col_labels[max(above_rows)] if above_rows else None
