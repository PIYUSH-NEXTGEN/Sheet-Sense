"""Batched group explanations (mocked; pass without Ollama)."""

import json
import re

import pytest

from app import config as app_config
from app.core.grouping.patterns import group_formulas
from app.core.llm.client import OllamaClient
from app.core.llm.explainer import PLACEHOLDER_TEXT, explain_groups
from app.core.parser.reader import read_workbook
from conftest import DIRTY_XLSX


class FakeResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self, script: list):
        self.script = list(script)
        self.requests: list[dict] = []

    def post(self, url, json=None, timeout=None):
        self.requests.append({"url": url, "json": json, "timeout": timeout})
        return self.script.pop(0)


def _ok(payload: dict) -> FakeResp:
    return FakeResp(200, {"message": {"content": json.dumps(payload)}})


def _item(gid: str, n: int = 0) -> dict:
    return {"group_id": gid, "summary": f"S{n} {gid}.", "plain_formula": f"P{n}."}


def _model_groups():
    from app.core.llm.templates import render_group

    wb = read_workbook(DIRTY_XLSX)
    groups = group_formulas(wb)
    picked = [g for g in groups if g.sheet == "Pricing" and render_group(g, wb) is None]
    assert len(picked) == 3  # C2, D2, C14
    return wb, picked


def _requested_ids(http: FakeHTTP, index: int = -1) -> list[str]:
    prompt = http.requests[index]["json"]["messages"][0]["content"]
    return re.findall(r'"group_id": "([0-9a-f]{16})"', prompt)


def test_full_batch_one_call(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    wb, groups = _model_groups()
    ids = [g.id for g in groups]
    http = FakeHTTP([_ok({"items": [_item(i, n) for n, i in enumerate(ids)]})])
    out = explain_groups(groups, wb, OllamaClient(model="m", http=http, workers=1))
    assert len(http.requests) == 1
    assert [out[i].text for i in ids] == [f"S{n} {i}." for n, i in enumerate(ids)]
    assert all(out[i].source == "model" for i in ids)


def test_batch_respects_configured_chunk_size(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app_config, "LLM_BATCH_SIZE", 2)
    wb, groups = _model_groups()
    ids = [g.id for g in groups]
    http = FakeHTTP(
        [
            _ok({"items": [_item(ids[0]), _item(ids[1])]}),
            _ok({"items": [_item(ids[2])]}),
        ]
    )
    out = explain_groups(groups, wb, OllamaClient(model="m", http=http, workers=1))
    assert len(http.requests) == 2
    assert set(out) == set(ids)


def test_missing_id_falls_back_to_single(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    wb, groups = _model_groups()
    ids = [g.id for g in groups]
    missing = ids[0]
    http = FakeHTTP(
        [
            _ok({"items": [_item(i) for i in ids[1:]]}),
            _ok({"summary": "Solo.", "plain_formula": "S."}),
        ]
    )
    out = explain_groups(groups, wb, OllamaClient(model="m", http=http, workers=1))
    assert len(http.requests) == 2
    assert out[missing].text == "Solo."
    assert all(out[i].text.startswith("S") for i in ids[1:])


def test_unknown_and_duplicate_ids_handled(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    wb, groups = _model_groups()
    ids = [g.id for g in groups]
    http = FakeHTTP(
        [
            _ok(
                {
                    "items": [_item(ids[0]), _item(ids[0]), _item("bogus"),
                              _item(ids[1]), _item(ids[2])]
                }
            )
        ]
    )
    out = explain_groups(groups, wb, OllamaClient(model="m", http=http, workers=1))
    assert len(http.requests) == 1  # no fallback calls needed
    assert set(out) == set(ids)
    assert "bogus" not in out


def test_partial_cache_hit_requests_only_uncached(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    wb, groups = _model_groups()
    ids = [g.id for g in groups]
    warm = OllamaClient(model="m", http=FakeHTTP([_ok({"items": [_item(ids[0])]})]), workers=1)
    explain_groups([groups[0]], wb, warm)
    http = FakeHTTP([_ok({"items": [_item(ids[1]), _item(ids[2])]})])
    out = explain_groups(groups, wb, OllamaClient(model="m", http=http, workers=1))
    requested = _requested_ids(http)
    assert requested == ids[1:]
    assert set(out) == set(ids)


def test_invalid_json_then_placeholder(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    wb, groups = _model_groups()
    one = [groups[0]]
    http = FakeHTTP(
        [
            FakeResp(200, {"message": {"content": "junk" }}),
            FakeResp(200, {"message": {"content": "junk" }}),
            FakeResp(200, {"message": {"content": "junk" }}),
            FakeResp(200, {"message": {"content": "junk" }}),
        ]
    )
    out = explain_groups(one, wb, OllamaClient(model="m", http=http, workers=1))
    assert len(http.requests) == 4  # batch try+retry, single try+retry
    assert out[one[0].id].text == PLACEHOLDER_TEXT
