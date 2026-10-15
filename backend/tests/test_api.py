"""Phase 3 API tests: upload -> analyze -> progress -> overview -> issues ->
graph -> ask -> export -> delete, plus validation and error paths.

Storage is isolated per test via the live ``DATA_DIR`` env override (see
``db.session.data_dir``); no reimport tricks needed.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from conftest import FIXTURE_DIR, FakeLLMClient


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch):
    """All API tests run with a fake model (golden rule 4)."""
    import app.api.chat as chat
    import app.core.pipeline as pipeline

    monkeypatch.setattr(
        pipeline,
        "default_client_factory",
        lambda: FakeLLMClient(),
    )
    monkeypatch.setattr(chat, "get_client", lambda: FakeLLMClient())

DIRTY_BYTES = (FIXTURE_DIR / "dirty.xlsx").read_bytes()
CLEAN_BYTES = (FIXTURE_DIR / "clean.xlsx").read_bytes()
XLSX_MEDIA = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, name="dirty.xlsx", content=DIRTY_BYTES):
    resp = client.post(
        "/api/workbooks",
        files={"file": (name, content, XLSX_MEDIA)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "uploaded"
    return body["workbook_id"]


def _analyze_and_wait(client, workbook_id):
    resp = client.post(f"/api/workbooks/{workbook_id}/analyze")
    assert resp.status_code == 200, resp.text
    # SSE blocks server-side until the background thread finishes.
    progress = client.get(f"/api/workbooks/{workbook_id}/progress")
    assert progress.status_code == 200
    assert progress.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[len("data: "):])
        for line in progress.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events, "no progress events streamed"
    assert events[-1]["percent"] == 100
    return events


def test_health_structure(client):
    body = client.get("/api/health").json()
    assert body["backend"] == "ok"
    assert isinstance(body["ollama"]["reachable"], bool)
    assert isinstance(body["model"]["available"], bool)


def test_full_flow_dirty(client):
    wid = _upload(client)
    events = _analyze_and_wait(client, wid)
    stages = [e["stage"] for e in events]
    for expected in (
        "parse",
        "references",
        "graph",
        "label",
        "group",
        "detect",
        "explain",
        "persist",
    ):
        assert expected in stages

    overview = client.get(f"/api/workbooks/{wid}/overview").json()
    assert overview["filename"] == "dirty.xlsx"
    assert overview["stats"]["n_groups"] == 11
    assert overview["issues_by_severity"] == {"high": 3, "medium": 1, "low": 2}
    assert "cached_values_missing" in overview["warnings"]
    assert overview["explanation"]["model"] == "fake-test-model"
    assert overview["explanation"]["text"] == "Fake overview."

    issues = client.get(f"/api/workbooks/{wid}/issues").json()
    assert issues["total"] == 6
    assert {
        (i["detector"], i["ref"]["sheet"], i["ref"]["address"])
        for i in issues["issues"]
    } == {
        ("hardcoded_constant", "Summary", "B5"),
        ("pattern_break", "Pricing", "C13"),
        ("range_gap", "Summary", "B3"),
        ("orphan_input", "Settings", "B3"),
        ("orphan_input", "Settings", "B4"),
        ("circular", "Summary", "B7"),
    }
    high = client.get(f"/api/workbooks/{wid}/issues?severity=high").json()
    assert high["total"] == 3

    sheet_graph = client.get(f"/api/workbooks/{wid}/graph").json()
    assert sheet_graph["level"] == "sheet"
    assert {n["id"] for n in sheet_graph["nodes"]} == {
        "Inputs",
        "Settings",
        "Pricing",
        "Summary",
    }
    assert sheet_graph["edges"], "expected cross-sheet edges"
    group_graph = client.get(
        f"/api/workbooks/{wid}/graph?level=group"
    ).json()
    assert group_graph["level"] == "group"
    assert len(group_graph["nodes"]) > len(sheet_graph["nodes"])

    sheet = client.get(f"/api/workbooks/{wid}/sheets/Pricing").json()
    assert sheet["sheet"] == "Pricing"
    assert len(sheet["groups"]) == 5  # A, B, C-low, C-high, D
    assert all("explanation" in g for g in sheet["groups"])
    assert sheet["issues"] and all(
        i["ref"]["sheet"] == "Pricing" for i in sheet["issues"]
    )

    ask = client.post(
        f"/api/workbooks/{wid}/ask",
        json={"question": "Where does the total with surcharge come from?"},
    ).json()
    assert ask["target"] == "Summary!B5"
    assert ask["cited_cells"][0] == "Summary!B5"
    assert any(c["ref"] == "Summary!B5" for c in ask["chain"])
    assert all("formula" in c for c in ask["chain"])

    export = client.get(f"/api/workbooks/{wid}/export?format=md")
    assert export.status_code == 200
    assert "text/markdown" in export.headers["content-type"]
    assert 'filename="dirty.md"' in export.headers["content-disposition"]
    assert "Summary!B5" in export.text
    assert "Suspicious cells to review" in export.text
    assert "| Severity | Detector | Cell | Finding | Formula |" in export.text
    assert "## Limitations" in export.text
    assert "Fake purpose." in export.text  # sheet explanations included
    assert "Original formula" in export.text

    assert client.delete(f"/api/workbooks/{wid}").json() == {"deleted": wid}
    assert client.get(f"/api/workbooks/{wid}/overview").status_code == 404
    assert client.get("/api/workbooks").json() == {"workbooks": []}


def test_full_flow_clean_zero_issues(client):
    wid = _upload(client, name="clean.xlsx", content=CLEAN_BYTES)
    _analyze_and_wait(client, wid)
    assert client.get(f"/api/workbooks/{wid}/issues").json()["total"] == 0
    overview = client.get(f"/api/workbooks/{wid}/overview").json()
    assert overview["issues_by_severity"] == {"high": 0, "medium": 0, "low": 0}


def test_overview_before_analyze_is_409(client):
    wid = _upload(client)
    assert client.get(f"/api/workbooks/{wid}/overview").status_code == 409
    assert client.get(f"/api/workbooks/{wid}/issues").status_code == 409
    assert client.get(f"/api/workbooks/{wid}/graph").status_code == 409


def test_reject_xlsm(client):
    resp = client.post(
        "/api/workbooks", files={"file": ("evil.xlsm", DIRTY_BYTES, XLSX_MEDIA)}
    )
    assert resp.status_code == 400
    assert ".xlsm" in resp.json()["detail"]


def test_reject_garbage_content(client):
    resp = client.post(
        "/api/workbooks", files={"file": ("x.xlsx", b"not a workbook", XLSX_MEDIA)}
    )
    assert resp.status_code == 422


def test_reject_wrong_extension(client):
    resp = client.post(
        "/api/workbooks", files={"file": ("x.csv", b"a,b", "text/csv")}
    )
    assert resp.status_code == 400


def test_unknown_ids_404(client):
    assert client.get("/api/workbooks/nope/overview").status_code == 404
    assert client.get("/api/workbooks/nope/issues").status_code == 404
    assert client.get("/api/workbooks/nope/graph").status_code == 404
    assert client.get("/api/workbooks/nope/progress").status_code == 404
    assert client.get("/api/workbooks/nope/sheets/Pricing").status_code == 404
    assert (
        client.post("/api/workbooks/nope/ask", json={"question": "x"}).status_code
        == 404
    )
    assert client.get("/api/workbooks/nope/export?format=md").status_code == 404
    assert client.delete("/api/workbooks/nope").status_code == 404


def test_invalid_params_422(client):
    wid = _upload(client)
    _analyze_and_wait(client, wid)
    assert (
        client.get(f"/api/workbooks/{wid}/issues?severity=bogus").status_code
        == 422
    )
    assert client.get(f"/api/workbooks/{wid}/graph?level=bogus").status_code == 422
    assert (
        client.get(f"/api/workbooks/{wid}/export?format=pdf").status_code == 422
    )
    assert client.get(f"/api/workbooks/{wid}/sheets/Nope").status_code == 404


def test_ask_without_match(client):
    wid = _upload(client)
    _analyze_and_wait(client, wid)
    body = client.post(
        f"/api/workbooks/{wid}/ask", json={"question": "xyzzy qqq zzz"}
    ).json()
    # No traceable cell: honestly-labeled general answer, never cited.
    assert body["target"] is None
    assert body["cited_cells"] == []
    assert body["answer"] == "Fake answer."
    assert body["traced"] is False


def test_list_shows_uploads(client):
    assert client.get("/api/workbooks").json() == {"workbooks": []}
    wid = _upload(client)
    listed = client.get("/api/workbooks").json()["workbooks"]
    assert [w["workbook_id"] for w in listed] == [wid]
    assert listed[0]["status"] == "uploaded"


def test_sheet_inputs_listed(client):
    wid = _upload(client)
    _analyze_and_wait(client, wid)
    body = client.get(f"/api/workbooks/{wid}/sheets/Inputs").json()
    assert len(body["inputs"]) == 40  # 20 costs + 20 quantities
    first = body["inputs"][0]
    assert set(first) == {
        "sheet", "address", "label_left", "label_above", "value",
        "number_format",
    }
    assert first["label_above"] == "Unit Cost"
    addresses = [i["address"] for i in body["inputs"]]
    assert addresses[0] == "B2" and addresses[-1] == "C21"  # row-major order
    pricing = client.get(f"/api/workbooks/{wid}/sheets/Pricing").json()
    # Dirty C13 is the planted constant inside a formula column.
    assert [(i["address"], i["value"]) for i in pricing["inputs"]] == [
        ("C13", 99.5)
    ]


def test_reupload_same_filename_replaces(client):
    first = _upload(client)
    second = _upload(client)
    assert first != second
    listed = client.get("/api/workbooks").json()["workbooks"]
    assert [w["workbook_id"] for w in listed] == [second]
    assert client.get(f"/api/workbooks/{first}/overview").status_code == 404
