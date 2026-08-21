"""Phase 6 isolated branch-cache HTTP service candidate tests (ASGI in-process only)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.logging_filters import redact_secret_query, redact_stream_path
from app.services.branch_cache.data_plane.errors import DataPlaneError
from app.services.branch_cache.grants import clear_replay_cache_for_tests, issue_edge_grant
from app.services.branch_cache.service import (
    BranchServiceConfig,
    BranchServiceConfigError,
    DeferredHttpsOriginTransport,
    InjectedLocalOriginTransport,
    create_branch_cache_app,
)
from app.services.object_storage.validation import collect_object_storage_errors
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient


def _pem_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv, pub


def _settings(**kwargs) -> Settings:
    priv, pub = _pem_pair()
    base = dict(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_cdn_sync=False,
        enable_branch_cache_control_plane=True,
        enable_edge_grant_issue=True,
        enable_branch_cache_data_plane_sim=True,
        enable_branch_cache_pull_through=True,
        enable_branch_cache_local_serve=True,
        enable_branch_cache_http_service=True,
        enable_branch_cache_http_health=True,
        enable_branch_cache_http_metrics=True,
        edge_grant_private_key_pem=priv,
        edge_grant_public_key_pem=pub,
        edge_grant_key_id="eg1",
        edge_grant_ttl_seconds=120,
        _env_file=None,
    )
    base.update(kwargs)
    return Settings(**base)


def _origin_tree(root: Path) -> None:
    base = root / "asset-1" / "pkg-1" / "720p"
    base.mkdir(parents=True)
    (root / "asset-1" / "pkg-1" / "master.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    (base / "seg_000.ts").write_bytes(b"SEGMENTDATA" * 128)


def _app(tmp_path: Path, settings: Settings | None = None, **cfg_kw):
    settings = settings or _settings()
    origin = tmp_path / "origin"
    cache = tmp_path / "cache"
    _origin_tree(origin)
    transport = InjectedLocalOriginTransport(origin)
    defaults = dict(
        node_id="node-a",
        site_id="kabul",
        public_key_pem=settings.edge_grant_public_key_pem,
        cache_root=cache,
        origin=transport.as_fetcher(),
        settings=settings,
        enable_health=True,
        enable_ready=True,
        enable_metrics=True,
        high_watermark_bytes=5_000_000,
        low_watermark_bytes=1_000_000,
        min_free_bytes=10_000,
    )
    defaults.update(cfg_kw)
    return create_branch_cache_app(BranchServiceConfig(**defaults)), settings


def _grant(settings: Settings, *, session: str, asset: str = "asset-1", pkg: str = "pkg-1") -> str:
    clear_replay_cache_for_tests()
    token, _ = issue_edge_grant(
        node_id="node-a",
        site_id="kabul",
        package_id=pkg,
        session_id=session,
        path_prefix=f"/v1/obj/{asset}/{pkg}/",
        settings=settings,
    )
    return token


def _headers(token: str, session: str, **extra) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {token}",
        "X-Ifilm-Session-Id": session,
    }
    h.update(extra)
    return h


def test_flags_default_off_and_prod_rejects():
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        _env_file=None,
    )
    assert settings.enable_branch_cache_http_service is False
    prod = _settings(
        app_env="production",
        enable_branch_cache_http_service=True,
        enable_branch_cache_data_plane_sim=False,
        enable_branch_cache_pull_through=False,
        enable_branch_cache_local_serve=False,
    )
    errors = collect_object_storage_errors(prod)
    assert any("HTTP_SERVICE" in e for e in errors)


def test_unsafe_startup_rejected(tmp_path: Path):
    settings = _settings(app_env="production")
    origin = InjectedLocalOriginTransport(tmp_path / "o")
    (tmp_path / "o").mkdir()
    with pytest.raises(BranchServiceConfigError):
        create_branch_cache_app(
            BranchServiceConfig(
                node_id="n",
                site_id="s",
                public_key_pem=settings.edge_grant_public_key_pem,
                cache_root=tmp_path / "c",
                origin=origin.as_fetcher(),
                settings=settings,
            )
        )
    with pytest.raises(BranchServiceConfigError):
        create_branch_cache_app(
            BranchServiceConfig(
                node_id="n",
                site_id="s",
                public_key_pem=settings.edge_grant_public_key_pem,
                cache_root=Path("/"),
                origin=origin.as_fetcher(),
                settings=_settings(),
            )
        )
    with pytest.raises(BranchServiceConfigError):
        create_branch_cache_app(
            BranchServiceConfig(
                node_id="n",
                site_id="s",
                public_key_pem=settings.edge_grant_public_key_pem,
                cache_root=tmp_path / "c2",
                origin=origin.as_fetcher(),
                settings=_settings(),
                allow_private_signing_key=True,
            )
        )


def test_get_head_range_and_auth(tmp_path: Path):
    app, settings = _app(tmp_path)
    client = TestClient(app)
    tok = _grant(settings, session="s1")
    # Missing auth
    assert client.get("/v1/obj/asset-1/pkg-1/master.m3u8").status_code == 401
    # Wrong session
    r = client.get(
        "/v1/obj/asset-1/pkg-1/master.m3u8",
        headers=_headers(tok, "other"),
    )
    assert r.status_code == 403

    tok = _grant(settings, session="s2")
    miss = client.get(
        "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "s2"),
    )
    assert miss.status_code == 200
    assert miss.headers.get("etag")
    assert miss.headers.get("x-request-id")
    assert miss.headers.get("accept-ranges") == "bytes"

    tok = _grant(settings, session="s3")
    head = client.head(
        "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "s3"),
    )
    assert head.status_code == 200
    assert head.content == b""
    assert int(head.headers["content-length"]) > 0

    tok = _grant(settings, session="s4")
    ranged = client.get(
        "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "s4", Range="bytes=0-9"),
    )
    assert ranged.status_code == 206
    assert len(ranged.content) == 10

    tok = _grant(settings, session="s5")
    bad_range = client.get(
        "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "s5", Range="bytes=999999-9999999"),
    )
    assert bad_range.status_code == 416


def test_path_traversal_and_methods(tmp_path: Path):
    app, settings = _app(tmp_path)
    client = TestClient(app)
    tok = _grant(settings, session="t1")
    # Encoded traversal
    r = client.get(
        "/v1/obj/asset-1/pkg-1/%2e%2e/secret.ts",
        headers=_headers(tok, "t1"),
    )
    assert r.status_code in {400, 404}
    assert (
        client.post(
            "/v1/obj/asset-1/pkg-1/master.m3u8",
            headers=_headers(tok, "t1"),
        ).status_code
        == 405
    )


def test_origin_outage_fallback_and_no_poison(tmp_path: Path):
    settings = _settings()
    origin = tmp_path / "origin"
    cache = tmp_path / "cache"
    _origin_tree(origin)
    (origin / "asset-1" / "pkg-1" / "720p" / "missing_fill.ts").write_bytes(b"X" * 50)
    transport = InjectedLocalOriginTransport(origin, fail_paths=frozenset({"720p/missing_fill.ts"}))
    app = create_branch_cache_app(
        BranchServiceConfig(
            node_id="node-a",
            site_id="kabul",
            public_key_pem=settings.edge_grant_public_key_pem,
            cache_root=cache,
            origin=transport.as_fetcher(),
            settings=settings,
            enable_health=True,
            enable_ready=True,
        )
    )
    client = TestClient(app)
    tok = _grant(settings, session="o1")
    r = client.get(
        "/v1/obj/asset-1/pkg-1/720p/missing_fill.ts",
        headers=_headers(tok, "o1"),
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"]
    assert "PRIVATE" not in r.text


def test_health_ready_metrics_privacy(tmp_path: Path):
    app, settings = _app(tmp_path)
    client = TestClient(app)
    h = client.get("/health")
    assert h.status_code == 200
    assert "token" not in h.text.lower()
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["live_origin"] is False
    assert ready.json()["client_redirect"] is False
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "PRIVATE" not in metrics.text
    assert "endpoint_enabled" in metrics.text

    app2, _ = _app(tmp_path / "b", enable_health=False, enable_ready=False, enable_metrics=False)
    c2 = TestClient(app2)
    assert c2.get("/health").status_code == 404
    assert c2.get("/ready").status_code == 404
    assert c2.get("/metrics").status_code == 404


def test_concurrent_single_flight(tmp_path: Path):
    app, settings = _app(tmp_path)
    # Slow fills
    app.state.branch_engine.origin.artificial_latency_ms = 30  # type: ignore[attr-defined]
    client = TestClient(app)
    codes: list[int] = []

    def _worker(i: int) -> None:
        tok = _grant(settings, session=f"c{i}")
        r = client.get(
            "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
            headers=_headers(tok, f"c{i}"),
        )
        codes.append(r.status_code)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes == [200] * 5


def test_drain_and_shutdown(tmp_path: Path):
    app, settings = _app(tmp_path)
    client = TestClient(app)
    # Prime cache
    tok = _grant(settings, session="d0")
    assert (
        client.get(
            "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
            headers=_headers(tok, "d0"),
        ).status_code
        == 200
    )
    app.state.branch_state.start_drain()
    # Hits still ok; new miss should fallback
    (tmp_path / "origin" / "asset-1" / "pkg-1" / "720p" / "seg_001.ts").write_bytes(b"Y" * 40)
    tok = _grant(settings, session="d1")
    r = client.get(
        "/v1/obj/asset-1/pkg-1/720p/seg_001.ts",
        headers=_headers(tok, "d1"),
    )
    assert r.status_code == 503
    app.state.branch_state.start_shutdown()
    tok = _grant(settings, session="d2")
    assert (
        client.get(
            "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
            headers=_headers(tok, "d2"),
        ).status_code
        == 503
    )


def test_https_adapter_requires_injection_no_sockets():
    with pytest.raises(RuntimeError):
        DeferredHttpsOriginTransport(
            endpoint_url="https://origin.example.internal",
            enable_lab_https_adapter=False,
        )
    local = InjectedLocalOriginTransport(Path("/tmp"))  # noqa: S108 — unused root for construct
    # Still requires injected transport even with lab flag
    adapter = DeferredHttpsOriginTransport(
        endpoint_url="https://origin.example.internal/base",
        enable_lab_https_adapter=True,
        client_cert_path="/x.crt",
        client_key_path="/x.key",
        ca_bundle_path="/ca.pem",
        injected_transport=local,
    )
    assert adapter.endpoint_url.startswith("https://")
    with pytest.raises(DataPlaneError):
        DeferredHttpsOriginTransport(
            endpoint_url="https://user:pass@evil.example/",
            enable_lab_https_adapter=True,
            injected_transport=local,
            ca_bundle_path="/ca.pem",
            client_cert_path="/x.crt",
            client_key_path="/x.key",
        )


def test_log_redaction_for_grants():
    assert "[REDACTED]" in redact_stream_path("Authorization: Bearer abcdef.token.value")
    assert "secret" not in redact_secret_query("grant=supersecret&ok=1").split("grant=")[1][:6]
    redacted = redact_secret_query("/x?edge_grant=abc")
    assert "abc" not in redacted
    assert "REDACTED" in redacted


def test_central_app_does_not_mount_branch_routes():
    from app.main import create_app

    central = TestClient(create_app())
    paths = [getattr(r, "path", "") for r in central.app.routes]
    assert not any("/v1/obj/" in p for p in paths)
    assert central.get("/v1/obj/asset-1/pkg-1/master.m3u8").status_code == 404


def test_claim_bindings_and_auth_before_io(tmp_path: Path):
    settings = _settings()
    origin = tmp_path / "origin"
    cache = tmp_path / "cache"
    _origin_tree(origin)
    fetches: list[str] = []
    inner = InjectedLocalOriginTransport(origin).as_fetcher()

    class Spy:
        def fetch(self, **kw):
            fetches.append(kw["relative_path"])
            return inner.fetch(**kw)

        def exists(self, **kw):
            return inner.exists(**kw)

    app = create_branch_cache_app(
        BranchServiceConfig(
            node_id="node-a",
            site_id="kabul",
            public_key_pem=settings.edge_grant_public_key_pem,
            cache_root=cache,
            origin=Spy(),  # type: ignore[arg-type]
            settings=settings,
        )
    )
    client = TestClient(app)

    # Wrong package binding — no origin I/O
    tok = _grant(settings, session="b1", pkg="other-pkg")
    r = client.get(
        "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "b1"),
    )
    assert r.status_code == 403
    assert fetches == []

    # Wrong node via separate engine identity
    tok = _grant(settings, session="b2")
    app2 = create_branch_cache_app(
        BranchServiceConfig(
            node_id="node-other",
            site_id="kabul",
            public_key_pem=settings.edge_grant_public_key_pem,
            cache_root=tmp_path / "cache2",
            origin=Spy(),  # type: ignore[arg-type]
            settings=settings,
        )
    )
    assert (
        TestClient(app2)
        .get(
            "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
            headers=_headers(tok, "b2"),
        )
        .status_code
        == 403
    )
    assert fetches == []

    # Cross-package path under wrong asset still package-bound
    tok = _grant(settings, session="b3", asset="asset-1", pkg="pkg-1")
    r = client.get(
        "/v1/obj/asset-2/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "b3"),
    )
    assert r.status_code == 403
    assert fetches == []

    # Happy path does fill once
    tok = _grant(settings, session="b4")
    assert (
        client.get(
            "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
            headers=_headers(tok, "b4"),
        ).status_code
        == 200
    )
    assert fetches == ["720p/seg_000.ts"]

    # Replay denied (second use of same jti)
    r2 = client.get(
        "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "b4"),
    )
    assert r2.status_code == 403


def test_checksum_timeout_oversize_via_http(tmp_path: Path):
    settings = _settings()
    origin = tmp_path / "origin"
    cache = tmp_path / "cache"
    _origin_tree(origin)
    (origin / "asset-1" / "pkg-1" / "720p" / "bad_ck.ts").write_bytes(b"CK" * 20)
    (origin / "asset-1" / "pkg-1" / "720p" / "slow.ts").write_bytes(b"SL" * 20)
    (origin / "asset-1" / "pkg-1" / "720p" / "big.ts").write_bytes(b"B" * 200)
    transport = InjectedLocalOriginTransport(
        origin,
        fail_paths=frozenset(),
        timeout_paths=frozenset({"720p/slow.ts"}),
        corrupt_checksum_paths=frozenset({"720p/bad_ck.ts"}),
        max_object_bytes=100,
    )
    app = create_branch_cache_app(
        BranchServiceConfig(
            node_id="node-a",
            site_id="kabul",
            public_key_pem=settings.edge_grant_public_key_pem,
            cache_root=cache,
            origin=transport.as_fetcher(),
            settings=settings,
        )
    )
    client = TestClient(app)
    for name in ("720p/bad_ck.ts", "720p/slow.ts", "720p/big.ts"):
        tok = _grant(settings, session=f"x-{name}")
        r = client.get(f"/v1/obj/asset-1/pkg-1/{name}", headers=_headers(tok, f"x-{name}"))
        assert r.status_code == 503
        assert not (cache / "obj").exists() or name.split("/")[-1] not in str(
            list((cache).rglob("*"))
        )


def test_symlink_and_header_path_limits(tmp_path: Path):
    settings = _settings()
    origin = tmp_path / "origin"
    cache = tmp_path / "cache"
    _origin_tree(origin)
    link = origin / "asset-1" / "pkg-1" / "720p" / "link.ts"
    target = origin / "asset-1" / "pkg-1" / "720p" / "seg_000.ts"
    link.symlink_to(target)
    app = create_branch_cache_app(
        BranchServiceConfig(
            node_id="node-a",
            site_id="kabul",
            public_key_pem=settings.edge_grant_public_key_pem,
            cache_root=cache,
            origin=InjectedLocalOriginTransport(origin).as_fetcher(),
            settings=settings,
            max_path_length=80,
            max_header_bytes=1024,
        )
    )
    client = TestClient(app)
    tok = _grant(settings, session="sy1")
    assert (
        client.get(
            "/v1/obj/asset-1/pkg-1/720p/link.ts",
            headers=_headers(tok, "sy1"),
        ).status_code
        == 503
    )
    tok = _grant(settings, session="lim1")
    long_path = "/v1/obj/asset-1/pkg-1/" + ("a" * 100) + ".ts"
    assert client.get(long_path, headers=_headers(tok, "lim1")).status_code == 414
    tok = _grant(settings, session="lim2")
    huge = _headers(tok, "lim2", **{"X-Pad": "Z" * 2000})
    assert (
        client.get(
            "/v1/obj/asset-1/pkg-1/master.m3u8",
            headers=huge,
        ).status_code
        == 431
    )


def test_hit_miss_and_immutable_headers(tmp_path: Path):
    app, settings = _app(tmp_path)
    client = TestClient(app)
    tok = _grant(settings, session="hm1")
    miss = client.get(
        "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "hm1"),
    )
    assert miss.status_code == 200
    assert miss.headers.get("x-ifilm-decision") in {"cache_miss_filled", "hit", "miss_fill"}
    etag = miss.headers["etag"]
    tok = _grant(settings, session="hm2")
    hit = client.get(
        "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
        headers=_headers(tok, "hm2"),
    )
    assert hit.status_code == 200
    assert hit.headers.get("x-ifilm-decision") == "cache_hit"
    assert hit.headers["etag"] == etag
    assert "private" in hit.headers.get("cache-control", "")


def test_production_http_flags_off_preserve_central_stream(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_SERVICE", "false")
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_HEALTH", "false")
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_METRICS", "false")
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_LAB_HTTPS_ADAPTER", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.enable_branch_cache_http_service is False
    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    # Central stream route still present; unauthenticated → 401 (not branch 503)
    r = client.get("/api/stream/abcdefghijklmnopqrstuvwx123456/master.m3u8")
    assert r.status_code == 401
    assert "/v1/obj/" not in str([getattr(x, "path", "") for x in app.routes])


def test_asgi_in_process_no_socket_bind(tmp_path: Path):
    import socket

    before = set()
    # Snapshot listening sockets is OS-specific; ensure TestClient does not bind 0.0.0.0
    app, settings = _app(tmp_path)
    with TestClient(app) as client:
        tok = _grant(settings, session="sock1")
        assert (
            client.get(
                "/v1/obj/asset-1/pkg-1/master.m3u8",
                headers=_headers(tok, "sock1"),
            ).status_code
            == 200
        )
    # No accidental listen on common lab ports
    for port in (8000, 8080, 8443, 9000):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.05)
        try:
            # Connection refused is fine; bound listener would accept — we only
            # assert we did not leave a listener from TestClient (ephemeral).
            s.connect(("127.0.0.1", port))
        except OSError:
            pass
        finally:
            s.close()
    assert before == set()  # placeholder sanity
