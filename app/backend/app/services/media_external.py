"""Validate external HTTPS media URLs (MP4 / HLS) with SSRF protections."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

ALLOWED_SCHEMES = {"https"}
BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "169.254.169.254",
}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal")
PLAYABLE_CONTENT_TYPES = (
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "video/mp4",
    "application/mp4",
    "video/mpeg",
    "application/octet-stream",
)


class ExternalMediaError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ExternalMediaValidation:
    url: str
    kind: str  # hls | mp4
    content_type: str | None
    content_length: int | None
    accept_ranges: bool
    validated_at: datetime


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_safe_external_url(url: str) -> tuple[str, str]:
    """Return (normalized_url, host). Raise ExternalMediaError on SSRF/unsafe input."""
    text = (url or "").strip()
    if not text:
        raise ExternalMediaError("empty_url", "External media URL is required")
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"file", "ftp", "http"}:
        raise ExternalMediaError("scheme_rejected", "Only https:// URLs are allowed")
    if scheme not in ALLOWED_SCHEMES:
        raise ExternalMediaError("scheme_rejected", "Only https:// URLs are allowed")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ExternalMediaError("invalid_host", "External media URL host is invalid")
    if host in BLOCKED_HOSTS or any(host.endswith(suf) for suf in BLOCKED_SUFFIXES):
        raise ExternalMediaError("host_blocked", "External media host is not allowed")
    if host == "metadata.google.internal" or host.endswith(".metadata.google.internal"):
        raise ExternalMediaError("host_blocked", "Metadata endpoints are not allowed")

    # Literal IP host
    try:
        ip = ipaddress.ip_address(host)
        if _is_private_ip(ip):
            raise ExternalMediaError("private_ip", "Private or loopback addresses are not allowed")
    except ValueError:
        # Hostname — resolve and reject private answers
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ExternalMediaError("dns_failed", "Could not resolve external media host") from exc
        if not infos:
            raise ExternalMediaError("dns_failed", "Could not resolve external media host")
        for info in infos:
            sockaddr = info[4]
            try:
                ip = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if _is_private_ip(ip):
                raise ExternalMediaError("private_ip", "Host resolves to a private address")

    if parsed.username or parsed.password:
        raise ExternalMediaError("credentials_rejected", "URLs with embedded credentials are not allowed")

    # Normalize without fragment
    normalized = parsed._replace(fragment="").geturl()
    return normalized, host


def _guess_kind(url: str, content_type: str | None) -> str:
    path = urlparse(url).path.lower()
    ct = (content_type or "").split(";")[0].strip().lower()
    if path.endswith(".m3u8") or "mpegurl" in ct:
        return "hls"
    if path.endswith(".mp4") or ct in {"video/mp4", "application/mp4"}:
        return "mp4"
    if ct in PLAYABLE_CONTENT_TYPES:
        return "hls" if "mpegurl" in ct else "mp4"
    raise ExternalMediaError(
        "unsupported_type",
        "External media must be HTTPS MP4 or HLS (.m3u8)",
    )


def validate_external_media_url(url: str, *, timeout: float = 10.0) -> ExternalMediaValidation:
    """Validate URL safety then HEAD-check Content-Type / Length / Range."""
    normalized, _host = assert_safe_external_url(url)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.head(normalized)
            # Some CDNs reject HEAD — fall back to ranged GET
            if response.status_code in {405, 501}:
                response = client.get(normalized, headers={"Range": "bytes=0-0"})
            # Disallow redirects to keep SSRF checks on the final host simple
            if response.is_redirect:
                raise ExternalMediaError("redirect_rejected", "External media redirects are not allowed")
            if response.status_code >= 400:
                raise ExternalMediaError(
                    "unreachable",
                    f"External media HEAD/GET failed with HTTP {response.status_code}",
                )
            content_type = response.headers.get("content-type")
            length_raw = response.headers.get("content-length")
            content_length = int(length_raw) if length_raw and length_raw.isdigit() else None
            accept_ranges = "bytes" in (response.headers.get("accept-ranges") or "").lower()
            kind = _guess_kind(normalized, content_type)
            # Soft content-type gate: allow octet-stream when path implies kind
            if content_type:
                base = content_type.split(";")[0].strip().lower()
                if base not in PLAYABLE_CONTENT_TYPES and kind not in {"hls", "mp4"}:
                    raise ExternalMediaError("unsupported_type", f"Unsupported Content-Type: {base}")
    except ExternalMediaError:
        raise
    except httpx.HTTPError as exc:
        raise ExternalMediaError("unreachable", "External media URL is unreachable") from exc

    return ExternalMediaValidation(
        url=normalized,
        kind=kind,
        content_type=(content_type.split(";")[0].strip() if content_type else None),
        content_length=content_length,
        accept_ranges=accept_ranges,
        validated_at=datetime.now(UTC),
    )
