"""Phase 4 offline branch-cache data-plane simulation tests."""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.core.config import Settings
from app.services.branch_cache import metrics
from app.services.branch_cache.data_plane.cache_store import CacheStore
from app.services.branch_cache.data_plane.engine import BranchDataPlaneEngine, build_sim_engine
from app.services.branch_cache.data_plane.errors import DataPlaneError
from app.services.branch_cache.data_plane.keys import normalize_relative_path
from app.services.branch_cache.data_plane.origin import (
    DeferredHttpOriginFetcher,
    LocalDirOriginFetcher,
)
from app.services.branch_cache.data_plane.sim_harness import run_pilot_readiness_report
from app.services.branch_cache.grants import (
    clear_replay_cache_for_tests,
    issue_edge_grant,
    redact_secrets_from_mapping,
)
from app.services.object_storage.status import safe_storage_status
from app.services.object_storage.validation import collect_object_storage_errors
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt


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
        edge_grant_private_key_pem=priv,
        edge_grant_public_key_pem=pub,
        edge_grant_key_id="eg1",
        edge_grant_ttl_seconds=120,
        _env_file=None,
    )
    base.update(kwargs)
    return Settings(**base)


def _write_pkg(origin: Path, *, asset: str = "asset-1", pkg: str = "pkg-1") -> None:
    base = origin / asset / pkg
    (base / "720p").mkdir(parents=True, exist_ok=True)
    (base / "master.m3u8").write_text("#EXTM3U\n720p/index.m3u8\n", encoding="utf-8")
    (base / "720p" / "index.m3u8").write_text("#EXTM3U\nseg_000.ts\n", encoding="utf-8")
    (base / "720p" / "seg_000.ts").write_bytes(b"SEGMENT-BYTES-" * 64)


def _engine(tmp_path: Path, settings: Settings | None = None) -> BranchDataPlaneEngine:
    cfg = settings or _settings()
    origin = tmp_path / "origin"
    cache = tmp_path / "cache"
    _write_pkg(origin)
    return build_sim_engine(
        cache_root=cache,
        origin_root=origin,
        node_id="node-a",
        site_id="kabul",
        public_key_pem=cfg.edge_grant_public_key_pem,
        settings=cfg,
        high_watermark_bytes=80_000,
        low_watermark_bytes=30_000,
        min_free_bytes=5_000,
    )


def _token(settings: Settings, *, session: str, path_prefix: str = "/hls/pkg-1/", **kw) -> str:
    clear_replay_cache_for_tests()
    token, _ = issue_edge_grant(
        node_id=kw.get("node_id", "node-a"),
        site_id=kw.get("site_id", "kabul"),
        package_id=kw.get("package_id", "pkg-1"),
        session_id=session,
        path_prefix=path_prefix,
        settings=settings,
    )
    return token


# --- flags ---


def test_phase4_flags_default_off():
    settings = Settings(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        _env_file=None,
    )
    assert settings.enable_branch_cache_data_plane_sim is False
    assert settings.enable_branch_cache_pull_through is False
    assert settings.enable_branch_cache_local_serve is False
    status = safe_storage_status(settings)
    assert status["roles"]["branch_cache"]["client_redirect_active"] is False
    assert status["policy"]["branch_data_plane_sim_only"] is True


def test_prod_rejects_data_plane_sim():
    priv, pub = _pem_pair()
    settings = _settings(
        app_env="production",
        enable_branch_cache_data_plane_sim=True,
        edge_grant_private_key_pem=priv,
        edge_grant_public_key_pem=pub,
    )
    errors = collect_object_storage_errors(settings)
    assert any("DATA_PLANE_SIM" in e for e in errors)


def test_pull_through_requires_sim_flag():
    settings = _settings(
        enable_branch_cache_data_plane_sim=False,
        enable_branch_cache_pull_through=True,
    )
    errors = collect_object_storage_errors(settings)
    assert any("PULL_THROUGH" in e for e in errors)


