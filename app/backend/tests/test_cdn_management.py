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
            "endpoint_url": "https://acct.r2.cloudflarestorage.com",
            "account_id": "acct",
            "bucket": "ifilm-hot",
            "region": "auto",
            "access_key_id": "r2-access-test",
            "secret_access_key": "r2-secret-test",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["credentials_configured"] is True
    assert "r2-access-test" not in json.dumps(body)
    assert "r2-secret-test" not in json.dumps(body)
    row = db_session.query(IntegrationConfig).filter_by(provider=svc.R2_PROVIDER).one()
    assert b"r2-secret-test" not in row.secret_ciphertext
    stored = json.loads(decrypt_secret(ciphertext=row.secret_ciphertext, master_key=encryption_key))
    assert stored["access_key_id"] == "r2-access-test"


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
        return result.json()

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
