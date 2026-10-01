from __future__ import annotations

import json
import socket

import pytest
from app.core.config import get_settings
from app.models.cdn_management import ManagedCDNNode
from app.models.integration_config import IntegrationConfig
from app.services import cdn_management as svc
from app.services.cdn_provisioning import ProvisioningError, redact_log, validate_target
from app.services.integration_secrets import decrypt_secret
from cryptography.fernet import Fernet


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_SECRETS_KEY", key)
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


def test_r2_secrets_encrypted_and_never_returned(client, admin_headers, db_session, encryption_key):
    response = client.put(
        "/api/admin/cdn-management/r2",
        headers=admin_headers,
        json={
            "enabled": True,
            "provider": "cloudflare_r2",
            "endpoint_url": "https://acct.r2.cloudflarestorage.com",
            "account_id": "acct",
            "bucket": "ifilm-hot",
            "region": "auto",
            "object_key_prefix": "ifilm",
            "public_base_url": "https://cdn.example.com",
            "artwork_cdn_enabled": True,
            "access_key_id": "r2-access-test",
            "secret_access_key": "r2-secret-test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["credentials_configured"] is True
    assert body["provider"] == "cloudflare_r2"
    assert body["object_key_prefix"] == "ifilm"
    assert body["artwork_cdn_enabled"] is True
    assert body["public_base_url"] == "https://cdn.example.com"
    assert "r2-access-test" not in json.dumps(body)
    assert "r2-secret-test" not in json.dumps(body)
    row = db_session.query(IntegrationConfig).filter_by(provider=svc.R2_PROVIDER).one()
    assert b"r2-secret-test" not in row.secret_ciphertext
    stored = json.loads(decrypt_secret(ciphertext=row.secret_ciphertext, master_key=encryption_key))
    assert stored["access_key_id"] == "r2-access-test"


def test_r2_blank_secret_preserves_and_replace_works(client, admin_headers, db_session, encryption_key):
    assert (
        client.put(
            "/api/admin/cdn-management/r2",
            headers=admin_headers,
            json={
                "account_id": "acct",
                "enabled": True,
                "endpoint_url": "https://acct.r2.cloudflarestorage.com",
                "bucket": "ifilm-hot",
                "region": "auto",
                "access_key_id": "first-key",
                "secret_access_key": "first-secret",
            },
        ).status_code
        == 200
    )
    preserved = client.put(
        "/api/admin/cdn-management/r2",
        headers=admin_headers,
        json={
            "account_id": "acct",
            "enabled": True,
            "endpoint_url": "https://acct.r2.cloudflarestorage.com",
            "bucket": "ifilm-hot",
            "region": "auto",
            "artwork_cdn_enabled": True,
            "public_base_url": "https://cdn.example.com",
        },
    )
    assert preserved.status_code == 200
    row = db_session.query(IntegrationConfig).filter_by(provider=svc.R2_PROVIDER).one()
    db_session.refresh(row)
    stored = json.loads(decrypt_secret(ciphertext=row.secret_ciphertext, master_key=encryption_key))
    assert stored["access_key_id"] == "first-key"
    replaced = client.put(
        "/api/admin/cdn-management/r2",
        headers=admin_headers,
        json={
            "account_id": "acct",
            "enabled": True,
            "endpoint_url": "https://acct.r2.cloudflarestorage.com",
            "bucket": "ifilm-hot",
            "region": "auto",
            "access_key_id": "second-key",
            "secret_access_key": "second-secret",
        },
    )
    assert replaced.status_code == 200
    db_session.refresh(row)
    stored = json.loads(decrypt_secret(ciphertext=row.secret_ciphertext, master_key=encryption_key))
    assert stored["access_key_id"] == "second-key"


def test_r2_remove_requires_confirmation(client, admin_headers, encryption_key):
    assert (
        client.put(
            "/api/admin/cdn-management/r2",
            headers=admin_headers,
            json={
                "account_id": "acct",
                "enabled": True,
                "endpoint_url": "https://acct.r2.cloudflarestorage.com",
                "bucket": "ifilm-hot",
                "region": "auto",
                "access_key_id": "k",
                "secret_access_key": "s",
            },
        ).status_code
        == 200
    )
    denied = client.put(
        "/api/admin/cdn-management/r2",
        headers=admin_headers,
        json={
            "account_id": "acct",
            "enabled": False,
            "endpoint_url": "https://acct.r2.cloudflarestorage.com",
            "bucket": "ifilm-hot",
            "region": "auto",
            "remove_credentials": True,
        },
    )
    assert denied.status_code == 400
    ok = client.put(
        "/api/admin/cdn-management/r2",
        headers=admin_headers,
        json={
            "account_id": "acct",
            "enabled": False,
            "endpoint_url": "https://acct.r2.cloudflarestorage.com",
            "bucket": "ifilm-hot",
            "region": "auto",
            "remove_credentials": True,
            "confirm": True,
        },
    )
    assert ok.status_code == 200
    assert ok.json()["credentials_configured"] is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://acct.r2.cloudflarestorage.com",
        "https://127.0.0.1/r2",
        "https://localhost/r2",
        "https://10.0.0.5/r2",
    ],
)
def test_r2_invalid_endpoint_rejected(client, admin_headers, encryption_key, endpoint):
    response = client.put(
        "/api/admin/cdn-management/r2",
        headers=admin_headers,
        json={
            "enabled": False,
            "provider": "s3_compatible",
            "endpoint_url": endpoint,
            "bucket": "ifilm-hot",
            "region": "auto",
            "access_key_id": "k",
            "secret_access_key": "s",
        },
    )
    assert response.status_code == 400


