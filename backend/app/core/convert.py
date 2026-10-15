"""Legacy ``.xls`` → ``.xlsx`` conversion via LibreOffice (opt-in).

Why a converter and not a reader: openpyxl cannot parse legacy BIFF
``.xls`` at all, and pure-Python ``.xls`` readers only yield cached values,
not formula text. SheetSense *is* formula analysis (graph, patterns, every
detector), so a values-only import would silently produce empty results.
LibreOffice converts faithfully, formulas included (and usually adds cached
values as a bonus). Macros do not survive: every converted analysis carries
a warning saying so.

Nothing here runs unless the user uploads ``.xls`` *and* ``soffice`` (or
``libreoffice``) is on PATH. Otherwise uploads fail fast with instructions.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

CONVERT_TIMEOUT_S = 120


class ConvertError(Exception):
    """Raised when legacy conversion is unavailable or fails."""


def soffice_path() -> str | None:
    """Path to a LibreOffice binary, or None when not installed."""
    return shutil.which("soffice") or shutil.which("libreoffice")


def convert_xls_to_xlsx(src: Path, out_dir: Path) -> Path:
    """Convert ``src`` (.xls) to ``out_dir/<stem>.xlsx``. Never uses a shell."""
    exe = soffice_path()
    if exe is None:
        raise ConvertError(
            "Automatic .xls conversion needs LibreOffice installed "
            "(https://libreoffice.org/download) and on PATH. Alternatively, "
            "open the file in Excel and use Save As to make an .xlsx copy, "
            "then upload that."
        )
    try:
        proc = subprocess.run(
            [exe, "--headless", "--convert-to", "xlsx", "--outdir",
             str(out_dir), str(src)],
            capture_output=True,
            text=True,
            timeout=CONVERT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConvertError(
            f"LibreOffice conversion timed out after {CONVERT_TIMEOUT_S}s."
        ) from exc
    except OSError as exc:
        raise ConvertError(f"Could not start LibreOffice: {exc}") from exc
    produced = out_dir / f"{src.stem}.xlsx"
    if proc.returncode != 0 or not produced.is_file():
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        hint = f" LibreOffice said: {detail[-1]}" if detail else ""
        raise ConvertError(f"LibreOffice could not convert this file.{hint}")
    return produced
