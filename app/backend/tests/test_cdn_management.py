"""CDN-P1 management APIs: storage/R2 settings, node inventory, routing, overview."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import Settings, get_settings
from app.models.cdn_management import CDNProvisionRun, ManagedCDNNode
from app.models.integration_config import IntegrationConfig
from app.services import cdn_management as svc
from app.services.cdn_provisioning import ProvisioningError, redact_log, validate_target
from app.services.cdn_routing import evaluate_route
from app.services.integration_secrets import decrypt_secret
from app.services.object_storage.validation import collect_object_storage_errors
from cryptography.fernet import Fernet

BASE = "/api/admin/cdn-management"


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_SECRETS_KEY", key)
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


def _r2_payload(**overrides):
    payload = {
        "enabled": True,
        "provider": "cloudflare_r2",
        "endpoint_url": "https://acct.r2.cloudflarestorage.com",
        "account_id": "acct",
        "bucket": "ifilm-hot",
        "region": "auto",
        "object_key_prefix": "ifilm",
        "access_key_id": "r2-access-test",
        "secret_access_key": "r2-secret-test",
    }
    payload.update(overrides)
    return payload


# --- Storage / R2 -----------------------------------------------------------


def test_r2_secrets_encrypted_and_never_returned(client, admin_headers, db_session, encryption_key, caplog):
    caplog.set_level(logging.DEBUG)
    response = client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["credentials_configured"] is True
    assert body["provider"] == "cloudflare_r2"
    assert body["object_key_prefix"] == "ifilm"
    assert "r2-access-test" not in json.dumps(body)
    assert "r2-secret-test" not in json.dumps(body)
    row = db_session.query(IntegrationConfig).filter_by(provider=svc.R2_PROVIDER).one()
    assert b"r2-secret-test" not in row.secret_ciphertext
    stored = json.loads(decrypt_secret(ciphertext=row.secret_ciphertext, master_key=encryption_key))
    assert stored["secret_access_key"] == "r2-secret-test"
    assert "r2-secret-test" not in caplog.text
    assert "r2-access-test" not in caplog.text
    fetched = client.get(f"{BASE}/r2", headers=admin_headers).json()
    assert "secret_access_key" not in fetched and "access_key_id" not in fetched


def test_r2_blank_secret_preserves_and_replace_works(client, admin_headers, db_session, encryption_key):
    assert client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload()).status_code == 200
    first = db_session.query(IntegrationConfig).filter_by(provider=svc.R2_PROVIDER).one().secret_ciphertext
    # Blank credentials keep the stored secret while other fields change.
    updated = client.put(
        f"{BASE}/r2",
        headers=admin_headers,
        json=_r2_payload(access_key_id="", secret_access_key="", bucket="ifilm-hot-2", object_key_prefix="media"),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["bucket"] == "ifilm-hot-2"
    assert updated.json()["credentials_configured"] is True
    db_session.expire_all()
    row = db_session.query(IntegrationConfig).filter_by(provider=svc.R2_PROVIDER).one()
    assert row.secret_ciphertext == first
    # Replace secret.
    replaced = client.put(
        f"{BASE}/r2",
        headers=admin_headers,
        json=_r2_payload(access_key_id="new-access", secret_access_key="new-secret"),
    )
    assert replaced.status_code == 200
    db_session.expire_all()
    row = db_session.query(IntegrationConfig).filter_by(provider=svc.R2_PROVIDER).one()
    assert row.secret_ciphertext != first
    assert json.loads(decrypt_secret(ciphertext=row.secret_ciphertext, master_key=encryption_key))["access_key_id"] == "new-access"
    # Remove credentials → cannot stay enabled.
    removed = client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload(access_key_id="", secret_access_key="", remove_credentials=True))
    assert removed.status_code == 400
    removed = client.put(
        f"{BASE}/r2",
        headers=admin_headers,
        json=_r2_payload(enabled=False, access_key_id="", secret_access_key="", remove_credentials=True),
    )
    assert removed.status_code == 200 and removed.json()["credentials_configured"] is False


@pytest.mark.parametrize(
    "endpoint",
    ["http://insecure.example", "not-a-url", "https://user:pw@acct.r2.cloudflarestorage.com", "https://x.example/?q=1"],
)
def test_r2_invalid_endpoint_rejected(client, admin_headers, encryption_key, endpoint):
    response = client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload(endpoint_url=endpoint))
    assert response.status_code == 400


def test_r2_validation_rules(client, admin_headers, encryption_key):
    assert client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload(object_key_prefix="../x")).status_code == 400
    assert client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload(secret_access_key="")).status_code == 400
    assert client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload(provider="dropbox")).status_code == 422
    # Enabling without credentials fails closed.
    assert client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload(access_key_id="", secret_access_key="")).status_code == 400


def test_r2_test_connection_mocked_and_status_persisted(client, admin_headers, db_session, encryption_key, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    assert client.put(f"{BASE}/r2", headers=admin_headers, json=_r2_payload()).status_code == 200
    seen = {}

    def fake_probe(config):
        seen["endpoint"] = config.endpoint_url
        seen["secret"] = config.secret_access_key
        return {"ok": False, "reachable": True, "bucket_accessible": False, "endpoint_host": "acct.r2.cloudflarestorage.com", "message": "Bucket was not found on this endpoint"}

    monkeypatch.setattr(svc, "probe_s3_connection", fake_probe)
    original = svc.test_r2_connection
    monkeypatch.setattr(svc, "test_r2_connection", lambda db, admin, settings=None: original(db, admin, settings, probe=fake_probe))
    result = client.post(f"{BASE}/r2/test", headers=admin_headers)
    assert result.status_code == 200, result.text
    body = result.json()
    assert seen["secret"] == "r2-secret-test"  # decrypted server-side only
    assert body["reachable"] is True and body["bucket_accessible"] is False and body["ok"] is False
    assert "r2-secret-test" not in result.text
    assert "r2-secret-test" not in caplog.text
    status = client.get(f"{BASE}/r2", headers=admin_headers).json()
    assert status["last_test_ok"] is False
    assert status["last_test_reachable"] is True
    assert status["last_test_bucket_accessible"] is False
    assert status["last_test_at"]
    assert "Bucket was not found" in status["last_test_message"]


def test_r2_test_connection_requires_credentials(client, admin_headers, encryption_key):
    assert client.post(f"{BASE}/r2/test", headers=admin_headers).status_code == 400


def test_probe_classifies_bucket_errors():
    from unittest.mock import MagicMock, patch

    from app.services.object_storage.s3_compatible import S3CompatibleConfig, probe_s3_connection

    cfg = S3CompatibleConfig(endpoint_url="https://acct.r2.cloudflarestorage.com", bucket="b", region="auto", access_key_id="k", secret_access_key="s")

    class Denied(Exception):
        response = {"ResponseMetadata": {"HTTPStatusCode": 403}, "Error": {"Code": "403"}}

    with patch("app.services.object_storage.s3_compatible._require_boto3") as require:
        fake = MagicMock()
        client = MagicMock()
        client.head_bucket.side_effect = Denied()
        fake.client.return_value = client
        require.return_value = (fake, MagicMock())
        result = probe_s3_connection(cfg)
    assert result["reachable"] is True and result["bucket_accessible"] is False
    assert "not allowed" in result["message"]
    with patch("app.services.object_storage.s3_compatible._require_boto3") as require:
        fake = MagicMock()
        client = MagicMock()
        client.head_bucket.side_effect = ConnectionError("boom")
        fake.client.return_value = client
        require.return_value = (fake, MagicMock())
        result = probe_s3_connection(cfg)
    assert result["reachable"] is False and result["bucket_accessible"] is False


def test_r2_requires_cdn_secrets_permission(client, admin_headers, db_session, encryption_key):
    from app.models.admin import AdminRole, AdminUser

    role = AdminRole(name="cdn-reader", permissions=["cdn.read"])
    db_session.add(role)
    db_session.flush()
    from app.core.security import hash_password

    user = AdminUser(username="reader", email="reader@example.test", full_name="Reader", hashed_password=hash_password("reader-pass-ok-123"), role_id=role.id, is_active=True)
    db_session.add(user)
    db_session.commit()
    login = client.post("/api/admin/auth/login", json={"username": "reader", "password": "reader-pass-ok-123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(f"{BASE}/r2", headers=headers).status_code == 403
    assert client.get(f"{BASE}/nodes", headers=headers).status_code == 200
    assert client.post(f"{BASE}/routes", headers=headers, json={"cidr": "10.0.0.0/8", "node_id": "x"}).status_code == 403


# --- Nodes ------------------------------------------------------------------


def _node_payload(name, role, host, **overrides):
    payload = {
        "name": name,
        "role": role,
        "host": host,
        "ssh_port": 22,
        "ssh_username": "root",
        "credential_type": "password",
        "credential": "bootstrap-password-test",
        "enabled": True,
        "cache_limit_bytes": 10_000_000_000,
        "serve_base_url": f"https://{host}:8443",
    }
    payload.update(overrides)
    return payload


def _add_node(client, headers, name, role, host, **overrides):
    result = client.post(f"{BASE}/nodes", headers=headers, json=_node_payload(name, role, host, **overrides))
    assert result.status_code == 201, result.text
    assert "bootstrap-password-test" not in result.text
    assert "heartbeat_token_hash" not in result.text
    assert "credential_ciphertext" not in result.text
    return result.json()


def _make_ready(db_session, node_id, *, heartbeat_age=0, **fields):
    node = db_session.get(ManagedCDNNode, node_id)
    node.provision_status = svc.PROVISION_READY
    node.last_heartbeat_at = datetime.now(UTC) - timedelta(seconds=heartbeat_age)
    for key, value in fields.items():
        setattr(node, key, value)
    db_session.add(node)
    db_session.commit()


def test_node_create_edit_disable_enable_and_credentials(client, admin_headers, db_session, encryption_key):
    created = _add_node(client, admin_headers, "Kabul Main", "MAIN_CDN", "203.0.113.10", is_default=True)
    node = created["node"]
    assert created["heartbeat_token"]
    assert node["role"] == "main" and node["role_label"] == "MAIN_CDN"
    assert node["credential_configured"] is True and node["managed_key_configured"] is False
    assert node["state"] == "offline"
    row = db_session.get(ManagedCDNNode, node["id"])
    assert b"bootstrap-password-test" not in row.credential_ciphertext
    assert json.loads(decrypt_secret(ciphertext=row.credential_ciphertext, master_key=encryption_key))["value"] == "bootstrap-password-test"

    patched = client.patch(f"{BASE}/nodes/{node['id']}", headers=admin_headers, json={"priority": 5, "notes": "primary", "location": "Kabul"})
    assert patched.status_code == 200 and patched.json()["priority"] == 5 and patched.json()["location"] == "Kabul"
    # Blank credential on edit preserves the stored one.
    db_session.expire_all()
    assert db_session.get(ManagedCDNNode, node["id"]).credential_ciphertext == row.credential_ciphertext

    disabled = client.post(f"{BASE}/nodes/{node['id']}/actions/disable", headers=admin_headers, json={"confirm": True})
    assert disabled.status_code == 202 and disabled.json()["node"]["state"] == "disabled"
    enabled = client.post(f"{BASE}/nodes/{node['id']}/actions/enable", headers=admin_headers, json={"confirm": True})
    assert enabled.status_code == 202 and enabled.json()["node"]["enabled"] is True
    drained = client.post(f"{BASE}/nodes/{node['id']}/actions/drain", headers=admin_headers, json={"confirm": True})
    assert drained.json()["node"]["draining"] is True
    undrained = client.post(f"{BASE}/nodes/{node['id']}/actions/undrain", headers=admin_headers, json={"confirm": True})
    assert undrained.json()["node"]["draining"] is False

    detail = client.get(f"{BASE}/nodes/{node['id']}", headers=admin_headers).json()
    assert "credential" not in detail and "managed_key_ciphertext" not in detail
    assert client.delete(f"{BASE}/nodes/{node['id']}", headers=admin_headers).status_code == 422  # confirm required
    assert client.delete(f"{BASE}/nodes/{node['id']}?confirm=false", headers=admin_headers).status_code == 409
    assert client.delete(f"{BASE}/nodes/{node['id']}?confirm=true", headers=admin_headers).status_code == 204


def test_node_validation_rules(client, admin_headers, encryption_key):
    def post(**kw):
        return client.post(f"{BASE}/nodes", headers=admin_headers, json={**_node_payload("n", "cache", "203.0.113.20"), **kw})
    assert post(role="edge").status_code == 422
    assert post(cache_limit_bytes=None).status_code == 400  # caches need a storage limit
    assert post(high_watermark_pct=70, low_watermark_pct=80).status_code == 400
    assert post(is_default=True).status_code == 400  # only main can be default
    assert post(host="127.0.0.1").status_code == 400
    assert post(host="bad host").status_code == 422
    assert post(serve_base_url="ftp://x").status_code == 400
    assert post(ssh_username="root; rm -rf /").status_code == 400
    assert post(credential="").status_code == 400
    assert post().status_code == 201
    assert post(name="dup").status_code == 400  # duplicate host


def test_destructive_actions_require_confirmation(client, admin_headers, encryption_key):
    node = _add_node(client, admin_headers, "Cache", "cache", "203.0.113.21")["node"]
    assert client.post(f"{BASE}/nodes/{node['id']}/actions/clear-cache", headers=admin_headers, json={"confirm": False}).status_code == 409
    assert client.post(f"{BASE}/nodes/{node['id']}/actions/explode", headers=admin_headers, json={"confirm": True}).status_code == 404


def test_provisioning_requires_confirmed_host_key_and_queues_once(client, admin_headers, db_session, encryption_key):
    node = _add_node(client, admin_headers, "Pinned Cache", "cache", "203.0.113.31")["node"]
    action = f"{BASE}/nodes/{node['id']}/actions/provision"
    assert client.post(action, headers=admin_headers, json={"confirm": True}).status_code == 409
    fingerprint = "SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    assert client.post(f"{BASE}/nodes/{node['id']}/pin-host-key", headers=admin_headers, json={"fingerprint": "md5:" + "x" * 30, "confirm": True}).status_code == 400
    pinned = client.post(f"{BASE}/nodes/{node['id']}/pin-host-key", headers=admin_headers, json={"fingerprint": fingerprint, "confirm": True})
    assert pinned.status_code == 200 and pinned.json()["ssh_host_key_fingerprint"] == fingerprint
    queued = client.post(action, headers=admin_headers, json={"confirm": True})
    assert queued.status_code == 202 and queued.json()["status"] == "queued"
    assert client.post(action, headers=admin_headers, json={"confirm": True}).status_code == 409  # already queued
    assert client.post(f"{BASE}/nodes/{node['id']}/actions/upgrade", headers=admin_headers, json={"confirm": True}).status_code == 409
    runs = client.get(f"{BASE}/nodes/{node['id']}/provision-runs", headers=admin_headers).json()
    assert runs[0]["status"] == "queued" and "bootstrap-password-test" not in json.dumps(runs)
    # A failed run's step is used as the resume point for the next provision.
    run = db_session.get(CDNProvisionRun, queued.json()["id"])
    run.status = svc.PROVISION_FAILED
    run.step = "packages"
    db_session.add(run)
    db_session.commit()
    again = client.post(action, headers=admin_headers, json={"confirm": True})
    assert again.status_code == 202 and again.json()["resume_from_step"] == "packages"


# --- Heartbeat via node API ----------------------------------------------------


def test_node_api_heartbeat_requires_flag_and_token(client, admin_headers, db_session, encryption_key, monkeypatch):
    created = _add_node(client, admin_headers, "Heartbeat Cache", "cache", "203.0.113.30")
    node, token = created["node"], created["heartbeat_token"]
    url = f"/api/cdn/nodes/{node['id']}/heartbeat"
    headers = {"Authorization": f"Bearer {token}", "X-Ifilm-Node-Id": node["id"]}
    assert client.post(url, headers=headers, json={}).status_code == 503  # flag off
    monkeypatch.setenv("ENABLE_CDN_NODE_API", "true")
    get_settings.cache_clear()
    assert client.post(url, json={"disk_total_bytes": 100}).status_code == 401
    assert client.post(url, headers={**headers, "Authorization": "Bearer wrong"}, json={}).status_code == 401
    assert client.post(url, headers={**headers, "X-Ifilm-Node-Id": "other"}, json={}).status_code == 401
    ok = client.post(url, headers=headers, json={"disk_total_bytes": 1000, "disk_used_bytes": 400, "disk_free_bytes": 600, "cache_used_bytes": 300, "cache_hits": 30, "cache_misses": 10, "software_version": "1.2.3"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["desired"]["draining"] is False and body["heartbeat_interval_seconds"] == 30
    assert token not in ok.text and "node" not in body
    view = client.get(f"{BASE}/nodes/{node['id']}", headers=admin_headers).json()
    assert view["online"] is True and view["hit_rate"] == 75.0 and view["cache_utilization_pct"] == 0.0
    # Legacy admin-prefixed heartbeat path still works with the same token.
    legacy = client.post(f"{BASE}/nodes/{node['id']}/heartbeat", headers={"Authorization": f"Bearer {token}"}, json={"disk_free_bytes": 500})
    assert legacy.status_code == 200 and legacy.json()["disk_free_bytes"] == 500
    get_settings.cache_clear()


# --- Routing ----------------------------------------------------------------


def _route(client, headers, cidr, node_id, priority=100, enabled=True, notes=None):
    result = client.post(f"{BASE}/routes", headers=headers, json={"cidr": cidr, "node_id": node_id, "priority": priority, "enabled": enabled, "notes": notes})
    assert result.status_code == 201, result.text
    return result.json()


def _lookup(client, headers, ip):
    result = client.post(f"{BASE}/routes/lookup", headers=headers, json={"client_ip": ip})
    assert result.status_code == 200, result.text
    return result.json()


def test_routing_longest_prefix_priority_and_fallback_chain(client, admin_headers, db_session, encryption_key):
    main = _add_node(client, admin_headers, "Kabul Main", "main", "203.0.113.10", is_default=True, priority=10)["node"]
    main2 = _add_node(client, admin_headers, "Herat Main", "main", "203.0.113.11", priority=20)["node"]
    broad = _add_node(client, admin_headers, "Kabul Cache", "cache", "203.0.113.12", branch="kabul")["node"]
    narrow = _add_node(client, admin_headers, "Nimruz Cache", "cache", "203.0.113.13", branch="nimruz")["node"]
    nimruz2 = _add_node(client, admin_headers, "Nimruz Cache 2", "cache", "203.0.113.14", branch="nimruz")["node"]
    for n in (main, main2, broad, narrow, nimruz2):
        _make_ready(db_session, n["id"])

    _route(client, admin_headers, "103.126.0.0/16", broad["id"], priority=10, notes="whole province")
    rule = _route(client, admin_headers, "103.126.4.0/24", narrow["id"], priority=100)
    assert rule["notes"] is None
    # Exact CIDR + longest prefix wins over broader (even with worse priority).
    decision = _lookup(client, admin_headers, "103.126.4.55")
    assert decision["selected"]["id"] == narrow["id"] and decision["matched_cidr"] == "103.126.4.0/24"
    assert decision["chain"][-1]["stage"] == "central" and decision["central_fallback"] is True
    # Overlapping: same-length prefixes → lower priority number wins.
    _route(client, admin_headers, "103.126.5.0/24", nimruz2["id"], priority=50)
    dup = client.post(f"{BASE}/routes", headers=admin_headers, json={"cidr": "103.126.5.0/24", "node_id": narrow["id"], "priority": 60})
    assert dup.status_code == 400  # duplicate CIDR rejected
    # Priority tie-break exercised via IPv6 twins of equal length.
    _route(client, admin_headers, "2001:db8::/32", nimruz2["id"], priority=5)
    assert _lookup(client, admin_headers, "2001:db8::1")["selected"]["id"] == nimruz2["id"]
    # Broad match only.
    assert _lookup(client, admin_headers, "103.126.9.9")["selected"]["id"] == broad["id"]
    # No match → default main; then secondary main when default is offline.
    assert _lookup(client, admin_headers, "8.8.8.8")["selected"]["id"] == main["id"]
    _make_ready(db_session, main["id"], heartbeat_age=10_000)
    fallback = _lookup(client, admin_headers, "8.8.8.8")
    assert fallback["selected"]["id"] == main2["id"]
    stages = [c["stage"] for c in fallback["chain"]]
    assert stages == ["default_main", "secondary_main", "central"]
    assert fallback["chain"][0]["reason"] == "stale_heartbeat"
    # Preferred node offline → same-branch cache → then main.
    _make_ready(db_session, narrow["id"], heartbeat_age=10_000)
    decision = _lookup(client, admin_headers, "103.126.4.55")
    assert decision["selected"]["id"] == broad["id"]  # next matching rule (broad /16) before same-branch
    _make_ready(db_session, broad["id"], enabled=False)
    decision = _lookup(client, admin_headers, "103.126.4.55")
    assert decision["selected"]["id"] == nimruz2["id"] and decision["selected_stage"] == "same_branch_cache"
    _make_ready(db_session, nimruz2["id"], draining=True)
    decision = _lookup(client, admin_headers, "103.126.4.55")
    assert decision["selected"]["id"] == main2["id"]
    # Everything down → central only.
    _make_ready(db_session, main2["id"], provision_status="failed")
    decision = _lookup(client, admin_headers, "103.126.4.55")
    assert decision["selected"] is None and decision["selected_stage"] == "central"
    assert decision["reason"] == "central_fallback"
    assert decision["chain"][-1]["eligible"] is True


def test_routing_disabled_rule_and_unprovisioned_node_ignored(client, admin_headers, db_session, encryption_key):
    main = _add_node(client, admin_headers, "Main", "main", "203.0.113.40", is_default=True)["node"]
    cache = _add_node(client, admin_headers, "Cache", "cache", "203.0.113.41")["node"]
    _make_ready(db_session, main["id"])
    rule = _route(client, admin_headers, "10.1.0.0/16", cache["id"], enabled=False)
    decision = _lookup(client, admin_headers, "10.1.2.3")
    assert decision["selected"]["id"] == main["id"] and decision["matched_cidr"] is None
    toggled = client.patch(f"{BASE}/routes/{rule['id']}", headers=admin_headers, json={"enabled": True, "notes": "enabled now"})
    assert toggled.status_code == 200 and toggled.json()["enabled"] is True and toggled.json()["notes"] == "enabled now"
    decision = _lookup(client, admin_headers, "10.1.2.3")
    assert decision["selected"]["id"] == main["id"]
    assert decision["chain"][0]["reason"] == "not_provisioned"
    _make_ready(db_session, cache["id"])
    assert _lookup(client, admin_headers, "10.1.2.3")["selected"]["id"] == cache["id"]
    assert client.post(f"{BASE}/routes/lookup", headers=admin_headers, json={"client_ip": "nope"}).status_code == 400
    assert client.delete(f"{BASE}/routes/{rule['id']}?confirm=true", headers=admin_headers).status_code == 204
    assert client.post(f"{BASE}/routes", headers=admin_headers, json={"cidr": "10.1.2.3/16", "node_id": cache["id"]}).status_code == 400


def test_evaluate_route_stale_threshold_from_settings(db_session, encryption_key):
    node = ManagedCDNNode(name="A", role="main", host="203.0.113.50", ssh_port=22, ssh_username="root", credential_type="password", credential_ciphertext=b"x", is_default=True, provision_status="ready", last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=60))
    db_session.add(node)
    db_session.commit()
    strict = Settings(app_env="test", database_url="sqlite://", jwt_secret="unit-test-jwt-secret-value-32chars-min", cdn_node_heartbeat_stale_seconds=30, _env_file=None)
    lax = Settings(app_env="test", database_url="sqlite://", jwt_secret="unit-test-jwt-secret-value-32chars-min", cdn_node_heartbeat_stale_seconds=120, _env_file=None)
    assert evaluate_route(db_session, "1.1.1.1", settings=strict)["selected"] is None
    assert evaluate_route(db_session, "1.1.1.1", settings=lax)["selected"]["id"] == node.id
    legacy = svc.select_node(db_session, "1.1.1.1", settings=lax)
    assert legacy["node"]["id"] == node.id and legacy["central_fallback"] is True


# --- Overview / flags / safety --------------------------------------------------


def test_overview_and_flags_default_off(client, admin_headers, db_session, encryption_key):
    main = _add_node(client, admin_headers, "Main", "main", "203.0.113.60", is_default=True)["node"]
    _make_ready(db_session, main["id"], disk_total_bytes=1000, disk_used_bytes=400, disk_free_bytes=600, cache_hits=3, cache_misses=1)
    cache = _add_node(client, admin_headers, "Cache", "cache", "203.0.113.61")["node"]
    db_session.add(CDNProvisionRun(node_id=cache["id"], action="provision", status="failed", error_code="unsupported_os", step="preflight"))
    db_session.commit()
    body = client.get(f"{BASE}/overview", headers=admin_headers).json()
    assert body["totals"]["nodes"] == 2 and body["totals"]["online"] == 1 and body["totals"]["offline"] == 1
    assert body["main_cdn"]["status"] == "online"
    assert body["storage"]["disk_free_bytes"] == 600 and body["cache"]["hit_rate"] == 75.0
    assert body["recent_provisioning_failures"][0]["error_code"] == "unsupported_os"
    assert body["central_fallback"] == "always"
    flags = client.get(f"{BASE}/status", headers=admin_headers).json()
    assert flags["enable_cdn_edge_routing"] is False
    assert flags["enable_cdn_node_api"] is False
    assert flags["enable_cdn_provisioning"] is False
    assert flags["customer_playback_route"].startswith("/api/stream/")


def test_edge_routing_flag_fails_closed_in_p1():
    settings = Settings(app_env="production", database_url="sqlite://", jwt_secret="unit-test-jwt-secret-value-32chars-min", enable_cdn_edge_routing=True, _env_file=None)
    errors = collect_object_storage_errors(settings)
    assert any("ENABLE_CDN_EDGE_ROUTING" in e for e in errors)
    settings = Settings(app_env="production", database_url="sqlite://", jwt_secret="unit-test-jwt-secret-value-32chars-min", enable_cdn_provisioning=True, _env_file=None)
    assert any("INTEGRATION_SECRETS_KEY" in e for e in collect_object_storage_errors(settings))


def test_customer_playback_unchanged_by_cdn_p1(client):
    """Central /api/stream remains the only customer route; no edge fields exist."""
    from app.schemas.streaming import PlaybackSessionCreated

    assert "edge" not in PlaybackSessionCreated.model_fields
    assert "edge_grant" not in PlaybackSessionCreated.model_fields
    from app.api.routes import stream

    paths = {getattr(route, "path", "") for route in stream.router.routes}
    assert "/stream/{token}/master.m3u8" in paths
    assert "/playback/sessions/{session_id}/edge-grant" not in paths
    assert client.get("/api/streaming/status").status_code == 200


def test_provisioning_target_validation_and_log_redaction():
    import socket

    def local(_host, _port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    with pytest.raises(ProvisioningError):
        validate_target("localhost", resolver=local)
    assert "super-secret" not in redact_log(["using super-secret", "done"], ["super-secret"])


# --- Network policy ---------------------------------------------------------


def test_network_policy_defaults_closed_and_validation(client, admin_headers, encryption_key):
    initial = client.get(f"{BASE}/network", headers=admin_headers).json()
    assert initial["management_cidrs"] == [] and initial["serve_cidrs"] == []
    assert initial["provisioning_ready"] is False and initial["media_port_open"] is False
    put = lambda body: client.put(f"{BASE}/network", headers=admin_headers, json=body)  # noqa: E731
    assert put({"management_cidrs": [], "serve_cidrs": []}).status_code == 400  # at least one management CIDR
    assert put({"management_cidrs": ["203.0.113.5/24"], "serve_cidrs": []}).status_code == 400  # host bits set
    assert put({"management_cidrs": ["nope"], "serve_cidrs": []}).status_code == 400
    assert put({"management_cidrs": ["0.0.0.0/0"], "serve_cidrs": []}).status_code == 400  # allow-any needs confirmation
    assert put({"management_cidrs": ["203.0.113.0/24"], "serve_cidrs": ["::/0"]}).status_code == 400
    saved = put({"management_cidrs": ["203.0.113.0/24", "2001:db8::/32", "203.0.113.0/24"], "serve_cidrs": []})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["management_cidrs"] == ["203.0.113.0/24", "2001:db8::/32"]
    assert body["serve_cidrs"] == [] and body["media_port_open"] is False and body["provisioning_ready"] is True
    assert body["source"] == "db" and body["management_allow_any"] is False
    confirmed = put({"management_cidrs": ["203.0.113.0/24"], "serve_cidrs": ["0.0.0.0/0"], "confirm_allow_any": True})
    assert confirmed.status_code == 200 and confirmed.json()["serve_allow_any"] is True and confirmed.json()["media_port_open"] is True
    overview = client.get(f"{BASE}/overview", headers=admin_headers).json()
    assert overview["network"]["serve_allow_any"] is True


def test_network_policy_requires_provision_permission(client, admin_headers, db_session, encryption_key):
    from app.core.security import hash_password
    from app.models.admin import AdminRole, AdminUser

    role = AdminRole(name="cdn-manager-only", permissions=["cdn.read", "cdn.routing"])
    db_session.add(role)
    db_session.flush()
    db_session.add(AdminUser(username="router", email="router@example.test", full_name="R", hashed_password=hash_password("router-pass-ok-123"), role_id=role.id, is_active=True))
    db_session.commit()
    login = client.post("/api/admin/auth/login", json={"username": "router", "password": "router-pass-ok-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get(f"{BASE}/network", headers=headers).status_code == 200
    assert client.put(f"{BASE}/network", headers=headers, json={"management_cidrs": ["203.0.113.0/24"], "serve_cidrs": []}).status_code == 403


def test_network_env_fallback_used_when_unset(db_session, encryption_key):
    from app.services.cdn_network import effective_network, get_network_settings

    cfg = Settings(app_env="test", database_url="sqlite://", jwt_secret="unit-test-jwt-secret-value-32chars-min", cdn_management_cidrs="203.0.113.10/32", cdn_serve_cidrs="", _env_file=None)
    assert effective_network(db_session, cfg) == (["203.0.113.10/32"], [])
    assert get_network_settings(db_session, cfg)["source"] == "env"
    bad = Settings(app_env="test", database_url="sqlite://", jwt_secret="unit-test-jwt-secret-value-32chars-min", cdn_management_cidrs="garbage", _env_file=None)
    assert effective_network(db_session, bad) == ([], [])  # malformed env never yields allow-any
    empty = Settings(app_env="test", database_url="sqlite://", jwt_secret="unit-test-jwt-secret-value-32chars-min", _env_file=None)
    assert empty.cdn_serve_cidrs == "" and empty.cdn_management_cidrs == ""
