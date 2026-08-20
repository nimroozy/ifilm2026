"""OriginFetcher protocol and safe adapters (simulation + deferred HTTP stub)."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services.branch_cache.data_plane.errors import (
    CODE_ORIGIN,
    CODE_OVERSIZE,
    CODE_SIZE,
    CODE_TIMEOUT,
    DataPlaneError,
)
from app.services.branch_cache.data_plane.keys import content_type_for, normalize_relative_path


@dataclass(frozen=True)
class OriginObject:
    key: str
    data: bytes
    size_bytes: int
    content_type: str
    checksum_sha256: str
    etag: str | None = None


class OriginFetcher(Protocol):
    def fetch(
        self,
        *,
        asset_id: str,
        package_id: str,
        relative_path: str,
    ) -> OriginObject: ...

    def exists(
        self,
        *,
        asset_id: str,
        package_id: str,
        relative_path: str,
    ) -> bool: ...


class LocalDirOriginFetcher:
    """Deterministic local/test origin rooted at a fixed directory.

    Never accepts per-request upstream URLs. Paths are confined under root.
    """

    def __init__(
        self,
        root: Path,
        *,
        max_object_bytes: int = 64 * 1024 * 1024,
        artificial_latency_ms: float = 0.0,
        fail_paths: frozenset[str] | None = None,
        timeout_paths: frozenset[str] | None = None,
        corrupt_checksum_paths: frozenset[str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.max_object_bytes = int(max_object_bytes)
        self.artificial_latency_ms = float(artificial_latency_ms)
        self.fail_paths = fail_paths or frozenset()
        self.timeout_paths = timeout_paths or frozenset()
        self.corrupt_checksum_paths = corrupt_checksum_paths or frozenset()
        if self.root.exists() and not self.root.is_dir():
            raise DataPlaneError("origin root must be a directory", code=CODE_ORIGIN)

    def _resolve(self, *, asset_id: str, package_id: str, relative_path: str) -> Path:
        rel = normalize_relative_path(relative_path)
        # Layout: {root}/{asset_id}/{package_id}/{rel}
        candidate = (self.root / asset_id / package_id / rel).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise DataPlaneError("origin path escapes root", code=CODE_ORIGIN) from exc
        cur = candidate
        while cur != self.root and cur != cur.parent:
            if cur.is_symlink():
                raise DataPlaneError("origin symlink rejected", code=CODE_ORIGIN)
            cur = cur.parent
        return candidate

    def exists(self, *, asset_id: str, package_id: str, relative_path: str) -> bool:
        try:
            path = self._resolve(
                asset_id=asset_id, package_id=package_id, relative_path=relative_path
            )
        except DataPlaneError:
            return False
        return path.is_file() and not path.is_symlink()

    def fetch(self, *, asset_id: str, package_id: str, relative_path: str) -> OriginObject:
        rel = normalize_relative_path(relative_path)
        if rel in self.timeout_paths:
            raise DataPlaneError("origin timeout", code=CODE_TIMEOUT)
        if rel in self.fail_paths:
            raise DataPlaneError("origin unavailable", code=CODE_ORIGIN)
        if self.artificial_latency_ms > 0:
            time.sleep(self.artificial_latency_ms / 1000.0)
        path = self._resolve(asset_id=asset_id, package_id=package_id, relative_path=rel)
        if not path.is_file() or path.is_symlink():
            raise DataPlaneError("origin object missing", code=CODE_ORIGIN)
        size = path.stat().st_size
        if size > self.max_object_bytes:
            raise DataPlaneError("object exceeds size limit", code=CODE_OVERSIZE)
        data = path.read_bytes()
        if len(data) != size:
            raise DataPlaneError("size mismatch reading origin", code=CODE_SIZE)
        digest = hashlib.sha256(data).hexdigest()
        if rel in self.corrupt_checksum_paths:
            # Simulate a fetcher that reports a wrong checksum (caller must reject).
            digest = "0" * 64
        key = f"{asset_id}/{package_id}/{rel}"
        return OriginObject(
            key=key,
            data=data,
            size_bytes=size,
            content_type=content_type_for(rel),
            checksum_sha256=digest,
            etag=f'W/"{digest[:16]}"',
        )


class DeferredHttpOriginFetcher:
    """Scaffold only — never instantiated by default configuration.

    Future mTLS adapter requirements (documented, not activated):
    - fixed allowlisted endpoint from config (no per-request URLs)
    - TLS verification required; redirects forbidden; URL credentials forbidden
    - bounded timeouts and body sizes
    """

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        raise RuntimeError(
            "DeferredHttpOriginFetcher is intentionally uninstantiated in Phase 4; "
            "use LocalDirOriginFetcher for simulation"
        )

    def fetch(self, *, asset_id: str, package_id: str, relative_path: str) -> OriginObject:
        raise RuntimeError("unreachable")

    def exists(self, *, asset_id: str, package_id: str, relative_path: str) -> bool:
        raise RuntimeError("unreachable")
