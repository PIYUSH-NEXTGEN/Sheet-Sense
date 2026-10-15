"""Converter tests — LibreOffice itself is never required.

The ``soffice`` binary and ``subprocess.run`` are stubbed; these tests cover
detection, success, failure, and timeout handling only.
"""

from pathlib import Path

import pytest

from app.core.convert import ConvertError, convert_xls_to_xlsx
from conftest import DIRTY_XLSX


def test_soffice_missing_raises_helpful_error(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.convert.soffice_path", lambda: None)
    with pytest.raises(ConvertError, match="LibreOffice"):
        convert_xls_to_xlsx(tmp_path / "a.xls", tmp_path)


def _ok_run_factory(payload: bytes):
    def _run(cmd, **kwargs):
        out_dir = Path(cmd[cmd.index("--outdir") + 1])
        src = Path(cmd[-1])
        (out_dir / f"{src.stem}.xlsx").write_bytes(payload)
        return _Result(0, "", "")
    return _run


class _Result:
    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_convert_success(monkeypatch, tmp_path):
    import subprocess

    monkeypatch.setattr("app.core.convert.soffice_path", lambda: "/fake/soffice")
    monkeypatch.setattr(
        subprocess, "run", _ok_run_factory(Path(DIRTY_XLSX).read_bytes())
    )
    src = tmp_path / "book.xls"
    src.write_bytes(b"fake-ole2")
    out = convert_xls_to_xlsx(src, tmp_path)
    assert out.name == "book.xlsx"
    assert out.read_bytes() == Path(DIRTY_XLSX).read_bytes()


def test_convert_failure_reports_stderr(monkeypatch, tmp_path):
    import subprocess

    monkeypatch.setattr("app.core.convert.soffice_path", lambda: "/fake/soffice")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _Result(1, "", "E: bad file")
    )
    src = tmp_path / "book.xls"
    src.write_bytes(b"fake-ole2")
    with pytest.raises(ConvertError, match="bad file"):
        convert_xls_to_xlsx(src, tmp_path)


def test_convert_timeout(monkeypatch, tmp_path):
    import subprocess

    monkeypatch.setattr("app.core.convert.soffice_path", lambda: "/fake/soffice")

    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="soffice", timeout=1)

    monkeypatch.setattr(subprocess, "run", _boom)
    src = tmp_path / "book.xls"
    src.write_bytes(b"fake-ole2")
    with pytest.raises(ConvertError, match="timed out"):
        convert_xls_to_xlsx(src, tmp_path)
