"""Debian 13 CDN node provisioning: idempotent, resumable, fail-closed steps.

Runs only inside the privileged worker (``python -m app.workers.cdn_provisioning``)
or, for the bounded ``Test SSH`` probe, the admin API. Every remote command is
an argv list (no shell interpolation of admin input); secrets travel over SFTP
into root-owned files and are redacted from all recorded logs.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import secrets
import shlex
import socket
import tarfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.cdn_management import CDNProvisionRun, ManagedCDNNode
from app.services import cdn_management as mgmt
from app.services.cdn_provisioning import ProvisioningError, redact_log, validate_target
from app.services.cdn_ssh import (
    CommandResult,
    ParamikoTransport,
    SSHCredential,
    SSHError,
    SSHSession,
    SSHTarget,
    SSHTransport,
    generate_ed25519_keypair,
)

logger = logging.getLogger("app.cdn.provisioner")

NODE_USER = "ifilm-cdn"
REMOTE_BASE = "/opt/ifilm-cdn"
REMOTE_CONFIG_DIR = "/etc/ifilm-cdn"
REMOTE_CACHE_DIR = "/var/lib/ifilm-cdn/cache"
REMOTE_LOG_DIR = "/var/log/ifilm-cdn"
REMOTE_SERVICE = "ifilm-cdn"
REMOTE_UNIT_PATH = f"/etc/systemd/system/{REMOTE_SERVICE}.service"
REMOTE_NFT_PATH = "/etc/nftables.conf"
SUPPORTED_DEBIAN_VERSIONS = ("13",)
MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024
APT_PACKAGES = ("ca-certificates", "curl", "nftables", "python3", "python3-venv")

PROVISION_STEPS = (
    "preflight",
    "packages",
    "user_dirs",
    "bundle",
    "config",
    "systemd",
    "firewall",
    "start",
    "verify",
    "collect",
    "rotate_key",
    "finalize",
)
UPGRADE_STEPS = ("preflight", "bundle", "config", "systemd", "start", "verify", "collect", "finalize")
CLEAR_CACHE_STEPS = ("preflight", "clear_cache", "start", "verify", "collect", "finalize")
ACTION_STEPS = {
    "provision": PROVISION_STEPS,
    "reprovision": PROVISION_STEPS,
    "upgrade": UPGRADE_STEPS,
    "clear-cache": CLEAR_CACHE_STEPS,
}

_VERSION_RE = re.compile(r'^VERSION_ID="?([0-9.]+)"?', re.MULTILINE)
_ID_RE = re.compile(r"^ID=\"?([a-z]+)\"?", re.MULTILINE)


class ProvisionStepError(Exception):
    def __init__(self, message: str, *, code: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Node bundle (versioned tarball of the node runtime built from this checkout)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeBundle:
    data: bytes = field(repr=False)
    sha256: str
    version: str

    @property
    def filename(self) -> str:
        return f"ifilm-cdn-node-{self.version}.tar.gz"


_BUNDLE_EXCLUDE_DIRS = {"__pycache__", "tests", ".pytest_cache", ".mypy_cache", ".venv"}
_BUNDLE_EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".env", ".log")


def build_node_bundle(settings: Settings | None = None) -> NodeBundle:
    """Package ``app/`` + minimal node requirements into a deterministic tar.gz."""
    cfg = settings or get_settings()
    import app as app_pkg

    app_dir = Path(app_pkg.__file__).resolve().parent
    backend_dir = app_dir.parent
    requirements = backend_dir / "requirements-branch-cache.txt"
    if not requirements.is_file():
        raise ProvisioningError("requirements-branch-cache.txt missing; cannot build node bundle")

    def _filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(info.name).parts
        if any(part in _BUNDLE_EXCLUDE_DIRS for part in parts):
            return None
        if info.name.endswith(_BUNDLE_EXCLUDE_SUFFIXES) or Path(info.name).name.startswith(".env"):
            return None
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        info.mtime = 0
        return info

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", compresslevel=6) as tar:
        tar.add(str(app_dir), arcname="app", filter=_filter)
        tar.add(str(requirements), arcname="requirements-branch-cache.txt", filter=_filter)
    data = buffer.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    base = (cfg.app_version or "0.0.0-dev").strip() or "0.0.0-dev"
    version = f"{base}+{digest[:8]}"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", compresslevel=6) as tar:
        tar.add(str(app_dir), arcname="app", filter=_filter)
        tar.add(str(requirements), arcname="requirements-branch-cache.txt", filter=_filter)
        version_info = tarfile.TarInfo("VERSION")
        payload = (version + "\n").encode("utf-8")
        version_info.size = len(payload)
        version_info.mtime = 0
        tar.addfile(version_info, io.BytesIO(payload))
    data = buffer.getvalue()
    return NodeBundle(data=data, sha256=hashlib.sha256(data).hexdigest(), version=version)


# ---------------------------------------------------------------------------
# Rendered node artifacts (no secrets in unit/firewall; secrets only in node.env)
# ---------------------------------------------------------------------------


def render_systemd_unit(*, serve_port: int) -> str:
    return f"""[Unit]
