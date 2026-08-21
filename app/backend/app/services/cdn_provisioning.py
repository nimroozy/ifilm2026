"""Fail-closed provisioning plan and injectable runner.

Production execution belongs in a privileged, isolated worker. This module
never puts passwords/private keys in argv, logs, or browser responses.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Protocol


class ProvisioningError(ValueError):
    pass


@dataclass(frozen=True)
class ProvisionPlan:
    host: str
    port: int
    username: str
    script_path: str
    cache_limit_bytes: int
    host_key_fingerprint: str
    strict_host_key_checking: bool = True
    rotate_password_to_key: bool = True


class SSHExecutor(Protocol):
    def execute(
        self, plan: ProvisionPlan, *, credential: str, environment: dict[str, str]
    ) -> list[str]: ...


def validate_target(host: str, *, resolver=socket.getaddrinfo) -> list[str]:
    """Reject loopback/link-local/multicast/unspecified targets (SSRF guard)."""
    try:
        addresses = sorted({item[4][0] for item in resolver(host, None)})
    except socket.gaierror as exc:
        raise ProvisioningError("Target hostname cannot be resolved") from exc
    if not addresses:
        raise ProvisioningError("Target hostname has no addresses")
    for raw in addresses:
        address = ipaddress.ip_address(raw.split("%", 1)[0])
        if (
            address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ProvisioningError("Target resolves to a prohibited address")
    return addresses


def build_plan(
    *,
    host: str,
    port: int,
    username: str,
    cache_limit_bytes: int,
    script_path: str,
    host_key_fingerprint: str,
) -> ProvisionPlan:
    if not 1 <= int(port) <= 65535:
        raise ProvisioningError("Invalid SSH port")
    if cache_limit_bytes <= 0:
        raise ProvisioningError("Cache limit must be greater than zero")
    if not username or any(c.isspace() for c in username):
        raise ProvisioningError("Invalid SSH username")
    if not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{20,}={0,2}", host_key_fingerprint or ""):
        raise ProvisioningError("A valid pinned SSH host-key fingerprint is required")
    validate_target(host)
    return ProvisionPlan(
        host=host,
        port=port,
        username=username,
        script_path=script_path,
        cache_limit_bytes=cache_limit_bytes,
        host_key_fingerprint=host_key_fingerprint,
    )


def redact_log(lines: list[str], secrets: list[str]) -> str:
    output = "\n".join(lines)
    for secret in secrets:
        if secret:
            output = output.replace(secret, "[REDACTED]")
    return output[-100_000:]
