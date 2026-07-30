"""Application readiness against CI Postgres/Redis services."""

from __future__ import annotations

import os

import pytest
from app.core.config import get_settings
from app.db import session as session_module
from app.db.base import Base
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL") or "postgres" not in os.getenv("TEST_DATABASE_URL", ""),
    reason="PostgreSQL TEST_DATABASE_URL not configured",
)
def test_application_readiness_with_postgres_and_redis(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("REDIS_URL", os.getenv("TEST_REDIS_URL", "redis://localhost:6379/0"))
    monkeypatch.setenv("REDIS_REQUIRED", "true")
    monkeypatch.setenv("JWT_SECRET", "readiness-test-jwt-secret-value-32")
    monkeypatch.setenv("RADIUS_MODE", "mock")
    monkeypatch.setenv("RADIUS_MOCK_USERS", "[]")
    monkeypatch.setenv("ENABLE_RADIUS_LOGIN", "false")
    get_settings.cache_clear()

    # Rebuild engine against Postgres for this test process.
    session_module._engine = None
    engine = session_module.get_engine()
    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        app = create_app()
        with TestClient(app) as client:
            health = client.get("/health")
            assert health.status_code == 200
            ready = client.get("/ready")
            assert ready.status_code == 200, ready.text
            body = ready.json()
            assert body["status"] == "ready"
            assert body["database"]["ok"] is True
            assert body["redis"]["ok"] is True
    finally:
        session_module._engine = None
        get_settings.cache_clear()
