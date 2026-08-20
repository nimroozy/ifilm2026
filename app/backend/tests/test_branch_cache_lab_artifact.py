"""Phase 7 lab artifact ASGI entry + import/hardening tests (no sockets)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from app.services.branch_cache.service.config import BranchServiceConfigError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

_SECRET_ENV = (
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_SECRET",
    "PLAYBACK_TOKEN_SECRET",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "EDGE_GRANT_PRIVATE_KEY_PEM",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "PORTAL_CLIENT_SECRET",
    "SAS_CLIENT_SECRET",
    "ADMIN_BOOTSTRAP_PASSWORD",
    "RADIUS_SECRET",
    "R2_SECRET_ACCESS_KEY",
    "MEDIA_ORIGIN_SECRET_ACCESS_KEY",
)


def _pem_pub() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


@pytest.fixture
def lab_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for key in _SECRET_ENV:
        monkeypatch.delenv(key, raising=False)
    origin = tmp_path / "origin"
    cache = tmp_path / "cache"
    origin.mkdir()
    cache.mkdir()
    (origin / "placeholder").write_text("x", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT", "true")
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_SERVICE", "true")
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_HEALTH", "false")
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_METRICS", "false")
    monkeypatch.setenv("BRANCH_CACHE_NODE_ID", "node-lab-1")
    monkeypatch.setenv("BRANCH_CACHE_SITE_ID", "lab-site")
    monkeypatch.setenv("BRANCH_CACHE_ORIGIN_ROOT", str(origin))
    monkeypatch.setenv("BRANCH_CACHE_CACHE_ROOT", str(cache))
    monkeypatch.setenv("EDGE_GRANT_PUBLIC_KEY_PEM", _pem_pub())
    monkeypatch.setenv("EDGE_GRANT_KEY_ID", "lab")
    return tmp_path


def test_validate_only_starts_without_db_stack(lab_env: Path):
    # Run in a fresh interpreter so we do not mutate sys.modules for other tests.
    code = """
import sys
from app.services.branch_cache.service.asgi import validate_lab_startup
result = validate_lab_startup()
assert result["ok"] == "true"
assert result["node_id"] == "node-lab-1"
assert not any(m.startswith("app.models") for m in sys.modules)
assert "sqlalchemy" not in sys.modules
assert "psycopg2" not in sys.modules
assert "redis" not in sys.modules
assert "boto3" not in sys.modules
print("ok")
"""
    env = {**os.environ}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout


def test_rejects_prod_env(lab_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "production")
    from app.services.branch_cache.service.asgi import load_lab_settings

    with pytest.raises(BranchServiceConfigError) as ei:
        load_lab_settings()
    assert ei.value.code == "prod_forbidden"


def test_rejects_missing_lab_flag(lab_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT", "false")
    from app.services.branch_cache.service.asgi import load_lab_settings

    with pytest.raises(BranchServiceConfigError) as ei:
        load_lab_settings()
    assert ei.value.code == "lab_artifact_flag"


def test_rejects_credential_env(lab_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/db")
    from app.services.branch_cache.service.asgi import load_lab_settings

    with pytest.raises(BranchServiceConfigError) as ei:
        load_lab_settings()
    assert ei.value.code == "secrets_forbidden"


def test_rejects_origin_url(lab_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRANCH_CACHE_ORIGIN_URL", "https://evil.example/obj")
    from app.services.branch_cache.service.asgi import build_lab_config

    with pytest.raises(BranchServiceConfigError) as ei:
        build_lab_config()
    assert ei.value.code == "origin_url_forbidden"


def test_rejects_private_key_in_public_pem(lab_env: Path, monkeypatch: pytest.MonkeyPatch):
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("EDGE_GRANT_PUBLIC_KEY_PEM", priv)
    from app.services.branch_cache.service.asgi import load_lab_settings

    with pytest.raises(BranchServiceConfigError):
        load_lab_settings()


def test_cli_validate_only(lab_env: Path):
    from app.services.branch_cache.service.__main__ import main

    assert main(["--validate-only"]) == 0


def test_lab_artifact_flag_default_off():
    from app.core.config import Settings

    s = Settings(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        _env_file=None,
    )
    assert s.enable_branch_cache_http_lab_artifact is False


def test_settings_validation_rejects_lab_artifact_in_prod():
    from app.core.config import Settings
    from app.services.object_storage.validation import collect_object_storage_errors

    s = Settings(
        app_env="production",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_branch_cache_http_service=True,
        enable_branch_cache_http_lab_artifact=True,
        _env_file=None,
    )
    errs = collect_object_storage_errors(s)
    assert any("LAB_ARTIFACT" in e for e in errs)


def test_central_stream_unaffected_by_lab_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT", "false")
    from app.core.config import get_settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)
    assert client.get("/api/stream/abcdefghijklmnopqrstuvwx123456/master.m3u8").status_code == 401
    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any("/v1/obj/" in p for p in paths)
