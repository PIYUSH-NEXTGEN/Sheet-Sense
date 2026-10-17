"""Structured-output schemas for Ollama (Phase 4, spec section 7).

Every model response is validated against one of these before use. Schemas
are also converted to Ollama ``format`` JSON Schemas by ``client.py``.
``validate_cited_cells`` enforces golden rule 3 (drop addresses the model
mentions that are not in the traced chain); Phase 6 ``qa.py`` will use it
together with ``QAAnswer``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GroupExplanation(BaseModel):
    summary: str = Field(min_length=1)
    plain_formula: str = Field(min_length=1)


class BatchGroupItem(BaseModel):
    group_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    plain_formula: str = Field(min_length=1)


class BatchGroupExplanations(BaseModel):
    items: list[BatchGroupItem] = Field(min_length=1)


class SheetSummary(BaseModel):
    purpose: str = Field(min_length=1)
    key_inputs: list[str] = Field(default_factory=list)
    key_outputs: list[str] = Field(default_factory=list)


class WorkbookOverview(BaseModel):
    overview: str = Field(min_length=1)
    reading_order: list[str] = Field(default_factory=list)


class TargetPick(BaseModel):
    target: str = Field(min_length=1)


class QAAnswer(BaseModel):
    answer: str = Field(min_length=1)
    cited_cells: list[str] = Field(default_factory=list)
    relevant: bool = True  # False when the question is not about this workbook


def validate_cited_cells(
    cited: list[str], allowed: set[str]
) -> list[str]:
    """Keep only cited cells present in the traced chain, order-preserved."""
    seen: set[str] = set()
    valid: list[str] = []
    for cell in cited:
        if cell in allowed and cell not in seen:
            seen.add(cell)
            valid.append(cell)
    return valid


def to_ollama_format(schema: type[BaseModel]) -> dict[str, Any]:
    """Return the JSON Schema object for Ollama's ``format`` field."""
    return schema.model_json_schema()