Description=iFilm CDN node (pull-through HLS cache)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={NODE_USER}
Group={NODE_USER}
EnvironmentFile={REMOTE_CONFIG_DIR}/node.env
WorkingDirectory={REMOTE_BASE}/current
ExecStart={REMOTE_BASE}/venv/bin/python -m app.services.cdn_node serve
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
ReadWritePaths=/var/lib/ifilm-cdn {REMOTE_LOG_DIR}
LimitNOFILE=65536
Environment=IFILM_CDN_BIND_PORT={int(serve_port)}

[Install]
WantedBy=multi-user.target
"""


def _split_cidrs(raw: str) -> tuple[list[str], list[str]]:
    import ipaddress

    v4: list[str] = []
    v6: list[str] = []
    for item in (raw or "").split(","):
        text = item.strip()
        if not text:
            continue
        network = ipaddress.ip_network(text, strict=False)
        (v4 if network.version == 4 else v6).append(str(network))
    return v4, v6


def _nft_accept_rules(port: int, cidrs: str, *, allow_any_when_empty: bool) -> list[str]:
    v4, v6 = _split_cidrs(cidrs)
    if not v4 and not v6:
        return [f"    tcp dport {port} accept"] if allow_any_when_empty else []
    rules: list[str] = []
    if "0.0.0.0/0" in v4:
        rules.append(f"    meta nfproto ipv4 tcp dport {port} accept")
    elif v4:
        rules.append(f"    ip saddr {{ {', '.join(v4)} }} tcp dport {port} accept")
    if "::/0" in v6:
        rules.append(f"    meta nfproto ipv6 tcp dport {port} accept")
    elif v6:
        rules.append(f"    ip6 saddr {{ {', '.join(v6)} }} tcp dport {port} accept")
    return rules


def render_nftables(*, ssh_port: int, serve_port: int, management_cidrs: str, serve_cidrs: str) -> str:
    ssh_rules = _nft_accept_rules(ssh_port, management_cidrs, allow_any_when_empty=True)
    serve_rules = _nft_accept_rules(serve_port, serve_cidrs, allow_any_when_empty=True)
    body = "\n".join(ssh_rules + serve_rules)
    return f"""#!/usr/sbin/nft -f
