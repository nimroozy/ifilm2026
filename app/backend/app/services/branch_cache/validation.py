"""Strict validation for branch cache node identifiers and internal endpoints.

Phase 3 never performs operator-supplied network calls. Validation is
syntactic / policy only (anti-SSRF shape checks).
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# node_id: lowercase slug, 3–64 chars
_NODE_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{1,62}[a-z0-9])$|^[a-z0-9]{3}$")
_SITE_ID_RE = re.compile(r"^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])$|^[a-z0-9]$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Hostnames / IPs that must never be used as branch-cache endpoints.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "instance-data",
    }
)

ALLOWED_SCHEMES = frozenset({"https"})
# http allowed only when explicitly opted in for lab/tests (never prod-like).
LAB_HTTP_SCHEMES = frozenset({"http", "https"})


class BranchCacheValidationError(ValueError):
    """Raised when node registry input fails policy checks."""

    def __init__(self, message: str, *, code: str = "invalid") -> None:
        super().__init__(message)
        self.code = code


def validate_node_id(value: str) -> str:
    raw = (value or "").strip()
    if not _NODE_ID_RE.match(raw):
        raise BranchCacheValidationError(
            "node_id must be 3–64 chars of lowercase letters, digits, and internal hyphens",
            code="invalid_node_id",
        )
    return raw


def validate_site_id(value: str) -> str:
    raw = (value or "").strip().lower()
    if not _SITE_ID_RE.match(raw):
        raise BranchCacheValidationError(
            "site_id must be 1–64 chars of lowercase letters, digits, underscore, hyphen",
            code="invalid_site_id",
        )
    return raw


def validate_key_id(value: str) -> str:
    raw = (value or "").strip()
    if not _KEY_ID_RE.match(raw):
        raise BranchCacheValidationError(
            "key_id must be 1–64 chars of letters, digits, ._- only",
            code="invalid_key_id",
        )
    return raw


def _is_blocked_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified:
        return True
    # Cloud metadata / common SSRF targets
    if isinstance(addr, ipaddress.IPv4Address):
        if addr in ipaddress.ip_network("169.254.0.0/16"):
            return True
        if addr in ipaddress.ip_network("0.0.0.0/8"):
            return True
    if isinstance(addr, ipaddress.IPv6Address):
        if addr in ipaddress.ip_network("fe80::/10"):
            return True
        if addr.ipv4_mapped is not None:
            return _is_blocked_ip(addr.ipv4_mapped)
    return False


def validate_base_url(value: str, *, allow_http: bool = False) -> str:
    """Validate a branch-cache base URL without fetching it.

    Rejects credentials, query/fragment, unsupported schemes, loopback,
    link-local, and cloud-metadata style hosts. Private RFC1918 hosts are
    allowed (branch caches typically sit on ISP private networks).
    """
    raw = (value or "").strip()
    if not raw or len(raw) > 512:
        raise BranchCacheValidationError(
            "base_url must be a non-empty URL ≤512 characters",
            code="invalid_base_url",
        )

    parsed = urlparse(raw)
    schemes = LAB_HTTP_SCHEMES if allow_http else ALLOWED_SCHEMES
    if parsed.scheme not in schemes:
        raise BranchCacheValidationError(
            f"base_url scheme must be one of: {', '.join(sorted(schemes))}",
            code="unsupported_scheme",
        )
    if parsed.username is not None or parsed.password is not None:
        raise BranchCacheValidationError(
            "base_url must not contain URL credentials",
            code="credentials_in_url",
        )
    if parsed.query or parsed.fragment:
        raise BranchCacheValidationError(
            "base_url must not contain query strings or fragments",
            code="query_or_fragment",
        )
    if not parsed.hostname:
        raise BranchCacheValidationError(
            "base_url must include a valid hostname",
            code="malformed_host",
        )
    # Reject path tricks that look like open redirects; allow empty or single trailing slash.
    path = parsed.path or ""
    if path not in {"", "/"}:
        # Allow a single path prefix without dots / encoded tricks.
        if ".." in path or "%" in path or "//" in path:
            raise BranchCacheValidationError(
                "base_url path must not contain redirects or encoded tricks",
                code="unsafe_path",
            )
        if not re.match(r"^/[A-Za-z0-9._/-]{0,200}$", path):
            raise BranchCacheValidationError(
                "base_url path contains unsupported characters",
                code="unsafe_path",
            )

    host = parsed.hostname.lower().rstrip(".")
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise BranchCacheValidationError(
            "base_url hostname is not allowed",
            code="blocked_host",
        )

    # Literal IP checks
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None:
        if _is_blocked_ip(addr):
            raise BranchCacheValidationError(
                "base_url must not target loopback, link-local, or metadata addresses",
                code="blocked_ip",
            )
    else:
        # Hostname — block metadata-looking labels
        if "metadata" in host.split("."):
            raise BranchCacheValidationError(
                "base_url hostname is not allowed",
                code="blocked_host",
            )
        if not re.match(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$", host):
            raise BranchCacheValidationError(
                "base_url hostname is malformed",
                code="malformed_host",
            )
    # Reconstruct canonical URL without credentials/query/fragment.
    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"
    path_out = path if path else ""
    return f"{parsed.scheme}://{netloc}{path_out}"
