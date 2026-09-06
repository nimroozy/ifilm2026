"""CDN-P1 provisioning: SSH safety, Debian 13 bootstrap, key rotation, worker claiming."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from app.core.config import Settings, get_settings
from app.models.admin import AdminUser
from app.models.cdn_management import CDNProvisionRun, ManagedCDNNode
from app.services import cdn_management as mgmt
from app.services.cdn_provisioner import (
    ACTION_STEPS,
    NodeBundle,
    ProvisionExecutor,
    ProvisionStepError,
    build_node_bundle,
    probe_ssh_connection,
    render_nftables,
    render_node_env,
    render_systemd_unit,
)
from app.services.cdn_ssh import (
    CommandResult,
    SSHCredential,
    SSHError,
    SSHTarget,
    generate_ed25519_keypair,
    render_command,
    sha256_fingerprint,
)
from app.workers import cdn_provisioning as worker
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization

HOST_FP = "SHA256:" + base64.b64encode(hashlib.sha256(b"fake-host-key").digest()).decode().rstrip("=")
DEBIAN13 = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nNAME="Debian GNU/Linux"\nVERSION_ID="13"\nID=debian\n'
UBUNTU = 'NAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\n'


def _public_from_private(pem: str) -> str:
    key = serialization.load_ssh_private_key(pem.encode(), password=None)
    return key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


@dataclass
class FakeHost:
    """Scripted Debian host reachable only through the fake transport."""

    password: str = "bootstrap-password-test"
    fingerprint: str = HOST_FP
    os_release: str = DEBIAN13
    uid: str = "0"
    arch: str = "x86_64"
    df_line: str = "  100000000000 30000000000 70000000000"
    fail_commands: dict[str, int] = field(default_factory=dict)
    timeout_commands: set[str] = field(default_factory=set)
    authorized_keys: str = ""
    files: dict[str, bytes] = field(default_factory=dict)
    installed: dict[str, tuple[str, str, str]] = field(default_factory=dict)  # dest -> (owner, group, mode)
    commands: list[list[str]] = field(default_factory=list)
    connections: list[str] = field(default_factory=list)
    service_active: bool = False
    release_marker: bool = False
    sudo_ok: bool = True
    ssh_source: str = "203.0.113.5"
    live_ruleset: str = "table inet filter {\n}\n"
    firewall_applied: bool = False
    lock_out_after_firewall: bool = False
    fresh_connections_after_firewall: int = 0

    def authorized(self, credential: SSHCredential) -> bool:
        if credential.kind == "password":
            return credential.secret == self.password
        try:
            public = _public_from_private(credential.secret)
        except ValueError:
            return False
        return public.split(" ")[1] in self.authorized_keys


class FakeSession:
    def __init__(self, host: FakeHost) -> None:
        self.host = host
        self.host_key_fingerprint = host.fingerprint
        self.closed = False

    def run(self, argv: Sequence[str], *, timeout: float, env: Mapping[str, str] | None = None, stdin: bytes | None = None) -> CommandResult:
        argv = [str(a) for a in argv]
        render_command(argv, env)  # must always be quotable
        self.host.commands.append(argv)
        core = [a for a in argv if a not in {"sudo", "-n"}]
        joined = " ".join(core)
        for key in self.host.timeout_commands:
            if key in joined:
                return CommandResult(exit_code=-1, stdout="", stderr="", timed_out=True)
        for key, code in self.host.fail_commands.items():
            if key in joined:
                return CommandResult(exit_code=code, stdout="", stderr=f"{key} failed")
        if core[:2] == ["cat", "/etc/os-release"]:
            return CommandResult(0, self.host.os_release, "")
        if core[:2] == ["id", "-u"] and len(core) == 2:
            return CommandResult(0, self.host.uid + "\n", "")
        if core[:2] == ["id", "-u"]:
            return CommandResult(0 if "ifilm-cdn-exists" in self.host.files else 1, "", "")
        if core[:1] == ["true"]:
            return CommandResult(0 if self.host.sudo_ok else 1, "", "")
        if core[:1] == ["printenv"]:
            if core[1] == "SSH_CLIENT" and self.host.ssh_source:
                return CommandResult(0, f"{self.host.ssh_source} 51234 22\n", "")
            return CommandResult(1, "", "")
        if core[:1] == ["nft"]:
            if core[1:3] == ["list", "ruleset"]:
                return CommandResult(0, self.host.live_ruleset, "")
            if core[1:3] == ["flush", "ruleset"]:
                self.host.live_ruleset = ""
                self.host.firewall_applied = False
                return CommandResult(0, "", "")
            if core[1] == "-c":
                return CommandResult(0, "", "")
            if core[1] == "-f":
                self.host.live_ruleset = self.host.files.get(core[2], b"").decode()
                self.host.firewall_applied = "ifilm_cdn" in self.host.live_ruleset
                return CommandResult(0, "", "")
            return CommandResult(0, "", "")
        if core[:2] == ["uname", "-m"]:
            return CommandResult(0, self.host.arch + "\n", "")
        if core[:1] == ["df"]:
            return CommandResult(0, "Size Used Avail\n" + self.host.df_line + "\n", "")
        if core[:1] == ["useradd"]:
            self.host.files["ifilm-cdn-exists"] = b"1"
            return CommandResult(0, "", "")
        if core[:1] == ["install"] and "-d" not in core:
            dest = core[-1]
            src = core[-2]
            data = self.host.files.get(src, b"")
            owner = core[core.index("-o") + 1] if "-o" in core else "root"
            group = core[core.index("-g") + 1] if "-g" in core else "root"
            mode = core[core.index("-m") + 1] if "-m" in core else "0644"
            self.host.files[dest] = data
            self.host.installed[dest] = (owner, group, mode)
            return CommandResult(0, "", "")
        if core[:1] == ["test"]:
            if "VERSION" in joined:
                return CommandResult(0 if self.host.release_marker else 1, "", "")
            return CommandResult(1, "", "")
        if core[:2] == ["sha256sum", "-c"]:
            spec = self.host.files.get(core[2], b"").decode().split()
            digest = hashlib.sha256(self.host.files.get(spec[1], b"")).hexdigest()
            return CommandResult(0 if digest == spec[0] else 1, "", "")
        if core[:1] == ["tar"]:
            self.host.release_marker = True
            return CommandResult(0, "", "")
        if core[:1] == ["getent"]:
            return CommandResult(0, f"{core[2]}:x:0:0:root:/root:/bin/bash\n", "")
        if core[:1] == ["cat"]:
            path = core[1]
            if path.endswith("authorized_keys"):
                return CommandResult(0, self.host.authorized_keys, "")
            return CommandResult(1, "", "missing")
        if core[:2] == ["tee", "-a"] and stdin is not None:
            self.host.authorized_keys += stdin.decode()
            return CommandResult(0, "", "")
        if core[:1] == ["systemctl"]:
            if core[1] in {"restart", "start"}:
                self.host.service_active = True
            if core[1] == "stop":
                self.host.service_active = False
            if core[1] == "is-active":
                return CommandResult(0 if self.host.service_active else 3, "", "")
            return CommandResult(0, "", "")
        if core[:1] == ["curl"]:
            return CommandResult(0 if self.host.service_active else 7, "", "")
        if core[:1] == ["rm"]:
            for path in core[2:]:
                self.host.files.pop(path, None)
            return CommandResult(0, "", "")
        return CommandResult(0, "", "")

    def put_bytes(self, data: bytes, remote_path: str, *, mode: int = 0o600) -> None:
        self.host.files[remote_path] = data

    def close(self) -> None:
        self.closed = True


class FakeTransport:
    def __init__(self, host: FakeHost) -> None:
        self.host = host

    def connect(self, target: SSHTarget, credential: SSHCredential, *, expected_fingerprint: str | None, connect_timeout: float) -> FakeSession:
        self.host.connections.append(credential.kind)
        if self.host.firewall_applied:
            self.host.fresh_connections_after_firewall += 1
            if self.host.lock_out_after_firewall:
                raise SSHError("SSH connection failed (timeout)", code="timeout")
        if expected_fingerprint and expected_fingerprint != self.host.fingerprint:
            raise SSHError("SSH host key does not match the pinned fingerprint", code="host_key_mismatch")
        if not self.host.authorized(credential):
            raise SSHError("SSH authentication failed", code="auth_failed")
        return FakeSession(self.host)


@pytest.fixture
def secrets_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_SECRETS_KEY", key)
    monkeypatch.setenv("CDN_CENTRAL_BASE_URL", "https://ifilm.example")
    get_settings.cache_clear()
    yield key
    get_settings.cache_clear()


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="sqlite://",
        jwt_secret="unit-test-jwt-secret-value-32chars-min",
        integration_secrets_key=get_settings().integration_secrets_key,
        cdn_central_base_url="https://ifilm.example",
        cdn_management_cidrs="203.0.113.0/24",
        edge_grant_public_key_pem="-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----",
        _env_file=None,
    )
    base.update(overrides)
    return Settings(**base)


def _fake_bundle(settings: Settings) -> NodeBundle:
    data = b"fake-bundle"
    return NodeBundle(data=data, sha256=hashlib.sha256(data).hexdigest(), version="1.0.0+test")


def _seed_node(db_session, *, pinned: str | None = HOST_FP, credential="bootstrap-password-test", role="cache") -> tuple[ManagedCDNNode, AdminUser]:
    admin = db_session.query(AdminUser).filter_by(username="admin").one()
    node_dict, _ = mgmt.save_node(
        db_session,
        admin,
        {
            "name": "Nimruz Cache",
            "role": role,
            "host": "203.0.113.31",
            "ssh_port": 22,
            "ssh_username": "root",
            "credential_type": "password",
            "credential": credential,
            "branch": "nimruz",
            "cache_limit_bytes": 50_000_000_000,
            "ssh_host_key_fingerprint": pinned,
            "serve_base_url": "https://203.0.113.31:8443",
        },
    )
    node = db_session.get(ManagedCDNNode, node_dict["id"])
    return node, admin


def _queue(db_session, admin, node, action="provision") -> CDNProvisionRun:
    run_dict = mgmt.queue_action(db_session, admin, node, action)
    return db_session.get(CDNProvisionRun, run_dict["id"])


# --- Command construction / rendering ----------------------------------------


def test_render_command_quotes_every_argument():
    cmd = render_command(["install", "-m", "0640", "/tmp/x y", "/etc/ifilm-cdn/node.env; rm -rf /"], {"DEBIAN_FRONTEND": "noninteractive"})
    assert cmd == "env DEBIAN_FRONTEND=noninteractive install -m 0640 '/tmp/x y' '/etc/ifilm-cdn/node.env; rm -rf /'"
    with pytest.raises(SSHError):
        render_command([])
    with pytest.raises(SSHError):
        render_command(["true"], {"BAD KEY": "x"})


def test_render_artifacts_are_secret_free_and_hardened():
    unit = render_systemd_unit(serve_port=8443)
    assert "User=ifilm-cdn" in unit and "NoNewPrivileges=true" in unit and "ProtectSystem=strict" in unit
    assert "python -m app.services.cdn_node serve" in unit
    node = ManagedCDNNode(id="n1", name="x", role="cache", host="h", ssh_port=22, ssh_username="root", branch="Nimruz", cache_limit_bytes=1000, high_watermark_pct=90, low_watermark_pct=80)
    env = render_node_env(node=node, central_url="https://ifilm.example", node_token="tok", serve_port=8443, edge_grant_key_id="eg1", version="1.0")
    assert "IFILM_CDN_HIGH_WATERMARK_BYTES=900" in env and "IFILM_CDN_LOW_WATERMARK_BYTES=800" in env
    assert "IFILM_CDN_SITE_ID=nimruz" in env and "ENABLE_CDN_SYNC=false" in env


def _accept_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if "accept" in ln and "dport" in ln]


def test_nftables_empty_management_fails_closed_and_no_allow_any_generated():
    with pytest.raises(ProvisionStepError) as exc:
        render_nftables(ssh_port=22, serve_port=8443, management_cidrs="", serve_cidrs="")
    assert exc.value.code == "management_cidrs_missing" and exc.value.retryable is False
    with pytest.raises(ProvisionStepError) as exc:
        render_nftables(ssh_port=22, serve_port=8443, management_cidrs=[], serve_cidrs=["10.0.0.0/8"])
    assert exc.value.code == "management_cidrs_missing"


def test_nftables_empty_serve_generates_no_media_rule():
    nft = render_nftables(ssh_port=22, serve_port=8443, management_cidrs="203.0.113.0/24", serve_cidrs="")
    lines = _accept_lines(nft)
    assert lines == ["ip saddr { 203.0.113.0/24 } tcp dport 22 accept"]
    assert "dport 8443 accept" not in nft and "media port 8443 closed" in nft
    assert "policy drop" in nft and "0.0.0.0/0" not in nft and "::/0" not in nft and "nfproto" not in nft


def test_nftables_explicit_cidrs_generate_only_those_sources_v4_and_v6():
    nft = render_nftables(
        ssh_port=2222,
        serve_port=8443,
        management_cidrs="203.0.113.0/24, 2001:db8::/32",
        serve_cidrs=["103.89.153.0/24", "103.126.4.0/24", "2001:db8:1::/48"],
    )
    assert _accept_lines(nft) == [
        "ip saddr { 203.0.113.0/24 } tcp dport 2222 accept",
        "ip6 saddr { 2001:db8::/32 } tcp dport 2222 accept",
        "ip saddr { 103.89.153.0/24, 103.126.4.0/24 } tcp dport 8443 accept",
        "ip6 saddr { 2001:db8:1::/48 } tcp dport 8443 accept",
    ]
    assert "0.0.0.0/0" not in nft and "nfproto" not in nft


def test_nftables_allow_any_only_when_explicit():
    nft = render_nftables(ssh_port=22, serve_port=8443, management_cidrs="203.0.113.0/24", serve_cidrs="0.0.0.0/0,::/0")
    assert "meta nfproto ipv4 tcp dport 8443 accept" in nft and "meta nfproto ipv6 tcp dport 8443 accept" in nft
    assert "meta nfproto ipv4 tcp dport 22 accept" not in nft


@pytest.mark.parametrize("bad", ["203.0.113.5/24", "not-a-cidr", "300.1.1.0/24", "203.0.113.0/33"])
def test_nftables_rejects_malformed_cidr_before_provisioning(bad):
    with pytest.raises(ProvisionStepError) as exc:
        render_nftables(ssh_port=22, serve_port=8443, management_cidrs=bad, serve_cidrs="")
    assert exc.value.code == "invalid_cidr" and exc.value.retryable is False
    with pytest.raises(ProvisionStepError) as exc:
        render_nftables(ssh_port=22, serve_port=8443, management_cidrs="203.0.113.0/24", serve_cidrs=bad)
    assert exc.value.code == "invalid_cidr"


def test_keypair_generation_and_fingerprint():
    private_pem, public_line, fingerprint = generate_ed25519_keypair()
    assert "OPENSSH PRIVATE KEY" in private_pem
    assert public_line.startswith("ssh-ed25519 ") and public_line.endswith("ifilm-cdn-managed")
    blob = base64.b64decode(public_line.split(" ")[1])
    assert sha256_fingerprint(blob) == fingerprint and fingerprint.startswith("SHA256:")
    assert _public_from_private(private_pem).split(" ")[1] == public_line.split(" ")[1]


def test_node_bundle_builds_deterministically_and_excludes_secrets(monkeypatch):
    settings = _settings(app_version="1.2.3")
    bundle = build_node_bundle(settings)
    assert bundle.version.startswith("1.2.3+") and hashlib.sha256(bundle.data).hexdigest() == bundle.sha256
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(bundle.data), mode="r:gz") as tar:
        names = tar.getnames()
    assert "app/services/cdn_node/asgi.py" in names and "requirements-branch-cache.txt" in names and "VERSION" in names
    assert not any(n.endswith(".env") or "__pycache__" in n or n.startswith("app/tests") for n in names)
    assert build_node_bundle(settings).sha256 == bundle.sha256


# --- Test SSH --------------------------------------------------------------------


def test_test_ssh_reports_os_privilege_disk_and_fingerprint(client, db_session, secrets_key):
    node, _ = _seed_node(db_session, pinned=None)
    host = FakeHost()
    result = probe_ssh_connection(node, settings=_settings(), transport=FakeTransport(host))
    assert result["ok"] is True and result["debian13"] is True and result["privileged"] is True
    assert result["host_key_fingerprint"] == HOST_FP and result["host_key_pinned"] is False
    assert result["disk_free_bytes"] == 70000000000
    assert "bootstrap-password-test" not in json.dumps(result)
    host.os_release = UBUNTU
    result = probe_ssh_connection(node, settings=_settings(), transport=FakeTransport(host))
    assert result["ok"] is True and result["debian13"] is False and "not Debian 13" in result["detail"]
    host.password = "different"
    result = probe_ssh_connection(node, settings=_settings(), transport=FakeTransport(host))
    assert result["ok"] is False and result["code"] == "auth_failed"


def test_test_ssh_host_key_mismatch_fails_closed(client, db_session, secrets_key):
    node, _ = _seed_node(db_session, pinned="SHA256:" + "B" * 43)
    result = probe_ssh_connection(node, settings=_settings(), transport=FakeTransport(FakeHost()))
    assert result["ok"] is False and result["code"] == "host_key_mismatch"


def test_test_ssh_endpoint_records_result(client, admin_headers, db_session, secrets_key, monkeypatch):
    node, _ = _seed_node(db_session, pinned=None)
    monkeypatch.setattr("app.api.routes.admin_cdn_management.probe_ssh_connection", lambda n, settings=None: probe_ssh_connection(n, settings=settings, transport=FakeTransport(FakeHost())))
    response = client.post(f"/api/admin/cdn-management/nodes/{node.id}/test-ssh", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["node"]["observed_host_key_fingerprint"] == HOST_FP
    assert body["node"]["last_ssh_test_ok"] is True and body["node"]["os_release"] == "debian 13"
    assert "bootstrap-password-test" not in response.text


# --- Full bootstrap ---------------------------------------------------------------


def test_successful_debian13_bootstrap_rotates_key_and_marks_ready(client, db_session, secrets_key, caplog):
    caplog.set_level(logging.DEBUG)
    node, admin = _seed_node(db_session)
    run = _queue(db_session, admin, node)
    host = FakeHost()
    executor = ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    executor.execute(db_session, run, worker_id="w1")
    db_session.refresh(run)
    db_session.refresh(node)
    assert run.status == "completed", run.log_text
    assert run.step == "finalize" and run.attempt == 1 and run.error_code is None
    assert node.provision_status == "ready" and node.provisioned_at is not None and node.health_status == "online"
    assert node.software_version == "1.0.0+test" and node.os_release == "debian 13"
    assert node.disk_total_bytes == 100000000000 and node.disk_free_bytes == 70000000000
    # Installed files: node.env (0640 root:ifilm-cdn) contains the token whose hash is stored.
    env_text = host.files["/etc/ifilm-cdn/node.env"].decode()
    assert host.installed["/etc/ifilm-cdn/node.env"] == ("root", "ifilm-cdn", "0640")
    token = re.search(r"IFILM_CDN_NODE_TOKEN=(\S+)", env_text).group(1)
    assert hashlib.sha256(token.encode()).hexdigest() == node.heartbeat_token_hash
    assert "IFILM_CDN_CENTRAL_URL=https://ifilm.example" in env_text
    assert "/etc/systemd/system/ifilm-cdn.service" in host.installed
    assert "/etc/nftables.conf" in host.installed and b"policy drop" in host.files["/etc/nftables.conf"]
    nft_text = host.files["/etc/nftables.conf"].decode()
    assert "ip saddr { 203.0.113.0/24 } tcp dport 22 accept" in nft_text
    assert "dport 8443 accept" not in nft_text and "0.0.0.0/0" not in nft_text  # media port closed in P1
    cmds = [" ".join(c) for c in host.commands]
    check_idx = next(i for i, c in enumerate(cmds) if "nft -c -f" in c)
    apply_idx = next(i for i, c in enumerate(cmds) if c.endswith("nft -f /etc/ifilm-cdn/nftables.candidate"))
    persist_idx = next(i for i, c in enumerate(cmds) if "nftables.candidate /etc/nftables.conf" in c)
    assert check_idx < apply_idx < persist_idx
    assert host.fresh_connections_after_firewall >= 1  # fresh SSH verified after apply
    assert b"BEGIN PUBLIC KEY" in host.files["/etc/ifilm-cdn/edge-grant-public.pem"]
    assert host.service_active is True
    # Bundle verified by checksum before extraction.
    assert any(c[:2] == ["sha256sum", "-c"] for c in host.commands)
    assert host.commands.index(next(c for c in host.commands if c[:2] == ["sha256sum", "-c"])) < host.commands.index(next(c for c in host.commands if c[:1] == ["tar"]))
    # Key rotation: private key verified on a fresh connection, then bootstrap password retired.
    assert host.connections == ["password", "password", "private_key"]  # bootstrap, fresh verify, key verify
    assert node.credential_ciphertext is None and node.credential_type == "managed_key"
    assert node.managed_key_ciphertext is not None and node.managed_key_fingerprint.startswith("SHA256:")
    assert node.managed_key_public.split(" ")[1] in host.authorized_keys
    private_pem = mgmt.load_managed_private_key(node, _settings())
    assert "OPENSSH PRIVATE KEY" in private_pem
    # No secrets in the run log, DB log, or captured logging output.
    for secret in ("bootstrap-password-test", token, private_pem.strip().splitlines()[1]):
        assert secret not in run.log_text
        assert secret not in caplog.text
    assert "[REDACTED]" not in host.files["/etc/ifilm-cdn/node.env"].decode()
    assert node.last_error is None
    steps_logged = [line for line in run.log_text.splitlines() if "== " in line]
    assert len(steps_logged) == len(ACTION_STEPS["provision"])


def test_bootstrap_idempotent_rerun_uses_managed_key(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    host = FakeHost()
    executor = ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    executor.execute(db_session, _queue(db_session, admin, node), worker_id="w1")
    db_session.refresh(node)
    assert node.credential_type == "managed_key"
    first_key = node.managed_key_fingerprint
    host.connections.clear()
    host.commands.clear()
    run2 = _queue(db_session, admin, node, "reprovision")
    executor.execute(db_session, run2, worker_id="w1")
    db_session.refresh(run2)
    db_session.refresh(node)
    assert run2.status == "completed", run2.log_text
    assert host.connections == ["private_key", "private_key"]  # bootstrap + fresh firewall verify; no password
    assert node.managed_key_fingerprint == first_key
    assert not any(c[:1] == ["useradd"] for c in host.commands)  # user already exists
    assert not any(c[:1] == ["tar"] for c in host.commands)  # release already installed
    upgrade = _queue(db_session, admin, node, "upgrade")
    executor.execute(db_session, upgrade, worker_id="w1")
    db_session.refresh(upgrade)
    assert upgrade.status == "completed" and upgrade.step == "finalize"
    clear = _queue(db_session, admin, node, "clear-cache")
    executor.execute(db_session, clear, worker_id="w1")
    db_session.refresh(clear)
    assert clear.status == "completed" and any(c[:1] == ["find"] for c in host.commands)


def test_bootstrap_failure_resume_and_retry(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    host = FakeHost(fail_commands={"apt-get install": 100})
    executor = ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    run = _queue(db_session, admin, node)
    executor.execute(db_session, run, worker_id="w1")
    db_session.refresh(run)
    db_session.refresh(node)
    assert run.status == "failed" and run.error_code == "apt_install_failed" and run.step == "packages"
    assert node.provision_status == "failed" and node.last_error == "packages: apt_install_failed"
    assert node.credential_ciphertext is not None  # bootstrap credential kept on failure
    assert "bootstrap-password-test" not in run.log_text
    # Retry resumes from the failed step (preflight not re-run) once apt works again.
    host.fail_commands.clear()
    host.commands.clear()
    retry = _queue(db_session, admin, node)
    assert retry.resume_from_step == "packages"
    executor.execute(db_session, retry, worker_id="w1")
    db_session.refresh(retry)
    db_session.refresh(node)
    assert retry.status == "completed", retry.log_text
    assert node.provision_status == "ready"
    assert not any(c[:2] == ["cat", "/etc/os-release"] for c in host.commands)


def test_bootstrap_rejects_unsupported_os_auth_failure_timeout_and_host_key(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    executor_for = lambda host: ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle)  # noqa: E731

    run = _queue(db_session, admin, node)
    executor_for(FakeHost(os_release=UBUNTU)).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "unsupported_os" and "ubuntu 24.04" in run.log_text

    run = _queue(db_session, admin, node)
    executor_for(FakeHost(password="other")).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "auth_failed"

    run = _queue(db_session, admin, node)
    executor_for(FakeHost(timeout_commands={"apt-get update"})).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "timeout"

    run = _queue(db_session, admin, node)
    executor_for(FakeHost(fingerprint="SHA256:" + "C" * 43)).execute(db_session, run)
    db_session.refresh(run)
    db_session.refresh(node)
    assert run.status == "failed" and run.error_code == "host_key_mismatch"
    assert node.credential_ciphertext is not None and node.provision_status == "failed"

    run = _queue(db_session, admin, node)
    executor_for(FakeHost(uid="1000", sudo_ok=False)).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "sudo_unavailable"

    run = _queue(db_session, admin, node)
    executor_for(FakeHost(df_line="  1000 500 500")).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "disk_too_small"


def test_key_rotation_keeps_bootstrap_when_key_login_fails(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)

    class NoKeyLoginHost(FakeHost):
        def authorized(self, credential):
            return credential.kind == "password" and credential.secret == self.password

    host = NoKeyLoginHost()
    executor = ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    run = _queue(db_session, admin, node)
    executor.execute(db_session, run)
    db_session.refresh(run)
    db_session.refresh(node)
    assert run.status == "failed" and run.error_code == "key_login_failed" and run.step == "rotate_key"
    assert node.credential_ciphertext is not None and node.managed_key_ciphertext is None
    assert node.credential_type == "password"


def test_bundle_checksum_mismatch_fails_before_extract(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    host = FakeHost()
    original_put = FakeSession.put_bytes

    def corrupt_put(self, data, remote_path, *, mode=0o600):
        if remote_path.endswith(".tar.gz"):
            data = data + b"tampered"
        original_put(self, data, remote_path, mode=mode)

    FakeSession.put_bytes = corrupt_put
    try:
        run = _queue(db_session, admin, node)
        ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle).execute(db_session, run)
    finally:
        FakeSession.put_bytes = original_put
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "bundle_checksum_mismatch"
    assert not any(c[:1] == ["tar"] for c in host.commands)


def test_executor_requires_central_url_and_pinned_key(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    run = _queue(db_session, admin, node)
    ProvisionExecutor(settings=_settings(cdn_central_base_url=""), transport=FakeTransport(FakeHost()), bundle_builder=_fake_bundle).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "central_url_missing"
    node.ssh_host_key_fingerprint = None
    db_session.add(node)
    db_session.commit()
    run = CDNProvisionRun(node_id=node.id, action="provision", status="queued")
    db_session.add(run)
    db_session.commit()
    ProvisionExecutor(settings=_settings(), transport=FakeTransport(FakeHost()), bundle_builder=_fake_bundle).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "host_key_unpinned"


# --- Worker ----------------------------------------------------------------------


def test_worker_claims_runs_and_recovers_stale(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    settings = _settings(enable_cdn_provisioning=True, cdn_provisioning_stale_after_seconds=60)
    assert worker.claim_next_run(db_session, worker_id="w1") is None
    run = _queue(db_session, admin, node)
    claimed = worker.claim_next_run(db_session, worker_id="w1")
    assert claimed is not None and claimed.id == run.id and claimed.status == "running" and claimed.claimed_by == "w1"
    assert worker.claim_next_run(db_session, worker_id="w2") is None
    claimed.claimed_at = datetime.now(UTC) - timedelta(seconds=600)
    db_session.add(claimed)
    db_session.commit()
    assert worker.recover_stale_runs(db_session, settings=settings) == 1
    db_session.refresh(claimed)
    db_session.refresh(node)
    assert claimed.status == "failed" and claimed.error_code == "worker_lost" and node.provision_status == "failed"
    # run_once executes a queued run end-to-end through the executor.
    run2 = _queue(db_session, admin, node)
    executor = ProvisionExecutor(settings=settings, transport=FakeTransport(FakeHost()), bundle_builder=_fake_bundle)
    assert worker.run_once(db_session, executor=executor, settings=settings, worker_id="w1") is True
    db_session.refresh(run2)
    assert run2.status == "completed" and run2.claimed_by == "w1"
    assert worker.run_once(db_session, executor=executor, settings=settings, worker_id="w1") is False


def test_worker_startup_fails_closed(secrets_key):
    ok, reason = worker.worker_startup_ok(_settings(enable_cdn_provisioning=False))
    assert not ok and "ENABLE_CDN_PROVISIONING" in reason
    ok, reason = worker.worker_startup_ok(_settings(enable_cdn_provisioning=True, integration_secrets_key=""))
    assert not ok and "INTEGRATION_SECRETS_KEY" in reason
    ok, reason = worker.worker_startup_ok(_settings(enable_cdn_provisioning=True, cdn_central_base_url="http://plain"))
    assert not ok and "https" in reason
    assert worker.worker_startup_ok(_settings(enable_cdn_provisioning=True))[0] is True


# --- Firewall fail-closed regression tests ------------------------------------------


def test_firewall_step_fails_closed_without_management_cidrs(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    host = FakeHost()
    executor = ProvisionExecutor(settings=_settings(cdn_management_cidrs=""), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    run = _queue(db_session, admin, node)
    executor.execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "management_cidrs_missing" and run.step == "firewall"
    assert "/etc/nftables.conf" not in host.installed
    assert not any(c[:2] == ["nft", "-f"] for c in host.commands)
    assert host.firewall_applied is False


def test_firewall_step_prefers_admin_network_policy_over_env(client, db_session, secrets_key):
    from app.services.cdn_network import update_network_settings

    node, admin = _seed_node(db_session)
    update_network_settings(db_session, admin, management_cidrs=["203.0.113.0/24"], serve_cidrs=["103.126.4.0/24"])
    host = FakeHost()
    executor = ProvisionExecutor(settings=_settings(cdn_management_cidrs="198.51.100.0/24", cdn_serve_cidrs=""), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    run = _queue(db_session, admin, node)
    executor.execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "completed", run.log_text
    nft_text = host.files["/etc/nftables.conf"].decode()
    assert "ip saddr { 203.0.113.0/24 } tcp dport 22 accept" in nft_text
    assert "ip saddr { 103.126.4.0/24 } tcp dport 8443 accept" in nft_text
    assert "198.51.100.0/24" not in nft_text


def test_firewall_refuses_to_lock_out_the_worker(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    host = FakeHost(ssh_source="198.51.100.9")  # worker source outside management CIDRs
    executor = ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    run = _queue(db_session, admin, node)
    executor.execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "management_cidrs_exclude_worker"
    assert not any(c[:2] == ["nft", "-f"] for c in host.commands)
    host = FakeHost(ssh_source="")
    run = _queue(db_session, admin, node)
    ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "management_source_unknown"


def test_firewall_syntax_error_blocks_apply(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    host = FakeHost(fail_commands={"nft -c": 1})
    executor = ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    run = _queue(db_session, admin, node)
    executor.execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "firewall_invalid"
    assert not any(c[:2] == ["nft", "-f"] for c in host.commands)
    assert host.firewall_applied is False and "/etc/nftables.conf" not in host.installed


def test_failed_fresh_ssh_verification_rolls_back_firewall(client, db_session, secrets_key, caplog):
    caplog.set_level(logging.DEBUG)
    node, admin = _seed_node(db_session)
    host = FakeHost(lock_out_after_firewall=True, live_ruleset="table inet previous {\n  chain input { type filter hook input priority 0; policy accept; }\n}\n")
    executor = ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle)
    run = _queue(db_session, admin, node)
    executor.execute(db_session, run)
    db_session.refresh(run)
    db_session.refresh(node)
    assert run.status == "failed" and run.error_code == "firewall_verify_failed" and run.step == "firewall"
    assert host.fresh_connections_after_firewall == 1
    cmds = [" ".join(c) for c in host.commands]
    assert any(c.endswith("nft flush ruleset") for c in cmds)
    assert any(c.endswith("nft -f /etc/ifilm-cdn/nftables.rollback") for c in cmds)
    assert "table inet previous" in host.live_ruleset  # previous ruleset restored
    assert host.firewall_applied is False
    assert "/etc/nftables.conf" not in host.installed  # never persisted an unverified ruleset
    assert not any("systemctl enable nftables" in c for c in cmds)
    assert node.provision_status == "failed" and node.credential_ciphertext is not None
    assert "previous ruleset restored" in run.log_text
    for secret in ("bootstrap-password-test",):
        assert secret not in run.log_text and secret not in caplog.text


def test_failed_fresh_ssh_verification_without_previous_ruleset_flushes(client, db_session, secrets_key):
    node, admin = _seed_node(db_session)
    host = FakeHost(lock_out_after_firewall=True, live_ruleset="")
    run = _queue(db_session, admin, node)
    ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle).execute(db_session, run)
    db_session.refresh(run)
    assert run.status == "failed" and run.error_code == "firewall_verify_failed"
    assert host.live_ruleset == "" and host.firewall_applied is False
    assert not any(c[:2] == ["nft", "-f"] and c[2].endswith("rollback") for c in host.commands)


def test_firewall_logs_never_contain_secrets(client, db_session, secrets_key, caplog):
    caplog.set_level(logging.DEBUG)
    node, admin = _seed_node(db_session)
    host = FakeHost()
    run = _queue(db_session, admin, node)
    ProvisionExecutor(settings=_settings(), transport=FakeTransport(host), bundle_builder=_fake_bundle).execute(db_session, run)
    db_session.refresh(run)
    db_session.refresh(node)
    assert run.status == "completed"
    env_text = host.files["/etc/ifilm-cdn/node.env"].decode()
    token = re.search(r"IFILM_CDN_NODE_TOKEN=(\S+)", env_text).group(1)
    private_pem = mgmt.load_managed_private_key(node, _settings())
    firewall_log = "\n".join(ln for ln in run.log_text.splitlines() if "nft" in ln or "firewall" in ln.lower())
    assert firewall_log  # firewall step was logged
    for secret in ("bootstrap-password-test", token, private_pem.strip().splitlines()[1]):
        assert secret not in run.log_text and secret not in caplog.text and secret not in host.files["/etc/nftables.conf"].decode()
