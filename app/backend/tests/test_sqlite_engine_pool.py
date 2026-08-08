"""File-backed SQLite must not use StaticPool under concurrent requests."""

from sqlalchemy.pool import NullPool, StaticPool

from app.db.session import _build_engine, _is_memory_sqlite


def test_memory_sqlite_detection() -> None:
    assert _is_memory_sqlite("sqlite://")
    assert _is_memory_sqlite("sqlite:///:memory:")
    assert _is_memory_sqlite("sqlite+pysqlite:///:memory:?cache=shared")
    assert not _is_memory_sqlite("sqlite:////tmp/ifilm.db")


def test_file_sqlite_uses_null_pool(tmp_path) -> None:
    engine = _build_engine(f"sqlite:///{tmp_path / 'qa.db'}")
    assert isinstance(engine.pool, NullPool)
    engine.dispose()


def test_memory_sqlite_uses_static_pool() -> None:
    engine = _build_engine("sqlite://")
    assert isinstance(engine.pool, StaticPool)
    engine.dispose()
