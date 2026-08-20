"""Phase 8 mTLS staging-candidate tests (loopback + generated test PKI only)."""

from __future__ import annotations

import json
import ssl
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from app.core.config import Settings
from app.services.branch_cache.data_plane.engine import BranchDataPlaneEngine
from app.services.branch_cache.data_plane.errors import DataPlaneError
from app.services.branch_cache.data_plane.mtls_origin import (
    MtLsHttpsOriginFetcher,
    MtLsOriginConfigError,
)
from app.services.branch_cache.data_plane.origin_allowlist import (
    build_object_url,
    parse_fixed_origin_url,
)
from app.services.branch_cache.enrollment.manifest import (
    BranchNodeEnrollmentManifest,
    OriginAllowlistEntry,
    PublicTrustRef,
    load_enrollment_manifest,
    write_enrollment_manifest,
)
from app.services.branch_cache.grants import clear_replay_cache_for_tests, issue_edge_grant
from app.services.branch_cache.ops.staging_gates import (
    StagingGateInput,
    evaluate_staging_candidate_gates,
)
from app.services.branch_cache.service import BranchServiceConfig, create_branch_cache_app
from app.services.object_storage.validation import collect_object_storage_errors
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from tests.helpers.branch_mtls_pki import (
    BranchMtLsPkiPaths,
    build_server_ssl_context,
    generate_test_pki,
)


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
        enable_branch_cache_http_mtls_staging_candidate=True,
        edge_grant_private_key_pem=priv,
        edge_grant_public_key_pem=pub,
        edge_grant_key_id="eg1",
        edge_grant_ttl_seconds=120,
        _env_file=None,
    )
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


class _OriginHandler(BaseHTTPRequestHandler):
    root: Path
    redirect: bool = False
    oversized: bool = False

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _map(self) -> Path | None:
        # /asset/pkg/rel...
        parts = self.path.split("?")[0].strip("/").split("/")
        if len(parts) < 3:
            return None
        candidate = self.root.joinpath(*parts)
        try:
            candidate.resolve().relative_to(self.root.resolve())
        except Exception:
            return None
        return candidate if candidate.is_file() else None

    def do_HEAD(self) -> None:  # noqa: N802
        if self.redirect:
            self.send_response(302)
            self.send_header("Location", "https://evil.example/x")
            self.end_headers()
            return
        path = self._map()
        if path is None:
            self.send_response(404)
            self.end_headers()
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.redirect:
            self.send_response(302)
            self.send_header("Location", "https://evil.example/x")
            self.end_headers()
            return
        path = self._map()
        if path is None:
            self.send_response(404)
            self.end_headers()
            return
        data = b"X" * (70 * 1024 * 1024) if self.oversized else path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Type",
            "video/mp2t" if path.suffix == ".ts" else "application/vnd.apple.mpegurl",
        )
        self.end_headers()
        self.wfile.write(data)


