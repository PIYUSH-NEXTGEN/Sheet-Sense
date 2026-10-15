"""Pytest bootstrap for Phase 1: import path + fixture availability."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _ensure_fixtures() -> None:
    needed = ["clean.xlsx", "dirty.xlsx", "expected_issues.json"]
    if all((FIXTURE_DIR / name).exists() for name in needed):
        return
    from fixtures.make_fixture import make_fixtures

    make_fixtures(FIXTURE_DIR)


_ensure_fixtures()

CLEAN_XLSX = str(FIXTURE_DIR / "clean.xlsx")
DIRTY_XLSX = str(FIXTURE_DIR / "dirty.xlsx")
EXPECTED_ISSUES = str(FIXTURE_DIR / "expected_issues.json")


class FakeLLMClient:
    """Deterministic stand-in for OllamaClient (never touches network).

    Returns canned fields covering every explanation schema, so the same
    fake works for group/sheet/workbook calls. ``fail=True`` raises on
    every call to exercise the placeholder path.
    """

    CANNED = {
        "summary": "Fake summary.",
        "plain_formula": "Fake times Fake.",
        "purpose": "Fake purpose.",
        "key_inputs": ["Fake input"],
        "key_outputs": ["Fake output"],
        "overview": "Fake overview.",
        "reading_order": ["FakeSheet"],
    }

    def __init__(self, model: str = "fake-test-model", fail: bool = False):
        self.model = model
        self.workers = 1
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def chat_structured(self, user_message: str, schema):
        from app.core.llm.client import LLMError

        self.calls.append((user_message, schema.__name__))
        if self.fail:
            raise LLMError("fake failure")
        return schema(**self.CANNED).model_dump()
