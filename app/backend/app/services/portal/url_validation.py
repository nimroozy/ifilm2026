"""SSRF-safe validation for administrator-configured Portal base URLs."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from app.core.runtime import is_prod_like


class PortalUrlValidationError(ValueError):
    pass


def _host_is_blocked(host: str) -> bool:
    host_norm = (host or "").strip().lower().rstrip(".")
    if not host_norm:
        return True
    if host_norm in {"localhost", "localhost.localdomain"}:
        return True
    if host_norm.endswith(".localhost"):
        return True

    try:
        addr = ipaddress.ip_address(host_norm)
    except ValueError:
        # Not a literal IP — hostname; allow public DNS names only in prod-like.
        return False

    return bool(
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_portal_base_url(url: str, *, app_env: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise PortalUrlValidationError("Portal base URL is required")

    parsed = urlparse(raw)
    if parsed.username or parsed.password:
        raise PortalUrlValidationError("Embedded credentials in Portal base URL are not allowed")

    scheme = (parsed.scheme or "").lower()
    if is_prod_like(app_env):
        if scheme != "https":
            raise PortalUrlValidationError("Portal base URL must use HTTPS in production-like environments")
    elif scheme not in {"https", "http"}:
        raise PortalUrlValidationError("Portal base URL must use HTTP or HTTPS")

    if not parsed.netloc:
        raise PortalUrlValidationError("Portal base URL is malformed")

    host = parsed.hostname or ""
    if _host_is_blocked(host):
        raise PortalUrlValidationError("Portal base URL must not target localhost or private networks")

    # Normalize: scheme + netloc only (no path/query/fragment).
    port = parsed.port
    if port and ((scheme == "https" and port != 443) or (scheme == "http" and port != 80)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    return f"{scheme}://{netloc}".rstrip("/")


def validate_api_prefix(prefix: str) -> str:
    raw = (prefix or "").strip()
    if not raw.startswith("/"):
        raise PortalUrlValidationError("API prefix must start with /")
    if "://" in raw:
        raise PortalUrlValidationError("API prefix must be a relative path")
    return raw.rstrip("/") or "/"
