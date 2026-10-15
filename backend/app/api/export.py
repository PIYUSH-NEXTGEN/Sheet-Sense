"""Markdown export endpoint (Phase 3)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ..export.markdown import build_markdown
from .analysis import get_ready_result

router = APIRouter()


@router.get("/{workbook_id}/export")
def export_workbook(
    workbook_id: str,
    format: str = Query(default="md"),
):
    """Download the analysis as Markdown (``?format=md``, the only format)."""
    if format != "md":
        raise HTTPException(
            status_code=422, detail="Only ?format=md is supported."
        )
    filename, _stored_path, result = get_ready_result(workbook_id)
    stem = Path(filename).stem or "workbook"
    return Response(
        content=build_markdown(filename, result),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{stem}.md"'},
    )
