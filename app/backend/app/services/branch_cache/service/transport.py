"""Fixed-origin transport interfaces (lab / injected only)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from app.services.branch_cache.data_plane.errors import CODE_ORIGIN, DataPlaneError
from app.services.branch_cache.data_plane.mtls_origin import MtLsHttpsOriginFetcher
from app.services.branch_cache.data_plane.origin import (
    LocalDirOriginFetcher,
    OriginFetcher,
    OriginObject,
)

__all__ = [
    "DeferredHttpsOriginTransport",
    "FixedOriginTransport",
    "InjectedLocalOriginTransport",
    "MtLsHttpsOriginFetcher",
]


class FixedOriginTransport(Protocol):
    """Fetch by asset/package/relative path only — never per-request URLs."""

    def fetch(self, *, asset_id: str, package_id: str, relative_path: str) -> OriginObject: ...

    def exists(self, *, asset_id: str, package_id: str, relative_path: str) -> bool: ...


class InjectedLocalOriginTransport:
    """Wraps LocalDirOriginFetcher for in-process tests (no sockets)."""

    def __init__(self, root: Path, **kwargs) -> None:  # noqa: ANN003
        self._inner = LocalDirOriginFetcher(root, **kwargs)

    def fetch(self, *, asset_id: str, package_id: str, relative_path: str) -> OriginObject:
        return self._inner.fetch(
            asset_id=asset_id, package_id=package_id, relative_path=relative_path
        )

    def exists(self, *, asset_id: str, package_id: str, relative_path: str) -> bool:
        return self._inner.exists(
            asset_id=asset_id, package_id=package_id, relative_path=relative_path
        )

    def as_fetcher(self) -> OriginFetcher:
        return self._inner


class DeferredHttpsOriginTransport:
    """Future mTLS HTTPS adapter scaffold — not for live use in Phase 6.

    Constructible only with a fixed endpoint + explicit lab flag. Still does not
    open sockets in this phase (raises unless a test double is injected).
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        enable_lab_https_adapter: bool,
        client_cert_path: str = "",
        client_key_path: str = "",
        ca_bundle_path: str = "",
        connect_timeout_seconds: float = 2.0,
        read_timeout_seconds: float = 10.0,
        total_timeout_seconds: float = 15.0,
        max_body_bytes: int = 64 * 1024 * 1024,
        injected_transport: FixedOriginTransport | None = None,
        allow_loopback_for_tests: bool = False,
    ) -> None:
        if not enable_lab_https_adapter:
            raise RuntimeError(
                "DeferredHttpsOriginTransport requires enable_lab_https_adapter=true"
            )
        self._validate_fixed_endpoint(endpoint_url, allow_loopback=allow_loopback_for_tests)
        if not ca_bundle_path and injected_transport is None:
            raise RuntimeError("ca_bundle_path required unless injected_transport is provided")
        if injected_transport is None and (not client_cert_path or not client_key_path):
            raise RuntimeError("client cert/key paths required for future mTLS adapter")
        # Forbid env proxy trust explicitly (documented; not reading proxies).
        self.endpoint_url = endpoint_url.rstrip("/")
        self.connect_timeout_seconds = float(connect_timeout_seconds)
        self.read_timeout_seconds = float(read_timeout_seconds)
        self.total_timeout_seconds = float(total_timeout_seconds)
        self.max_body_bytes = int(max_body_bytes)
        self._injected = injected_transport
        if self._injected is None:
            raise RuntimeError(
                "Phase 6 keeps real HTTPS sockets disabled; provide injected_transport "
                "for lab tests or defer live mTLS to a later phase"
            )

    @staticmethod
    def _validate_fixed_endpoint(url: str, *, allow_loopback: bool) -> None:
        parsed = urlparse((url or "").strip())
        if parsed.scheme != "https":
            raise DataPlaneError("origin endpoint must be https", code=CODE_ORIGIN)
        if parsed.username or parsed.password:
            raise DataPlaneError("origin endpoint must not contain credentials", code=CODE_ORIGIN)
        if parsed.query or parsed.fragment:
            raise DataPlaneError(
                "origin endpoint must not contain query/fragment", code=CODE_ORIGIN
            )
        host = (parsed.hostname or "").lower()
        if not host:
            raise DataPlaneError("origin endpoint host required", code=CODE_ORIGIN)
        if host in {"localhost", "metadata.google.internal", "metadata"}:
            if not allow_loopback:
                raise DataPlaneError("origin host not allowed", code=CODE_ORIGIN)
        # Block obvious link-local / metadata
        if host.startswith("169.254.") or host == "127.0.0.1" or host == "::1":
            if not allow_loopback:
                raise DataPlaneError("origin host not allowed", code=CODE_ORIGIN)

    def fetch(self, *, asset_id: str, package_id: str, relative_path: str) -> OriginObject:
        assert self._injected is not None
        return self._injected.fetch(
            asset_id=asset_id, package_id=package_id, relative_path=relative_path
        )

    def exists(self, *, asset_id: str, package_id: str, relative_path: str) -> bool:
        assert self._injected is not None
        return self._injected.exists(
            asset_id=asset_id, package_id=package_id, relative_path=relative_path
        )
