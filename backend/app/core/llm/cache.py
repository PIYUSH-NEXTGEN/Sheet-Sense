"""Explanation cache (Phase 4, spec section 7.3).

Key = sha256(normalized formula + labels JSON + model name + prompt
version), namespaced per explanation kind. Stored in SQLite so identical
requests never hit the model twice — including across restarts and reruns.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from ...db.session import session_scope
from ...db.tables import LLMCacheRow

# Serializes concurrent SQLite access from the explainer worker pool.
_cache_lock = threading.Lock()


def cache_key(
    kind: str, payload: str, model: str, prompt_version: str
) -> str:
    """Deterministic cache key for one explanation request."""
    return hashlib.sha256(
        "\x00".join([kind, payload, model, prompt_version]).encode("utf-8")
    ).hexdigest()


def group_payload(pattern_r1c1: str, labels: dict[str, str]) -> str:
    """Cache payload for a group: normalized formula + labels JSON."""
    return pattern_r1c1 + "\x00" + json.dumps(
        labels, sort_keys=True, ensure_ascii=True, default=str
    )


def cache_get(key: str) -> dict[str, Any] | None:
    """Return the cached validated response, or None on miss."""
    with _cache_lock, session_scope() as session:
        row = session.get(LLMCacheRow, key)
        if row is None:
            return None
        try:
            value = json.loads(row.value_json)
        except Exception:
            return None
        return value if isinstance(value, dict) else None


def cache_put(key: str, value: dict[str, Any]) -> None:
    """Store a validated response (overwrites on key reuse)."""
    with _cache_lock, session_scope() as session:
        row = session.get(LLMCacheRow, key)
        payload = json.dumps(value, sort_keys=True, ensure_ascii=True)
        if row is None:
            session.add(LLMCacheRow(key=key, value_json=payload))
        else:
            row.value_json = payload
