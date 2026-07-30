import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["RADIUS_ENABLED"] = "false"
os.environ["RADIUS_MODE"] = "mock"
os.environ["CDN_SYNC_ENABLED"] = "true"
os.environ["MEDIA_ROOT"] = str(Path("/tmp/ifilm-test-media").resolve())
os.environ["HLS_PUBLIC_BASE_URL"] = "http://testserver/media/hls"

from app.core.config import get_settings

get_settings.cache_clear()

from app.db.base import Base
from app.db import session as session_module
import app.models  # noqa: F401

Path(os.environ["MEDIA_ROOT"]).mkdir(parents=True, exist_ok=True)

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

session_module.engine = engine
session_module.SessionLocal = TestingSessionLocal

from app.db.session import get_db
from app.main import create_app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

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
