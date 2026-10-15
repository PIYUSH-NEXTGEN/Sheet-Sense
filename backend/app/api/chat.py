"""Q&A endpoint (Phase 3, stub-backed).

Deterministic trace, zero model calls: the question is fuzzy-matched in code
against cell labels and sheet names (up to 8 candidates, best wins), the
chain comes from ``graph.queries`` (ancestors up to depth 6), and the answer
text is a template. Phase 6 replaces the template with a Gemma answer while
keeping candidate-matching and chain validation in code.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..core.graph.builder import build_graph
from ..core.graph.queries import ancestors
from ..core.parser.reader import read_workbook
from .analysis import get_ready_result

router = APIRouter()

TRACE_DEPTH = 6
MAX_CANDIDATES = 8


class AskRequest(BaseModel):
    question: str


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _match_target(question: str, wb) -> str | None:
    """Best cell key by label/sheet token overlap; None when nothing matches."""
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
        overlap = len(_tokens(question) & _tokens(haystack))
        if overlap:
            scored.append((overlap, key))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


@router.post("/{workbook_id}/ask")
def ask(workbook_id: str, body: AskRequest) -> dict[str, Any]:
    """``{question}`` → answer + cited cells + traced chain (stub text)."""
    _filename, stored_path, _result = get_ready_result(workbook_id)
    wb = read_workbook(stored_path)
    graph = build_graph(wb)
    target = _match_target(body.question, wb)
    if target is None or target not in graph:
        return {
            "question": body.question,
            "target": None,
            "answer": "I couldn't trace that — none of the workbook's "
            "labels match the question. Try naming a row or column "
            "header, e.g. 'Where does the total with surcharge come from?'",
            "cited_cells": [],
            "chain": [],
        }
    chain_keys = [target, *ancestors(graph, target, TRACE_DEPTH)]
    chain = [
        {
            "ref": key,
            "formula": graph.nodes[key].get("formula"),
            "sheet": graph.nodes[key].get("sheet"),
            "address": graph.nodes[key].get("address"),
        }
        for key in chain_keys
    ]
    return {
        "question": body.question,
        "target": target,
        "answer": (
            f"{target} is computed from {len(chain_keys) - 1} upstream "
            f"cell(s) (stub answer — connect Ollama/Gemma for a "
            f"plain-English explanation). Trace shown in cited_cells."
        ),
        "cited_cells": chain_keys,
        "chain": chain,
    }