def _start_mtls_origin(
    pki: BranchMtLsPkiPaths,
    content_root: Path,
    *,
    require_client: bool = True,
    redirect: bool = False,
    oversized: bool = False,
) -> tuple[ThreadingHTTPServer, str, threading.Thread]:
    handler = type(
        "H",
        (_OriginHandler,),
        {"root": content_root, "redirect": redirect, "oversized": oversized},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    ctx = build_server_ssl_context(pki, require_client=require_client)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"https://127.0.0.1:{port}", thread


def _seed_origin(root: Path) -> None:
    base = root / "asset-1" / "pkg-1" / "720p"
    base.mkdir(parents=True)
    (root / "asset-1" / "pkg-1" / "master.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
    (base / "seg_000.ts").write_bytes(b"SEGMENTDATA" * 64)


def test_flags_default_off_and_prod_rejects():
    s = Settings(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        _env_file=None,
    )
    assert s.enable_branch_cache_http_mtls_staging_candidate is False
    prod = _settings(
        app_env="production",
        enable_branch_cache_http_mtls_staging_candidate=True,
        enable_branch_cache_data_plane_sim=False,
        enable_branch_cache_pull_through=False,
        enable_branch_cache_local_serve=False,
        enable_branch_cache_http_service=False,
    )
    errs = collect_object_storage_errors(prod)
    assert any("MTLS_STAGING" in e for e in errs)


def test_allowlist_rejects_ssrf_shapes():
    with pytest.raises(DataPlaneError):
        parse_fixed_origin_url("http://origin.example/")
    with pytest.raises(DataPlaneError):
        parse_fixed_origin_url("https://user:pass@origin.example/")
    with pytest.raises(DataPlaneError):
        parse_fixed_origin_url("https://127.0.0.1:8443/")
    ep = parse_fixed_origin_url("https://127.0.0.1:8443/", allow_loopback=True)
    url = build_object_url(ep, asset_id="a", package_id="p", relative_path="720p/seg_000.ts")
    assert url.startswith("https://127.0.0.1:8443/")
    assert ".." not in url


def test_mtls_hit_miss_head_range_and_failures(tmp_path: Path):
    pki = generate_test_pki(tmp_path / "pki")
    origin_root = tmp_path / "origin"
    _seed_origin(origin_root)
    server, base, _thread = _start_mtls_origin(pki, origin_root)
    try:
        settings = _settings()
        fetcher = MtLsHttpsOriginFetcher(
            endpoint_url=base,
            client_cert_path=pki.client_cert,
            client_key_path=pki.client_key,
            ca_bundle_path=pki.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="test",
        )
        # Miss fill via engine
        from app.services.branch_cache.data_plane.cache_store import CacheStore

        cache = CacheStore(
            tmp_path / "cache",
            node_id="node-a",
            high_watermark_bytes=5_000_000,
            low_watermark_bytes=1_000_000,
            min_free_bytes=10_000,
        )
        engine = BranchDataPlaneEngine(
            node_id="node-a",
            site_id="kabul",
            cache=cache,
            origin=fetcher,
            public_key_pem=settings.edge_grant_public_key_pem,
            settings=settings,
        )
        clear_replay_cache_for_tests()
        tok, _ = issue_edge_grant(
            node_id="node-a",
            site_id="kabul",
            package_id="pkg-1",
            session_id="s1",
            path_prefix="/v1/obj/asset-1/pkg-1/",
            settings=settings,
        )
        miss = engine.serve(
            grant_token=tok,
            asset_id="asset-1",
            package_id="pkg-1",
            session_id="s1",
            relative_path="720p/seg_000.ts",
            path_prefix="/v1/obj/asset-1/pkg-1/",
        )
        assert miss.status_code == 200
        assert miss.decision.decision == "cache_miss_filled"

        clear_replay_cache_for_tests()
        tok2, _ = issue_edge_grant(
            node_id="node-a",
            site_id="kabul",
            package_id="pkg-1",
            session_id="s2",
            path_prefix="/v1/obj/asset-1/pkg-1/",
            settings=settings,
        )
        hit = engine.serve(
            grant_token=tok2,
            asset_id="asset-1",
            package_id="pkg-1",
            session_id="s2",
            relative_path="720p/seg_000.ts",
            path_prefix="/v1/obj/asset-1/pkg-1/",
        )
        assert hit.decision.decision == "cache_hit"

        clear_replay_cache_for_tests()
        tok3, _ = issue_edge_grant(
            node_id="node-a",
            site_id="kabul",
            package_id="pkg-1",
            session_id="s3",
            path_prefix="/v1/obj/asset-1/pkg-1/",
            settings=settings,
        )
        ranged = engine.serve(
            grant_token=tok3,
            asset_id="asset-1",
            package_id="pkg-1",
            session_id="s3",
            relative_path="720p/seg_000.ts",
            path_prefix="/v1/obj/asset-1/pkg-1/",
            range_header="bytes=0-9",
        )
        assert ranged.status_code == 206
        assert len(ranged.body) == 10
        fetcher.close()
    finally:
        server.shutdown()


def test_mtls_invalid_ca_and_missing_client(tmp_path: Path):
    good = generate_test_pki(tmp_path / "good")
    other = generate_test_pki(tmp_path / "other")
    origin_root = tmp_path / "origin"
    _seed_origin(origin_root)
    server, base, _ = _start_mtls_origin(good, origin_root)
    try:
        with pytest.raises((DataPlaneError, ssl.SSLError, Exception)):
            bad = MtLsHttpsOriginFetcher(
                endpoint_url=base,
                client_cert_path=other.client_cert,
                client_key_path=other.client_key,
                ca_bundle_path=other.ca_cert,
                enable_mtls_staging_candidate=True,
                allow_loopback_for_tests=True,
                app_env="test",
            )
            try:
                bad.fetch(asset_id="asset-1", package_id="pkg-1", relative_path="720p/seg_000.ts")
            finally:
                bad.close()
    finally:
        server.shutdown()

    # Server requires client — connecting without client cert fails at handshake
    server2, base2, _ = _start_mtls_origin(good, origin_root, require_client=True)
    try:
        # Use a fetcher with wrong key material already covered; missing client
        # is enforced at construction (paths required).
        with pytest.raises(MtLsOriginConfigError):
            MtLsHttpsOriginFetcher(
                endpoint_url=base2,
                client_cert_path=tmp_path / "missing.crt",
                client_key_path=tmp_path / "missing.key",
                ca_bundle_path=good.ca_cert,
                enable_mtls_staging_candidate=True,
                allow_loopback_for_tests=True,
                app_env="test",
            )
    finally:
        server2.shutdown()


def test_mtls_expired_and_wrong_san_and_revoked(tmp_path: Path):
    expired = generate_test_pki(tmp_path / "exp", client_days=-1, not_before_days=-10)
    with pytest.raises(MtLsOriginConfigError) as ei:
        MtLsHttpsOriginFetcher(
            endpoint_url="https://127.0.0.1:1",
            client_cert_path=expired.client_cert,
            client_key_path=expired.client_key,
            ca_bundle_path=expired.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="test",
            skip_dns_check=True,
        )
    assert ei.value.code == "cert_expired"

    wrong_san = generate_test_pki(tmp_path / "san", server_sans=["wrong.example"])
    origin_root = tmp_path / "origin"
    _seed_origin(origin_root)
    server, base, _ = _start_mtls_origin(wrong_san, origin_root)
    try:
        fetcher = MtLsHttpsOriginFetcher(
            endpoint_url=base,
            client_cert_path=wrong_san.client_cert,
            client_key_path=wrong_san.client_key,
            ca_bundle_path=wrong_san.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="test",
        )
        with pytest.raises(DataPlaneError):
            fetcher.fetch(asset_id="asset-1", package_id="pkg-1", relative_path="720p/seg_000.ts")
        fetcher.close()
    finally:
        server.shutdown()

    good = generate_test_pki(tmp_path / "rev")
    with pytest.raises(MtLsOriginConfigError) as ei2:
        MtLsHttpsOriginFetcher(
            endpoint_url="https://127.0.0.1:1",
            client_cert_path=good.client_cert,
            client_key_path=good.client_key,
            ca_bundle_path=good.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="test",
            skip_dns_check=True,
            revoked_client_fingerprints=frozenset({good.client_fingerprint_sha256}),
        )
    assert ei2.value.code == "cert_revoked"


def test_mtls_redirect_and_oversize_refused(tmp_path: Path):
    pki = generate_test_pki(tmp_path / "pki")
    origin_root = tmp_path / "origin"
    _seed_origin(origin_root)
    server, base, _ = _start_mtls_origin(pki, origin_root, redirect=True)
    try:
        fetcher = MtLsHttpsOriginFetcher(
            endpoint_url=base,
            client_cert_path=pki.client_cert,
            client_key_path=pki.client_key,
            ca_bundle_path=pki.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="test",
        )
        with pytest.raises(DataPlaneError) as ei:
            fetcher.fetch(asset_id="asset-1", package_id="pkg-1", relative_path="720p/seg_000.ts")
        assert "redirect" in str(ei.value).lower() or ei.value.code == "origin_unavailable"
        fetcher.close()
    finally:
        server.shutdown()

    server2, base2, _ = _start_mtls_origin(pki, origin_root, oversized=True)
    try:
        fetcher = MtLsHttpsOriginFetcher(
            endpoint_url=base2,
            client_cert_path=pki.client_cert,
            client_key_path=pki.client_key,
            ca_bundle_path=pki.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="test",
            max_body_bytes=1024,
        )
        with pytest.raises(DataPlaneError) as ei2:
            fetcher.fetch(asset_id="asset-1", package_id="pkg-1", relative_path="720p/seg_000.ts")
        assert (
            ei2.value.code == "object_too_large"
            or "size" in str(ei2.value).lower()
            or "large" in str(ei2.value).lower()
        )
        fetcher.close()
    finally:
        server2.shutdown()


def test_loopback_forbidden_outside_lab_env(tmp_path: Path):
    pki = generate_test_pki(tmp_path / "pki")
    with pytest.raises(MtLsOriginConfigError) as ei:
        MtLsHttpsOriginFetcher(
            endpoint_url="https://127.0.0.1:8443",
            client_cert_path=pki.client_cert,
            client_key_path=pki.client_key,
            ca_bundle_path=pki.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="staging",
            skip_dns_check=True,
        )
    assert ei.value.code == "loopback_env"


def test_enrollment_manifest_no_secrets(tmp_path: Path):
    man = BranchNodeEnrollmentManifest(
        node_id="node-lab-1",
        site_id="kabul",
        environment="staging-candidate",
        origin_allowlist=[
            OriginAllowlistEntry(https_base_url="https://origin.example.internal:8443")
        ],
        public_trust=PublicTrustRef(
            edge_grant_public_key_fingerprint_sha256="a" * 64,
            edge_grant_key_id="eg1",
            mtls_ca_bundle_fingerprint_sha256="b" * 64,
            mtls_client_cert_fingerprint_sha256="c" * 64,
        ),
    )
    path = tmp_path / "enrollment.json"
    write_enrollment_manifest(path, man)
    loaded = load_enrollment_manifest(path)
    assert loaded.node_id == "node-lab-1"
    assert loaded.live_pilot_ready is False
    text = path.read_text(encoding="utf-8")
    assert "PRIVATE KEY" not in text
    assert "BEGIN CERTIFICATE" not in text
    with pytest.raises(ValueError):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"private_key": "x", **man.model_dump()}), encoding="utf-8")
        load_enrollment_manifest(bad)


