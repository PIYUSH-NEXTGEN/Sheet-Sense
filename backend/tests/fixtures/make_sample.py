"""Fixture generator: ``sample-workbook.xlsx``.

A richer demo workbook than ``harbor-supply-pricing.xlsx``: four sheets,
cross-sheet formula chains, column/row labels, totals that reach the last
data row, and six planted issues (one per detector family) so the SheetSense
issue list and Q&A page have something meaningful to show.

Sheets
------
Inputs      : raw item catalog (name, unit cost, qty) — all input cells.
Pricing     : per-item cost/price with tax — formula column, one pattern break.
Summary     : roll-up totals + surcharge — hardcoded constant, range gap,
              circular pair.
Settings    : global rates (markup, tax, surcharge) + one orphan input.

Usage: ``python make_sample.py [out_dir]`` (defaults to this directory).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from openpyxl import Workbook

SAMPLE_NAME = "sample-workbook.xlsx"

FIRST_ROW = 2
N_ROWS = 15
LAST_ROW = FIRST_ROW + N_ROWS - 1  # 16

# Realistic product catalog: (item, unit cost, qty).
PRODUCTS: list[tuple[str, float, int]] = [
    ("Copy Paper A4 Rim", 4.80, 12),
    ("Ballpoint Pen Box", 6.40, 8),
    ("Stapler Pro", 14.95, 3),
    ("Sticky Notes Pack", 3.25, 20),
    ("Binder Clips Box", 2.10, 15),
    ("Highlighters Set", 5.60, 9),
    ("Desk Organizer", 18.75, 2),
    ("USB-C Cable 2m", 9.90, 11),
    ("Wireless Mouse", 24.50, 4),
    ("Keyboard Wired", 32.00, 4),
    ("Monitor Stand", 45.95, 2),
    ("Notebook A5", 3.90, 25),
    ("Envelope Box", 7.30, 6),
    ("Tape Dispenser", 8.85, 5),
    ("Scissors Pair", 4.45, 7),
]

EXPECTED_ISSUES = [
    {"detector": "hardcoded_constant", "sheet": "Summary", "address": "B6"},
    {"detector": "pattern_break", "sheet": "Pricing", "address": "D10"},
    {"detector": "range_gap", "sheet": "Summary", "address": "B4"},
    {"detector": "orphan_input", "sheet": "Settings", "address": "B5"},
    {"detector": "circular", "sheet": "Summary", "address": "B9"},
    {"detector": "circular", "sheet": "Summary", "address": "B10"},
]


def _build(wb: Workbook) -> None:
    """Build the full workbook (dirty = with planted issues)."""

    # ---- Inputs sheet --------------------------------------------------
    inputs = wb.active
    inputs.title = "Inputs"
    inputs["A1"] = "Item"
    inputs["B1"] = "Unit Cost"
    inputs["C1"] = "Qty"
    for i, (item, cost, qty) in enumerate(PRODUCTS, start=1):
        r = FIRST_ROW + i - 1
        inputs[f"A{r}"] = item
        inputs[f"B{r}"] = cost
        inputs[f"C{r}"] = qty

    # ---- Settings sheet ------------------------------------------------
    settings = wb.create_sheet("Settings")
    settings["A1"] = "Markup rate"
    settings["B1"] = 0.25
    settings["A2"] = "Tax rate"
    settings["B2"] = 0.08
    settings["A3"] = "Surcharge rate"
    settings["B3"] = 0.15
    settings["A5"] = "Unused discount"      # orphan input (never referenced)
    settings["B5"] = 0.10

    # ---- Pricing sheet -------------------------------------------------
    pricing = wb.create_sheet("Pricing")
    pricing["A1"] = "Item"
    pricing["B1"] = "Cost Total"
    pricing["C1"] = "Price (markup)"
    pricing["D1"] = "Price (with tax)"
    for r in range(FIRST_ROW, LAST_ROW + 1):
        pricing[f"A{r}"] = f"=Inputs!A{r}"
        pricing[f"B{r}"] = f"=Inputs!B{r}*Inputs!C{r}"
        pricing[f"C{r}"] = f"=B{r}*(1+Settings!$B$1)"
        pricing[f"D{r}"] = f"=C{r}+C{r}*Settings!$B$2"

    # Planted pattern break: a hardcoded number inside a formula column.
    pricing["D10"] = 99.5

    # ---- Summary sheet -------------------------------------------------
    summary = wb.create_sheet("Summary")
    summary["A2"] = "Total cost"
    summary["B2"] = f"=SUM(Pricing!B{FIRST_ROW}:B{LAST_ROW})"
    summary["A3"] = "Total price (markup)"
    summary["B3"] = f"=SUM(Pricing!C{FIRST_ROW}:C{LAST_ROW})"
    summary["A4"] = "Total with tax"
    summary["B4"] = f"=SUM(Pricing!D{FIRST_ROW}:D{LAST_ROW-1})"  # range gap
    summary["A5"] = "Total with surcharge"
    summary["B5"] = f"=B4*(1+Settings!B3)"
    summary["A6"] = "Grand total"
    summary["B6"] = "=B5*1.15"  # hardcoded constant instead of Settings!B3
    summary["A9"] = "Loop A"
    summary["B9"] = "=B10+1"    # circular pair
    summary["A10"] = "Loop B"
    summary["B10"] = "=B9*2"


def _maybe_recalc(path: Path) -> None:
    """Optionally recalculate cached values via LibreOffice (opt-in)."""
    if os.environ.get("SHEETSENSE_RECALC") != "1":
        return
    soffice = shutil.which("soffice")
    if soffice is None:
        print("SHEETSENSE_RECALC=1 but soffice not found; skipping recalc.")
        return
    subprocess.run(
        [soffice, "--headless", "--convert-to", "xlsx", "--outdir",
         str(path.parent), str(path)],
        check=True,
    )


def make_sample(out_dir: str | Path | None = None) -> Path:
    """Write the sample workbook and expected_issues.json; return out_dir."""
    out = Path(out_dir) if out_dir is not None else Path(__file__).resolve().parent
    out.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    _build(wb)
    sample_path = out / SAMPLE_NAME
    wb.save(sample_path)
    _maybe_recalc(sample_path)

    with open(out / "expected_issues.json", "w", encoding="utf-8") as fh:
        json.dump(EXPECTED_ISSUES, fh, indent=2)
        fh.write("\n")
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Sample written to {make_sample(target)}")
