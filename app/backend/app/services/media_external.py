"""Validate external HTTPS media URLs (MP4 / HLS) with SSRF protections."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

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
SAFE_USER_AGENT = "iFilm-ExternalMediaValidator/1.0"
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 10.0
MAX_REDIRECTS = 0
MAX_PLAYLIST_BYTES = 256 * 1024
MAX_PROBE_BYTES = 64 * 1024
_URI_ATTR_RE = re.compile(r'URI="([^"]+)"')


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


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Reject private, loopback, link-local, multicast, reserved, and non-global space (incl. CGNAT)."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    # Shared / CGNAT / documentation / other non-global space
    if not ip.is_global:
        return True
    return False


def assert_safe_external_url(url: str) -> tuple[str, str]:
    """Return (normalized_url, host). Raise ExternalMediaError on SSRF/unsafe input."""
    text = (url or "").strip()
    if not text:
        raise ExternalMediaError("empty_url", "External media URL is required")
    parsed = urlparse(text)
    if parsed.username or parsed.password:
        raise ExternalMediaError("credentials_rejected", "URLs with embedded credentials are not allowed")
    scheme = (parsed.scheme or "").lower()
    if scheme in {"file", "ftp", "http", "data", "javascript"}:
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
    except ValueError:
        ip = None
    if ip is not None:
        if _is_blocked_ip(ip):
            raise ExternalMediaError("private_ip", "Private or loopback addresses are not allowed")
    else:
        # Hostname — resolve and reject blocked answers
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ExternalMediaError("dns_failed", "Could not resolve external media host") from exc
        if not infos:
            raise ExternalMediaError("dns_failed", "Could not resolve external media host")
        for info in infos:
            sockaddr = info[4]
            try:
                resolved = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if _is_blocked_ip(resolved):
                raise ExternalMediaError("private_ip", "Host resolves to a private address")

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


def _playlist_referenced_urls(playlist_text: str, base_url: str) -> list[str]:
    refs: list[str] = []
    for match in _URI_ATTR_RE.finditer(playlist_text):
        refs.append(urljoin(base_url, match.group(1).strip()))
    for line in playlist_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        refs.append(urljoin(base_url, stripped))
    return refs


def _assert_playlist_hosts_safe(playlist_text: str, base_url: str) -> None:
    """Ensure referenced playlist/segment hosts follow the same SSRF policy (no fetch)."""
    for ref in _playlist_referenced_urls(playlist_text, base_url):
        parsed = urlparse(ref)
        if not parsed.scheme:
            continue
        # Relative resolved to absolute via urljoin; validate absolute https refs only.
        assert_safe_external_url(ref)


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(CONNECT_TIMEOUT + READ_TIMEOUT, connect=CONNECT_TIMEOUT, read=READ_TIMEOUT)


def validate_external_media_url(url: str, *, timeout: float | None = None) -> ExternalMediaValidation:
    """Validate URL safety then HEAD/GET-check Content-Type / Length / Range / playlist."""
    normalized, _host = assert_safe_external_url(url)
    headers = {"User-Agent": SAFE_USER_AGENT, "Accept": "*/*"}
    connect_read = timeout if timeout is not None else None
    client_timeout = (
        httpx.Timeout(float(connect_read), connect=min(CONNECT_TIMEOUT, float(connect_read)), read=float(connect_read))
        if connect_read is not None
        else _timeout()
    )

    content_type: str | None = None
    content_length: int | None = None
    accept_ranges = False
    kind: str

    try:
        with httpx.Client(
            timeout=client_timeout,
            follow_redirects=False,
            max_redirects=MAX_REDIRECTS,
            headers=headers,
            verify=True,
        ) as client:
            response = client.head(normalized)
            # Some CDNs reject HEAD — fall back to bounded ranged GET
            if response.status_code in {405, 501}:
                response = client.get(
                    normalized,
                    headers={**headers, "Range": f"bytes=0-{MAX_PROBE_BYTES - 1}"},
                )
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
            if content_type:
                base = content_type.split(";")[0].strip().lower()
                if base not in PLAYABLE_CONTENT_TYPES and kind not in {"hls", "mp4"}:
                    raise ExternalMediaError("unsupported_type", f"Unsupported Content-Type: {base}")

            if kind == "hls":
                playlist = client.get(
                    normalized,
                    headers={**headers, "Range": f"bytes=0-{MAX_PLAYLIST_BYTES - 1}"},
                )
                if playlist.is_redirect:
                    raise ExternalMediaError("redirect_rejected", "External media redirects are not allowed")
                if playlist.status_code >= 400:
                    raise ExternalMediaError(
                        "unreachable",
                        f"External media playlist fetch failed with HTTP {playlist.status_code}",
                    )
                raw = playlist.content[:MAX_PLAYLIST_BYTES]
                try:
                    text = raw.decode("utf-8", errors="replace")
                except Exception as exc:  # pragma: no cover
                    raise ExternalMediaError("invalid_playlist", "Playlist is not valid text") from exc
                if not text.lstrip().startswith("#EXTM3U"):
                    raise ExternalMediaError("invalid_playlist", "HLS playlist must start with #EXTM3U")
                _assert_playlist_hosts_safe(text, normalized)
    except ExternalMediaError:
        raise
    except httpx.TimeoutException as exc:
        raise ExternalMediaError("timeout", "External media request timed out") from exc
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
