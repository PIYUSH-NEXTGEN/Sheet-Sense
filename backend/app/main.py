"""FastAPI app entrypoint (Phase 3).

Security: serve on 127.0.0.1 only; CORS allows exactly the Vite dev origin
``http://localhost:5173``. No telemetry, no CDN assets.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config as app_config
from .api import analysis, chat, export, workbooks
from .core.llm.client import ollama_status
from .db.session import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="SheetSense", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(workbooks.router, prefix="/api/workbooks", tags=["workbooks"])
app.include_router(analysis.router, prefix="/api/workbooks", tags=["analysis"])
app.include_router(chat.router, prefix="/api/workbooks", tags=["ask"])
app.include_router(export.router, prefix="/api/workbooks", tags=["export"])


@app.get("/api/health")
def health() -> dict:
    """Backend + Ollama + model status (never raises when Ollama is down)."""
    reachable, models = ollama_status()
    model_name = app_config.MODEL_NAME
    return {
        "backend": "ok",
        "ollama": {"url": app_config.OLLAMA_URL, "reachable": reachable},
        "model": {"name": model_name, "available": bool(model_name) and model_name in models},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
