"""Phase 6 Q&A tests — all mocked, pass without Ollama.

Covers: code candidate matching, invalid citations dropped, off-list model
picks rejected (code-best fallback), trace depth respected, stub path with
no client, pick/answer failures degrading gracefully, and empty citations
yielding the couldn't-trace message.
"""

import pytest

from app.core.graph.builder import build_graph
from app.core.grouping.patterns import group_formulas
from app.core.llm.client import LLMError
from app.core.llm.qa import (
    CANT_TRACE,
    answer_question,
    candidate_targets,
    collapse_chain,
)
from app.core.llm.schemas import QAAnswer, TargetPick
from app.core.parser.reader import read_workbook
from conftest import DIRTY_XLSX, FakeLLMClient


@pytest.fixture(scope="module")
def dirty_setup():
    wb = read_workbook(DIRTY_XLSX)
    graph = build_graph(wb)
    groups = group_formulas(wb)
    return wb, graph, groups


class ScriptedFake:
    """Fake model with scripted pick/answer and optional failures."""

    model = "scripted-fake"
    workers = 1

    def __init__(
        self,
        pick: str = "Summary!B5",
        cited: tuple = ("Summary!B5",),
        answer: str = "Scripted answer.",
        fail_pick: bool = False,
        fail_answer: bool = False,
    ):
        self.pick = pick
        self.cited = cited
        self.answer = answer
        self.fail_pick = fail_pick
        self.fail_answer = fail_answer
        self.calls: list[str] = []

    def chat_structured(self, user_message: str, schema):
        self.calls.append(schema.__name__)
        if schema is TargetPick:
            if self.fail_pick:
                raise LLMError("pick failed")
            return {"target": self.pick}
        if self.fail_answer:
            raise LLMError("answer failed")
        return {"answer": self.answer, "cited_cells": list(self.cited)}


def _answer(dirty_setup, fake, question="Where does the total with surcharge come from?", **kwargs):
    wb, graph, groups = dirty_setup
    return answer_question(question, wb, graph, groups, {}, fake, **kwargs)


def test_candidates_come_from_code(dirty_setup):
    wb, _, _ = dirty_setup
    candidates = candidate_targets("Where does the total with surcharge come from?", wb)
    assert candidates and candidates[0] == "Summary!B5"
    assert len(candidates) <= 8
    assert candidate_targets("xyzzy qqq zzz", wb) == []


def test_invalid_citations_dropped(dirty_setup):
    out = _answer(
        dirty_setup,
        ScriptedFake(cited=("Summary!B5", "Summary!B4", "Nope!Z9")),
    )
    assert out["target"] == "Summary!B5"
    assert out["cited_cells"] == ["Summary!B5", "Summary!B4"]
    assert out["answer"] == "Scripted answer."


def test_off_list_pick_rejected_falls_back_to_code_best(dirty_setup):
    out = _answer(dirty_setup, ScriptedFake(pick="Nope!Z9"))
    assert out["target"] == "Summary!B5"  # code-best, not the hallucination
    assert "Nope!Z9" not in out["cited_cells"]


def test_trace_depth_respected(dirty_setup):
    wb, graph, groups = dirty_setup
    collapsed = collapse_chain(graph, groups, "Summary!B5", depth=1)
    # Dirty B5 (=B4*1.15) has a single precedent: the surcharge link is cut.
    assert set(collapsed["cells"]) == {"Summary!B5", "Summary!B4"}
    out = _answer(dirty_setup, ScriptedFake(), depth=1)
    assert set(out["cited_cells"]) <= set(collapsed["cells"])
    full = collapse_chain(graph, groups, "Summary!B5", depth=6)
    assert len(full["cells"]) > len(collapsed["cells"])


def test_chain_is_target_first_then_by_depth(dirty_setup):
    wb, graph, groups = dirty_setup
    collapsed = collapse_chain(graph, groups, "Summary!B5", depth=6)
    assert collapsed["cells"][0] == "Summary!B5"
    assert collapsed["cells"][1] == "Summary!B4"  # depth 1 before depth 2+
    assert set(collapsed["cells"][2:22]) == {f"Pricing!D{r}" for r in range(2, 22)}


def test_chain_collapses_into_groups(dirty_setup):
    wb, graph, groups = dirty_setup
    collapsed = collapse_chain(graph, groups, "Summary!B5", depth=2)
    by_ref = {e["ref"]: e for e in collapsed["entries"]}
    assert by_ref["Summary!B4"]["group_id"] is not None
    assert by_ref["Pricing!D2"]["group_id"] is not None
    assert collapsed["group_ids"], "expected grouped cells in the chain"


def test_no_client_stub_path(dirty_setup):
    out = _answer(dirty_setup, None)
    assert out["target"] == "Summary!B5"
    assert out["cited_cells"][0] == "Summary!B5"
    assert "Ollama" in out["answer"] or "model" in out["answer"]


def test_pick_failure_falls_back(dirty_setup):
    out = _answer(dirty_setup, ScriptedFake(fail_pick=True, fail_answer=True))
    assert out["target"] == "Summary!B5"
    assert out["cited_cells"][0] == "Summary!B5"  # full-chain template answer


def test_empty_citations_yield_cant_trace(dirty_setup):
    out = _answer(dirty_setup, ScriptedFake(cited=()))
    assert out["cited_cells"] == []
    assert out["answer"] == CANT_TRACE
    assert out["chain"], "chain formulas still shown for display"


def test_no_candidates_cant_trace(dirty_setup):
    out = _answer(dirty_setup, ScriptedFake(), question="xyzzy qqq zzz")
    assert out["target"] is None
    assert out["answer"] == CANT_TRACE


def test_fake_client_end_to_end(dirty_setup):
    out = _answer(dirty_setup, FakeLLMClient())
    assert out["target"] == "Summary!B5"
    assert out["cited_cells"] == ["Summary!B5", "Summary!B4"]


def test_qa_schemas_validate():
    assert TargetPick(target="S!A1").target == "S!A1"
    assert QAAnswer(answer="a", cited_cells=["S!A1"]).cited_cells == ["S!A1"]
