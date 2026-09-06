"""CDN-P1 node runtime + central origin endpoint (in-process, no sockets)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import httpx
import pytest
from app.core.config import get_settings
from app.models.media_assets import MediaAsset, new_uuid, utcnow
from app.models.media_encoding import PACKAGE_TYPE_HLS_VOD, MediaPackage, MediaRendition
from app.services import cdn_management as mgmt
from app.services.branch_cache import metrics
from app.services.branch_cache.data_plane.errors import DataPlaneError
from app.services.branch_cache.grants import clear_replay_cache_for_tests, issue_edge_grant
from app.services.branch_cache.service.state import BranchServiceState
from app.services.cdn_node.asgi import create_node_app
from app.services.cdn_node.config import NodeRuntimeError, load_node_runtime_config
from app.services.cdn_node.heartbeat import HeartbeatClient, collect_metrics
from app.services.cdn_node.origin import CentralHttpOriginFetcher
from app.services.cdn_origin import CDNOriginError, read_package_object
from app.services.storage import ensure_media_layout, media_root, relative_media_path
from app.services.streaming.activation import activate_completed_package
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

BASE = "/api/admin/cdn-management"


def _pem_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return priv, pub


def _node_env(tmp_path: Path, **overrides) -> dict[str, str]:
    env = {
        "ENABLE_CDN_NODE_SERVICE": "true",
        "IFILM_CDN_NODE_ID": "node-1",
        "IFILM_CDN_NODE_ROLE": "cache",
        "IFILM_CDN_SITE_ID": "nimruz",
        "IFILM_CDN_CENTRAL_URL": "https://ifilm.example",
        "IFILM_CDN_NODE_TOKEN": "node-token-test",
        "IFILM_CDN_CACHE_ROOT": str(tmp_path / "cache"),
        "IFILM_CDN_CACHE_LIMIT_BYTES": "10000000",
        "IFILM_CDN_HIGH_WATERMARK_BYTES": "9000000",
        "IFILM_CDN_LOW_WATERMARK_BYTES": "8000000",
        "IFILM_CDN_BIND_PORT": "8443",
        "IFILM_CDN_SOFTWARE_VERSION": "1.0.0+test",
    }
    env.update(overrides)
    return env


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_SECRETS_KEY", key)
    monkeypatch.setenv("ENABLE_CDN_NODE_API", "true")
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


def _seed_active_package(db_session) -> tuple[MediaAsset, MediaPackage]:
    ensure_media_layout()
    asset = MediaAsset(
        id=new_uuid(),
        original_filename="clip.mp4",
        stored_filename="clip.mp4",
        mime_type="video/mp4",
        extension=".mp4",
        size_bytes=1000,
        category="originals",
        upload_status="completed",
        processing_status="completed",
        storage_backend="local",
        storage_path=f"originals/{new_uuid()}/clip.mp4",
        width=640,
        height=360,
        probed_at=utcnow(),
    )
    db_session.add(asset)
    db_session.flush()
    package = MediaPackage(
        id=new_uuid(),
        media_asset_id=asset.id,
        package_type=PACKAGE_TYPE_HLS_VOD,
        status="completed",
        is_active=False,
        segment_duration_seconds=6,
        rendition_count=1,
        completed_at=utcnow(),
    )
    db_session.add(package)
    db_session.flush()
    pkg_dir = media_root() / "packages" / asset.id / package.id
    (pkg_dir / "240p").mkdir(parents=True, exist_ok=True)
    (pkg_dir / "master.m3u8").write_text("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=400000\n240p/index.m3u8\n", encoding="utf-8")
    (pkg_dir / "240p" / "index.m3u8").write_text("#EXTM3U\n#EXTINF:6.0,\nsegment_000.ts\n#EXT-X-ENDLIST\n", encoding="utf-8")
    (pkg_dir / "240p" / "segment_000.ts").write_bytes(b"\x00\x01\x02\x03" * 64)
    package.storage_path = relative_media_path(pkg_dir)
    package.master_playlist_path = relative_media_path(pkg_dir / "master.m3u8")
    db_session.add(
        MediaRendition(
            id=new_uuid(),
            package_id=package.id,
            label="240p",
            height=240,
            width=426,
            bandwidth=400000,
            playlist_path=relative_media_path(pkg_dir / "240p" / "index.m3u8"),
            segment_count=1,
            status="completed",
        )
    )
    db_session.flush()
    activate_completed_package(db_session, package)
    db_session.commit()
    db_session.refresh(package)
    return asset, package


def _register_node(client, admin_headers) -> tuple[dict, str]:
    created = client.post(
        f"{BASE}/nodes",
        headers=admin_headers,
        json={"name": "Node", "role": "cache", "host": "203.0.113.70", "ssh_username": "root", "credential": "bootstrap-x", "cache_limit_bytes": 1000},
    ).json()
    return created["node"], created["heartbeat_token"]


# --- Node runtime config ------------------------------------------------------------


def test_node_config_fails_closed(tmp_path):
    with pytest.raises(NodeRuntimeError) as exc:
        load_node_runtime_config(_node_env(tmp_path, ENABLE_CDN_NODE_SERVICE="false"))
    assert exc.value.code == "flag_off"
    for key, value, code in [
        ("DATABASE_URL", "postgresql://x", "secrets_forbidden"),
        ("EDGE_GRANT_PRIVATE_KEY_PEM", "-----BEGIN PRIVATE KEY-----", "secrets_forbidden"),
        ("ENABLE_CDN_SYNC", "true", "cdn_sync"),
        ("IFILM_CDN_CENTRAL_URL", "http://ifilm.example", "central_url"),
        ("IFILM_CDN_CACHE_ROOT", "/", "cache_root"),
        ("IFILM_CDN_LOW_WATERMARK_BYTES", "9500000", "limits"),
        ("IFILM_CDN_NODE_TOKEN", "", "identity"),
        ("IFILM_CDN_NODE_ROLE", "edge", "role"),
    ]:
        with pytest.raises(NodeRuntimeError) as exc:
            load_node_runtime_config(_node_env(tmp_path, **{key: value}))
        assert exc.value.code == code, key
    cfg = load_node_runtime_config(_node_env(tmp_path))
    assert cfg.node_id == "node-1" and cfg.heartbeat_seconds == 30 and cfg.public_key_pem == ""
    assert "node-token-test" not in repr(cfg)
    key_file = tmp_path / "pub.pem"
    key_file.write_text("-----BEGIN PRIVATE KEY-----\nx\n")
    with pytest.raises(NodeRuntimeError):
        load_node_runtime_config(_node_env(tmp_path, IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE=str(key_file)))


# --- Central origin fetcher (mocked HTTP) -------------------------------------------


class _Responder:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[httpx.Request] = []

    def _client(self):
        def transport(request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            return self.handler(request)

        return httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=False)


def _fetcher(handler, **kw) -> tuple[CentralHttpOriginFetcher, _Responder]:
    responder = _Responder(handler)
    fetcher = CentralHttpOriginFetcher(central_url="https://ifilm.example", node_id="node-1", node_token="node-token-test", client=responder._client(), **kw)
    return fetcher, responder


def test_central_origin_fetcher_validates_checksum_size_and_sends_identity():
    body = b"segment-bytes" * 10
    digest = hashlib.sha256(body).hexdigest()

    def ok(request):
        return httpx.Response(200, content=body, headers={"X-Ifilm-Sha256": digest, "Content-Type": "video/mp2t"})

    fetcher, responder = _fetcher(ok)
    obj = fetcher.fetch(asset_id="a", package_id="p", relative_path="240p/segment_000.ts")
    assert obj.data == body and obj.checksum_sha256 == digest and obj.content_type == "video/mp2t"
    request = responder.calls[0]
    assert request.url == "https://ifilm.example/api/cdn/origin/a/p/240p/segment_000.ts"
    assert request.headers["authorization"] == "Bearer node-token-test"
    assert request.headers["x-ifilm-node-id"] == "node-1"

    fetcher, _ = _fetcher(lambda r: httpx.Response(200, content=body, headers={"X-Ifilm-Sha256": "0" * 64}))
    with pytest.raises(DataPlaneError) as exc:
        fetcher.fetch(asset_id="a", package_id="p", relative_path="240p/segment_000.ts")
    assert exc.value.code == "checksum_mismatch"

    fetcher, _ = _fetcher(lambda r: httpx.Response(200, content=body), max_object_bytes=10)
    with pytest.raises(DataPlaneError) as exc:
        fetcher.fetch(asset_id="a", package_id="p", relative_path="240p/segment_000.ts")
    assert exc.value.code == "object_too_large"

    fetcher, _ = _fetcher(lambda r: httpx.Response(404))
    with pytest.raises(DataPlaneError):
        fetcher.fetch(asset_id="a", package_id="p", relative_path="240p/segment_000.ts")
    assert fetcher.exists(asset_id="a", package_id="p", relative_path="240p/segment_000.ts") is False

    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    fetcher, _ = _fetcher(timeout)
    with pytest.raises(DataPlaneError) as exc:
        fetcher.fetch(asset_id="a", package_id="p", relative_path="240p/segment_000.ts")
    assert exc.value.code == "origin_timeout"
    with pytest.raises(DataPlaneError):
        fetcher.fetch(asset_id="a", package_id="p", relative_path="../../etc/passwd")


# --- Heartbeat client ----------------------------------------------------------------


def test_heartbeat_client_posts_metrics_and_applies_drain(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    cfg = load_node_runtime_config(_node_env(tmp_path))
    from app.services.branch_cache.data_plane.cache_store import CacheStore

    cache = CacheStore(tmp_path / "cache", node_id="node-1", high_watermark_bytes=9_000_000, low_watermark_bytes=8_000_000, min_free_bytes=1000)
    state = BranchServiceState()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "desired": {"draining": True}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    hb = HeartbeatClient(cfg, cache=cache, state=state, client=client)
    assert hb.send_once() is True
    assert seen["url"] == "https://ifilm.example/api/cdn/nodes/node-1/heartbeat"
    assert seen["auth"] == "Bearer node-token-test"
    assert seen["body"]["software_version"] == "1.0.0+test" and "disk_total_bytes" in seen["body"]
    assert state.draining is True and cache.draining is True
    hb.apply_desired({"draining": False})
    assert state.draining is False and cache.draining is False
    assert "node-token-test" not in caplog.text
    metrics_payload = collect_metrics(cfg, cache, last_error="boom")
    assert metrics_payload["degraded"] is True and metrics_payload["cache_used_bytes"] == 0

    def failing(request):
        raise httpx.ConnectError("down", request=request)

    hb_fail = HeartbeatClient(cfg, cache=cache, state=state, client=httpx.Client(transport=httpx.MockTransport(failing)))
    assert hb_fail.send_once() is False and hb_fail.last_ok is False


# --- Node ASGI app ------------------------------------------------------------------


class _LocalOrigin:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.fetches = 0

    def fetch(self, *, asset_id, package_id, relative_path):
        from app.services.branch_cache.data_plane.origin import OriginObject

        key = f"{asset_id}/{package_id}/{relative_path}"
        if key not in self.objects:
            raise DataPlaneError("missing", code="origin_error")
        self.fetches += 1
        data = self.objects[key]
        return OriginObject(key=key, data=data, size_bytes=len(data), content_type="video/mp2t", checksum_sha256=hashlib.sha256(data).hexdigest())

    def exists(self, *, asset_id, package_id, relative_path):
        return f"{asset_id}/{package_id}/{relative_path}" in self.objects


def test_node_app_health_ready_metrics_and_grant_gated_objects(tmp_path):
    metrics.reset_for_tests()
    clear_replay_cache_for_tests()
    priv, pub = _pem_pair()
    origin = _LocalOrigin({"a/p/240p/seg_000.ts": b"SEGMENT" * 100})
    # Without an edge-grant public key: health/ready ok, object serving fails closed.
    cfg = load_node_runtime_config(_node_env(tmp_path))
    app = create_node_app(cfg, origin=origin, start_heartbeat=False)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        ready = client.get("/ready")
        assert ready.status_code == 200 and ready.json()["edge_grant_key"] is False and ready.json()["live_origin"] is True
        assert client.get("/metrics").status_code == 200
        denied = client.get("/v1/obj/a/p/240p/seg_000.ts", headers={"Authorization": "Bearer x", "X-Ifilm-Session-Id": "s1"})
        assert denied.status_code == 503 and denied.json()["error"]["code"] == "edge_grants_not_configured"
        assert origin.fetches == 0
    # With the public key installed: valid grant → miss/fill then hit; bad grants rejected.
    cfg = load_node_runtime_config(_node_env(tmp_path, IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_PEM=pub))
    app = create_node_app(cfg, origin=origin, start_heartbeat=False)
    issue_settings = app.state.branch_cfg.settings.model_copy(update={"enable_branch_cache_control_plane": True, "enable_edge_grant_issue": True, "edge_grant_private_key_pem": priv})
    with TestClient(app) as client:
        token, _ = issue_edge_grant(node_id="node-1", site_id="nimruz", package_id="p", session_id="s1", path_prefix="/v1/obj/a/p/", settings=issue_settings)
        headers = {"Authorization": f"Bearer {token}", "X-Ifilm-Session-Id": "s1"}
        first = client.get("/v1/obj/a/p/240p/seg_000.ts", headers=headers)
        assert first.status_code == 200, first.text
        assert first.headers["X-Ifilm-Decision"] == "cache_miss_filled" and origin.fetches == 1
        token2, _ = issue_edge_grant(node_id="node-1", site_id="nimruz", package_id="p", session_id="s1", path_prefix="/v1/obj/a/p/", settings=issue_settings)
        second = client.get("/v1/obj/a/p/240p/seg_000.ts", headers={**headers, "Authorization": f"Bearer {token2}"})
        assert second.status_code == 200 and second.headers["X-Ifilm-Decision"] == "cache_hit" and origin.fetches == 1
        wrong_node, _ = issue_edge_grant(node_id="node-2", site_id="nimruz", package_id="p", session_id="s1", path_prefix="/v1/obj/a/p/", settings=issue_settings)
        assert client.get("/v1/obj/a/p/240p/seg_000.ts", headers={**headers, "Authorization": f"Bearer {wrong_node}"}).status_code == 403
        assert client.get("/v1/obj/a/p/240p/seg_000.ts", headers={**headers, "Authorization": f"Bearer {token2[:-4]}zzzz"}).status_code == 403
        assert client.get("/v1/obj/a/p/240p/seg_000.ts", headers={"X-Ifilm-Session-Id": "s1"}).status_code == 401
        assert client.post("/v1/obj/a/p/240p/seg_000.ts", headers=headers).status_code == 405
        snapshot = metrics.snapshot()
        assert snapshot["dp_hit"] == 1 and snapshot["dp_miss"] == 1
        payload = collect_metrics(cfg, app.state.branch_engine.cache)
        assert payload["cache_hits"] == 1 and payload["cache_misses"] == 1 and payload["cached_objects"] == 1


# --- Central origin endpoint --------------------------------------------------------


def test_central_origin_endpoint_requires_flag_and_node_token(client, admin_headers, db_session, encryption_key, monkeypatch):
    monkeypatch.setenv("ENABLE_CDN_NODE_API", "false")
    get_settings.cache_clear()
    node, token = _register_node(client, admin_headers)
    headers = {"Authorization": f"Bearer {token}", "X-Ifilm-Node-Id": node["id"]}
    assert client.get("/api/cdn/origin/a/p/master.m3u8", headers=headers).status_code == 503
    get_settings.cache_clear()


def test_central_origin_endpoint_serves_package_objects(client, admin_headers, db_session, encryption_key):
    node, token = _register_node(client, admin_headers)
    asset, package = _seed_active_package(db_session)
    headers = {"Authorization": f"Bearer {token}", "X-Ifilm-Node-Id": node["id"]}
    url = f"/api/cdn/origin/{asset.id}/{package.id}"
    assert client.get(f"{url}/master.m3u8").status_code == 401
    assert client.get(f"{url}/master.m3u8", headers={**headers, "Authorization": "Bearer nope"}).status_code == 401
    master = client.get(f"{url}/master.m3u8", headers=headers)
    assert master.status_code == 200, master.text
    assert master.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert master.headers["X-Ifilm-Sha256"] == hashlib.sha256(master.content).hexdigest()
    assert master.headers["Cache-Control"] == "private, no-store"
    assert master.headers["X-Ifilm-Origin"] == "local"
    segment = client.get(f"{url}/240p/segment_000.ts", headers=headers)
    assert segment.status_code == 200 and segment.content == b"\x00\x01\x02\x03" * 64
    assert client.get(f"{url}/240p/index.m3u8", headers=headers).status_code == 200
    head = client.head(f"{url}/240p/segment_000.ts", headers=headers)
    assert head.status_code == 200 and head.content == b""
    # Path safety / membership.
    assert client.get(f"{url}/../../originals/x.mp4", headers=headers).status_code in {400, 404}
    assert client.get(f"{url}/240p/%2e%2e/master.m3u8", headers=headers).status_code in {400, 404}
    assert client.get(f"{url}/1080p/segment_000.ts", headers=headers).status_code == 404
    assert client.get(f"{url}/240p/segment_000.mp4", headers=headers).status_code in {400, 404}
    assert client.get(f"/api/cdn/origin/{asset.id}/other-package/master.m3u8", headers=headers).status_code == 404
    assert client.get(f"/api/cdn/origin/wrong-asset/{package.id}/master.m3u8", headers=headers).status_code == 404
    # Disabled node loses access.
    client.post(f"{BASE}/nodes/{node['id']}/actions/disable", headers=admin_headers, json={"confirm": True})
    assert client.get(f"{url}/master.m3u8", headers=headers).status_code == 403
    # Object size ceiling applies.
    from app.core.config import Settings

    small = Settings(app_env="test", database_url="sqlite://", jwt_secret="unit-test-jwt-secret-value-32chars-min", cdn_origin_max_object_bytes=10, media_root=get_settings().media_root, _env_file=None)
    with pytest.raises(CDNOriginError) as exc:
        read_package_object(db_session, asset_id=asset.id, package_id=package.id, relative_path="240p/segment_000.ts", settings=small)
    assert exc.value.status_code == 413


def test_inactive_package_not_served(client, admin_headers, db_session, encryption_key):
    node, token = _register_node(client, admin_headers)
    asset, package = _seed_active_package(db_session)
    package.is_active = False
    db_session.add(package)
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}", "X-Ifilm-Node-Id": node["id"]}
    assert client.get(f"/api/cdn/origin/{asset.id}/{package.id}/master.m3u8", headers=headers).status_code == 404
    from app.models.cdn_management import ManagedCDNNode

    assert mgmt.verify_heartbeat_token(db_session.get(ManagedCDNNode, node["id"]), token)
