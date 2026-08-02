"""CSP / security header enforcement tests."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.csp import build_csp, security_header_map
from app.main import create_app
from fastapi.testclient import TestClient


def test_production_csp_is_restrictive():
    csp = build_csp("production")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp
    assert "media-src 'self' blob:" in csp
    assert "connect-src 'self' blob:" in csp
    assert "worker-src 'self' blob:" in csp
    assert "frame-src 'self' https://www.youtube-nocookie.com https://www.youtube.com" in csp
    assert "child-src 'self' https://www.youtube-nocookie.com https://www.youtube.com" in csp
    assert "https://fonts.googleapis.com" in csp
    assert "https://fonts.gstatic.com" in csp
    assert "unsafe-eval" not in csp
    assert "connect-src *" not in csp
    assert "media-src *" not in csp
    assert "script-src *" not in csp


def test_development_csp_allows_vite_toolchain_only():
    csp = build_csp("development")
    assert "unsafe-eval" in csp
    assert "ws:" in csp
    assert "object-src 'none'" in csp
    assert "media-src 'self' blob:" in csp


def test_health_response_includes_production_csp_when_forced(monkeypatch):
    monkeypatch.setenv("CSP_MODE", "production")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as tc:
        resp = tc.get("/health")
        assert resp.status_code == 200
        csp = resp.headers.get("content-security-policy")
        assert csp
        assert "object-src 'none'" in csp
        assert "unsafe-eval" not in csp
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
    get_settings.cache_clear()


def test_spa_index_receives_csp_when_frontend_dist_set(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>ifilm</title>", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    monkeypatch.setenv("CSP_MODE", "production")
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as tc:
        resp = tc.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        csp = resp.headers["content-security-policy"]
        assert "media-src 'self' blob:" in csp
        assert "object-src 'none'" in csp
    get_settings.cache_clear()


def test_security_header_map_keys():
    headers = security_header_map(mode="production")
    assert "Content-Security-Policy" in headers
    assert "Referrer-Policy" in headers
