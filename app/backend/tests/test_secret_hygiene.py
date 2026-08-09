"""Secret hygiene: tokens must not leak into log-shaped strings."""

from __future__ import annotations

from pathlib import Path

from app.core.logging_filters import redact_secret_query, redact_stream_path
from app.frontend_env_allowlist import FRONTEND_PUBLIC_ENV_KEYS


def test_redact_stream_path_token():
    raw = "abcdefghijklmnopqrstuvwx"
    path = f"/api/stream/{raw}/master.m3u8"
    out = redact_stream_path(path)
    assert raw not in out
    assert "[REDACTED]" in out


def test_redact_query_token_and_expires():
    url = "/api/stream/abcdefghijklmnopqrstuvwx/master.m3u8?token=sekret&expires=99&lang=en"
    out = redact_stream_path(url)
    assert "abcdefghijklmnopqrstuvwx" not in out
    assert "sekret" not in out
    assert "expires=99" not in out
    assert "lang=en" in out
    assert "[REDACTED]" in out


def test_redact_bearer_header_fragment():
    msg = "authorization: Bearer super-secret-jwt-value path=/api/health"
    out = redact_stream_path(msg)
    assert "super-secret-jwt-value" not in out
    assert "[REDACTED]" in out


def test_redact_tmdb_and_credential_assignments():
    msg = "tmdb_api_key=super-tmdb-secret jwt_secret=abc123playback"
    out = redact_stream_path(msg)
    assert "super-tmdb-secret" not in out
    assert "abc123playback" not in out
    assert "[REDACTED]" in out


def test_redact_secret_query_standalone():
    out = redact_secret_query("token=abc&x=1")
    assert "abc" not in out
    assert "x=1" in out


def test_frontend_public_env_allowlist_has_no_secrets():
    forbidden = {
        "VITE_JWT_SECRET",
        "VITE_PLAYBACK_TOKEN_SECRET",
        "VITE_POSTGRES_PASSWORD",
        "VITE_REDIS_PASSWORD",
        "VITE_ADMIN_BOOTSTRAP_PASSWORD",
        "VITE_UPDATE_AGENT_SHARED_SECRET",
    }
    assert FRONTEND_PUBLIC_ENV_KEYS.isdisjoint(forbidden)
    for key in FRONTEND_PUBLIC_ENV_KEYS:
        assert key.startswith("VITE_")
        assert "SECRET" not in key.upper()
        assert "PASSWORD" not in key.upper()
        assert "TOKEN" not in key.upper()


def test_vite_env_d_ts_has_no_secret_keys():
    # tests/ -> backend/ -> app/ -> frontend/
    vite = Path(__file__).resolve().parents[2] / "frontend" / "src" / "vite-env.d.ts"
    text = vite.read_text(encoding="utf-8")
    for key in (
        "VITE_JWT_SECRET",
        "VITE_PLAYBACK_TOKEN_SECRET",
        "VITE_DATABASE_URL",
    ):
        assert key not in text