def test_staging_gates_require_human_approval(tmp_path: Path):
    man = BranchNodeEnrollmentManifest(
        node_id="node-lab-1",
        site_id="kabul",
        environment="staging-candidate",
        origin_allowlist=[
            OriginAllowlistEntry(https_base_url="https://origin.example.internal:8443")
        ],
        public_trust=PublicTrustRef(
            edge_grant_public_key_fingerprint_sha256="a" * 64,
            edge_grant_key_id="eg1",
            mtls_ca_bundle_fingerprint_sha256="b" * 64,
            mtls_client_cert_fingerprint_sha256="c" * 64,
        ),
    )
    pki = generate_test_pki(tmp_path / "pki")
    _, pub = _pem_pair()
    report = evaluate_staging_candidate_gates(
        StagingGateInput(
            manifest=man,
            cache_root=tmp_path / "cache",
            public_key_pem=pub,
            client_cert_not_after=datetime.now(tz=UTC) + timedelta(days=60),
            ca_bundle_path=pki.ca_cert,
            client_cert_path=pki.client_cert,
            client_key_path=pki.client_key,
            mtls_preflight_ok=True,
            human_approval_recorded=False,
            disk_free_bytes=5_000_000_000,
        )
    )
    assert report["live_pilot_ready"] is False
    assert report["client_redirect_active"] is False
    assert report["deployment_authorized"] is False
    assert "human_approval" in report["failed"]