def test_r2_test_connection_mocked_and_status_persisted(
    client, admin_headers, db_session, encryption_key, monkeypatch, caplog
):
    assert (
        client.put(
            "/api/admin/cdn-management/r2",
            headers=admin_headers,
            json={
                "account_id": "acct",
                "enabled": True,
                "endpoint_url": "https://acct.r2.cloudflarestorage.com",
                "bucket": "ifilm-hot",
                "region": "auto",
                "access_key_id": "k",
                "secret_access_key": "s",
            },
        ).status_code
        == 200
    )

    def fake_probe(config):
        assert config.bucket == "ifilm-hot"
        assert config.access_key_id == "k"
        return {
            "ok": True,
            "reachable": True,
            "bucket_accessible": True,
            "endpoint_host": "acct.r2.cloudflarestorage.com",
            "message": "Endpoint reachable and bucket accessible",
        }

    original = svc.test_r2_connection
    monkeypatch.setattr(
        svc,
        "test_r2_connection",
        lambda db, admin, settings=None: original(db, admin, settings, probe=fake_probe),
    )
    with caplog.at_level("INFO"):
        result = client.post("/api/admin/cdn-management/r2/test", headers=admin_headers)
    assert result.status_code == 200
    body = result.json()
    assert body["ok"] is True
    assert body["reachable"] is True
    assert body["bucket_accessible"] is True
    dumped = json.dumps(body)
    assert "access_key_id" not in dumped
    assert "secret_access_key" not in dumped
    assert body["settings"]["last_test_ok"] is True
    assert "cdn_storage_event" in caplog.text
    assert "first-secret" not in caplog.text and "second-secret" not in caplog.text


def test_r2_test_connection_requires_credentials(client, admin_headers, encryption_key):
    response = client.post("/api/admin/cdn-management/r2/test", headers=admin_headers)
    assert response.status_code == 400