# Managed by iFilm CDN provisioning. Default deny inbound; SSH + media port only.
flush ruleset
table inet ifilm_cdn {{
  chain input {{
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    ct state invalid drop
    iif "lo" accept
    ip protocol icmp accept
    ip6 nexthdr ipv6-icmp accept
{body}
  }}
  chain forward {{
    type filter hook forward priority 0; policy drop;
  }}
  chain output {{
    type filter hook output priority 0; policy accept;
  }}
}}
"""


def render_node_env(
    *,
    node: ManagedCDNNode,
    central_url: str,
    node_token: str,
    serve_port: int,
    edge_grant_key_id: str,
    version: str,
) -> str:
    limit = int(node.cache_limit_bytes or 0)
    high = int(node.high_watermark_pct or 90)
    low = int(node.low_watermark_pct or 80)
    lines = [
        "# Managed by iFilm CDN provisioning. Contains the node identity token: keep 0640 root:ifilm-cdn.",
        "ENABLE_CDN_NODE_SERVICE=true",
        "ENABLE_CDN_SYNC=false",
        f"IFILM_CDN_NODE_ID={node.id}",
        f"IFILM_CDN_NODE_ROLE={node.role}",
        f"IFILM_CDN_SITE_ID={(node.branch or 'default').strip().lower() or 'default'}",
        f"IFILM_CDN_CENTRAL_URL={central_url}",
        f"IFILM_CDN_NODE_TOKEN={node_token}",
        f"IFILM_CDN_CACHE_ROOT={REMOTE_CACHE_DIR}",
        f"IFILM_CDN_CACHE_LIMIT_BYTES={limit}",
        f"IFILM_CDN_HIGH_WATERMARK_BYTES={limit * high // 100}",
        f"IFILM_CDN_LOW_WATERMARK_BYTES={limit * low // 100}",
        "IFILM_CDN_BIND_HOST=0.0.0.0",
        f"IFILM_CDN_BIND_PORT={int(serve_port)}",
        f"IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE={REMOTE_CONFIG_DIR}/edge-grant-public.pem",
        f"IFILM_CDN_EDGE_GRANT_KEY_ID={edge_grant_key_id}",
        f"IFILM_CDN_SOFTWARE_VERSION={version}",
        "IFILM_CDN_HEARTBEAT_SECONDS=30",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Redacting run log
# ---------------------------------------------------------------------------


class RunLog:
    def __init__(self, secrets_to_redact: Sequence[str] = ()) -> None:
        self._lines: list[str] = []
        self._secrets = [s for s in secrets_to_redact if s]

    def add_secret(self, value: str | None) -> None:
        if value:
            self._secrets.append(value)

    def info(self, message: str) -> None:
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        self._lines.append(f"[{stamp}] {message}")

    def command(self, argv: Sequence[str], result: CommandResult) -> None:
        shown = " ".join(shlex.quote(str(a)) for a in argv[:6])
        if len(argv) > 6:
            shown += " …"
        status = "timeout" if result.timed_out else f"exit={result.exit_code}"
        self.info(f"$ {shown} → {status}")
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        for line in tail:
            self.info(f"    {line[:200]}")

    def text(self) -> str:
        return redact_log(self._lines, self._secrets)


# ---------------------------------------------------------------------------
# Execution context + step implementations
# ---------------------------------------------------------------------------


@dataclass
class ProvisionContext:
    db: Session
    node: ManagedCDNNode
    run: CDNProvisionRun
    settings: Settings
    transport: SSHTransport
    log: RunLog
    session: SSHSession | None = None
    bundle: NodeBundle | None = None
    node_token: str | None = None
    disk: dict[str, int] = field(default_factory=dict)
    key_rotated: bool = False

    @property
    def sudo(self) -> list[str]:
        return [] if self.node.ssh_username == "root" else ["sudo", "-n"]

    def run_cmd(
        self,
        argv: Sequence[str],
        *,
        privileged: bool = True,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
        check: bool = True,
        code: str = "command_failed",
    ) -> CommandResult:
        assert self.session is not None
        full = [*self.sudo, *argv] if privileged else list(argv)
        result = self.session.run(
            full,
            timeout=timeout or float(self.settings.cdn_ssh_command_timeout_seconds),
            env=env,
            stdin=stdin,
        )
        self.log.command(full, result)
        if result.timed_out:
            raise ProvisionStepError(f"command timed out: {argv[0]}", code="timeout")
        if check and result.exit_code != 0:
            raise ProvisionStepError(f"command failed: {argv[0]}", code=code)
        return result

    def install_file(
        self, data: bytes, dest: str, *, mode: str, owner: str = "root", group: str = "root"
    ) -> None:
        """Upload to a private temp path, then install atomically with root ownership."""
        assert self.session is not None
        tmp = f"/tmp/ifilm-cdn-{secrets.token_hex(8)}"
        self.session.put_bytes(data, tmp, mode=0o600)
        try:
            self.run_cmd(["install", "-o", owner, "-g", group, "-m", mode, tmp, dest])
        finally:
            self.run_cmd(["rm", "-f", tmp], privileged=False, check=False)


def _credential_for(node: ManagedCDNNode, settings: Settings) -> SSHCredential:
    managed = mgmt.load_managed_private_key(node, settings)
    if managed:
        return SSHCredential(kind="private_key", secret=managed)
    bootstrap = mgmt.load_bootstrap_credential(node, settings)
    if not bootstrap:
        raise ProvisionStepError("no SSH credential available", code="no_credential", retryable=False)
    kind = "private_key" if node.credential_type == mgmt.CREDENTIAL_PRIVATE_KEY else "password"
    return SSHCredential(kind=kind, secret=bootstrap)


def _parse_os_release(text: str) -> tuple[str, str]:
    os_id = (_ID_RE.search(text or "") or [None, ""])[1] or ""
    version = (_VERSION_RE.search(text or "") or [None, ""])[1] or ""
    return os_id.strip().lower(), version.strip()


def _parse_df(text: str) -> dict[str, int]:
    lines = [ln for ln in (text or "").strip().splitlines() if ln.strip()]
    if not lines:
        raise ProvisionStepError("unable to read disk usage", code="disk_unreadable")
    parts = lines[-1].split()
    try:
        size, used, avail = (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError) as exc:
        raise ProvisionStepError("unable to parse disk usage", code="disk_unreadable") from exc
    return {"total": size, "used": used, "free": avail}


def _central_url(settings: Settings) -> str:
    url = (settings.cdn_central_base_url or "").strip().rstrip("/")
    if not url.startswith("https://"):
        raise ProvisionStepError(
            "CDN_CENTRAL_BASE_URL must be an https URL reachable by nodes",
            code="central_url_missing",
            retryable=False,
        )
    return url


def step_preflight(ctx: ProvisionContext) -> None:
    result = ctx.run_cmd(["cat", "/etc/os-release"], privileged=False, code="os_unreadable")
    os_id, version = _parse_os_release(result.stdout)
    ctx.node.os_release = f"{os_id} {version}".strip()[:64]
    if os_id != "debian" or version.split(".")[0] not in SUPPORTED_DEBIAN_VERSIONS:
        raise ProvisionStepError(
            f"unsupported operating system: {os_id or 'unknown'} {version or ''}".strip(),
            code="unsupported_os",
            retryable=False,
        )
    ctx.log.info(f"Detected {os_id} {version}")
    whoami = ctx.run_cmd(["id", "-u"], privileged=False)
    if whoami.stdout.strip() != "0":
        ctx.run_cmd(["true"], privileged=True, code="sudo_unavailable")
    arch = ctx.run_cmd(["uname", "-m"], privileged=False).stdout.strip()
    if arch not in {"x86_64", "aarch64"}:
        raise ProvisionStepError(f"unsupported architecture {arch}", code="unsupported_arch", retryable=False)
    ctx.run_cmd(["install", "-d", "-m", "0755", "/var/lib/ifilm-cdn"])
    df = ctx.run_cmd(["df", "-B1", "--output=size,used,avail", "/var/lib/ifilm-cdn"], privileged=False)
    ctx.disk = _parse_df(df.stdout)
    if ctx.disk["free"] < MIN_FREE_BYTES:
        raise ProvisionStepError("insufficient free disk (need at least 2 GiB)", code="disk_too_small", retryable=False)
    limit = int(ctx.node.cache_limit_bytes or 0)
    if limit and limit > ctx.disk["total"]:
        ctx.log.info("Warning: configured storage limit exceeds the disk size; eviction will enforce the disk.")


def step_packages(ctx: ProvisionContext) -> None:
    env = {"DEBIAN_FRONTEND": "noninteractive"}
    ctx.run_cmd(["apt-get", "update", "-q"], env=env, code="apt_update_failed")
    ctx.run_cmd(
        ["apt-get", "install", "-y", "-q", "--no-install-recommends", *APT_PACKAGES],
        env=env,
        code="apt_install_failed",
    )


def step_user_dirs(ctx: ProvisionContext) -> None:
    exists = ctx.run_cmd(["id", "-u", NODE_USER], privileged=False, check=False)
    if exists.exit_code != 0:
        ctx.run_cmd(
            [
                "useradd",
                "--system",
                "--home-dir",
                "/var/lib/ifilm-cdn",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                NODE_USER,
            ]
        )
    ctx.run_cmd(["install", "-d", "-o", NODE_USER, "-g", NODE_USER, "-m", "0750", REMOTE_CACHE_DIR, REMOTE_LOG_DIR])
    ctx.run_cmd(["install", "-d", "-o", "root", "-g", NODE_USER, "-m", "0750", REMOTE_CONFIG_DIR])
    ctx.run_cmd(["install", "-d", "-o", "root", "-g", "root", "-m", "0755", REMOTE_BASE, f"{REMOTE_BASE}/releases"])


def step_bundle(ctx: ProvisionContext) -> None:
    bundle = ctx.bundle or build_node_bundle(ctx.settings)
    ctx.bundle = bundle
    release_dir = f"{REMOTE_BASE}/releases/{bundle.version}"
    marker = ctx.run_cmd(["test", "-f", f"{release_dir}/VERSION"], check=False)
    if marker.exit_code == 0:
        ctx.log.info(f"Release {bundle.version} already installed; skipping upload")
    else:
        assert ctx.session is not None
        tmp = f"/tmp/{bundle.filename}"
        ctx.session.put_bytes(bundle.data, tmp, mode=0o600)
        ctx.session.put_bytes(f"{bundle.sha256}  {tmp}\n".encode(), f"{tmp}.sha256", mode=0o600)
        ctx.run_cmd(["sha256sum", "-c", f"{tmp}.sha256"], privileged=False, code="bundle_checksum_mismatch")
        ctx.run_cmd(["install", "-d", "-m", "0755", release_dir])
        ctx.run_cmd(["tar", "-xzf", tmp, "-C", release_dir], code="bundle_extract_failed")
        ctx.run_cmd(["rm", "-f", tmp, f"{tmp}.sha256"], privileged=False, check=False)
    venv_python = f"{REMOTE_BASE}/venv/bin/python"
    if ctx.run_cmd(["test", "-x", venv_python], check=False).exit_code != 0:
        ctx.run_cmd(["python3", "-m", "venv", f"{REMOTE_BASE}/venv"], code="venv_failed")
    ctx.run_cmd(
        [f"{REMOTE_BASE}/venv/bin/pip", "install", "-q", "--disable-pip-version-check", "-r", f"{release_dir}/requirements-branch-cache.txt"],
        code="pip_install_failed",
    )
    ctx.run_cmd(["ln", "-sfn", release_dir, f"{REMOTE_BASE}/current"])
    ctx.run_cmd(["chown", "-R", f"root:{NODE_USER}", release_dir])
    ctx.log.info(f"Installed node runtime {bundle.version}")


def step_config(ctx: ProvisionContext) -> None:
    central = _central_url(ctx.settings)
    token = mgmt.issue_heartbeat_token(ctx.node)
    ctx.node_token = token
    ctx.log.add_secret(token)
    version = ctx.bundle.version if ctx.bundle else (ctx.node.software_version or "unknown")
    env_text = render_node_env(
        node=ctx.node,
        central_url=central,
        node_token=token,
        serve_port=int(ctx.settings.cdn_node_serve_port),
        edge_grant_key_id=(ctx.settings.edge_grant_key_id or "eg1").strip() or "eg1",
        version=version,
    )
    ctx.install_file(env_text.encode("utf-8"), f"{REMOTE_CONFIG_DIR}/node.env", mode="0640", group=NODE_USER)
    public_pem = (ctx.settings.edge_grant_public_key_pem or "").strip()
    if public_pem and "PRIVATE KEY" not in public_pem:
        ctx.install_file((public_pem + "\n").encode("utf-8"), f"{REMOTE_CONFIG_DIR}/edge-grant-public.pem", mode="0644")
    else:
        ctx.log.info("Edge-grant public key not configured centrally; node object serving stays disabled until CDN-P2")
    # Token hash is persisted with the node row when the run completes/fails.
    ctx.db.add(ctx.node)
    ctx.db.commit()


def step_systemd(ctx: ProvisionContext) -> None:
    unit = render_systemd_unit(serve_port=int(ctx.settings.cdn_node_serve_port))
    ctx.install_file(unit.encode("utf-8"), REMOTE_UNIT_PATH, mode="0644")
    ctx.run_cmd(["systemctl", "daemon-reload"])
    ctx.run_cmd(["systemctl", "enable", REMOTE_SERVICE])


def step_firewall(ctx: ProvisionContext) -> None:
    rules = render_nftables(
        ssh_port=int(ctx.node.ssh_port),
        serve_port=int(ctx.settings.cdn_node_serve_port),
        management_cidrs=ctx.settings.cdn_management_cidrs,
        serve_cidrs=ctx.settings.cdn_serve_cidrs,
    )
    candidate = "/etc/ifilm-cdn/nftables.candidate"
    ctx.install_file(rules.encode("utf-8"), candidate, mode="0640", group=NODE_USER)
    ctx.run_cmd(["nft", "-c", "-f", candidate], code="firewall_invalid")
    ctx.run_cmd(["install", "-o", "root", "-g", "root", "-m", "0640", candidate, REMOTE_NFT_PATH])
    ctx.run_cmd(["nft", "-f", REMOTE_NFT_PATH], code="firewall_apply_failed")
    ctx.run_cmd(["systemctl", "enable", "nftables"])
    ctx.run_cmd(["rm", "-f", candidate], check=False)


def step_start(ctx: ProvisionContext) -> None:
    ctx.run_cmd(["systemctl", "restart", REMOTE_SERVICE], code="service_start_failed")
    for _ in range(10):
        active = ctx.run_cmd(["systemctl", "is-active", "--quiet", REMOTE_SERVICE], check=False)
        if active.exit_code == 0:
            return
        time.sleep(1)
    raise ProvisionStepError("service did not become active", code="service_not_active")


def step_verify(ctx: ProvisionContext) -> None:
    port = int(ctx.settings.cdn_node_serve_port)
    for path in ("/health", "/ready"):
        ok = False
        for _ in range(10):
            probe = ctx.run_cmd(
                ["curl", "-fsS", "--max-time", "5", f"http://127.0.0.1:{port}{path}"],
                privileged=False,
                check=False,
                timeout=15,
            )
            if probe.exit_code == 0:
                ok = True
                break
            time.sleep(1)
        if not ok:
            raise ProvisionStepError(f"local health check failed: {path}", code="health_check_failed")


def step_collect(ctx: ProvisionContext) -> None:
    df = ctx.run_cmd(["df", "-B1", "--output=size,used,avail", REMOTE_CACHE_DIR], privileged=False)
    ctx.disk = _parse_df(df.stdout)
    ctx.node.disk_total_bytes = ctx.disk["total"]
    ctx.node.disk_used_bytes = ctx.disk["used"]
    ctx.node.disk_free_bytes = ctx.disk["free"]
    if ctx.bundle:
        ctx.node.software_version = ctx.bundle.version[:64]
    ctx.db.add(ctx.node)
    ctx.db.commit()


def _authorized_keys_path(ctx: ProvisionContext) -> tuple[str, str]:
    user = ctx.node.ssh_username
    passwd = ctx.run_cmd(["getent", "passwd", user], privileged=False)
    fields = passwd.stdout.strip().split(":")
    if len(fields) < 6 or not fields[5].startswith("/"):
        raise ProvisionStepError("unable to resolve SSH user home", code="home_unresolved")
    home = fields[5]
    return home, f"{home}/.ssh/authorized_keys"


def step_rotate_key(ctx: ProvisionContext) -> None:
    node = ctx.node
    if node.managed_key_ciphertext and node.credential_type == mgmt.CREDENTIAL_MANAGED_KEY:
        ctx.log.info("Managed SSH key already active; bootstrap credential retired earlier")
        return
    private_pem, public_line, fingerprint = generate_ed25519_keypair(f"ifilm-cdn-managed-{node.id[:8]}")
    ctx.log.add_secret(private_pem)
    home, authorized = _authorized_keys_path(ctx)
    user = node.ssh_username
    ctx.run_cmd(["install", "-d", "-m", "0700", "-o", user, "-g", user, f"{home}/.ssh"])
    existing = ctx.run_cmd(["cat", authorized], check=False)
    if public_line.split(" ")[1] not in (existing.stdout or ""):
        ctx.run_cmd(["tee", "-a", authorized], stdin=(public_line + "\n").encode("utf-8"))
    ctx.run_cmd(["chown", f"{user}:{user}", authorized])
    ctx.run_cmd(["chmod", "0600", authorized])
    # Verify key login on a fresh connection BEFORE retiring the bootstrap credential.
    target = SSHTarget(host=node.host, port=int(node.ssh_port), username=user)
    try:
        verify = ctx.transport.connect(
            target,
            SSHCredential(kind="private_key", secret=private_pem),
            expected_fingerprint=node.ssh_host_key_fingerprint,
            connect_timeout=float(ctx.settings.cdn_ssh_connect_timeout_seconds),
        )
    except SSHError as exc:
        raise ProvisionStepError("managed key login verification failed", code="key_login_failed") from exc
    try:
        result = verify.run(["true"], timeout=15)
    finally:
        verify.close()
    if not result.ok:
        raise ProvisionStepError("managed key login verification failed", code="key_login_failed")
    mgmt.store_managed_key(
        node,
        private_key_pem=private_pem,
        public_key_line=public_line,
        fingerprint=fingerprint,
        settings=ctx.settings,
    )
    node.credential_ciphertext = None
    node.credential_type = mgmt.CREDENTIAL_MANAGED_KEY
    ctx.key_rotated = True
    ctx.db.add(node)
    ctx.db.commit()
    ctx.log.info(f"Installed managed ed25519 key {fingerprint}; bootstrap credential retired")


def step_clear_cache(ctx: ProvisionContext) -> None:
    ctx.run_cmd(["systemctl", "stop", REMOTE_SERVICE], check=False)
    ctx.run_cmd(["find", REMOTE_CACHE_DIR, "-mindepth", "1", "-delete"], code="cache_clear_failed")
    ctx.node.cache_used_bytes = 0
    ctx.node.cached_objects = 0
    ctx.node.cached_titles = 0


def step_finalize(ctx: ProvisionContext) -> None:
    node = ctx.node
    node.provision_status = mgmt.PROVISION_READY
    node.provisioned_at = datetime.now(UTC)
    node.health_status = "online"
    node.last_heartbeat_at = datetime.now(UTC)
    node.last_error = None
    node.last_error_at = None
    ctx.db.add(node)
    ctx.db.commit()


STEP_IMPL: dict[str, Callable[[ProvisionContext], None]] = {
    "preflight": step_preflight,
    "packages": step_packages,
    "user_dirs": step_user_dirs,
    "bundle": step_bundle,
    "config": step_config,
    "systemd": step_systemd,
    "firewall": step_firewall,
    "start": step_start,
    "verify": step_verify,
    "collect": step_collect,
    "rotate_key": step_rotate_key,
    "clear_cache": step_clear_cache,
    "finalize": step_finalize,
}


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class ProvisionExecutor:
    """Runs one queued ``CDNProvisionRun`` to completion (success or failure)."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        transport: SSHTransport | None = None,
        bundle_builder: Callable[[Settings], NodeBundle] = build_node_bundle,
        resolver: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport or ParamikoTransport()
        self.bundle_builder = bundle_builder
        self.resolver = resolver
        self._bundle_cache: NodeBundle | None = None

    def _bundle(self) -> NodeBundle:
        if self._bundle_cache is None:
            self._bundle_cache = self.bundle_builder(self.settings)
        return self._bundle_cache

    def execute(self, db: Session, run: CDNProvisionRun, *, worker_id: str = "worker") -> CDNProvisionRun:
        node = db.get(ManagedCDNNode, run.node_id)
        if node is None:
            run.status = mgmt.PROVISION_FAILED
            run.error_code = "node_missing"
            run.finished_at = datetime.now(UTC)
            db.add(run)
            db.commit()
            return run
        steps = list(ACTION_STEPS.get(run.action, ()))
        log = RunLog()
        if run.log_text:
            log.info("Resuming queued run")
        ctx = ProvisionContext(db=db, node=node, run=run, settings=self.settings, transport=self.transport, log=log)
        run.status = mgmt.PROVISION_RUNNING
        run.started_at = run.started_at or datetime.now(UTC)
        run.attempt = int(run.attempt or 0) + 1
        run.claimed_by = worker_id
        node.provision_status = mgmt.PROVISION_RUNNING
        db.add_all([run, node])
        db.commit()

        skip_until = run.resume_from_step if run.resume_from_step in steps else None
        if skip_until:
            log.info(f"Resuming from step '{skip_until}' (earlier steps completed previously)")
        failed_code: str | None = None
        failed_message: str | None = None
        try:
            self._connect(ctx)
            if "bundle" in steps:
                ctx.bundle = self._bundle()
            for step in steps:
                if skip_until and step != skip_until:
                    continue
                skip_until = None
                run.step = step
                db.add(run)
                db.commit()
                log.info(f"== {step}")
                STEP_IMPL[step](ctx)
                run.log_text = log.text()
                db.add(run)
                db.commit()
            run.status = "completed"
            run.error_code = None
            log.info("Run completed successfully")
        except ProvisionStepError as exc:
            failed_code, failed_message = exc.code, str(exc)
        except SSHError as exc:
            failed_code, failed_message = exc.code, str(exc)
        except ProvisioningError as exc:
            failed_code, failed_message = "target_rejected", str(exc)
        except Exception as exc:  # noqa: BLE001 — never leak tracebacks/secrets into the run log
            failed_code, failed_message = "internal_error", type(exc).__name__
            logger.exception("cdn_provision_internal_error run_id=%s", run.id)
        finally:
            if ctx.session is not None:
                ctx.session.close()
        if failed_code:
            run.status = mgmt.PROVISION_FAILED
            run.error_code = failed_code
            log.info(f"FAILED at step '{run.step}': {failed_code} — {failed_message}")
            node.provision_status = mgmt.PROVISION_FAILED
            node.last_error = f"{run.step}: {failed_code}"[:2000]
            node.last_error_at = datetime.now(UTC)
        run.finished_at = datetime.now(UTC)
        run.log_text = log.text()
        db.add_all([run, node])
        db.commit()
        db.refresh(run)
        logger.info(
            "cdn_provision_run run_id=%s node_id=%s action=%s status=%s step=%s code=%s",
            run.id,
            node.id,
            run.action,
            run.status,
            run.step,
            run.error_code,
        )
        return run

    def _connect(self, ctx: ProvisionContext) -> None:
        node = ctx.node
        if not node.ssh_host_key_fingerprint:
            raise ProvisionStepError("SSH host key is not pinned", code="host_key_unpinned", retryable=False)
        validate_target(node.host, resolver=self.resolver or socket.getaddrinfo)
        credential = _credential_for(node, ctx.settings)
        ctx.log.add_secret(credential.secret)
        target = SSHTarget(host=node.host, port=int(node.ssh_port), username=node.ssh_username)
        ctx.log.info(f"Connecting to {node.host}:{node.ssh_port} as {node.ssh_username} ({credential.kind})")
        ctx.session = self.transport.connect(
            target,
            credential,
            expected_fingerprint=node.ssh_host_key_fingerprint,
            connect_timeout=float(ctx.settings.cdn_ssh_connect_timeout_seconds),
        )
        ctx.log.info(f"Connected; host key {ctx.session.host_key_fingerprint} verified")


