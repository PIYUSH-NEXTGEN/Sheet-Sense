"""Group → sheet → workbook explainer (Phase 4, spec section 7).

Code determines the facts; the model only phrases them. Each call sends one
small fact bundle and validates the JSON response against a schema. Failures
(a typed ``LLMError`` per item, or anything unexpected) yield a placeholder
explanation ("Explanation unavailable") so the pipeline never crashes.
Cache is checked before every call: identical requests never hit the model
twice, even with no client configured.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..models import Explanation, FormulaGroup, ParsedWorkbook
from .cache import cache_get, cache_put, cache_key, group_payload
from .client import LLMClient
from .prompts import PROMPT_VERSION, group_prompt, sheet_prompt, workbook_prompt
from .schemas import GroupExplanation, SheetSummary, WorkbookOverview

PLACEHOLDER_TEXT = "Explanation unavailable"


def placeholder(target_type: str, target_id: str, model: str) -> Explanation:
    """Fallback explanation stored when the model cannot answer."""
    return Explanation(
        target_type=target_type,  # type: ignore[arg-type]
        target_id=target_id,
        text=PLACEHOLDER_TEXT,
        structured={"target": target_id},
        model=model or "unavailable",
        prompt_version=PROMPT_VERSION,
    )


def group_facts(group: FormulaGroup, wb: ParsedWorkbook) -> dict[str, Any]:
    """Small fact bundle for one group (never a whole workbook)."""
    cells = group.cells or []
    span = cells[0] if len(cells) == 1 else f"{cells[0]}:{cells[-1]}"
    return {
        "sample_formula": group.sample_formula,
        "column_header": group.labels.get("header", ""),
        "input_labels": {
            ref: label
            for ref, label in group.labels.items()
            if ref != "header"
        },
        "sample_values": group.sample_values[:3],
        "cell_count": len(cells),
        "cell_range": f"{group.sheet}!{span}",
    }


def _explain_one(
    kind: str,
    payload: str,
    prompt: str,
    text_key: str,
    target_type: str,
    target_id: str,
    client: LLMClient | None,
    model: str,
    schema: Any,
) -> Explanation:
    key = cache_key(kind, payload, model, PROMPT_VERSION)
    cached = cache_get(key)
    if cached is not None:
        return Explanation(
            target_type=target_type,  # type: ignore[arg-type]
            target_id=target_id,
            text=str(cached.get(text_key, "")),
            structured=dict(cached),
            model=model,
            prompt_version=PROMPT_VERSION,
        )
    if client is None:
        return placeholder(target_type, target_id, model)
    try:
        validated = client.chat_structured(prompt, schema)
    except Exception:
        return placeholder(target_type, target_id, model)
    cache_put(key, validated)
    return Explanation(
        target_type=target_type,  # type: ignore[arg-type]
        target_id=target_id,
        text=str(validated.get(text_key, "")),
        structured=dict(validated),
        model=model,
        prompt_version=PROMPT_VERSION,
    )


def _pool_size(client: LLMClient | None) -> int:
    workers = getattr(client, "workers", 3) or 3
    return max(1, int(workers))


def explain_groups(
    groups: list[FormulaGroup], wb: ParsedWorkbook, client: LLMClient | None
) -> dict[str, Explanation]:
    """Explain every group concurrently (worker pool); returns {id: expl}."""
    model = client.model if client else ""
    jobs = [(group, group_facts(group, wb)) for group in groups]

    def _run(job: tuple[FormulaGroup, dict[str, Any]]) -> tuple[str, Explanation]:
        group, facts = job
        return group.id, _explain_one(
            kind="group",
            payload=group_payload(group.pattern_r1c1, group.labels),
            prompt=group_prompt(facts),
            text_key="summary",
            target_type="group",
            target_id=group.id,
            client=client,
            model=model,
            schema=GroupExplanation,
        )

    with ThreadPoolExecutor(max_workers=_pool_size(client)) as pool:
        return dict(pool.map(_run, jobs))


def explain_sheets(
    sheets: list[str],
    groups: list[FormulaGroup],
    group_explanations: dict[str, Explanation],
    sheet_stats: dict[str, dict[str, int]],
    client: LLMClient | None,
) -> dict[str, Explanation]:
    """Explain every sheet concurrently; returns {sheet: expl}."""
    model = client.model if client else ""
    jobs = []
    for sheet in sheets:
        summaries = [
            group_explanations[group.id].text
            for group in groups
            if group.sheet == sheet and group.id in group_explanations
        ]
        stats = sheet_stats.get(sheet, {})
        facts = {
            "sheet": sheet,
            "group_summaries": summaries,
            "n_inputs": stats.get("n_inputs", 0),
            "n_outputs": stats.get("n_outputs", 0),
        }
        jobs.append((sheet, facts))

    def _run(job: tuple[str, dict[str, Any]]) -> tuple[str, Explanation]:
        sheet, facts = job
        return sheet, _explain_one(
            kind="sheet",
            payload=sheet + "\x00" + json.dumps(
                facts, sort_keys=True, ensure_ascii=True, default=str
            ),
            prompt=sheet_prompt(facts),
            text_key="purpose",
            target_type="sheet",
            target_id=sheet,
            client=client,
            model=model,
            schema=SheetSummary,
        )

    with ThreadPoolExecutor(max_workers=_pool_size(client)) as pool:
        return dict(pool.map(_run, jobs))


def explain_workbook(
    sheets: list[str],
    sheet_explanations: dict[str, Explanation],
    sheet_edges: list[list[str]],
    client: LLMClient | None,
) -> Explanation:
    """Explain the workbook (single call)."""
    model = client.model if client else ""
    facts = {
        "sheet_summaries": {
            sheet: sheet_explanations[sheet].text
            for sheet in sheets
            if sheet in sheet_explanations
        },
        "sheet_edges": sheet_edges,
    }
    return _explain_one(
        kind="workbook",
        payload=json.dumps(facts, sort_keys=True, ensure_ascii=True, default=str),
        prompt=workbook_prompt(facts),
        text_key="overview",
        target_type="workbook",
        target_id="workbook",
        client=client,
        model=model,
        schema=WorkbookOverview,
    )


__all__ = [
    "PLACEHOLDER_TEXT",
    "explain_groups",
    "explain_sheets",
    "explain_workbook",
    "group_facts",
    "placeholder",
]
