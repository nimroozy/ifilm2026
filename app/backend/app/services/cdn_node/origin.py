"""Central HTTP origin fetcher for CDN nodes (node token bearer auth)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from app.services.branch_cache.data_plane.errors import (
    CODE_CHECKSUM,
    CODE_ORIGIN,
    CODE_OVERSIZE,
    CODE_TIMEOUT,
    DataPlaneError,
)
from app.services.branch_cache.data_plane.keys import content_type_for, normalize_relative_path
from app.services.branch_cache.data_plane.origin import OriginObject

logger = logging.getLogger("app.cdn_node.origin")


class CentralHttpOriginFetcher:
    """Pulls package objects from ``{central}/api/cdn/origin/...`` over HTTPS.

    - Fixed base URL from config (never per-request).
    - Redirects are not followed; proxies from the environment are ignored.
    - Body size is bounded; the ``X-Ifilm-Sha256`` header must match the bytes.
    - The node token is sent only as an Authorization header and never logged.
    """

    def __init__(
        self,
        *,
        central_url: str,
        node_id: str,
        node_token: str,
        max_object_bytes: int = 64 * 1024 * 1024,
        connect_timeout_seconds: float = 3.0,
        read_timeout_seconds: float = 20.0,
        client: Any | None = None,
    ) -> None:
        self.base = central_url.rstrip("/")
        self.node_id = node_id
        self._token = node_token
        self.max_object_bytes = int(max_object_bytes)
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(read_timeout_seconds, connect=connect_timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            verify=True,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-Ifilm-Node-Id": self.node_id,
            "Accept": "*/*",
        }

    def _url(self, asset_id: str, package_id: str, rel: str) -> str:
        return f"{self.base}/api/cdn/origin/{asset_id}/{package_id}/{rel}"

    def exists(self, *, asset_id: str, package_id: str, relative_path: str) -> bool:
        rel = normalize_relative_path(relative_path)
        try:
            response = self._client.head(self._url(asset_id, package_id, rel), headers=self._headers())
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def fetch(self, *, asset_id: str, package_id: str, relative_path: str) -> OriginObject:
        rel = normalize_relative_path(relative_path)
        ref = hashlib.sha256(f"{asset_id}/{package_id}/{rel}".encode()).hexdigest()[:16]
        try:
            response = self._client.get(self._url(asset_id, package_id, rel), headers=self._headers())
        except httpx.TimeoutException as exc:
            logger.info("event=origin_timeout object_ref=%s", ref)
            raise DataPlaneError("origin timeout", code=CODE_TIMEOUT) from exc
        except httpx.HTTPError as exc:
            logger.info("event=origin_error object_ref=%s error=%s", ref, type(exc).__name__)
            raise DataPlaneError("origin unavailable", code=CODE_ORIGIN) from exc
        if response.status_code != 200:
            logger.info("event=origin_status object_ref=%s status=%s", ref, response.status_code)
            raise DataPlaneError("origin object unavailable", code=CODE_ORIGIN)
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_object_bytes:
            raise DataPlaneError("object exceeds size limit", code=CODE_OVERSIZE)
        data = response.content
        if len(data) > self.max_object_bytes:
            raise DataPlaneError("object exceeds size limit", code=CODE_OVERSIZE)
        digest = hashlib.sha256(data).hexdigest()
        expected = (response.headers.get("x-ifilm-sha256") or "").strip().lower()
        if expected and expected != digest:
            logger.info("event=origin_checksum_mismatch object_ref=%s", ref)
            raise DataPlaneError("origin checksum mismatch", code=CODE_CHECKSUM)
        return OriginObject(
            key=f"{asset_id}/{package_id}/{rel}",
            data=data,
            size_bytes=len(data),
            content_type=response.headers.get("content-type") or content_type_for(rel),
            checksum_sha256=digest,
            etag=f'W/"{digest[:16]}"',
        )
