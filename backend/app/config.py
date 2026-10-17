"""Runtime configuration (Phases 1+4).

All values come from environment variables, optionally via a ``.env`` file
(``backend/.env``, repo-root ``.env``, or ``./.env`` — explicit environment
wins). In particular the model name is never hardcoded here or anywhere
else: the backend reads ``MODEL_NAME`` and reports it as missing (see the
SetupPage / health check) when unset. Run ``ollama list`` and pick an
installed Gemma variant, e.g. ``MODEL_NAME=gemma3:4b``.
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal ``.env`` loader (no extra dependency).

    Only fills variables not already present in the environment.
    """
    here = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / ".env",
        here.parent / ".env",  # backend/.env
        here.parent.parent / ".env",  # repo-root .env
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if (len(value) >= 2 and value[0] == value[-1]
                    and value[0] in ("'", '"')):
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

# Base URL of the local Ollama server. No other network destination is used.
OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Open-weight model served by Ollama. Empty by default on purpose: the user
# must pick a Gemma variant their hardware can handle (see README in Phase 7).
MODEL_NAME: str = os.environ.get("MODEL_NAME", "")

# Upload / parse guards.
MAX_FILE_MB: float = float(os.environ.get("MAX_FILE_MB", "10"))
MAX_CELLS: int = int(os.environ.get("MAX_CELLS", "500000"))

# Local persistence directory (SQLite file + uploaded workbooks live here).
DATA_DIR: Path = Path(os.environ.get("DATA_DIR", str(Path.home() / ".sheetsense")))

# Concurrent Ollama calls. Default 1: a stock Ollama server serializes
# requests (OLLAMA_NUM_PARALLEL unset), so a bigger pool adds contention
# without speedup (measured 0.79x at 3 workers). Raise together with the
# server's OLLAMA_NUM_PARALLEL only.
LLM_WORKERS: int = int(os.environ.get("LLM_WORKERS", "1"))

# Per-call HTTP timeout (seconds) for Ollama chat requests.
LLM_TIMEOUT_S: float = float(os.environ.get("LLM_TIMEOUT_S", "180"))

# Groups per sheet explained in a single model call (batching). Kept small
# for a 4B model; raise for bigger models or lower for longer chains.
LLM_BATCH_SIZE: int = int(os.environ.get("LLM_BATCH_SIZE", "6"))
