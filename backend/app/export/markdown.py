"""Markdown handoff document export (Phases 3+7).

Builds the downloadable workbook documentation from a persisted analysis
result: overview, sheet-by-sheet explanations with original formulas, an
issues table, and known limitations. Copy rule: "suspicious cells to
review", never "errors found"; results are not an audit certificate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

LIMITATIONS = [
    "VBA/macros are unsupported (`.xlsm` files are rejected).",
    "Cached values may be missing; value-based checks degrade gracefully.",
    "Very large workbooks are processed with range-node collapsing and are slower to explain.",
    "Model explanations can be imperfect; the formula and evidence beside each claim are the source of truth.",
    "Results are suspicious cells to review, not an audit.",
]


def _cell(text: Any) -> str:
    """Render one Markdown table cell (pipes would break the table)."""
    return str(text if text is not None else "").replace("|", "/").replace("\n", " ")


def build_markdown(filename: str, result: dict[str, Any]) -> str:
    """Render the analysis ``result`` payload as a handoff document."""
    stats = result.get("stats", {})
    warnings = result.get("warnings", [])
    groups: list[dict[str, Any]] = result.get("groups", [])
    issues: list[dict[str, Any]] = result.get("issues", [])
    explanations = result.get("explanations", {}) or {}
    workbook_text = (explanations.get("workbook") or {}).get("text", "")
    sheet_texts = explanations.get("sheets", {}) or {}
    group_texts = explanations.get("groups", {}) or {}

    lines: list[str] = []
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# SheetSense report — {filename}")
    lines.append("")
    lines.append(f"_Generated {generated} from `{_cell(filename)}`._")
    lines.append("")
    lines.append(
        "> Suspicious cells to review, not an audit. "
        "Model explanations can be imperfect; the formula and evidence "
        "beside each claim are the source of truth."
    )
    lines.append("")

    lines.append("## Overview")
    lines.append("")
    if workbook_text:
        lines.append(workbook_text)
        lines.append("")
    by_sev = stats.get("issues_by_severity", {})
    lines.append(f"- Sheets: {', '.join(stats.get('sheets', []))}")
    lines.append(f"- Cells: {stats.get('n_cells', 0)}")
    lines.append(
        f"- Formulas: {stats.get('n_formulas', 0)}, "
        f"inputs: {stats.get('n_inputs', 0)}, "
        f"outputs: {stats.get('n_outputs', 0)}"
    )
    lines.append(f"- Formula groups: {stats.get('n_groups', 0)}")
    lines.append(
        "- Suspicious cells: "
        f"{by_sev.get('high', 0)} high, {by_sev.get('medium', 0)} medium, "
        f"{by_sev.get('low', 0)} low"
    )
    if warnings:
        lines.append("- Warnings:")
        for warning in warnings:
            lines.append(f"  - {_cell(warning)}")
    lines.append("")

    lines.append("## Sheets")
    lines.append("")
    for sheet in stats.get("sheets", []):
        lines.append(f"### {sheet}")
        lines.append("")
        sheet_expl = (sheet_texts.get(sheet) or {}).get("text", "")
        if sheet_expl:
            lines.append(sheet_expl)
            lines.append("")
        sheet_groups = [g for g in groups if g.get("sheet") == sheet]
        if not sheet_groups:
            lines.append("_No formula groups._")
            lines.append("")
            continue
        for group in sheet_groups:
            cells = group.get("cells", [])
            span = cells[0] if len(cells) == 1 else f"{cells[0]}:{cells[-1]}"
            lines.append(f"#### {sheet}!{span} ({len(cells)} cells)")
            lines.append("")
            group_expl = (group_texts.get(group.get("id", "")) or {}).get(
                "text", ""
            )
            if group_expl:
                lines.append(group_expl)
                lines.append("")
            lines.append(f"- Original formula: `{group.get('sample_formula', '')}`")
            lines.append(f"- Pattern: `{group.get('pattern_r1c1', '')}`")
            labels = group.get("labels", {}) or {}
            if labels:
                lines.append(
                    "- Labels: "
                    + ", ".join(f"{k}={v}" for k, v in labels.items())
                )
            lines.append("")

    lines.append("## Suspicious cells to review")
    lines.append("")
    if not issues:
        lines.append("_No suspicious cells found._")
        lines.append("")
    else:
        lines.append("| Severity | Detector | Cell | Finding | Formula |")
        lines.append("|---|---|---|---|---|")
        for severity in ("high", "medium", "low"):
            for issue in [i for i in issues if i.get("severity") == severity]:
                ref = issue.get("ref", {})
                cell = f"{ref.get('sheet', '')}!{ref.get('address', '')}"
                formula = (issue.get("evidence", {}) or {}).get("formula", "")
                lines.append(
                    f"| {severity} | {_cell(issue.get('detector'))} | "
                    f"{_cell(cell)} | {_cell(issue.get('message', ''))} | "
                    f"`{_cell(formula)}` |"
                )
        lines.append("")

    lines.append("## Limitations")
    lines.append("")
    for limitation in LIMITATIONS:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)