def test_flags_off_engine_does_not_serve(tmp_path: Path):
    settings = _settings(
        enable_branch_cache_data_plane_sim=False,
        enable_branch_cache_local_serve=False,
        enable_branch_cache_pull_through=False,
    )
    # Validation would fail for pull-through without sim; construct engine directly
    engine = _engine(tmp_path, settings=_settings(enable_branch_cache_data_plane_sim=False))
    engine.settings = settings
    tok = _token(_settings(), session="s0")
    resp = engine.serve(
        grant_token=tok,
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="s0",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
    )
    assert resp.decision.fallback_to_central is True


# --- path / auth ---


def test_path_rejects_traversal_and_encoding():
    with pytest.raises(DataPlaneError):
        normalize_relative_path("../etc/passwd.ts")
    with pytest.raises(DataPlaneError):
        normalize_relative_path("%2e%2e/secret.ts")
    with pytest.raises(DataPlaneError):
        normalize_relative_path("720p/seg.exe")


def test_auth_before_io_and_bindings(tmp_path: Path):
    metrics.reset_for_tests()
    settings = _settings()
    engine = _engine(tmp_path, settings)
    # Wrong package
    tok = _token(settings, session="s1", package_id="other-pkg")
    resp = engine.serve(
        grant_token=tok,
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="s1",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
    )
    assert resp.status_code == 403
    assert not engine.cache.has("master.m3u8")

    # Outside path prefix
    tok2 = _token(settings, session="s2", path_prefix="/hls/other/")
    resp2 = engine.serve(
        grant_token=tok2,
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="s2",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
    )
    assert resp2.status_code == 403

    # Session mismatch
    tok3 = _token(settings, session="s3")
    resp3 = engine.serve(
        grant_token=tok3,
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="different",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
    )
    assert resp3.status_code == 403


def test_expired_and_alg_confusion_rejected(tmp_path: Path):
    settings = _settings()
    engine = _engine(tmp_path, settings)
    past = datetime.now(UTC) - timedelta(hours=1)
    clear_replay_cache_for_tests()
    token, _ = issue_edge_grant(
        node_id="node-a",
        site_id="kabul",
        package_id="pkg-1",
        session_id="sx",
        path_prefix="/hls/pkg-1/",
        settings=settings,
        now=past,
        ttl_seconds=30,
    )
    resp = engine.serve(
        grant_token=token,
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="sx",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
        enforce_replay=False,
    )
    assert resp.status_code == 403

    forged = jwt.encode(
        {
            "typ": "edge_grant",
            "jti": "z",
            "iss": settings.edge_grant_issuer,
            "aud": settings.edge_grant_audience,
            "nid": "node-a",
            "sid": "kabul",
            "pkg": "pkg-1",
            "sess": "sy",
            "path_prefix": "/hls/pkg-1/",
            "iat": int(datetime.now(UTC).timestamp()),
            "nbf": int(datetime.now(UTC).timestamp()),
            "exp": int(datetime.now(UTC).timestamp()) + 60,
        },
        settings.jwt_secret,
        algorithm="HS256",
        headers={"alg": "HS256", "kid": "eg1"},
    )
    resp2 = engine.serve(
        grant_token=forged,
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="sy",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
        enforce_replay=False,
    )
    assert resp2.status_code == 403


# --- cache store ---


def test_symlink_and_root_confinement(tmp_path: Path):
    root = tmp_path / "cache"
    store = CacheStore(
        root,
        node_id="n",
        high_watermark_bytes=10_000_000,
        low_watermark_bytes=5_000_000,
        min_free_bytes=1000,
    )
    data = b"hello-segment-data-ok"
    digest = hashlib.sha256(data).hexdigest()
    store.put_atomic(
        "720p/seg_000.ts",
        data,
        content_type="video/mp2t",
        checksum_sha256=digest,
        origin_key="o",
    )
    # Plant symlink attack outside
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = store.objects_dir / "aa" / "evil"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink not supported")
    with pytest.raises(DataPlaneError):
        store._reject_symlinks(link)  # noqa: SLF001


