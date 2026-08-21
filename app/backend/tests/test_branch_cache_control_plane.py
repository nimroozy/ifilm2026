"""Hybrid CDN Phase 3 — branch-cache control plane tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.models.admin import AdminRole, AdminUser
from app.models.branch_cache import STATUS_ONLINE, BranchCacheNode
from app.models.media_assets import new_uuid
from app.services.branch_cache import grants as grant_svc
from app.services.branch_cache import metrics
from app.services.branch_cache import registry as reg
from app.services.branch_cache import routing as route_svc
from app.services.branch_cache.validation import (
    BranchCacheValidationError,
    validate_base_url,
    validate_node_id,
)
from app.services.object_storage.status import safe_storage_status
from app.services.object_storage.validation import collect_object_storage_errors
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwt


def _es256_pem_pair() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def _settings(**kwargs) -> Settings:
    priv, pub = _es256_pem_pair()
    base = dict(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        enable_object_storage=False,
        enable_cdn_sync=False,
        enable_branch_cache_control_plane=False,
        enable_edge_grant_issue=False,
        enable_branch_cache_shadow_routing=False,
        edge_grant_private_key_pem=priv,
        edge_grant_public_key_pem=pub,
        edge_grant_key_id="eg1",
        edge_grant_ttl_seconds=120,
        branch_cache_heartbeat_stale_seconds=90,
        branch_cache_min_free_bytes=1_000_000_000,
        branch_cache_min_protocol_version="1",
        _env_file=None,
    )
    base.update(kwargs)
    return Settings(**base)


def _admin_headers(db_session, *, permissions: list[str] | None = None) -> dict[str, str]:
    perms = permissions or ["cdn.read", "cdn.manage"]
    role = AdminRole(name=f"bc-{new_uuid()[:8]}", permissions=perms)
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=f"bc-{new_uuid()[:8]}",
        email=f"{new_uuid()[:8]}@example.test",
        full_name="Branch Cache Admin",
        hashed_password=hash_password("branch-cache-admin-pass"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    token = create_access_token(str(admin.id), {"typ": "admin", "username": admin.username})
    return {"Authorization": f"Bearer {token}"}


def _enable_control_plane(monkeypatch, **extra):
    priv, pub = _es256_pem_pair()
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_CONTROL_PLANE", "true")
    monkeypatch.setenv(
        "ENABLE_EDGE_GRANT_ISSUE",
        "true" if extra.get("enable_edge_grant_issue", True) else "false",
    )
    monkeypatch.setenv(
        "ENABLE_BRANCH_CACHE_SHADOW_ROUTING",
        "true" if extra.get("enable_shadow", True) else "false",
    )
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_branch_cache_control_plane", True)
    monkeypatch.setattr(
        settings,
        "enable_edge_grant_issue",
        bool(extra.get("enable_edge_grant_issue", True)),
    )
    monkeypatch.setattr(
        settings,
        "enable_branch_cache_shadow_routing",
        bool(extra.get("enable_shadow", True)),
    )
    monkeypatch.setattr(settings, "edge_grant_private_key_pem", priv)
    monkeypatch.setattr(settings, "edge_grant_public_key_pem", pub)
    monkeypatch.setattr(settings, "edge_grant_key_id", "eg1")
    return priv, pub


# --- flags / validation ---


def test_phase3_flags_default_off():
    settings = _settings()
    assert settings.enable_branch_cache_control_plane is False
    assert settings.enable_edge_grant_issue is False
    assert settings.enable_branch_cache_shadow_routing is False
    status = safe_storage_status(settings)
    assert status["enable_branch_cache_control_plane"] is False
    assert status["roles"]["branch_cache"]["data_plane_active"] is False
    assert status["roles"]["branch_cache"]["client_redirect_active"] is False


def test_edge_grant_requires_control_plane_flag():
    settings = _settings(enable_edge_grant_issue=True, enable_branch_cache_control_plane=False)
    errors = collect_object_storage_errors(settings)
    assert any("ENABLE_EDGE_GRANT_ISSUE" in e for e in errors)


def test_prod_rejects_legacy_cdn_with_control_plane():
    settings = _settings(
        app_env="production",
        enable_branch_cache_control_plane=True,
        enable_cdn_sync=True,
    )
    errors = collect_object_storage_errors(settings)
    assert any("ENABLE_CDN_SYNC" in e for e in errors)


@pytest.mark.parametrize(
    "url,code",
    [
        ("http://cache.branch.example/path", "unsupported_scheme"),
        ("https://user:pass@cache.example/", "credentials_in_url"),
        ("https://cache.example/?x=1", "query_or_fragment"),
        ("https://cache.example/#frag", "query_or_fragment"),
        ("https://127.0.0.1/", "blocked_ip"),
        ("https://169.254.169.254/", "blocked_ip"),
        ("https://localhost/", "blocked_host"),
        ("https://metadata.google.internal/", "blocked_host"),
        ("https://cache.example/../escape", "unsafe_path"),
    ],
)
def test_base_url_rejects_unsafe(url, code):
    with pytest.raises(BranchCacheValidationError) as exc:
        validate_base_url(url, allow_http=False)
    assert exc.value.code == code


def test_base_url_allows_private_https():
    assert validate_base_url("https://10.20.30.40:8443/") == "https://10.20.30.40:8443/"


def test_node_id_validation():
    assert validate_node_id("kabul-01") == "kabul-01"
    with pytest.raises(BranchCacheValidationError):
        validate_node_id("AB")


# --- registry / routing ---


def test_registry_lifecycle_and_routing(db_session):
    metrics.reset_for_tests()
    settings = _settings(
        enable_branch_cache_control_plane=True,
        enable_branch_cache_shadow_routing=True,
        branch_cache_min_free_bytes=100,
    )
    role = AdminRole(name=f"r-{new_uuid()[:8]}", permissions=["cdn.manage"])
    db_session.add(role)
    db_session.flush()
    admin = AdminUser(
        username=f"a-{new_uuid()[:8]}",
        email=f"{new_uuid()[:8]}@t",
        full_name="A",
        hashed_password=hash_password("x"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    node, enrollment = reg.create_node(
        db_session,
        admin=admin,
        node_id="kabul-a",
        display_name="Kabul A",
        site_id="kabul",
        base_url="https://10.1.1.10/",
        capacity_bytes=10_000,
        protocol_version="1.0",
        issue_enrollment_token=True,
        settings=settings,
    )
    assert enrollment
    assert node.heartbeat_token_hash
    public = reg.node_to_public_dict(node)
    assert "heartbeat_token_hash" not in public
    assert public["has_heartbeat_token"] is True

    # Not eligible until healthy heartbeat
    decision = route_svc.select_branch_cache_node(db_session, site_id="kabul", settings=settings)
    assert decision.mode == "central_origin"

    # Bad enrollment token
    with pytest.raises(BranchCacheValidationError):
        reg.record_heartbeat(
            db_session, node, enrollment_token="wrong", used_bytes=10, settings=settings
        )

    node = reg.record_heartbeat(
        db_session,
        node,
        enrollment_token=enrollment,
        used_bytes=10,
        capacity_bytes=10_000,
        protocol_version="1.0",
        healthy=True,
        settings=settings,
    )
    assert node.status == STATUS_ONLINE
    assert node.health_status == "healthy"

    decision = route_svc.select_branch_cache_node(
        db_session, site_id="kabul", package_id="pkg-1", settings=settings
    )
    assert decision.mode == "branch_cache"
    assert decision.node_id == "kabul-a"
    assert decision.reason == route_svc.REASON_SELECTED

    # Drain → fallback
    node = reg.update_node(db_session, node, draining=True, settings=settings)
    decision = route_svc.select_branch_cache_node(db_session, site_id="kabul", settings=settings)
    assert decision.mode == "central_origin"

    # Re-enable, then disable
    node = reg.update_node(
        db_session, node, draining=False, status=STATUS_ONLINE, settings=settings
    )
    node = reg.update_node(db_session, node, disabled=True, settings=settings)
    decision = route_svc.select_branch_cache_node(db_session, site_id="kabul", settings=settings)
    assert decision.mode == "central_origin"


def test_routing_determinism_and_capacity(db_session):
    settings = _settings(
        enable_branch_cache_control_plane=True,
        branch_cache_min_free_bytes=100,
    )
    now = datetime.now(UTC)
    for nid, used, cap in (("node-b", 100, 1000), ("node-a", 50, 1000)):
        n = BranchCacheNode(
            id=new_uuid(),
            node_id=nid,
            display_name=nid,
            site_id="herat",
            base_url=f"https://10.2.2.{nid[-1]}/",
            status=STATUS_ONLINE,
            draining=False,
            disabled=False,
            protocol_version="1",
            capacity_bytes=cap,
            used_bytes=used,
            last_heartbeat_at=now,
            last_health_ok_at=now,
            health_status="healthy",
        )
        db_session.add(n)
    db_session.commit()

    d1 = route_svc.select_branch_cache_node(db_session, site_id="herat", settings=settings)
    d2 = route_svc.select_branch_cache_node(db_session, site_id="herat", settings=settings)
    # Higher free capacity first: node-a has 950 free vs node-b 900
    assert d1.node_id == "node-a"
    assert d2.node_id == "node-a"

    # Capacity threshold
    d3 = route_svc.select_branch_cache_node(
        db_session, site_id="herat", require_bytes=960, settings=settings
    )
    # Only node-a has 950 free — both fail if require 960 and min_free is max(960,100)=960
    assert d3.mode == "central_origin"

    # Stale heartbeat
    stale = db_session.query(BranchCacheNode).filter_by(node_id="node-a").one()
    stale.last_heartbeat_at = now - timedelta(seconds=500)
    db_session.commit()
    d4 = route_svc.select_branch_cache_node(db_session, site_id="herat", settings=settings)
    assert d4.node_id == "node-b"

    # Protocol mismatch
    other = db_session.query(BranchCacheNode).filter_by(node_id="node-b").one()
    other.protocol_version = "2"
    db_session.commit()
    d5 = route_svc.select_branch_cache_node(db_session, site_id="herat", settings=settings)
    assert d5.mode == "central_origin"


def test_routing_off_preserves_central_fallback(db_session):
    settings = _settings(enable_branch_cache_control_plane=False)
    decision = route_svc.select_branch_cache_node(db_session, site_id="kabul", settings=settings)
    assert decision.mode == "central_origin"
    assert decision.reason == route_svc.REASON_CONTROL_PLANE_OFF


# --- edge grants ---


def test_edge_grant_sign_verify_and_bindings():
    grant_svc.clear_replay_cache_for_tests()
    settings = _settings(
        enable_branch_cache_control_plane=True,
        enable_edge_grant_issue=True,
    )
    token, claims = grant_svc.issue_edge_grant(
        node_id="kabul-01",
        site_id="kabul",
        package_id="pkg-abc",
        session_id="sess-1",
        path_prefix="/hls/pkg-abc/",
        settings=settings,
    )
    assert claims.kid == "eg1"
    verified = grant_svc.verify_edge_grant(
        token,
        expected_node_id="kabul-01",
        expected_package_id="pkg-abc",
        expected_path="/hls/pkg-abc/master.m3u8",
        settings=settings,
    )
    assert verified.jti == claims.jti

    # Replay
    with pytest.raises(grant_svc.EdgeGrantError) as exc:
        grant_svc.verify_edge_grant(
            token,
            expected_node_id="kabul-01",
            expected_package_id="pkg-abc",
            settings=settings,
        )
    assert exc.value.code == "replay"

    grant_svc.clear_replay_cache_for_tests()
    with pytest.raises(grant_svc.EdgeGrantError) as exc:
        grant_svc.verify_edge_grant(
            token,
            expected_node_id="other-node",
            settings=settings,
            enforce_replay=False,
        )
    assert exc.value.code == "node_mismatch"

    with pytest.raises(grant_svc.EdgeGrantError) as exc:
        grant_svc.verify_edge_grant(
            token,
            expected_node_id="kabul-01",
            expected_package_id="other-pkg",
            settings=settings,
            enforce_replay=False,
        )
    assert exc.value.code == "package_mismatch"

    with pytest.raises(grant_svc.EdgeGrantError) as exc:
        grant_svc.verify_edge_grant(
            token,
            expected_node_id="kabul-01",
            expected_path="/other/path",
            settings=settings,
            enforce_replay=False,
        )
    assert exc.value.code == "path_mismatch"


def test_edge_grant_alg_confusion_and_ttl_and_expiry():
    grant_svc.clear_replay_cache_for_tests()
    settings = _settings(
        enable_branch_cache_control_plane=True,
        enable_edge_grant_issue=True,
    )
    with pytest.raises(grant_svc.EdgeGrantError) as exc:
        grant_svc.issue_edge_grant(
            node_id="kabul-01",
            site_id="kabul",
            package_id="p",
            session_id="s",
            path_prefix="/x/",
            ttl_seconds=9999,
            settings=settings,
        )
    assert exc.value.code == "ttl_too_long"

    token, _ = grant_svc.issue_edge_grant(
        node_id="kabul-01",
        site_id="kabul",
        package_id="p",
        session_id="s",
        path_prefix="/x/",
        ttl_seconds=30,
        settings=settings,
    )

    # Alg confusion: HS256 with jwt_secret must be rejected
    forged = jwt.encode(
        {
            "typ": grant_svc.EDGE_GRANT_TYP,
            "jti": "x",
            "iss": settings.edge_grant_issuer,
            "aud": settings.edge_grant_audience,
            "nid": "kabul-01",
            "sid": "kabul",
            "pkg": "p",
            "sess": "s",
            "path_prefix": "/x/",
            "iat": int(datetime.now(UTC).timestamp()),
            "nbf": int(datetime.now(UTC).timestamp()),
            "exp": int(datetime.now(UTC).timestamp()) + 60,
        },
        settings.jwt_secret,
        algorithm="HS256",
        headers={"alg": "HS256", "kid": "eg1"},
    )
    with pytest.raises(grant_svc.EdgeGrantError) as exc:
        grant_svc.verify_edge_grant(
            forged, expected_node_id="kabul-01", settings=settings, enforce_replay=False
        )
    assert exc.value.code == "alg_confusion"

    # Expired
    past = datetime.now(UTC) - timedelta(hours=1)
    token2, _ = grant_svc.issue_edge_grant(
        node_id="kabul-01",
        site_id="kabul",
        package_id="p",
        session_id="s",
        path_prefix="/x/",
        ttl_seconds=30,
        settings=settings,
        now=past,
    )
    with pytest.raises(grant_svc.EdgeGrantError) as exc:
        grant_svc.verify_edge_grant(
            token2, expected_node_id="kabul-01", settings=settings, enforce_replay=False
        )
    assert exc.value.code in {"expired", "verify_failed"}


def test_edge_grant_key_rotation_kid_mismatch():
    grant_svc.clear_replay_cache_for_tests()
    settings = _settings(
        enable_branch_cache_control_plane=True,
        enable_edge_grant_issue=True,
        edge_grant_key_id="eg1",
    )
    token, _ = grant_svc.issue_edge_grant(
        node_id="kabul-01",
        site_id="kabul",
        package_id="p",
        session_id="s",
        path_prefix="/x/",
        settings=settings,
    )
    rotated = _settings(
        enable_branch_cache_control_plane=True,
        enable_edge_grant_issue=True,
        edge_grant_key_id="eg2",
        edge_grant_private_key_pem=settings.edge_grant_private_key_pem,
        edge_grant_public_key_pem=settings.edge_grant_public_key_pem,
    )
    with pytest.raises(grant_svc.EdgeGrantError) as exc:
        grant_svc.verify_edge_grant(
            token, expected_node_id="kabul-01", settings=rotated, enforce_replay=False
        )
    assert exc.value.code == "untrusted_kid"


def test_secret_redaction():
    redacted = grant_svc.redact_secrets_from_mapping(
        {"edge_grant_private_key_pem": "SECRET", "ok": 1, "nested": {"token": "x"}}
    )
    assert redacted["edge_grant_private_key_pem"] == "[redacted]"
    assert redacted["nested"]["token"] == "[redacted]"
    assert redacted["ok"] == 1


def test_jwks_never_includes_private_key():
    settings = _settings(enable_branch_cache_control_plane=True)
    jwks = grant_svc.public_jwks(settings)
    blob = str(jwks)
    assert "PRIVATE KEY" not in blob
    assert settings.edge_grant_private_key_pem not in blob
    assert "PUBLIC KEY" in blob


# --- API / RBAC ---


def test_admin_apis_rbac_and_lifecycle(client, db_session, monkeypatch):
    metrics.reset_for_tests()
    _enable_control_plane(monkeypatch)
    headers = _admin_headers(db_session)
    reader = _admin_headers(db_session, permissions=["cdn.read"])

    # Flag-gated status always available for read (status does not require feature)
    st = client.get("/api/admin/branch-cache/status", headers=headers)
    assert st.status_code == 200
    body = st.json()
    assert body["data_plane_active"] is False
    assert body["client_redirect_active"] is False
    assert "edge_grant_private_key_pem" not in str(body).lower()

    # Manage required for create
    denied = client.post(
        "/api/admin/branch-cache/nodes",
        headers=reader,
        json={
            "node_id": "kabul-01",
            "display_name": "Kabul",
            "site_id": "kabul",
            "base_url": "https://10.9.9.9/",
            "issue_enrollment_token": True,
        },
    )
    assert denied.status_code == 403

    created = client.post(
        "/api/admin/branch-cache/nodes",
        headers=headers,
        json={
            "node_id": "kabul-01",
            "display_name": "Kabul",
            "site_id": "kabul",
            "base_url": "https://10.9.9.9/",
            "capacity_bytes": 5_000_000_000,
            "protocol_version": "1",
            "issue_enrollment_token": True,
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["enrollment_token"]
    assert "heartbeat_token_hash" not in payload["node"]
    enrollment = payload["enrollment_token"]

    # List never leaks hash
    listed = client.get("/api/admin/branch-cache/nodes", headers=reader)
    assert listed.status_code == 200
    assert all("heartbeat_token_hash" not in n for n in listed.json())

    # Reject unsafe URL
    bad = client.post(
        "/api/admin/branch-cache/nodes",
        headers=headers,
        json={
            "node_id": "evil-01",
            "display_name": "Evil",
            "site_id": "kabul",
            "base_url": "https://169.254.169.254/",
        },
    )
    assert bad.status_code == 400

    hb = client.post(
        "/api/admin/branch-cache/nodes/kabul-01/heartbeat",
        headers=headers,
        json={
            "enrollment_token": enrollment,
            "used_bytes": 1000,
            "capacity_bytes": 5_000_000_000,
            "protocol_version": "1",
            "healthy": True,
        },
    )
    assert hb.status_code == 200, hb.text
    assert hb.json()["status"] == "online"

    route = client.post(
        "/api/admin/branch-cache/routing/dry-run",
        headers=reader,
        json={"site_id": "kabul", "package_id": "pkg-1"},
    )
    assert route.status_code == 200
    assert route.json()["mode"] == "branch_cache"
    assert route.json()["shadow"] is True

    grant = client.post(
        "/api/admin/branch-cache/edge-grants/issue",
        headers=headers,
        json={
            "node_id": "kabul-01",
            "site_id": "kabul",
            "package_id": "pkg-1",
            "session_id": "sess-1",
            "path_prefix": "/hls/pkg-1/",
        },
    )
    assert grant.status_code == 200, grant.text
    token = grant.json()["token"]
    assert "PRIVATE" not in grant.text

    verified = client.post(
        "/api/admin/branch-cache/edge-grants/verify",
        headers=headers,
        json={"token": token, "node_id": "kabul-01", "package_id": "pkg-1", "path": "/hls/pkg-1/a"},
    )
    assert verified.status_code == 200
    assert verified.json()["valid"] is True

    jwks = client.get("/api/admin/branch-cache/jwks", headers=reader)
    assert jwks.status_code == 200
    assert "PRIVATE KEY" not in jwks.text

    get_settings.cache_clear()


def test_apis_disabled_when_flag_off(client, db_session, monkeypatch):
    monkeypatch.setenv("ENABLE_BRANCH_CACHE_CONTROL_PLANE", "false")
    get_settings.cache_clear()
    headers = _admin_headers(db_session)
    resp = client.get("/api/admin/branch-cache/nodes", headers=headers)
    assert resp.status_code == 503
    get_settings.cache_clear()


def test_legacy_cdn_routes_unchanged_and_separate(client, admin_headers):
    # Legacy experimental CDN still gated on enable_cdn_sync (true in conftest).
    resp = client.get("/api/admin/cdn/nodes", headers=admin_headers)
    assert resp.status_code == 200
    # New control plane is a different prefix.
    assert client.get("/api/admin/branch-cache/status", headers=admin_headers).status_code == 200


def test_flags_off_does_not_alter_playback_token_path():
    """Central playback remains independent of Phase 3 edge grants."""
    settings = _settings()
    assert settings.enable_branch_cache_control_plane is False
    assert grant_svc.EDGE_GRANT_TYP == "edge_grant"
    assert grant_svc.EDGE_GRANT_ALG == "ES256"
    # Opaque playback tokens use a different secret/alg path than edge grants.
    assert grant_svc.edge_grant_issue_enabled(settings) is False


def test_cdn_permission_aliases_in_super():
    from app.bootstrap import SUPER_PERMISSIONS
    from app.core.deps import PERMISSION_ALIASES

    assert "cdn.read" in SUPER_PERMISSIONS
    assert "cdn.manage" in SUPER_PERMISSIONS
    assert "cdn" in PERMISSION_ALIASES["cdn.read"]