def test_asgi_http_service_with_mtls_origin_and_drain(tmp_path: Path):
    pki = generate_test_pki(tmp_path / "pki")
    origin_root = tmp_path / "origin"
    _seed_origin(origin_root)
    server, base, _ = _start_mtls_origin(pki, origin_root)
    try:
        settings = _settings()
        fetcher = MtLsHttpsOriginFetcher(
            endpoint_url=base,
            client_cert_path=pki.client_cert,
            client_key_path=pki.client_key,
            ca_bundle_path=pki.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="test",
        )
        app = create_branch_cache_app(
            BranchServiceConfig(
                node_id="node-a",
                site_id="kabul",
                public_key_pem=settings.edge_grant_public_key_pem,
                cache_root=tmp_path / "cache",
                origin=fetcher,
                settings=settings,
                enable_health=True,
                enable_ready=True,
            )
        )
        client = TestClient(app)
        clear_replay_cache_for_tests()
        tok, _ = issue_edge_grant(
            node_id="node-a",
            site_id="kabul",
            package_id="pkg-1",
            session_id="h1",
            path_prefix="/v1/obj/asset-1/pkg-1/",
            settings=settings,
        )
        r = client.get(
            "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
            headers={"Authorization": f"Bearer {tok}", "X-Ifilm-Session-Id": "h1"},
        )
        assert r.status_code == 200
        ready = client.get("/ready").json()
        assert ready["live_origin"] is False
        assert ready["client_redirect"] is False
        app.state.branch_state.start_drain()
        (origin_root / "asset-1" / "pkg-1" / "720p" / "seg_001.ts").write_bytes(b"Y" * 40)
        clear_replay_cache_for_tests()
        tok2, _ = issue_edge_grant(
            node_id="node-a",
            site_id="kabul",
            package_id="pkg-1",
            session_id="h2",
            path_prefix="/v1/obj/asset-1/pkg-1/",
            settings=settings,
        )
        r2 = client.get(
            "/v1/obj/asset-1/pkg-1/720p/seg_001.ts",
            headers={"Authorization": f"Bearer {tok2}", "X-Ifilm-Session-Id": "h2"},
        )
        assert r2.status_code == 503
        app.state.branch_state.start_shutdown()
        clear_replay_cache_for_tests()
        tok3, _ = issue_edge_grant(
            node_id="node-a",
            site_id="kabul",
            package_id="pkg-1",
            session_id="h3",
            path_prefix="/v1/obj/asset-1/pkg-1/",
            settings=settings,
        )
        assert (
            client.get(
                "/v1/obj/asset-1/pkg-1/720p/seg_000.ts",
                headers={"Authorization": f"Bearer {tok3}", "X-Ifilm-Session-Id": "h3"},
            ).status_code
            == 503
        )
        fetcher.close()
    finally:
        server.shutdown()