def test_r2_derives_endpoint_from_account_id(client, admin_headers, encryption_key):
    response = client.put(
        "/api/admin/cdn-management/r2",
        headers=admin_headers,
        json={
            "enabled": False,
            "provider": "cloudflare_r2",
            "account_id": "myaccount",
            "bucket": "ifilm-art",
            "region": "auto",
            "access_key_id": "k",
            "secret_access_key": "s",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["endpoint_url"] == "https://myaccount.r2.cloudflarestorage.com"
    assert body["region"] == "auto"

def test_nodes_prefix_routing_and_main_fallback(client, admin_headers, db_session, encryption_key):
    def add(name, role, host, default=False):
        result = client.post(
            "/api/admin/cdn-management/nodes",
            headers=admin_headers,
            json={
                "name": name,
                "role": role,
                "host": host,
                "ssh_port": 22,
                "ssh_username": "root",
                "credential_type": "password",
                "credential": "bootstrap-password-test",
                "enabled": True,
                "is_default": default,
                "cache_limit_bytes": 10_000_000_000,
            },
        )
        assert result.status_code == 201, result.text
        assert "bootstrap-password-test" not in result.text
        body = result.json()
        assert body["heartbeat_token"]
        assert "heartbeat_token_hash" not in result.text
        return body["node"]

    main = add("Kabul Main", "main", "203.0.113.10", True)
    broad = add("Kabul Cache", "cache", "203.0.113.11")
    narrow = add("Nimruz Cache", "cache", "203.0.113.12")
    for cidr, node, priority in [("103.126.0.0/16", broad, 10), ("103.126.4.0/24", narrow, 100)]:
        assert (
            client.post(
                "/api/admin/cdn-management/routes",
                headers=admin_headers,
                json={"cidr": cidr, "node_id": node["id"], "priority": priority, "enabled": True},
            ).status_code
            == 201
        )
    selected = client.post(
        "/api/admin/cdn-management/routes/lookup",
        headers=admin_headers,
        json={"client_ip": "103.126.4.55"},
    ).json()
    assert selected["node"]["id"] == narrow["id"]
    fallback = client.post(
        "/api/admin/cdn-management/routes/lookup",
        headers=admin_headers,
        json={"client_ip": "8.8.8.8"},
    ).json()
    assert fallback["node"]["id"] == main["id"]


def test_destructive_actions_require_confirmation(
    client, admin_headers, db_session, encryption_key
):
    node = ManagedCDNNode(
        name="Cache",
        role="cache",
        host="203.0.113.20",
        ssh_port=22,
        ssh_username="root",
        credential_type="password",
        credential_ciphertext=b"opaque",
    )
    db_session.add(node)
    db_session.commit()
    response = client.post(
        f"/api/admin/cdn-management/nodes/{node.id}/actions/clear-cache",
        headers=admin_headers,
        json={"confirm": False},
    )
    assert response.status_code == 409


def test_provisioning_target_validation_and_log_redaction():
    def local(_host, _port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    with pytest.raises(ProvisioningError):
        validate_target("localhost", resolver=local)
    assert "super-secret" not in redact_log(["using super-secret", "done"], ["super-secret"])


def test_heartbeat_requires_one_time_token(client, admin_headers, encryption_key):
    created = client.post(
        "/api/admin/cdn-management/nodes",
        headers=admin_headers,
        json={
            "name": "Heartbeat Cache",
            "role": "cache",
            "host": "203.0.113.30",
            "ssh_username": "root",
            "credential": "bootstrap-test",
            "cache_limit_bytes": 1_000_000,
        },
    ).json()
    node, token = created["node"], created["heartbeat_token"]
    url = f"/api/admin/cdn-management/nodes/{node['id']}/heartbeat"
    assert client.post(url, json={"disk_total_bytes": 100}).status_code == 401
    assert client.post(url, headers={"Authorization": "Bearer wrong"}, json={}).status_code == 401
    ok = client.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={"disk_total_bytes": 1000, "disk_free_bytes": 600, "software_version": "1.2.3"},
    )
    assert ok.status_code == 200
    assert ok.json()["disk_free_bytes"] == 600
    assert token not in ok.text


def test_provisioning_requires_confirmed_host_key(client, admin_headers, encryption_key):
    created = client.post(
        "/api/admin/cdn-management/nodes",
        headers=admin_headers,
        json={
            "name": "Pinned Cache",
            "role": "cache",
            "host": "203.0.113.31",
            "ssh_username": "root",
            "credential": "bootstrap-test",
            "cache_limit_bytes": 1000,
        },
    ).json()["node"]
    action = f"/api/admin/cdn-management/nodes/{created['id']}/actions/provision"
    assert client.post(action, headers=admin_headers, json={"confirm": True}).status_code == 409
    fingerprint = "SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    pinned = client.post(
        f"/api/admin/cdn-management/nodes/{created['id']}/pin-host-key",
        headers=admin_headers,
        json={"fingerprint": fingerprint, "confirm": True},
    )
    assert pinned.status_code == 200
    assert client.post(action, headers=admin_headers, json={"confirm": True}).status_code == 202
