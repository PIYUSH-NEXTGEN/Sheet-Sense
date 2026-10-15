"""Workbook upload/list/delete endpoints (Phase 3).

Uploads are validated by extension AND by opening with openpyxl; ``.xlsm``
macro workbooks are rejected with a clear error. Legacy ``.xls`` files are
converted locally via LibreOffice when available. Files are stored under
``DATA_DIR/uploads`` with random names. ``MAX_FILE_MB`` is enforced here;
``MAX_CELLS`` is enforced by the reader at analyze time.
"""

from __future__ import annotations

import secrets
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from openpyxl import load_workbook

from .. import config as app_config
from ..core.convert import ConvertError, convert_xls_to_xlsx
from ..db.session import init_db, session_scope, uploads_dir
from ..db.tables import (
    STATUS_UPLOADED,
    WorkbookRow,
)

CONVERSION_NOTICE = (
    "Uploaded as a legacy .xls file and converted locally; "
    "any macros were dropped. Verify totals against the original."
)

router = APIRouter()


def _stored_path(stored_name: str) -> Path:
    return uploads_dir() / stored_name


@router.post("")
async def upload_workbook(file: UploadFile = File(...)):
    """Multipart upload ``.xlsx`` (or legacy ``.xls``); returns ``workbook_id``."""
    filename = (file.filename or "").strip()
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in (".xlsx", ".xls"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Only .xlsx workbooks are accepted (got {filename!r}). "
                "Macro workbooks (.xlsm) are unsupported in v1 — please "
                "save a macro-free .xlsx copy."
            ),
        )
    data = await file.read()
    limit = int(app_config.MAX_FILE_MB * 1024 * 1024)
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File is {len(data) / (1024 * 1024):.1f} MB, above the "
                f"{app_config.MAX_FILE_MB:g} MB limit."
            ),
        )
    converted = False
    if suffix == ".xls":
        with tempfile.TemporaryDirectory(prefix="ss-xls-") as tmp:
            src = Path(tmp) / "upload.xls"
            src.write_bytes(data)
            try:
                converted_path = convert_xls_to_xlsx(src, Path(tmp))
            except ConvertError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            data = converted_path.read_bytes()
        if len(data) > limit:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Converted file exceeds the "
                    f"{app_config.MAX_FILE_MB:g} MB limit."
                ),
            )
        converted = True
    init_db()
    stored_name = f"{uuid.uuid4().hex}.xlsx"
    path = _stored_path(stored_name)
    path.write_bytes(data)
    try:
        wb = load_workbook(path, read_only=True, data_only=False)
        wb.close()
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise HTTPException(
            status_code=422,
            detail=f"{filename!r} is not a readable .xlsx workbook.",
        )
    workbook_id = secrets.token_hex(8)
    with session_scope() as session:
        # Same filename re-uploaded replaces the previous entry, so the
        # list never fills with duplicates of one file.
        old_rows = (
            session.query(WorkbookRow)
            .filter(WorkbookRow.filename == filename)
            .all()
        )
        old_ids = [old.id for old in old_rows]
        for old in old_rows:
            try:
                _stored_path(old.stored_name).unlink(missing_ok=True)
            except OSError:
                pass
            session.delete(old)
        session.add(
            WorkbookRow(
                id=workbook_id,
                filename=filename,
                stored_name=stored_name,
                size_bytes=len(data),
                status=STATUS_UPLOADED,
            )
        )
    from .analysis import drop_progress, note_conversion, seed_progress

    for old_id in old_ids:
        drop_progress(old_id)
    seed_progress(workbook_id)
    if converted:
        note_conversion(workbook_id, CONVERSION_NOTICE)
    return {
        "workbook_id": workbook_id,
        "filename": filename,
        "status": STATUS_UPLOADED,
        "converted": converted,
    }


@router.get("")
def list_workbooks():
    """List saved analyses."""
    init_db()
    with session_scope() as session:
        rows = (
            session.query(WorkbookRow).order_by(WorkbookRow.created_at).all()
        )
        return {
            "workbooks": [
                {
                    "workbook_id": row.id,
                    "filename": row.filename,
                    "status": row.status,
                    "size_bytes": row.size_bytes,
                    "created_at": row.created_at.isoformat()
                    if row.created_at
                    else None,
                    "error": row.error,
                }
                for row in rows
            ]
        }


@router.delete("/{workbook_id}")
def delete_workbook(workbook_id: str):
    """Delete workbook, stored file, and analysis data."""
    with session_scope() as session:
        row = session.get(WorkbookRow, workbook_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Workbook not found.")
        stored_name = row.stored_name
        session.delete(row)
    try:
        _stored_path(stored_name).unlink(missing_ok=True)
    except OSError:
        pass
    from .analysis import drop_progress

    drop_progress(workbook_id)
    return {"deleted": workbook_id}
