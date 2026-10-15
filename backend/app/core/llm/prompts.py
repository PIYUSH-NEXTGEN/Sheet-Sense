"""Prompt templates (Phase 4, spec section 7.2).

One shared ``PROMPT_VERSION`` (bumped whenever any template changes; it is
part of the cache key). Every prompt carries a small structured fact bundle
— never a whole workbook — and the standing instruction: "Use only the
facts provided. If the facts are insufficient, say so."
"""

from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "v1"

_STANDING_INSTRUCTION = (
    "Use only the facts provided. If the facts are insufficient, say so."
)


def _facts_block(facts: dict[str, Any]) -> str:
    return json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=True)


def group_prompt(facts: dict[str, Any]) -> str:
    """User message explaining one formula group.

    Facts: sample formula (A1), column header, labels of each referenced
    input, up to 3 sample values, cell count and range.
    """
    return f"""Explain what this spreadsheet formula group computes, in 1-2 plain sentences with no jargon and no speculation beyond the given facts.

Facts:
{_facts_block(facts)}

Reply with JSON only: {{"summary": "<1-2 plain sentences>", "plain_formula": "<the formula in words, e.g. 'Price times Quantity'>"}}.

{_STANDING_INSTRUCTION}"""


def sheet_prompt(facts: dict[str, Any]) -> str:
    """User message summarizing one sheet.

    Facts: list of group summaries, counts of inputs/outputs.
    """
    return f"""Summarize what this spreadsheet sheet is for, using only the group summaries and counts below.

Facts:
{_facts_block(facts)}

Reply with JSON only: {{"purpose": "<1-2 plain sentences>", "key_inputs": ["<named inputs>"], "key_outputs": ["<named outputs>"]}}.

{_STANDING_INSTRUCTION}"""


def workbook_prompt(facts: dict[str, Any]) -> str:
    """User message describing the whole workbook.

    Facts: sheet summaries + sheet-level edges.
    """
    return f"""Describe what this workbook does overall and the order in which to read its sheets.

Facts:
{_facts_block(facts)}

Reply with JSON only: {{"overview": "<2-3 plain sentences>", "reading_order": ["<sheet names in reading order>"]}}.

{_STANDING_INSTRUCTION}"""


def qa_pick_prompt(question: str, candidates: list[dict[str, Any]]) -> str:
    """User message asking the model to pick one candidate cell (Phase 6).

    ``candidates`` are ``{"ref": key, "label": human label}`` dicts built
    in code; the model must reply with one of the keys.
    """
    return f"""Pick the single spreadsheet cell the user is asking about. Reply with that cell only — it must be one of the candidate refs.

Question: {question}

Candidates (ref + human label):
{_facts_block({"candidates": candidates})}

Reply with JSON only: {{"target": "<one of the candidate refs>"}}.

{_STANDING_INSTRUCTION}"""


def qa_answer_prompt(
    question: str, target: str, chain: list[dict[str, Any]]
) -> str:
    """User message asking the model to answer from the traced chain (Phase 6)."""
    return f"""Answer the user's question using ONLY the traced calculation chain below. Cite the cells you used.

Question: {question}

Target cell: {target}

Traced chain (target first, then its precedents):
{_facts_block({"chain": chain})}

Reply with JSON only: {{"answer": "<2-4 plain sentences grounded in the chain>", "cited_cells": ["<cells from the chain you used>"]}}.

{_STANDING_INSTRUCTION}"""
