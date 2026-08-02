"""Regression tests for DATABASE_URL password encoding (special chars @ : / #)."""

from __future__ import annotations

import os

import pytest
from app.core.db_url import (
    build_postgres_sqlalchemy_url,
    build_redis_url,
    database_url_from_postgres_env,
    redact_database_url,
    resolve_database_url,
    validate_database_url,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

SPECIAL_PASSWORD = "p@ss:/#w0rd%X"


def test_build_postgres_url_encodes_at_colon_slash_hash_percent():
    url = build_postgres_sqlalchemy_url(
        user="ifilm_staging",
        password=SPECIAL_PASSWORD,
        host="postgres",
        port=5432,
        database="ifilm_staging",
    )
    assert "@" in url  # host separator still present
    # Raw special characters must not appear unencoded in the password region.
    userinfo = url.split("://", 1)[1].rsplit("@", 1)[0]
    _user, _, pwd = userinfo.partition(":")
    assert "@" not in pwd
    assert "/" not in pwd
    assert "#" not in pwd
    assert "%40" in pwd  # '@'
    assert "%3A" in pwd.upper() or "%3a" in pwd  # ':'
    assert "%2F" in pwd.upper() or "%2f" in pwd  # '/'
    assert "%23" in pwd  # '#'

    parsed = make_url(url)
    assert parsed.password == SPECIAL_PASSWORD
    assert parsed.username == "ifilm_staging"
    assert parsed.host == "postgres"
    assert parsed.database == "ifilm_staging"
    validate_database_url(url)


def test_validate_rejects_unencoded_password_in_url_string():
    # Broken Compose-style concatenation: password contains '@' and '#'.
    broken = "postgresql+psycopg2://ifilm:p@ss:/#bad@postgres:5432/ifilm"
    with pytest.raises(ValueError, match="unencoded|not parseable|missing"):
        validate_database_url(broken)


def test_redis_url_encodes_password():
    url = build_redis_url(host="redis", password=SPECIAL_PASSWORD)
    assert "%40" in url
    assert SPECIAL_PASSWORD not in url


def test_redact_database_url_hides_password():
    url = build_postgres_sqlalchemy_url(
        user="u",
        password=SPECIAL_PASSWORD,
        host="h",
        database="d",
    )
    redacted = redact_database_url(url)
    assert SPECIAL_PASSWORD not in redacted
    assert "***" in redacted or ":***@" in redacted or "hide" in redacted.lower() or "xxx" in redacted


def test_database_url_from_postgres_env_encodes_special_password():
    url = database_url_from_postgres_env(
        {
            "POSTGRES_USER": "ifilm",
            "POSTGRES_PASSWORD": SPECIAL_PASSWORD,
            "POSTGRES_HOST": "postgres",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "ifilm",
        }
    )
    assert url is not None
    assert make_url(url).password == SPECIAL_PASSWORD
    assert SPECIAL_PASSWORD not in (url.split("@", 1)[0])


def test_database_url_from_postgres_env_incomplete_returns_none():
    assert database_url_from_postgres_env({"POSTGRES_USER": "u"}) is None


def test_resolve_database_url_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg2://explicit:secret@db:5432/app",
    )
    monkeypatch.setenv("POSTGRES_USER", "ifilm")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")
    monkeypatch.setenv("POSTGRES_DB", "ifilm")
    assert resolve_database_url().startswith("postgresql+psycopg2://explicit:")


def test_resolve_database_url_falls_back_to_postgres_components(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "ifilm")
    monkeypatch.setenv("POSTGRES_PASSWORD", SPECIAL_PASSWORD)
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_DB", "ifilm")
    url = resolve_database_url(settings_database_url="")
    assert make_url(url).password == SPECIAL_PASSWORD
    assert make_url(url).username == "ifilm"


def test_resolve_database_url_raises_when_unavailable(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for key in (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        resolve_database_url(settings_database_url="")


def test_connect_with_special_password_database_url():
    """Prove SQLAlchemy can connect using a URL built with password containing @:/#.

    Requires STAGING_DB_URL_TEST=1 and a reachable Postgres (e.g. staging compose).
    Components may be supplied via POSTGRES_* or a base TEST_DATABASE_URL whose
    password is replaced with the special password for a dedicated role — here we
    connect using POSTGRES_* from the environment (staging bring-up sets these).
    """
    if os.getenv("STAGING_DB_URL_TEST") != "1":
        pytest.skip("Set STAGING_DB_URL_TEST=1 to run live connection proof")

    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    database = os.environ["POSTGRES_DB"]

    assert any(ch in password for ch in "@:/#"), "staging password must include @:/# for this test"

    url = build_postgres_sqlalchemy_url(
        user=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    validate_database_url(url)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
    engine.dispose()
