"""Pydantic domain models (Phase 1).

Mirror of spec section 3, plus ``ParsedWorkbook`` — the parser output that the
pipeline, detectors and graph builder share. The frontend mirror
(``frontend/src/api/types.ts``) is built in Phase 5.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CellRef(BaseModel):
    sheet: str
    address: str  # "F12"


class CellRecord(BaseModel):
    ref: CellRef
    formula: str | None = None  # "=D12*E12"
    value: Any | None = None  # cached value; None when never calculated
    number_format: str | None = None
    label_left: str | None = None  # nearest text cell to the left, same row
    label_above: str | None = None  # column header (nearest text above)
    kind: Literal["input", "formula", "label", "empty"]


class FormulaGroup(BaseModel):
    id: str
    sheet: str
    pattern_r1c1: str  # normalized relative formula
    cells: list[str] = Field(default_factory=list)  # addresses in the block
    sample_formula: str
    labels: dict[str, str] = Field(default_factory=dict)
    sample_values: list[Any] = Field(default_factory=list)


class Issue(BaseModel):
    id: str
    detector: str
    severity: Literal["high", "medium", "low"]
    ref: CellRef
    message: str  # written by code templates, never by the model
    evidence: dict[str, Any] = Field(default_factory=dict)


class Explanation(BaseModel):
    target_type: Literal["group", "sheet", "workbook"]
    target_id: str
    text: str
    structured: dict[str, Any] = Field(default_factory=dict)
    model: str
    prompt_version: str


class ParsedWorkbook(BaseModel):
    """Result of parsing one .xlsx file (reader.py).

    ``cells`` holds only non-empty records keyed by ``"Sheet!A1"``
    (see ``core.parser.refs.cell_key``); an absent key means an empty cell.
    """

    cells: dict[str, CellRecord] = Field(default_factory=dict)
    defined_names: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    has_cached_values: bool = True
    source_path: str | None = None
