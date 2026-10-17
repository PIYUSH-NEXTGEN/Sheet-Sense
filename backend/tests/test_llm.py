"""Phase 4 LLM tests — everything mocked; pass with Ollama not installed.

Covers: schema validation, schema-format fallback, retry-then-placeholder,
cache hit on second run, hallucinated citation dropping, prompt versions,
and pipeline continuity when the model fails. The single live test is
marked ``ollama`` and skips unless a local server is reachable.
"""

import json
import os

import pytest

from app import config as app_config
from app.core.llm import cache as llm_cache
from app.core.llm import prompts
from app.core.llm.cache import cache_get, cache_key, cache_put
from app.core.llm.client import LLMError, OllamaClient, ollama_status
from app.core.llm.explainer import (
    PLACEHOLDER_TEXT,
    explain_groups,
    group_facts,
)
from app.core.llm.schemas import (
    GroupExplanation,
    validate_cited_cells,
)
from app.core.parser.reader import read_workbook
from app.core.pipeline import default_client_factory, run_analysis
from conftest import DIRTY_XLSX, FakeLLMClient


class FakeResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeHTTP:
    """Scripted transport: list of FakeResp or Exceptions, plus a log."""

    def __init__(self, script: list):
        self.script = list(script)
        self.requests: list[dict] = []

    def post(self, url, json=None, timeout=None):
        self.requests.append({"url": url, "json": json, "timeout": timeout})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok(payload: dict) -> FakeResp:
    return FakeResp(200, {"message": {"content": json.dumps(payload)}})


def test_timing_log_records_call_stats(tmp_path, monkeypatch):
    log = tmp_path / "timings.jsonl"
    monkeypatch.setenv("SHEETSENSE_TIMING_LOG", str(log))
    http = FakeHTTP(
        [
            FakeResp(
                200,
                {
                    "message": {"content": json.dumps({"summary": "S.", "plain_formula": "P."})},
                    "prompt_eval_count": 40,
                    "eval_count": 25,
                    "load_duration": 1000,
                    "eval_duration": 2000,
                    "total_duration": 3000,
                },
            )
        ]
    )
    client = OllamaClient(model="m", http=http)
    client.chat_structured("explain this", GroupExplanation)
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["kind"] == "GroupExplanation"
    assert entry["prompt_chars"] == len("explain this")
    assert entry["wall_s"] >= 0
    assert entry["prompt_eval_count"] == 40
    assert entry["eval_count"] == 25
    assert entry["load_duration"] == 1000
    assert entry["eval_duration"] == 2000
    assert entry["total_duration"] == 3000


def test_no_timing_log_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("SHEETSENSE_TIMING_LOG", raising=False)
    http = FakeHTTP([_ok({"summary": "S.", "plain_formula": "P."})])
    client = OllamaClient(model="m", http=http)
    client.chat_structured("explain this", GroupExplanation)
    assert list(tmp_path.iterdir()) == []


def test_chat_structured_validates_schema():
    http = FakeHTTP([_ok({"summary": "S.", "plain_formula": "P."})])
    client = OllamaClient(model="m", http=http)
    out = client.chat_structured("explain this", GroupExplanation)
    assert out == {"summary": "S.", "plain_formula": "P."}
    req = http.requests[0]["json"]
    assert req["model"] == "m"
    assert req["stream"] is False
    assert req["options"] == {"temperature": 0}
    assert [m["role"] for m in req["messages"]] == ["user"]
    assert isinstance(req["format"], dict)  # schema first
    assert req["format"]["type"] == "object"


def test_schema_format_fallback_to_json():
    http = FakeHTTP(
        [
            FakeResp(400, {"error": "unsupported format, must be json"}),
            _ok({"summary": "S.", "plain_formula": "P."}),
        ]
    )
    client = OllamaClient(model="m", http=http)
    out = client.chat_structured("explain this", GroupExplanation)
    assert out["summary"] == "S."
    assert http.requests[1]["json"]["format"] == "json"


def test_retry_once_then_llm_error():
    http = FakeHTTP(
        [
            FakeResp(200, {"message": {"content": "not json at all"}}),
            FakeResp(200, {"message": {"content": "{{{broken"}}),
        ]
    )
    client = OllamaClient(model="m", http=http)
    with pytest.raises(LLMError):
        client.chat_structured("explain this", GroupExplanation)
    assert len(http.requests) == 2


def test_retry_recovers_on_second_try():
    http = FakeHTTP(
        [
            FakeResp(200, {"message": {"content": "oops"}}),
            _ok({"summary": "S.", "plain_formula": "P."}),
        ]
    )
    client = OllamaClient(model="m", http=http)
    assert client.chat_structured("hi", GroupExplanation)["summary"] == "S."
    assert len(http.requests) == 2


def test_transport_error_raises_llm_error():
    http = FakeHTTP([ConnectionError("refused")])
    with pytest.raises(LLMError):
        OllamaClient(model="m", http=http).chat_structured(
            "hi", GroupExplanation
        )


def test_missing_model_name_raises_without_http(monkeypatch):
    monkeypatch.setattr(app_config, "MODEL_NAME", "")
    http = FakeHTTP([])
    with pytest.raises(LLMError):
        OllamaClient(model="", http=http).chat_structured("hi", GroupExplanation)
    assert http.requests == []


def _model_groups(wb):
    """Groups that need the model (templates must not cover them)."""
    from app.core.grouping.patterns import group_formulas
    from app.core.llm.templates import render_group

    return [g for g in group_formulas(wb) if render_group(g, wb) is None]


