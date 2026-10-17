"""QA Stage 9: realistic workbooks with no planted errors.

Budget (monthly), pricing model (tiers), payroll (hourly). Each has 30+
formulas built the way careful users build them: no magic numbers, totals
that reach the last data row, every input referenced. Returns paths.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


def budget(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws["A1"] = "Category"
    ws["B1"] = "Planned"
    ws["C1"] = "Actual"
    ws["D1"] = "Variance"
    ws["E1"] = "VarPct"
    cats = ["Rent", "Payroll", "Supplies", "Travel", "Ads", "Tools",
            "Repairs", "Fees", "Meals", "Training", "Misc", "Reserve",
            "Contingency"]
    planned = [5000, 22000, 800, 1500, 2000, 400, 600, 300, 700, 900, 500,
               1200, 1500]
    actual = [5000, 23100, 750, 1620, 1950, 420, 0, 310, 680, 900, 530,
              1200, 1100]
    for i, (cat, p, a) in enumerate(zip(cats, planned, actual), start=2):
        ws[f"A{i}"] = cat
        ws[f"B{i}"] = p
        ws[f"C{i}"] = a
        ws[f"D{i}"] = f"=C{i}-B{i}"
        ws[f"E{i}"] = f"=IF(C{i}=0,0,D{i}/C{i})"
        ws[f"E{i}"].number_format = "0.00%"
    t = 15
    ws[f"A{t}"] = "Total"
    ws[f"B{t}"] = "=SUM(B2:B14)"
    ws[f"C{t}"] = "=SUM(C2:C14)"
    ws[f"D{t}"] = "=SUM(D2:D14)"
    ws[f"E{t}"] = f"=IF(C{t}=0,0,D{t}/C{t})"
    ws[f"E{t}"].number_format = "0.00%"
    wb.save(path / "budget.xlsx")
    return path / "budget.xlsx"


def pricing(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Model"
    ws["A1"] = "Product"
    ws["B1"] = "Base"
    ws["C1"] = "Qty"
    ws["D1"] = "Extended"
    ws["E1"] = "DiscRate"
    ws["F1"] = "Net"
    ws["G1"] = "Tax"
    ws["I1"] = "TaxRate"
    ws["J1"] = 0.08
    prods = ["Widget", "Gadget", "Doohickey", "Thingamajig", "Gizmo",
             "Contraption", "Gadget Pro", "Widget XL", "Sprocket", "Cog"]
    bases = [12.5, 8.0, 45.0, 3.25, 99.0, 27.5, 15.75, 60.0, 5.5, 7.75]
    qtys = [40, 100, 12, 500, 8, 30, 64, 20, 200, 150]
    discs = [0.05, 0.10, 0.0, 0.15, 0.05, 0.0, 0.10, 0.05, 0.20, 0.0]
    for i, (prod, base, qty, disc) in enumerate(
        zip(prods, bases, qtys, discs), start=2
    ):
        ws[f"A{i}"] = prod
        ws[f"B{i}"] = base
        ws[f"C{i}"] = qty
        ws[f"D{i}"] = f"=B{i}*C{i}"
        ws[f"E{i}"] = disc
        ws[f"F{i}"] = f"=D{i}*(1-E{i})"
        ws[f"G{i}"] = f"=F{i}*$J$1"
    t = 12
    ws[f"A{t}"] = "Total"
    ws[f"D{t}"] = "=SUM(D2:D11)"
    ws[f"F{t}"] = "=SUM(F2:F11)"
    ws[f"G{t}"] = "=SUM(G2:G11)"
    wb.save(path / "pricing.xlsx")
    return path / "pricing.xlsx"


def payroll(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Pay"
    ws["A1"] = "Name"
    ws["B1"] = "Hours"
    ws["C1"] = "Rate"
    ws["D1"] = "Gross"
    ws["E1"] = "Tax"
    ws["F1"] = "Net"
    ws["H1"] = "TaxRate"
    ws["I1"] = 0.22
    names = ["Ava", "Ben", "Cy", "Dee", "Eli", "Fay", "Gus", "Hal", "Ivy", "Jay"]
    hours = [40, 38, 42, 35, 40, 20, 45, 40, 32, 40]
    rates = [25, 30, 22, 28, 35, 20, 26, 31, 24, 29]
    for i, (name, h, r) in enumerate(zip(names, hours, rates), start=2):
        ws[f"A{i}"] = name
        ws[f"B{i}"] = h
        ws[f"C{i}"] = r
        ws[f"D{i}"] = f"=B{i}*C{i}"
        ws[f"E{i}"] = f"=D{i}*$I$1"
        ws[f"F{i}"] = f"=D{i}-E{i}"
    t = 12
    ws[f"A{t}"] = "Total"
    ws[f"D{t}"] = "=SUM(D2:D11)"
    ws[f"E{t}"] = "=SUM(E2:E11)"
    ws[f"F{t}"] = "=SUM(F2:F11)"
    wb.save(path / "payroll.xlsx")
    return path / "payroll.xlsx"


def build_all(out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    return {
        "budget": budget(out),
        "pricing": pricing(out),
        "payroll": payroll(out),
    }


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("realistic")
    for name, path in build_all(target).items():
        print(f"{name}: {path}")
