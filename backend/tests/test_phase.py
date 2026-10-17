"""Phase A/B split tests (mocked; pass without Ollama)."""

import threading
import time

from app.core.pipeline import run_phase_a, run_phase_b
from app.core.parser.reader import read_workbook
from conftest import DIRTY_XLSX, FakeLLMClient
from tests.test_api import DIRTY_BYTES, client  # noqa: F401 (fixture reuse)


def _phase_a():
    events: list = []
    result, context = run_phase_a(
        "w1", DIRTY_XLSX, "w.xlsx", emit=lambda s, p, d: events.append(s)
    )
    return result, context, events


def test_phase_a_usable_without_model():
    result, context, events = _phase_a()
    assert len(result["issues"]) == 6
    assert result["stats"]["n_groups"] == 11
    assert result["pending_groups"], "model-bound groups must be pending"
    assert result["explanation_total"] > len(result["pending_groups"])
    assert any(
        g["source"] == "template"
        for g in result["explanations"]["groups"].values()
    )
    assert events[-1] == "persist"
    assert set(context) >= {"wb", "graph", "groups", "result"}


def test_phase_b_failure_preserves_phase_a():
    result, context, _ = _phase_a()
    issues_before = result["issues"]
    groups_before = result["groups"]
    out = run_phase_b(context, emit=lambda s, p, d: None,
                      make_client=lambda: FakeLLMClient(fail=True))
    assert out["issues"] == issues_before
    assert out["groups"] == groups_before
    assert out["pending_groups"], "still pending after total model failure"
    assert all(
        g["text"] != "" for g in out["explanations"]["groups"].values()
    )


def test_phase_b_completes_with_fake():
    result, context, _ = _phase_a()
    out = run_phase_b(context, emit=lambda s, p, d: None,
                      make_client=lambda: FakeLLMClient())
    assert out["pending_groups"] == []
    assert out["explanations"]["workbook"]["text"] == "Fake overview."


class BlockingFake(FakeLLMClient):
    """Blocks the first model call until released (phase B gating)."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()
        self._blocked_once = False

    def chat_structured(self, user_message, schema):
        if not self._blocked_once:
            self._blocked_once = True
            assert self.gate.wait(timeout=120), "phase B never started"
        return super().chat_structured(user_message, schema)


def test_explaining_status_flow_usable_midway(client, monkeypatch):
    import app.api.chat as chat
    import app.core.pipeline as pipeline

    fake = BlockingFake()
    monkeypatch.setattr(pipeline, "default_client_factory", lambda: fake)
    monkeypatch.setattr(chat, "get_client", lambda: fake)

    from tests.test_api import _upload

    resp = client.post(
        "/api/workbooks", files={"file": ("w.xlsx", DIRTY_BYTES, "x")}
    )
    wid = resp.json()["workbook_id"]
    assert client.post(f"/api/workbooks/{wid}/analyze").status_code == 200

    deadline = time.time() + 120
    while True:
        status = client.get(f"/api/workbooks/{wid}/overview").json()["status"]
        if status == "explaining":
            break
        assert time.time() < deadline, "never entered explaining state"
        time.sleep(0.5)

    # Phase A results usable while phase B is blocked.
    issues = client.get(f"/api/workbooks/{wid}/issues").json()
    assert issues["total"] == 6
    sheet = client.get(f"/api/workbooks/{wid}/sheets/Pricing").json()
    statuses = {g["explanation_status"] for g in sheet["groups"]}
    assert "pending" in statuses

    fake.gate.set()
    deadline = time.time() + 120
    while True:
        ov = client.get(f"/api/workbooks/{wid}/overview").json()
        prog = ov.get("explanation_progress", {})
        if ov["status"] == "ready" and prog.get("explained", 0) >= prog.get("total", 1):
            break
        assert time.time() < deadline, "phase B did not finish"
        time.sleep(1)
    assert ov["explanation_progress"]["total"] > 0
