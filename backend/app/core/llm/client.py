"""Ollama chat client (Phase 4, spec section 7.1).

- ``POST {OLLAMA_URL}/api/chat`` with ``stream: false`` and
  ``options: {temperature: 0}``. All instructions go in the **user** message;
  no system role is used.
- Structured output: the pydantic JSON Schema is passed in ``format``. If the
  installed Ollama rejects schema-format, falls back to ``format: "json"``
  plus pydantic validation.
- Invalid JSON is retried once, then a typed ``LLMError`` is raised; callers
  (pipeline/explainer) store "Explanation unavailable" and continue.
- No network destination other than ``OLLAMA_URL`` is ever contacted.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from ... import config as app_config
from .schemas import to_ollama_format


class LLMError(Exception):
    """Typed failure for all model-call problems (transport or content)."""


class LLMClient(Protocol):
    """Minimal interface the explainer needs (fakes implement this in tests)."""

    model: str

    def chat_structured(
        self, user_message: str, schema: type[BaseModel]
    ) -> dict[str, Any]: ...


class _FormatRejected(Exception):
    """The server refused the schema ``format``; retry with ``"json"``."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _record_timing(
    kind: str,
    prompt_chars: int,
    out_chars: int,
    wall_s: float,
    server: dict[str, Any],
) -> None:
    """Append one JSON timing line if SHEETSENSE_TIMING_LOG is set.

    Log-only instrumentation: never raises, never changes call behavior.
    """
    path = os.environ.get("SHEETSENSE_TIMING_LOG", "")
    if not path:
        return
    entry = {
        "kind": kind,
        "prompt_chars": prompt_chars,
        "out_chars": out_chars,
        "wall_s": round(wall_s, 3),
        "prompt_eval_count": server.get("prompt_eval_count"),
        "eval_count": server.get("eval_count"),
        "load_duration": server.get("load_duration"),
        "eval_duration": server.get("eval_duration"),
        "total_duration": server.get("total_duration"),
    }
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


class OllamaClient:
    """Synchronous Ollama client with structured output and one retry."""

    def __init__(
        self,
        base_url: str = "",
        model: str = "",
        workers: int = 0,
        timeout_s: float = 0,
        http: Any | None = None,
    ) -> None:
        self.base_url = base_url or app_config.OLLAMA_URL
        self.model = model or app_config.MODEL_NAME
        self.workers = workers or app_config.LLM_WORKERS
        self.timeout_s = timeout_s or app_config.LLM_TIMEOUT_S
        self._http = http  # injectable fake transport for tests

    def _post(self, payload: dict[str, Any]) -> httpx.Response | Any:
        url = f"{self.base_url}/api/chat"
        if self._http is not None:
            return self._http.post(url, json=payload, timeout=self.timeout_s)
        with httpx.Client(timeout=self.timeout_s) as client:
            return client.post(url, json=payload)

    def _chat_once(
        self, user_message: str, fmt: dict[str, Any] | str
    ) -> tuple[str, dict[str, Any]]:
        try:
            resp = self._post(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": user_message}],
                    "stream": False,
                    "options": {"temperature": 0},
                    "format": fmt,
                }
            )
        except Exception as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        status = getattr(resp, "status_code", 200)
        if status == 400:
            try:
                body = json.dumps(resp.json())
            except Exception:
                body = ""
            if "format" in body.lower():
                raise _FormatRejected(body)
        if status != 200:
            raise LLMError(f"Ollama returned HTTP {status}")
        try:
            data = resp.json()
        except Exception as exc:
            raise LLMError(f"Ollama returned non-JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError("Ollama returned non-JSON")
        content = (data.get("message") or {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("Ollama returned an empty message")
        return content, data

    def chat_structured(
        self, user_message: str, schema: type[BaseModel]
    ) -> dict[str, Any]:
        """Call the model; return the validated response dict.

        Raises :class:`LLMError` after one retry on invalid JSON.
        """
        if not self.model:
            raise LLMError("MODEL_NAME is not configured")
        schema_format = to_ollama_format(schema)
        use_format: dict[str, Any] | str = schema_format
        last_error = "unknown error"
        started = time.perf_counter()
        server_data: dict[str, Any] = {}
        for _attempt in (1, 2):  # initial try + one retry
            try:
                content, server_data = self._chat_once(user_message, use_format)
            except _FormatRejected:
                use_format = "json"
                try:
                    content, server_data = self._chat_once(user_message, use_format)
                except _FormatRejected as exc:  # pragma: no cover
                    raise LLMError(f"Ollama rejects JSON mode: {exc}")
                except LLMError:
                    raise
            try:
                parsed = json.loads(_strip_fences(content))
                validated = schema(**parsed).model_dump()
                _record_timing(
                    schema.__name__,
                    len(user_message),
                    len(content),
                    time.perf_counter() - started,
                    server_data,
                )
                return validated
            except Exception as exc:
                last_error = f"invalid model output: {exc}"
                continue
        raise LLMError(last_error)


def ollama_status(
    base_url: str = "", timeout_s: float = 5.0
) -> tuple[bool, list[str]]:
    """Return (reachable, model names) for the local Ollama server."""
    url = f"{base_url or app_config.OLLAMA_URL}/api/tags"
    try:
        resp = httpx.get(url, timeout=timeout_s)
        if resp.status_code != 200:
            return False, []
        names = [
            name
            for item in resp.json().get("models", [])
            if (name := item.get("name") or item.get("model"))
        ]
        return True, names
    except Exception:
        return False, []
