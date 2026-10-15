"""Q&A endpoint (Phase 6): deterministic trace + Gemma answer via llm/qa.py.

Candidate matching, ancestor tracing and citation validation all stay in
code; the model only picks among candidates and phrases the answer from
the traced chain. Pass ``get_client`` a fake in tests (golden rule 4).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..core.graph.builder import build_graph
from ..core.llm.client import LLMClient
from ..core.llm.qa import TRACE_DEPTH, answer_question
from ..core.models import FormulaGroup
from ..core.parser.reader import read_workbook
from ..core.pipeline import default_client_factory
from .analysis import get_ready_result

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    depth: int = TRACE_DEPTH


def get_client() -> LLMClient | None:
    """Client factory (monkeypatch in tests to inject a fake)."""
    return default_client_factory()


@router.post("/{workbook_id}/ask")
def ask(workbook_id: str, body: AskRequest) -> dict[str, Any]:
    """``{question}`` → answer + validated cited cells + traced chain."""
    _filename, stored_path, result = get_ready_result(workbook_id)
    wb = read_workbook(stored_path)
    graph = build_graph(wb)
    groups = [FormulaGroup.model_validate(g) for g in result["groups"]]
    group_texts = {
        gid: (expl.get("text") or "")
        for gid, expl in result["explanations"]["groups"].items()
    }
    depth = body.depth if body.depth and body.depth > 0 else TRACE_DEPTH
    return answer_question(
        body.question, wb, graph, groups, group_texts, get_client(), depth
    )