def test_explainer_placeholder_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    wb = read_workbook(DIRTY_XLSX)

    groups = _model_groups(wb)[:2]
    out = explain_groups(groups, wb, FakeLLMClient(fail=True))
    assert len(out) == 2
    for expl in out.values():
        assert expl.text == PLACEHOLDER_TEXT
        assert expl.prompt_version == prompts.PROMPT_VERSION


def test_cache_hit_on_second_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    wb = read_workbook(DIRTY_XLSX)

    groups = _model_groups(wb)[:2]
    fake = FakeLLMClient()
    first = explain_groups(groups, wb, fake)
    assert len(fake.calls) == 1  # one batched call for the same-sheet chunk
    fake.calls.clear()
    second = explain_groups(groups, wb, fake)
    assert fake.calls == []  # served from SQLite, zero model calls
    assert [e.text for e in second.values()] == [
        e.text for e in first.values()
    ]


def test_pipeline_continues_with_placeholders(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    events: list = []
    result = run_analysis(
        "w1",
        DIRTY_XLSX,
        "harbor-supply-pricing.xlsx",
        emit=lambda s, p, d: events.append((s, p)),
        make_client=lambda: FakeLLMClient(fail=True),
    )
    assert len(result["issues"]) == 6  # deterministic facts unaffected
    assert result["explanations"]["workbook"]["text"] == PLACEHOLDER_TEXT
    from app.core.grouping.patterns import group_formulas as _groups
    from app.core.llm.templates import render_group as _render

    wb = read_workbook(DIRTY_XLSX)
    by_id = {g.id: g for g in _groups(wb)}
    for gid, g in result["explanations"]["groups"].items():
        if _render(by_id[gid], wb) is None:
            assert g["text"] == PLACEHOLDER_TEXT
        else:
            assert g["source"] == "template"  # templates need no model


def test_pipeline_uses_fake_model_text(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    result = run_analysis(
        "w1",
        DIRTY_XLSX,
        "harbor-supply-pricing.xlsx",
        emit=lambda s, p, d: None,
        make_client=lambda: FakeLLMClient(),
    )
    assert result["explanations"]["workbook"]["model"] == "fake-test-model"
    assert result["explanations"]["workbook"]["text"] == "Fake overview."


def test_hallucinated_citations_dropped():
    assert validate_cited_cells(
        ["S!A1", "S!ZZZ9", "S!A1", "Other!B2"], {"S!A1", "Other!B2"}
    ) == ["S!A1", "Other!B2"]


def test_prompts_have_version_and_guardrail():
    assert prompts.PROMPT_VERSION == "v1"
    facts = {
        "sample_formula": "=A1*2",
        "column_header": "H",
        "input_labels": {},
        "sample_values": [],
        "cell_count": 1,
        "cell_range": "S!A1",
    }
    for text in (
        prompts.group_prompt(facts),
        prompts.sheet_prompt({"sheet": "S"}),
        prompts.workbook_prompt({"sheet_summaries": {}}),
    ):
        assert "Use only the facts provided" in text


def test_group_facts_are_a_small_bundle():
    wb = read_workbook(DIRTY_XLSX)
    from app.core.grouping.patterns import group_formulas

    group = group_formulas(wb)[0]
    facts = group_facts(group, wb)
    assert set(facts) == {
        "sample_formula",
        "column_header",
        "input_labels",
        "sample_values",
        "cell_count",
        "cell_range",
    }
    assert len(facts["sample_values"]) <= 3


def test_cache_roundtrip_and_key_stability(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert cache_get("nope") is None
    key = cache_key("group", "payload", "m", "v1")
    cache_put(key, {"summary": "S.", "plain_formula": "P."})
    assert cache_get(key) == {"summary": "S.", "plain_formula": "P."}
    assert cache_key("group", "payload", "m", "v1") == key
    assert cache_key("sheet", "payload", "m", "v1") != key


def test_default_factory_none_without_model(monkeypatch):
    monkeypatch.setattr(app_config, "MODEL_NAME", "")
    assert default_client_factory() is None


def test_default_factory_builds_client(monkeypatch):
    monkeypatch.setattr(app_config, "MODEL_NAME", "gemma3:4b")
    client = default_client_factory()
    assert isinstance(client, OllamaClient)
    assert client.model == "gemma3:4b"


def test_concurrent_cache_access_no_init_race(tmp_path, monkeypatch):
    import threading

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    errors: list = []

    def work(i: int) -> None:
        try:
            cache_put(f"k{i % 4}", {"n": i})
            cache_get(f"k{i % 4}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


@pytest.mark.ollama
def test_real_ollama_group_explanation(tmp_path, monkeypatch):
    """Live check (skipped unless Ollama is reachable with the model)."""
    # Fresh DATA_DIR so this always exercises the real HTTP path, not cache.
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    reachable, models = ollama_status()
    if not reachable:
        pytest.skip("Ollama not reachable at localhost:11434")
    model = os.environ.get("MODEL_NAME") or app_config.MODEL_NAME
    if not model or model not in models:
        pytest.skip(f"model {model!r} not installed")
    wb = read_workbook(DIRTY_XLSX)
    from app.core.grouping.patterns import group_formulas

    group = next(
        g
        for g in group_formulas(wb)
        if g.sheet == "Pricing" and g.cells[0] == "C2"
    )
    out = explain_groups([group], wb, OllamaClient(model=model))
    text = out[group.id].text
    assert isinstance(text, str) and len(text) > 10
    print(f"\nLIVE group explanation: {text}")
