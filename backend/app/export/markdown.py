"""Markdown documentation export (Phase 3).

Builds the downloadable workbook documentation from a persisted analysis
result. Copy rule: "suspicious cells to review", never "errors found";
results are not an audit certificate.
"""

from __future__ import annotations

from typing import Any


def build_markdown(filename: str, result: dict[str, Any]) -> str:
    """Render the analysis ``result`` payload as Markdown."""
    stats = result.get("stats", {})
    warnings = result.get("warnings", [])
    groups: list[dict[str, Any]] = result.get("groups", [])
    issues: list[dict[str, Any]] = result.get("issues", [])
    lines: list[str] = []
    lines.append(f"# SheetSense report — {filename}")
    lines.append("")
    lines.append(
        "> Suspicious cells to review, not an audit. "
        "Model explanations can be imperfect; the formula and evidence "
        "beside each claim are the source of truth."
    )
    lines.append("")

    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    by_sev = stats.get("issues_by_severity", {})
    lines.append("## Overview")
    lines.append("")
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
    lines.append("")

    lines.append("## Sheets and formula groups")
    lines.append("")
    for sheet in stats.get("sheets", []):
        lines.append(f"### {sheet}")
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
            lines.append(f"- Sample formula: `{group.get('sample_formula', '')}`")
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
    for severity in ("high", "medium", "low"):
        for issue in [i for i in issues if i.get("severity") == severity]:
            ref = issue.get("ref", {})
            lines.append(
                f"### [{severity}] {issue.get('detector')}: "
                f"{ref.get('sheet', '')}!{ref.get('address', '')}"
            )
            lines.append("")
            lines.append(issue.get("message", ""))
            lines.append("")
            evidence = issue.get("evidence", {}) or {}
            if evidence.get("formula"):
                lines.append(f"- Formula: `{evidence['formula']}`")
            if evidence.get("pattern"):
                lines.append(f"- Pattern: `{evidence['pattern']}`")
            neighbors = evidence.get("neighbors")
            if isinstance(neighbors, dict) and neighbors:
                lines.append("- Neighbors:")
                for addr, formula in neighbors.items():
                    lines.append(f"  - {addr}: `{formula}`")
            lines.append("")
    return "\n".join(lines)
