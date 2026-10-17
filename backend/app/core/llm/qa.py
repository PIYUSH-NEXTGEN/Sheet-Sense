"""Trace-based Q&A (Phase 6, spec section 8).

Code owns the facts: fuzzy candidate matching, ancestor tracing with a
depth limit, and cited-cell validation. The model only (a) picks the best
candidate and (b) phrases the answer from the traced chain. Any model
failure degrades gracefully — code-best candidate, then a template answer —
never a crash and never an invented citation.
"""

from __future__ import annotations

import re
from typing import Any

import networkx as nx

from ..models import FormulaGroup, ParsedWorkbook
from .client import LLMClient
from .prompts import qa_answer_prompt, qa_general_prompt, qa_pick_prompt
from .schemas import QAAnswer, TargetPick, validate_cited_cells

TRACE_DEPTH = 6
MAX_CANDIDATES = 8
# Model-bound fact window: the traced chain can exceed 100 cells, so the
# model sees the most relevant slice (target first, then by depth) while
# validation and display always use the full chain.
CHAIN_FACT_LIMIT = 30

CANT_TRACE = (
    "I couldn't trace that. None of the workbook's labels match the "
    "question, or nothing citeable remained in the traced chain. Try "
    "naming a row or column header, e.g. 'Where does the total with "
    "surcharge come from?'"
)


def question_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def candidate_targets(
    question: str, wb: ParsedWorkbook, limit: int = MAX_CANDIDATES
) -> list[str]:
    """Up to ``limit`` cell keys by label/sheet token overlap (code only)."""
    wanted = question_tokens(question)
    scored: list[tuple[int, str]] = []
    for key, rec in wb.cells.items():
        haystack = " ".join(
            part
            for part in (
                rec.label_left or "",
                rec.label_above or "",
                rec.ref.sheet,
            )
            if part
        )
        overlap = len(wanted & question_tokens(haystack))
        if overlap:
            scored.append((overlap, key))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [key for _, key in scored[:limit]]


def _bfs_order(
    graph: nx.DiGraph, target: str, depth: int
) -> list[str]:
    """Target first, then precedents layer by layer (cycle-safe)."""
    ordered = [target]
    seen = {target}
    frontier = [target]
    for _ in range(max(depth, 0)):
        nxt: list[str] = []
        for node in frontier:
            if node not in graph:
                continue
            for prev in sorted(graph.predecessors(node)):
                if prev not in seen:
                    seen.add(prev)
                    nxt.append(prev)
        if not nxt:
            break
        ordered.extend(nxt)
        frontier = nxt
    return ordered


def collapse_chain(
    graph: nx.DiGraph,
    groups: list[FormulaGroup],
    target: str,
    depth: int = TRACE_DEPTH,
) -> dict[str, Any]:
    """Ancestors of ``target`` up to ``depth``, collapsed into groups.

    Returns ``{"cells": [keys], "entries": [...], "group_ids": [...]}`` where
    each entry carries ref/formula/sheet/address/group_id. Cells are ordered
    target-first, then by trace depth.
    """
    ordered = _bfs_order(graph, target, depth)
    cell_to_group = {
        f"{group.sheet}!{address}": group.id
        for group in groups
        for address in group.cells
    }
    entries: list[dict[str, Any]] = []
    group_ids: list[str] = []
    for key in ordered:
        node = graph.nodes[key] if key in graph else {}
        group_id = cell_to_group.get(key)
        if group_id is not None and group_id not in group_ids:
            group_ids.append(group_id)
        entries.append(
            {
                "ref": key,
                "formula": node.get("formula"),
                "sheet": node.get("sheet"),
                "address": node.get("address"),
                "group_id": group_id,
            }
        )
    return {"cells": ordered, "entries": entries, "group_ids": group_ids}


def _cell_label(wb: ParsedWorkbook, key: str) -> str:
    rec = wb.cells.get(key)
    if rec is None:
        return ""
    return " / ".join(
        part
        for part in (
            rec.label_left or "",
            rec.label_above or "",
            rec.ref.sheet,
        )
        if part
    )


_CELL_TOKEN_RE = re.compile(r"\b([A-Za-z]{1,3})(\d{1,7})\b")


def _mentions_missing_cells(question: str, wb: ParsedWorkbook) -> bool:
    """True when the question names a cell address present nowhere.

    Guards the general-answer fallback: without this, the model happily
    locates nonexistent cells ("Cell ZZZ999 comes from ...").
    """
    tokens = {m.group(0).upper() for m in _CELL_TOKEN_RE.finditer(question)}
    if not tokens:
        return False
    existing = {rec.ref.address.upper() for rec in wb.cells.values()}
    return bool(tokens - existing)


