"""Fixed-origin HTTPS allowlisting (SSRF-resistant).

Builds object URLs from a single configured HTTPS base + normalized package
paths. Never accepts caller-controlled scheme/authority.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from app.services.branch_cache.data_plane.errors import CODE_ORIGIN, DataPlaneError
from app.services.branch_cache.data_plane.keys import normalize_relative_path

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "instance-data",
    }
)


@dataclass(frozen=True)
class FixedOriginEndpoint:
    """Immutable allowlisted origin endpoint."""

    scheme: str
    host: str
    port: int
    path_prefix: str  # e.g. "" or "/origin"

    @property
    def base_url(self) -> str:
        netloc = f"{self.host}:{self.port}"
        prefix = self.path_prefix.rstrip("/")
        return urlunparse((self.scheme, netloc, prefix, "", "", ""))


def parse_fixed_origin_url(
    url: str,
    *,
    allow_loopback: bool = False,
) -> FixedOriginEndpoint:
    """Parse and validate a fixed origin base URL."""
    text = (url or "").strip()
    if not text:
        raise DataPlaneError("origin endpoint required", code=CODE_ORIGIN)
    parsed = urlparse(text)
    if parsed.scheme != "https":
        raise DataPlaneError("origin endpoint must be https", code=CODE_ORIGIN)
    if parsed.username or parsed.password:
        raise DataPlaneError("origin endpoint must not contain credentials", code=CODE_ORIGIN)
    if parsed.query or parsed.fragment:
        raise DataPlaneError("origin endpoint must not contain query/fragment", code=CODE_ORIGIN)
    host = (parsed.hostname or "").lower()
    if not host:
        raise DataPlaneError("origin endpoint host required", code=CODE_ORIGIN)
    if ".." in (parsed.path or ""):
        raise DataPlaneError("origin path rejected", code=CODE_ORIGIN)

    port = int(parsed.port or 443)
    if port < 1 or port > 65535:
        raise DataPlaneError("origin port invalid", code=CODE_ORIGIN)

    _assert_host_policy(host, allow_loopback=allow_loopback)
    path_prefix = (parsed.path or "").rstrip("/")
    if path_prefix and not path_prefix.startswith("/"):
        path_prefix = f"/{path_prefix}"
    return FixedOriginEndpoint(scheme="https", host=host, port=port, path_prefix=path_prefix)


def _assert_host_policy(host: str, *, allow_loopback: bool) -> None:
    if host in _BLOCKED_HOSTNAMES and not allow_loopback:
        raise DataPlaneError("origin host not allowed", code=CODE_ORIGIN)
    # Literal IPs
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_unsafe_ip(ip) and not (allow_loopback and ip.is_loopback):
            raise DataPlaneError("origin host not allowed", code=CODE_ORIGIN)
        if allow_loopback and not ip.is_loopback:
            raise DataPlaneError("loopback mode requires loopback address", code=CODE_ORIGIN)
        return
    if host.startswith("169.254."):
        raise DataPlaneError("origin host not allowed", code=CODE_ORIGIN)
    if allow_loopback and host not in {"localhost", "127.0.0.1", "::1"}:
        # Hostnames other than localhost require resolution checks at connect time.
        pass


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or not ip.is_global
    )


def resolve_and_assert_safe(host: str, *, allow_loopback: bool) -> list[str]:
    """Resolve host and reject DNS-rebinding / unexpected private targets."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DataPlaneError("origin host resolution failed", code=CODE_ORIGIN) from exc
    addrs: list[str] = []
    for info in infos:
        sockaddr = info[4]
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if allow_loopback:
            if not ip.is_loopback:
                raise DataPlaneError("origin resolution not loopback", code=CODE_ORIGIN)
        elif _is_unsafe_ip(ip):
            raise DataPlaneError("origin resolution targets unsafe address", code=CODE_ORIGIN)
        addrs.append(str(ip))
    if not addrs:
        raise DataPlaneError("origin host resolution empty", code=CODE_ORIGIN)
    return addrs


def build_object_url(
    endpoint: FixedOriginEndpoint,
    *,
    asset_id: str,
    package_id: str,
    relative_path: str,
) -> str:
    """Build https://host:port/{prefix}/{asset}/{package}/{rel} — path only controllable."""
    rel = normalize_relative_path(relative_path)
    for seg in (asset_id, package_id):
        if not seg or "/" in seg or ".." in seg or "\\" in seg:
            raise DataPlaneError("unsafe object identity", code=CODE_ORIGIN)
    prefix = endpoint.path_prefix.rstrip("/")
    path = f"{prefix}/{asset_id}/{package_id}/{rel}"
    # Collapse accidental double slashes at join boundary only.
    while "//" in path:
        path = path.replace("//", "/")
    if not path.startswith("/"):
        path = f"/{path}"
    netloc = f"{endpoint.host}:{endpoint.port}"
    return urlunparse(("https", netloc, path, "", "", ""))
