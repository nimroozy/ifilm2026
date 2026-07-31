import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

TEST_JWT = "unit-test-jwt-secret-value-32chars-min"
TEST_ADMIN_PASSWORD = "unit-test-admin-pass-ok"
TEST_FIXTURE_USER = "mobin_user_001"
TEST_FIXTURE_PASSWORD = "fixture-pass-ok"

os.environ["APP_ENV"] = "test"
os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = TEST_JWT
os.environ["ADMIN_BOOTSTRAP_USERNAME"] = "admin"
os.environ["ADMIN_BOOTSTRAP_PASSWORD"] = TEST_ADMIN_PASSWORD
os.environ["ADMIN_BOOTSTRAP_EMAIL"] = "admin@example.test"
os.environ["RADIUS_ENABLED"] = "true"
os.environ["RADIUS_MODE"] = "mock"
os.environ["RADIUS_SECRET"] = "unit-test-radius-secret"
os.environ["ENABLE_RADIUS_LOGIN"] = "true"
os.environ["ENABLE_UPLOADS"] = "true"
os.environ["ENABLE_ENCODING"] = "true"
os.environ["ENABLE_CDN_SYNC"] = "true"
os.environ["REDIS_REQUIRED"] = "false"
os.environ["MEDIA_ROOT"] = str(Path("/tmp/ifilm-test-media").resolve())
os.environ["HLS_PUBLIC_BASE_URL"] = "http://testserver/media/hls"
os.environ["RADIUS_MOCK_USERS"] = json.dumps(
    [
        {
            "username": TEST_FIXTURE_USER,
            "password": TEST_FIXTURE_PASSWORD,
            "package": "Premium 50Mbps",
            "branch": "Kabul",
            "expiration": "2026-12-31",
            "name": "Ahmad Karimi",
        }
    ]
)

from app.core.config import get_settings

get_settings.cache_clear()

import app.models  # noqa: F401
from app.bootstrap import seed_development_data
from app.db import session as session_module
from app.db.base import Base

Path(os.environ["MEDIA_ROOT"]).mkdir(parents=True, exist_ok=True)

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
session_module.reset_engine_for_tests(engine)

from app.db.session import get_db
from app.main import create_app


@pytest.fixture()
def client():
    # Isolate from integration tests that may swap engines or cached settings.
    get_settings.cache_clear()
    session_module.reset_engine_for_tests(engine)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        seed_development_data(db, include_demo_catalog=True)
    finally:
        db.close()

    app = create_app()

    def _override_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def admin_headers(client):
    login = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": TEST_ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture()
def db_session(client):
    """ORM session bound to the same in-memory engine as the test client.

    Prefer this over importing ``TestingSessionLocal`` from ``tests.conftest``:
    pytest loads this file as plugin module ``conftest``, which is a different
    module object than ``tests.conftest`` and would use a separate empty DB.
    """
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