def _chain_facts(
    collapsed: dict[str, Any],
    wb: ParsedWorkbook,
    group_texts: dict[str, str],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for entry in collapsed["entries"]:
        key = entry["ref"]
        rec = wb.cells.get(key)
        fact: dict[str, Any] = {
            "ref": key,
            "formula": entry["formula"],
        }
        if rec is not None and (rec.label_left or rec.label_above):
            fact["label"] = rec.label_left or rec.label_above
        group_id = entry["group_id"]
        if group_id is not None and group_id in group_texts:
            fact["group_explanation"] = group_texts[group_id]
        facts.append(fact)
    return facts


def _general_answer(
    question: str,
    sheet_texts: dict[str, str],
    stats: dict[str, Any],
    client: LLMClient,
) -> dict[str, Any]:
    """Answer without a traced chain (honestly labeled, never cited)."""
    facts = {
        "sheet_summaries": sheet_texts,
        "stats": {
            key: stats.get(key)
            for key in (
                "sheets",
                "n_cells",
                "n_formulas",
                "n_inputs",
                "n_outputs",
                "n_groups",
            )
        },
    }
    try:
        response = client.chat_structured(
            qa_general_prompt(question, facts), QAAnswer
        )
        answer_text = str(response.get("answer", ""))
        relevant = bool(response.get("relevant", True))
    except Exception:
        answer_text = (
            "I couldn't answer that from this workbook. Try naming a row "
            "or column header, e.g. 'Where does the total with surcharge "
            "come from?'"
        )
        relevant = False
    if not answer_text.strip():
        answer_text = CANT_TRACE
        relevant = False
    return {
        "question": question,
        "target": None,
        "answer": answer_text,
        "cited_cells": [],
        "chain": [],
        "traced": False,
        "relevant": relevant,
    }


def answer_question(
    question: str,
    wb: ParsedWorkbook,
    graph: nx.DiGraph,
    groups: list[FormulaGroup],
    group_texts: dict[str, str],
    client: LLMClient | None,
    depth: int = TRACE_DEPTH,
    sheet_texts: dict[str, str] | None = None,
    stats: dict[str, Any] | None = None,
    pending_group_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Answer ``question`` from the traced chain (see module docstring).

    When no candidate cell matches and a client plus workbook context are
    available, falls back to a clearly-labeled general answer (never cited);
    otherwise returns the couldn't-trace message.
    """
    candidates = candidate_targets(question, wb)
    if _mentions_missing_cells(question, wb):
        return {
            "question": question,
            "target": None,
            "answer": CANT_TRACE,
            "cited_cells": [],
            "chain": [],
            "traced": False,
            "relevant": False,
        }
    if not candidates:
        if client is not None and sheet_texts is not None and stats is not None:
            return _general_answer(question, sheet_texts, stats, client)
        return {
            "question": question,
            "target": None,
            "answer": CANT_TRACE,
            "cited_cells": [],
            "chain": [],
            "traced": False,
            "relevant": False,
        }
    target = candidates[0]
    if client is not None:
        described = [
            {
                "ref": key,
                "label": _cell_label(wb, key),
            }
            for key in candidates
        ]
        try:
            picked = client.chat_structured(
                qa_pick_prompt(question, described), TargetPick
            ).get("target")
        except Exception:
            picked = None
        if picked in candidates:
            target = picked
        # Anything else (hallucinated cell): keep the code-best candidate.

    collapsed = collapse_chain(graph, groups, target, depth)
    allowed = set(collapsed["cells"])
    if client is None:
        return {
            "question": question,
            "target": target,
            "answer": (
                f"{target} is computed from {len(collapsed['cells']) - 1} "
                f"upstream cell(s) (no model configured. Connect "
                f"Ollama/Gemma for a plain-English answer). Trace shown "
                f"in cited_cells."
            ),
            "cited_cells": collapsed["cells"],
            "chain": collapsed["entries"],
            "traced": True,
            "relevant": True,
        }
    try:
        facts = _chain_facts(collapsed, wb, group_texts)
        if len(facts) > CHAIN_FACT_LIMIT:
            facts = [
                *facts[:CHAIN_FACT_LIMIT],
                {
                    "note": (
                        f"+{len(facts) - CHAIN_FACT_LIMIT} more cells in the "
                        f"full trace; cite only the listed cells."
                    )
                },
            ]
        response = client.chat_structured(
            qa_answer_prompt(question, target, facts),
            QAAnswer,
        )
        answer_text = str(response.get("answer", ""))
        cited = validate_cited_cells(
            [c for c in response.get("cited_cells", []) if isinstance(c, str)],
            allowed,
        )
    except Exception:
        answer_text = (
            f"{target} is computed from {len(collapsed['cells']) - 1} "
            f"upstream cell(s) (the model answer was unavailable; the "
            f"trace below is exact). See the chain formulas for detail."
        )
        cited = collapsed["cells"]
    if not cited:
        return {
            "question": question,
            "target": target,
            "answer": CANT_TRACE,
            "cited_cells": [],
            "chain": collapsed["entries"],
            "traced": False,
            "relevant": False,
        }
    pending = {
        gid for gid in collapsed["group_ids"] if gid in (pending_group_ids or set())
    }
    if pending:
        answer_text += (
            f" Note: explanations for {len(pending)} group(s) in this "
            f"trace are still being generated."
        )
    return {
        "question": question,
        "target": target,
        "answer": answer_text,
        "cited_cells": cited,
        "chain": collapsed["entries"],
        "traced": True,
        "relevant": True,
    }


__all__ = [
    "CANT_TRACE",
    "MAX_CANDIDATES",
    "TRACE_DEPTH",
    "answer_question",
    "candidate_targets",
    "collapse_chain",
]