def test_atomic_fill_checksum_and_partial_cleanup(tmp_path: Path):
    store = CacheStore(
        tmp_path / "c",
        node_id="n",
        high_watermark_bytes=10_000_000,
        low_watermark_bytes=5_000_000,
        min_free_bytes=1000,
    )
    data = b"abc123"
    with pytest.raises(DataPlaneError):
        store.put_atomic(
            "720p/seg_000.ts",
            data,
            content_type="video/mp2t",
            checksum_sha256="0" * 64,
            origin_key="o",
        )
    assert store.has("720p/seg_000.ts") is False
    # leftover part cleaned by failed path
    assert list((tmp_path / "c" / "tmp").glob("*.part")) == []


def test_hit_miss_range_etag_manifest(tmp_path: Path):
    settings = _settings()
    engine = _engine(tmp_path, settings)
    tok = _token(settings, session="h1")
    miss = engine.serve(
        grant_token=tok,
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="h1",
        relative_path="720p/seg_000.ts",
        path_prefix="/hls/pkg-1/",
    )
    assert miss.status_code == 200
    assert miss.decision.decision == "cache_miss_filled"
    assert miss.etag

    hit = engine.serve(
        grant_token=_token(settings, session="h2"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="h2",
        relative_path="720p/seg_000.ts",
        path_prefix="/hls/pkg-1/",
    )
    assert hit.decision.from_cache is True
    assert hit.body == miss.body

    ranged = engine.serve(
        grant_token=_token(settings, session="h3"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="h3",
        relative_path="720p/seg_000.ts",
        path_prefix="/hls/pkg-1/",
        range_header="bytes=0-9",
    )
    assert ranged.status_code == 206
    assert ranged.content_length == 10
    assert ranged.body == miss.body[:10]

    playlist = engine.serve(
        grant_token=_token(settings, session="h4"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="h4",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
    )
    assert "mpegurl" in playlist.content_type
    assert "no-store" in playlist.cache_control


def test_single_flight_coalesce(tmp_path: Path):
    settings = _settings()
    engine = _engine(tmp_path, settings)
    # Slow origin
    engine.origin.artificial_latency_ms = 50  # type: ignore[attr-defined]
    results: list[int] = []

    def _worker(i: int) -> None:
        resp = engine.serve(
            grant_token=_token(settings, session=f"c{i}"),
            asset_id="asset-1",
            package_id="pkg-1",
            session_id=f"c{i}",
            relative_path="720p/seg_000.ts",
            path_prefix="/hls/pkg-1/",
        )
        results.append(resp.status_code)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200] * 6
    assert metrics.snapshot()["dp_coalesced"] >= 1


def test_origin_outage_and_checksum_no_poison(tmp_path: Path):
    settings = _settings()
    engine = _engine(tmp_path, settings)
    engine.origin.fail_paths = frozenset({"720p/index.m3u8"})  # type: ignore[attr-defined]
    resp = engine.serve(
        grant_token=_token(settings, session="o1"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="o1",
        relative_path="720p/index.m3u8",
        path_prefix="/hls/pkg-1/",
    )
    assert resp.decision.fallback_to_central
    assert engine.cache.has("720p/index.m3u8") is False

    engine.origin.fail_paths = frozenset()  # type: ignore[attr-defined]
    engine.origin.corrupt_checksum_paths = frozenset({"master.m3u8"})  # type: ignore[attr-defined]
    resp2 = engine.serve(
        grant_token=_token(settings, session="o2"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="o2",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
    )
    assert resp2.decision.fallback_to_central
    assert engine.cache.has("master.m3u8") is False


def test_eviction_in_use_pin_drain(tmp_path: Path):
    store = CacheStore(
        tmp_path / "c",
        node_id="n",
        high_watermark_bytes=10_000,
        low_watermark_bytes=4_000,
        min_free_bytes=1_000,
    )
    for i in range(8):
        payload = bytes([i]) * 2000
        digest = hashlib.sha256(payload).hexdigest()
        store.put_atomic(
            f"720p/obj_{i}.ts",
            payload,
            content_type="video/mp2t",
            checksum_sha256=digest,
            origin_key=f"o{i}",
        )
    assert store.used_bytes() <= store.high_watermark_bytes

    # Pin one and mark in use — should survive further pressure
    remaining = [p for p in store._index]  # noqa: SLF001
    assert remaining
    pinned = remaining[0]
    store.pin(pinned, True)
    store.mark_in_use(pinned, 1)
    for i in range(8, 16):
        payload = bytes([i]) * 2000
        digest = hashlib.sha256(payload).hexdigest()
        store.put_atomic(
            f"720p/more_{i}.ts",
            payload,
            content_type="video/mp2t",
            checksum_sha256=digest,
            origin_key=f"m{i}",
        )
    assert store.has(pinned)

    store.draining = True
    with pytest.raises(DataPlaneError):
        store.put_atomic(
            "720p/new.ts",
            b"x" * 100,
            content_type="video/mp2t",
            checksum_sha256=hashlib.sha256(b"x" * 100).hexdigest(),
            origin_key="n",
        )


def test_prewarm_bounds_dedupe_cancel(tmp_path: Path):
    settings = _settings()
    engine = _engine(tmp_path, settings)
    planner = engine.prewarm
    planner.max_queue = 3
    planner.max_per_package = 2
    a = planner.enqueue(asset_id="asset-1", package_id="pkg-1", relative_path="master.m3u8")
    b = planner.enqueue(asset_id="asset-1", package_id="pkg-1", relative_path="master.m3u8")
    assert a is b  # dedupe
    planner.enqueue(asset_id="asset-1", package_id="pkg-1", relative_path="720p/index.m3u8")
    assert (
        planner.enqueue(asset_id="asset-1", package_id="pkg-1", relative_path="720p/seg_000.ts")
        is None
    )
    planner.cancel(asset_id="asset-1", package_id="pkg-1", relative_path="master.m3u8")
    item = planner.pop_next()
    assert item is not None
    assert item.relative_path == "720p/index.m3u8"
    out = engine.run_prewarm_once()
    # queue may be empty after pop — run processes current running via mark; call again
    assert out["processed"] is False or "ok" in out


def test_deferred_http_fetcher_uninstantiable():
    with pytest.raises(RuntimeError):
        DeferredHttpOriginFetcher("https://example")


def test_secret_redaction_and_status(tmp_path: Path):
    settings = _settings()
    engine = _engine(tmp_path, settings)
    public = engine.serve(
        grant_token=_token(settings, session="r1"),
        asset_id="asset-1",
        package_id="pkg-1",
        session_id="r1",
        relative_path="master.m3u8",
        path_prefix="/hls/pkg-1/",
    ).as_public_dict()
    blob = str(public) + str(engine.cache.status()) + str(metrics.snapshot())
    assert "PRIVATE" not in blob
    assert settings.edge_grant_private_key_pem not in blob
    redacted = redact_secrets_from_mapping({"token": "abc", "edge_grant_private_key_pem": "SECRET"})
    assert redacted["token"] == "[redacted]"


def test_pilot_readiness_report(tmp_path: Path):
    settings = _settings()
    report = run_pilot_readiness_report(
        cache_root=tmp_path / "cache",
        origin_root=tmp_path / "origin",
        settings=settings,
        public_key_pem=settings.edge_grant_public_key_pem,
        node_id="pilot-node-01",
        site_id="kabul",
    )
    assert report["client_redirect_active"] is False
    assert report["live_network"] is False
    assert report["data_plane_mode"] == "simulation"
    assert report["pilot_ready"] is True
    assert "hit_ratio" in report["model"]


def test_oversized_object_rejected(tmp_path: Path):
    origin = tmp_path / "origin"
    _write_pkg(origin)
    big = origin / "asset-1" / "pkg-1" / "720p" / "big.ts"
    big.write_bytes(b"Z" * 10_000)
    fetcher = LocalDirOriginFetcher(origin, max_object_bytes=1000)
    with pytest.raises(DataPlaneError) as exc:
        fetcher.fetch(asset_id="asset-1", package_id="pkg-1", relative_path="720p/big.ts")
    assert exc.value.code == "object_too_large"
