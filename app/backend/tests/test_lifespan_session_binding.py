"""Lifespan must bind SessionLocal before merging Super Admin permissions.

Production constructs ``SessionLocal`` with no bind. ``get_engine()`` is what
configures it. Opening a session before that raises ``UnboundExecutionError``,
which startup used to swallow as "Super Admin permission merge skipped".

These tests boot from that unbound default. They do not call
``reset_engine_for_tests`` or any other test-only pre-bind before lifespan.
"""

from __future__ import annotations

import logging

import pytest
from app.bootstrap import SUPER_PERMISSIONS
from app.core.config import get_settings
from app.db import session as session_module
from app.db.base import Base
from app.db.session import SessionLocal
from app.main import create_app
from app.models.admin import AdminRole
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, UnboundExecutionError
from sqlalchemy.pool import NullPool


@pytest.fixture()
def unbound_database(tmp_path, monkeypatch):
    """Schema on a private SQLite file; application session factory left unbound."""
    database_url = f"sqlite:///{tmp_path / 'lifespan.db'}"
    setup = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    Base.metadata.create_all(bind=setup)
    setup.dispose()

    original_engine = session_module._engine
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    session_module._engine = None
    SessionLocal.configure(bind=None)
    assert session_module._engine is None
    assert SessionLocal.kw.get("bind") is None
    try:
        yield
    finally:
        get_settings.cache_clear()
        if original_engine is not None:
            session_module.reset_engine_for_tests(original_engine)
        else:
            session_module._engine = None
            SessionLocal.configure(bind=None)


def _super_admin(db):
    return db.query(AdminRole).filter(AdminRole.name == "Super Admin").one_or_none()


def test_lifespan_merges_permissions_from_unbound_session(unbound_database, caplog):
    """A normal boot must merge permissions without a pre-bound test engine."""
    probe = SessionLocal()
    try:
        with pytest.raises(UnboundExecutionError):
            probe.query(AdminRole).first()
    finally:
        probe.close()
    assert session_module._engine is None
    assert SessionLocal.kw.get("bind") is None

    app = create_app()
    with caplog.at_level(logging.ERROR):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
        # Second boot stays idempotent: one role, no duplicate permissions.
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    assert "Super Admin permission merge skipped" not in caplog.text
    assert "UnboundExecutionError" not in caplog.text

    db = SessionLocal()
    try:
        role = _super_admin(db)
        assert role is not None
        permissions = list(role.permissions or [])
        assert set(SUPER_PERMISSIONS).issubset(set(permissions))
        assert len(permissions) == len(set(permissions))
        assert db.query(AdminRole).filter(AdminRole.name == "Super Admin").count() == 1
    finally:
        db.close()


def test_lifespan_still_boots_when_permission_merge_database_fails(unbound_database, monkeypatch, caplog):
    """A real database failure must not take the API down."""

    def _unavailable(_db):
        raise OperationalError("SELECT 1", {}, Exception("database unavailable"))

    monkeypatch.setattr("app.bootstrap.ensure_super_admin_permissions", _unavailable)

    app = create_app()
    with caplog.at_level(logging.ERROR, logger="app.main"):
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

    assert "Super Admin permission merge skipped" in caplog.text
    db = SessionLocal()
    try:
        assert _super_admin(db) is None
    finally:
        db.close()
