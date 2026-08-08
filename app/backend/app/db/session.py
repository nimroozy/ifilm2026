from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import get_settings

_engine: Engine | None = None
SessionLocal: sessionmaker = sessionmaker(autocommit=False, autoflush=False)


def _is_memory_sqlite(database_url: str) -> bool:
    """StaticPool is only safe for shared in-memory SQLite (tests)."""
    normalized = database_url.lower()
    return (
        normalized in {"sqlite://", "sqlite:///:memory:"}
        or ":memory:" in normalized
        or "mode=memory" in normalized
    )


def _build_engine(database_url: str) -> Engine:
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    if database_url.startswith("sqlite"):
        if _is_memory_sqlite(database_url):
            return create_engine(
                database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        # File-backed SQLite under concurrent FastAPI requests must not share a
        # single StaticPool connection (corrupts result rows / IndexError).
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=NullPool,
        )

        @event.listens_for(engine, "connect")
        def _sqlite_on_connect(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

        return engine
    return create_engine(database_url, pool_pre_ping=True)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings().database_url)
        SessionLocal.configure(bind=_engine)
    return _engine


class _EngineProxy:
    def connect(self, *args, **kwargs):
        return get_engine().connect(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(get_engine(), item)


engine = _EngineProxy()


def get_db() -> Generator[Session, None, None]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_engine_for_tests(test_engine: Engine) -> None:
    """Used by unit tests to inject an in-memory engine."""
    global _engine
    _engine = test_engine
    SessionLocal.configure(bind=test_engine)
