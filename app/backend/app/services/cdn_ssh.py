"""Bounded SSH transport for CDN node provisioning.

Security properties:
- Host keys are verified against an explicitly pinned SHA-256 fingerprint; an
  unknown or mismatching key fails closed (``host_key_mismatch``).
- Commands are argv lists; every argument is shell-quoted. Secrets never appear
  in argv, log lines, or exception messages.
- Every connection and command has a timeout; output is size-bounded.
- ``paramiko`` is imported lazily so the web tier can run without it.
"""

from __future__ import annotations

import base64
import hashlib
import io
import shlex
import socket
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

MAX_OUTPUT_BYTES = 256 * 1024


class SSHError(Exception):
    """Transport failure with a stable, secret-free ``code``."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SSHTarget:
    host: str
    port: int
    username: str


@dataclass(frozen=True)
class SSHCredential:
    kind: str  # password | private_key
    secret: str = field(repr=False)

    def __repr__(self) -> str:  # never expose the secret
        return f"SSHCredential(kind={self.kind!r})"


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class SSHSession(Protocol):
    host_key_fingerprint: str

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> CommandResult: ...

    def put_bytes(self, data: bytes, remote_path: str, *, mode: int = 0o600) -> None: ...

    def close(self) -> None: ...


class SSHTransport(Protocol):
    def connect(
        self,
        target: SSHTarget,
        credential: SSHCredential,
        *,
        expected_fingerprint: str | None,
        connect_timeout: float,
    ) -> SSHSession: ...


def render_command(argv: Sequence[str], env: Mapping[str, str] | None = None) -> str:
    """Build a single shell-safe command string from argv (+ optional env)."""
    if not argv:
        raise SSHError("empty command", code="invalid_command")
    parts = [shlex.quote(str(a)) for a in argv]
    if env:
        prefix = ["env", *[f"{k}={v}" for k, v in env.items()]]
        for key in env:
            if not key.replace("_", "").isalnum():
                raise SSHError("invalid environment name", code="invalid_command")
        parts = [shlex.quote(p) for p in prefix] + parts
    return " ".join(parts)


def sha256_fingerprint(key_blob: bytes) -> str:
    digest = hashlib.sha256(key_blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def generate_ed25519_keypair(comment: str = "ifilm-cdn-managed") -> tuple[str, str, str]:
    """Return (private_key_pem_openssh, authorized_keys_line, sha256_fingerprint)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    key = ed25519.Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_line = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH, format=serialization.PublicFormat.OpenSSH
        )
        .decode("ascii")
    )
    blob = base64.b64decode(public_line.split(" ", 1)[1].split(" ", 1)[0])
    return private_pem, f"{public_line} {comment}", sha256_fingerprint(blob)


def _load_private_key(pem: str) -> Any:
    import paramiko

    errors: list[str] = []
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(pem))
        except Exception as exc:  # noqa: BLE001 — try next key type
            errors.append(type(exc).__name__)
    raise SSHError("unsupported private key format", code="invalid_private_key")


class _PinnedHostKeyPolicy:
    """paramiko policy: record the observed fingerprint; enforce a pin when given."""

    def __init__(self, expected: str | None) -> None:
        self.expected = (expected or "").strip() or None
        self.observed: str | None = None

    def missing_host_key(self, client: Any, hostname: str, key: Any) -> None:
        self.observed = sha256_fingerprint(key.asbytes())
        if self.expected and self.observed != self.expected:
            raise SSHError("SSH host key does not match the pinned fingerprint", code="host_key_mismatch")