def test_mtls_origin_logs_never_leak_identifiers(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    import logging

    from app.services.branch_cache.data_plane.mtls_origin import _object_ref_hash

    pki = generate_test_pki(tmp_path / "pki")
    origin_root = tmp_path / "origin"
    _seed_origin(origin_root)
    server, base, _ = _start_mtls_origin(pki, origin_root)
    asset = "asset-secret-42"
    package = "pkg-secret-99"
    rel = "720p/seg_000.ts"
    # Unique identifiable strings that must never appear in logs.
    (origin_root / asset / package / "720p").mkdir(parents=True)
    (origin_root / asset / package / rel).write_bytes(b"SEGMENTDATA" * 64)
    expected_ref = _object_ref_hash(asset_id=asset, package_id=package, relative_path=rel)
    try:
        fetcher = MtLsHttpsOriginFetcher(
            endpoint_url=base,
            client_cert_path=pki.client_cert,
            client_key_path=pki.client_key,
            ca_bundle_path=pki.ca_cert,
            enable_mtls_staging_candidate=True,
            allow_loopback_for_tests=True,
            app_env="test",
        )
        with caplog.at_level(logging.DEBUG, logger="app.branch_cache.mtls_origin"):
            obj = fetcher.fetch(asset_id=asset, package_id=package, relative_path=rel)
            assert obj.size_bytes > 0
            # Force an error path that previously might have logged exception text.
            with pytest.raises(DataPlaneError):
                fetcher.fetch(asset_id=asset, package_id=package, relative_path="720p/missing.ts")
        text = "\n".join(r.getMessage() for r in caplog.records)
        # Must not appear at any captured level:
        for forbidden in (
            asset,
            package,
            rel,
            "720p/",
            base,
            "https://",
            "BEGIN ",
            "PRIVATE KEY",
            "CERTIFICATE",
            "Authorization",
            "Bearer ",
            str(pki.client_cert),
            str(pki.client_key),
            pki.client_fingerprint_sha256,
        ):
            assert forbidden not in text, f"leaked {forbidden!r} in logs: {text}"
        assert "event=mtls_origin_fetch" in text
        assert "correlation_id=" in text
        assert f"object_ref={expected_ref}" in text
        assert "host=" not in text
        assert "asset=" not in text
        assert "package=" not in text
        assert " path=" not in text and not any(
            m.startswith("path=") for m in text.replace("object_ref=", "").split()
        )
        fetcher.close()
    finally:
        server.shutdown()


def test_central_stream_unchanged(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE", "false")
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)
    assert client.get("/api/stream/abcdefghijklmnopqrstuvwx123456/master.m3u8").status_code == 401