# ---------------------------------------------------------------------------
# Test SSH (bounded, used by the admin API)
# ---------------------------------------------------------------------------


def probe_ssh_connection(
    node: ManagedCDNNode,
    *,
    settings: Settings | None = None,
    transport: SSHTransport | None = None,
    resolver: Any = None,
) -> dict[str, Any]:
    """Authenticated probe. Returns secret-free facts + observed host key fingerprint."""
    cfg = settings or get_settings()
    transport = transport or ParamikoTransport()
    started = time.monotonic()
    try:
        validate_target(node.host, resolver=resolver or socket.getaddrinfo)
        credential = _credential_for(node, cfg)
    except (ProvisioningError, ProvisionStepError, mgmt.CDNManagementError) as exc:
        return {"ok": False, "code": getattr(exc, "code", "target_rejected"), "detail": str(exc)}
    target = SSHTarget(host=node.host, port=int(node.ssh_port), username=node.ssh_username)
    try:
        session = transport.connect(
            target,
            credential,
            expected_fingerprint=node.ssh_host_key_fingerprint,
            connect_timeout=float(cfg.cdn_ssh_connect_timeout_seconds),
        )
    except SSHError as exc:
        return {
            "ok": False,
            "code": exc.code,
            "detail": {
                "auth_failed": "SSH authentication failed; check the username and credential",
                "host_key_mismatch": "SSH host key changed since it was pinned; re-pin only after verifying the server",
                "timeout": "SSH connection timed out",
            }.get(exc.code, "SSH connection failed"),
        }
    rtt_ms = int((time.monotonic() - started) * 1000)
    facts: dict[str, Any] = {
        "ok": True,
        "code": "ok",
        "detail": "SSH authentication succeeded",
        "host_key_fingerprint": session.host_key_fingerprint,
        "host_key_pinned": bool(node.ssh_host_key_fingerprint),
        "rtt_ms": rtt_ms,
        "credential_kind": credential.kind,
    }
    try:
        os_info = session.run(["cat", "/etc/os-release"], timeout=15)
        os_id, version = _parse_os_release(os_info.stdout)
        facts["os_release"] = f"{os_id} {version}".strip()
        facts["debian13"] = os_id == "debian" and version.split(".")[0] in SUPPORTED_DEBIAN_VERSIONS
        uid = session.run(["id", "-u"], timeout=15).stdout.strip()
        if uid == "0":
            facts["privileged"] = True
        else:
            facts["privileged"] = session.run(["sudo", "-n", "true"], timeout=15).ok
        df = session.run(["df", "-B1", "--output=size,used,avail", "/var/lib"], timeout=15)
        try:
            disk = _parse_df(df.stdout)
            facts["disk_total_bytes"] = disk["total"]
            facts["disk_free_bytes"] = disk["free"]
        except ProvisionStepError:
            pass
    except SSHError as exc:
        facts["ok"] = False
        facts["code"] = exc.code
        facts["detail"] = "SSH connected but command execution failed"
    finally:
        session.close()
    if facts.get("ok") and not facts.get("debian13"):
        facts["detail"] = "Connected, but the server is not Debian 13 (provisioning will refuse it)"
    if facts.get("ok") and facts.get("privileged") is False:
        facts["detail"] = "Connected, but the SSH user cannot use sudo without a password"
    return facts


__all__ = [
    "ACTION_STEPS",
    "NodeBundle",
    "ProvisionContext",
    "ProvisionExecutor",
    "ProvisionStepError",
    "RunLog",
    "build_node_bundle",
    "render_nftables",
    "render_node_env",
    "render_systemd_unit",
    "probe_ssh_connection",
]

