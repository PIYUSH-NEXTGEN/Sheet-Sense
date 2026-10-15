"""SQLite session management (Phase 3).

The data directory is resolved from the live ``DATA_DIR`` environment
variable on every call (falling back to ``app.config.DATA_DIR``), so tests
and embedders can redirect storage without import-order tricks. Engines are
cached per directory. SQLite runs with ``check_same_thread=False`` plus one
short-lived Session per call because analysis runs in a background thread.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .. import config as app_config
from .tables import Base


def data_dir() -> Path:
    """Live data directory (env override wins over import-time config)."""
    return Path(os.environ.get("DATA_DIR", str(app_config.DATA_DIR)))


def uploads_dir() -> Path:
    return data_dir() / "uploads"


def db_path() -> Path:
    return data_dir() / "sheetsense.db"


_engines: dict[str, object] = {}
_init_lock = threading.Lock()


def get_engine():
    key = str(db_path())
    engine = _engines.get(key)
    if engine is None:
        init_db()
        from sqlalchemy import create_engine as _create

        engine = _create(
            f"sqlite:///{key}", connect_args={"check_same_thread": False}
        )
        _engines[key] = engine
    return engine


def init_db() -> Path:
    """Create directories and tables; idempotent and thread-safe."""
    with _init_lock:
        data_dir().mkdir(parents=True, exist_ok=True)
        uploads_dir().mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            f"sqlite:///{db_path()}", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(engine)
        engine.dispose()
        return db_path()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a Session with commit/rollback handling (one per call/thread)."""
    from sqlalchemy.orm import sessionmaker

    init_db()
    factory = sessionmaker(bind=get_engine())
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