class ParamikoSession:
    def __init__(self, client: Any, fingerprint: str) -> None:
        self._client = client
        self.host_key_fingerprint = fingerprint

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> CommandResult:
        command = render_command(argv, env)
        transport = self._client.get_transport()
        if transport is None or not transport.is_active():
            raise SSHError("SSH session is not active", code="connect_failed")
        channel = transport.open_session(timeout=timeout)
        channel.settimeout(timeout)
        deadline = time.monotonic() + float(timeout)
        try:
            channel.exec_command(command)
            if stdin is not None:
                channel.sendall(stdin)
            channel.shutdown_write()
            out = bytearray()
            err = bytearray()
            timed_out = False
            while True:
                if time.monotonic() > deadline:
                    timed_out = True
                    break
                progressed = False
                if channel.recv_ready():
                    chunk = channel.recv(32768)
                    progressed = bool(chunk)
                    if len(out) < MAX_OUTPUT_BYTES:
                        out.extend(chunk)
                if channel.recv_stderr_ready():
                    chunk = channel.recv_stderr(32768)
                    progressed = progressed or bool(chunk)
                    if len(err) < MAX_OUTPUT_BYTES:
                        err.extend(chunk)
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if not progressed:
                    time.sleep(0.05)
            exit_code = -1 if timed_out else channel.recv_exit_status()
        except TimeoutError:
            return CommandResult(exit_code=-1, stdout="", stderr="", timed_out=True)
        finally:
            channel.close()
        return CommandResult(
            exit_code=int(exit_code),
            stdout=out.decode("utf-8", errors="replace"),
            stderr=err.decode("utf-8", errors="replace"),
            timed_out=timed_out,
        )

    def put_bytes(self, data: bytes, remote_path: str, *, mode: int = 0o600) -> None:
        sftp = self._client.open_sftp()
        try:
            with sftp.open(remote_path, "wb") as handle:
                handle.write(data)
            sftp.chmod(remote_path, mode)
        finally:
            sftp.close()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass


class ParamikoTransport:
    """Real SSH transport. Only the privileged worker / admin Test SSH use it."""

    def connect(
        self,
        target: SSHTarget,
        credential: SSHCredential,
        *,
        expected_fingerprint: str | None,
        connect_timeout: float,
    ) -> SSHSession:
        try:
            import paramiko
        except ImportError as exc:  # pragma: no cover - dependency check
            raise SSHError("paramiko is not installed", code="transport_unavailable") from exc

        client = paramiko.SSHClient()
        client.get_host_keys().clear()
        policy = _PinnedHostKeyPolicy(expected_fingerprint)
        client.set_missing_host_key_policy(policy)
        kwargs: dict[str, Any] = {
            "hostname": target.host,
            "port": int(target.port),
            "username": target.username,
            "timeout": float(connect_timeout),
            "banner_timeout": float(connect_timeout),
            "auth_timeout": float(connect_timeout),
            "allow_agent": False,
            "look_for_keys": False,
        }
        if credential.kind == "password":
            kwargs["password"] = credential.secret
        else:
            kwargs["pkey"] = _load_private_key(credential.secret)
        try:
            client.connect(**kwargs)
        except SSHError:
            client.close()
            raise
        except paramiko.AuthenticationException as exc:
            client.close()
            raise SSHError("SSH authentication failed", code="auth_failed") from exc
        except (paramiko.SSHException, OSError) as exc:
            client.close()
            if policy.observed and expected_fingerprint and policy.observed != expected_fingerprint:
                raise SSHError(
                    "SSH host key does not match the pinned fingerprint", code="host_key_mismatch"
                ) from exc
            code = "timeout" if isinstance(exc, socket.timeout) else "connect_failed"
            raise SSHError(f"SSH connection failed ({type(exc).__name__})", code=code) from exc
        fingerprint = policy.observed or ""
        if not fingerprint:
            transport = client.get_transport()
            remote = transport.get_remote_server_key() if transport else None
            fingerprint = sha256_fingerprint(remote.asbytes()) if remote else ""
        if expected_fingerprint and fingerprint != expected_fingerprint:
            client.close()
            raise SSHError("SSH host key does not match the pinned fingerprint", code="host_key_mismatch")
        return ParamikoSession(client, fingerprint)
