"""Analysis endpoints (Phase 3): analyze, SSE progress, overview, sheets,
issues, graph.

Analysis runs in a background thread; progress events
``{stage, percent, detail}`` are stored in memory per workbook and streamed
by the SSE endpoint. Results persist in SQLite, so overview/issues reopen
instantly; the graph endpoints rebuild the deterministic graph from the
stored .xlsx on demand.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..core.graph.builder import build_graph
from ..core.parser.reader import read_workbook
from ..core.pipeline import run_analysis
from ..db.session import session_scope, uploads_dir
from ..db.tables import (
    STATUS_ANALYZING,
    STATUS_FAILED,
    STATUS_READY,
    WorkbookRow,
)

router = APIRouter()

_progress: dict[str, dict[str, Any]] = {}
_progress_lock = threading.Lock()


def _event(stage: str, percent: int, detail: str) -> dict[str, Any]:
    return {"stage": stage, "percent": percent, "detail": detail}


def seed_progress(workbook_id: str) -> None:
    with _progress_lock:
        _progress[workbook_id] = {
            "events": [_event("uploaded", 0, "workbook uploaded")],
            "done": True,  # nothing running; SSE replays and closes
        }


def drop_progress(workbook_id: str) -> None:
    with _progress_lock:
        _progress.pop(workbook_id, None)


def emit_progress(workbook_id: str, stage: str, percent: int, detail: str) -> None:
    with _progress_lock:
        entry = _progress.setdefault(
            workbook_id, {"events": [], "done": False}
        )
        entry["events"].append(_event(stage, percent, detail))
        if stage in ("persist", "failed"):
            entry["done"] = True


def _finish_progress(workbook_id: str, ok: bool, detail: str) -> None:
    emit_progress(workbook_id, "persist" if ok else "failed", 100, detail)


def _run_analysis_thread(workbook_id: str, stored_path: str, filename: str) -> None:
    try:
        result = run_analysis(
            workbook_id,
            stored_path,
            filename,
            emit=lambda stage, pct, detail: emit_progress(
                workbook_id, stage, pct, detail
            ),
        )
    except Exception as exc:  # reader guards (size/cells/macros) land here
        with session_scope() as session:
            row = session.get(WorkbookRow, workbook_id)
            if row is not None:
                row.status = STATUS_FAILED
                row.error = str(exc)
        _finish_progress(workbook_id, False, str(exc))
        return
    with session_scope() as session:
        row = session.get(WorkbookRow, workbook_id)
        if row is not None:
            row.status = STATUS_READY
            row.error = None
            row.result_json = json.dumps(result)
    # "persist" was already emitted by the pipeline; mark done.
    with _progress_lock:
        entry = _progress.setdefault(
            workbook_id, {"events": [], "done": True}
        )
        entry["done"] = True


def _get_row_or_404(session, workbook_id: str) -> WorkbookRow:
    row = session.get(WorkbookRow, workbook_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workbook not found.")
    return row


def get_ready_result(workbook_id: str) -> tuple[str, str, dict[str, Any]]:
    """Return (filename, stored_path, result); 404 unknown, 409 not ready.

    Plain values only — never ORM instances, which detach when the session
    closes.
    """
    with session_scope() as session:
        row = _get_row_or_404(session, workbook_id)
        status, error, payload = row.status, row.error, row.result_json
        filename, stored_path = row.filename, stored_path_for(row)
    if status != STATUS_READY or not payload:
        raise HTTPException(
            status_code=409,
            detail=error
            if status == STATUS_FAILED and error
            else f"Analysis is {status}; retry after it is ready.",
        )
    return filename, stored_path, json.loads(payload)


def stored_path_for(row: WorkbookRow) -> str:
    return str(uploads_dir() / row.stored_name)


@router.post("/{workbook_id}/analyze")
def start_analysis(workbook_id: str):
    """Start the pipeline in a background thread."""
    with session_scope() as session:
        row = _get_row_or_404(session, workbook_id)
        if row.status == STATUS_ANALYZING:
            raise HTTPException(
                status_code=409, detail="Analysis already running."
            )
        row.status = STATUS_ANALYZING
        row.error = None
        stored_path = stored_path_for(row)
        filename = row.filename
    with _progress_lock:
        _progress[workbook_id] = {
            "events": [_event("started", 0, "analysis started")],
            "done": False,
        }
    thread = threading.Thread(
        target=_run_analysis_thread,
        args=(workbook_id, stored_path, filename),
        daemon=True,
    )
    thread.start()
    return {"workbook_id": workbook_id, "status": STATUS_ANALYZING}


@router.get("/{workbook_id}/progress")
def progress(workbook_id: str):
    """SSE stream of ``{stage, percent, detail}`` events."""

    def _snapshot() -> tuple[list[dict[str, Any]], bool]:
        with _progress_lock:
            entry = _progress.get(workbook_id)
            if entry is None:
                return [], True
            return list(entry["events"]), bool(entry["done"])

    if workbook_id not in _progress:
        with session_scope() as session:
            _get_row_or_404(session, workbook_id)

    def gen():
        index = 0
        deadline = time.time() + 30
        while True:
            events, done = _snapshot()
            while index < len(events):
                yield f"data: {json.dumps(events[index])}\n\n"
                index += 1
            if done or time.time() > deadline:
                break
            time.sleep(0.15)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/{workbook_id}/overview")
def get_overview(workbook_id: str):
    """Workbook explanation + stats + warnings."""
    filename, _stored_path, result = get_ready_result(workbook_id)
    return {
        "workbook_id": workbook_id,
        "filename": filename,
        "status": STATUS_READY,
        "explanation": result["explanations"]["workbook"],
        "stats": result["stats"],
        "warnings": result["warnings"],
        "issues_by_severity": result["stats"]["issues_by_severity"],
    }


@router.get("/{workbook_id}/sheets/{name}")
def get_sheet(workbook_id: str, name: str):
    """Groups + explanations + issues on one sheet."""
    _filename, _stored_path, result = get_ready_result(workbook_id)
    if name not in result["stats"]["sheets"]:
        raise HTTPException(status_code=404, detail=f"Sheet {name!r} not found.")
    explanations = result["explanations"]["groups"]
    groups = [
        {**group, "explanation": explanations.get(group["id"])}
        for group in result["groups"]
        if group["sheet"] == name
    ]
    issues = [
        issue
        for issue in result["issues"]
        if issue["ref"]["sheet"] == name
    ]
    inputs = [
        entry
        for entry in result.get("inputs", [])
        if entry.get("sheet") == name
    ]
    return {
        "workbook_id": workbook_id,
        "sheet": name,
        "explanation": result["explanations"]["sheets"].get(name),
        "groups": groups,
        "issues": issues,
        "inputs": inputs,
    }


@router.get("/{workbook_id}/issues")
def get_issues(
    workbook_id: str,
    severity: str | None = Query(default=None),
):
    """Issues, optionally filtered by severity."""
    _filename, _stored_path, result = get_ready_result(workbook_id)
    if severity is not None and severity not in ("high", "medium", "low"):
        raise HTTPException(
            status_code=422, detail="severity must be high, medium or low."
        )
    issues = result["issues"]
    if severity is not None:
        issues = [i for i in issues if i["severity"] == severity]
    return {"workbook_id": workbook_id, "total": len(issues), "issues": issues}


def _sheet_graph_view(graph) -> dict[str, Any]:
    per_sheet: dict[str, dict[str, int]] = {}
    for _node, data in graph.nodes(data=True):
        info = per_sheet.setdefault(
            data.get("sheet", "?"),
            {"formulas": 0, "inputs": 0, "outputs": 0},
        )
        kind = data.get("kind")
        if kind == "formula":
            info["formulas"] += 1
        elif kind == "output":
            info["outputs"] += 1
        else:
            info["inputs"] += 1
    edge_set: set[tuple[str, str]] = set()
    for source, target in graph.edges:
        s_sheet = graph.nodes[source].get("sheet", "?")
        t_sheet = graph.nodes[target].get("sheet", "?")
        if s_sheet != t_sheet:
            edge_set.add((s_sheet, t_sheet))
    return {
        "level": "sheet",
        "nodes": [
            {"id": sheet, **counts} for sheet, counts in sorted(per_sheet.items())
        ],
        "edges": [
            {"source": s, "target": t} for s, t in sorted(edge_set)
        ],
    }


def _group_graph_view(graph, groups: list[dict[str, Any]]) -> dict[str, Any]:
    cell_to_group: dict[str, str] = {}
    nodes: list[dict[str, Any]] = []
    for group in groups:
        nodes.append(
            {
                "id": group["id"],
                "type": "group",
                "sheet": group["sheet"],
                "cells": group["cells"],
                "sample_formula": group["sample_formula"],
            }
        )
        for address in group["cells"]:
            cell_to_group[f"{group['sheet']}!{address}"] = group["id"]
    for node, data in graph.nodes(data=True):
        if node in cell_to_group:
            continue
        nodes.append(
            {
                "id": node,
                "type": data.get("kind", "input"),
                "sheet": data.get("sheet"),
                "address": data.get("address"),
                "formula": data.get("formula"),
            }
        )

    def _owner(node: str) -> str:
        return cell_to_group.get(node, node)

    edge_set: set[tuple[str, str]] = set()
    for source, target in graph.edges:
        mapped = (_owner(source), _owner(target))
        if mapped[0] != mapped[1]:
            edge_set.add(mapped)
    nodes.sort(key=lambda n: (n.get("sheet", ""), n["id"]))
    return {
        "level": "group",
        "nodes": nodes,
        "edges": [
            {"source": s, "target": t} for s, t in sorted(edge_set)
        ],
    }


@router.get("/{workbook_id}/graph")
def get_graph(
    workbook_id: str,
    level: str = Query(default="sheet"),
):
    """Nodes and edges for the dependency map (sheet or group level)."""
    if level not in ("sheet", "group"):
        raise HTTPException(
            status_code=422, detail="level must be 'sheet' or 'group'."
        )
    _filename, stored_path, result = get_ready_result(workbook_id)
    graph = build_graph(read_workbook(stored_path))
    if level == "sheet":
        return {"workbook_id": workbook_id, **_sheet_graph_view(graph)}
    return {
        "workbook_id": workbook_id,
        **_group_graph_view(graph, result["groups"]),
    }


__all__ = [
    "drop_progress",
    "emit_progress",
    "get_ready_result",
    "seed_progress",
    "stored_path_for",
]
