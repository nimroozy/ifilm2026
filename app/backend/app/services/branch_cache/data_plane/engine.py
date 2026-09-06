"""Branch data-plane engine: grant verify → cache read / origin fill (simulation)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.services.branch_cache import metrics
from app.services.branch_cache.data_plane.cache_store import CacheStore
from app.services.branch_cache.data_plane.errors import (
    CODE_AUTH,
    CODE_DISABLED,
    CODE_ORIGIN,
    CODE_RANGE,
    DECISION_AUTH_DENIED,
    DECISION_BAD_RANGE,
    DECISION_DISABLED,
    DECISION_DRAINING,
    DECISION_FALLBACK_CENTRAL,
    DECISION_HIT,
    DECISION_MISS_FILL,
    DataPlaneError,
)
from app.services.branch_cache.data_plane.keys import (
    content_type_for,
    grant_path_for_relative,
    normalize_relative_path,
)
from app.services.branch_cache.data_plane.origin import LocalDirOriginFetcher, OriginFetcher
from app.services.branch_cache.data_plane.prewarm import PrewarmPlanner, assert_not_cancelled
from app.services.branch_cache.data_plane.singleflight import SingleFlight
from app.services.branch_cache.grants import EdgeGrantError, verify_edge_grant
from app.services.streaming.range import RangeError, parse_byte_range


@dataclass(frozen=True)
class DataPlaneDecision:
    decision: str
    reason: str
    fallback_to_central: bool
    coalesced: bool = False
    from_cache: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "fallback_to_central": self.fallback_to_central,
            "coalesced": self.coalesced,
            "from_cache": self.from_cache,
            "client_redirect": False,
        }


@dataclass(frozen=True)
class DataPlaneResponse:
    status_code: int
    body: bytes
    content_type: str
    etag: str | None
    content_length: int
    content_range: str | None
    accept_ranges: str
    cache_control: str
    decision: DataPlaneDecision
    headers: dict[str, str]

    def as_public_dict(self) -> dict[str, Any]:
        """Secret-free summary (no body, no token, no paths)."""
        return {
            "status_code": self.status_code,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "etag_present": bool(self.etag),
            "ranged": self.content_range is not None,
            "decision": self.decision.as_dict(),
        }


class BranchDataPlaneEngine:
    """Offline/sim branch cache data-plane core.

    Authorization (public-key edge grant) runs before any cache or origin I/O.
    """

    def __init__(
        self,
        *,
        node_id: str,
        site_id: str,
        cache: CacheStore,
        origin: OriginFetcher,
        public_key_pem: str,
        settings: Settings | None = None,
        max_concurrent_fills: int = 4,
        prewarm: PrewarmPlanner | None = None,
    ) -> None:
        self.node_id = node_id
        self.site_id = site_id
        self.cache = cache
        self.origin = origin
        self.public_key_pem = public_key_pem
        self.settings = settings or get_settings()
        self._flight = SingleFlight()
        self._fill_sem = threading.Semaphore(int(max_concurrent_fills))
        self.prewarm = prewarm or PrewarmPlanner()

    def enabled(self) -> bool:
        cfg = self.settings
        return bool(
            cfg.enable_branch_cache_data_plane_sim
            and (cfg.enable_branch_cache_local_serve or cfg.enable_branch_cache_pull_through)
        )

    def _verify_grant(
        self,
        token: str,
        *,
        package_id: str,
        session_id: str,
        relative_path: str,
        path_prefix: str,
        now: datetime | None = None,
        enforce_replay: bool = True,
    ) -> None:
        grant_path = grant_path_for_relative(path_prefix, relative_path)
        try:
            claims = verify_edge_grant(
                token,
                expected_node_id=self.node_id,
                expected_package_id=package_id,
                expected_path=grant_path,
                settings=self.settings,
                public_key_pem=self.public_key_pem,
                enforce_replay=enforce_replay,
                now=now,
            )
        except EdgeGrantError as exc:
            metrics.incr("dp_auth_fail")
            metrics.incr("edge_grants_verified_fail")
            raise DataPlaneError("authorization failed", code=CODE_AUTH) from exc
        if claims.session_id != session_id:
            metrics.incr("dp_auth_fail")
            raise DataPlaneError("session binding mismatch", code=CODE_AUTH)
        if claims.site_id and claims.site_id != self.site_id:
            metrics.incr("dp_auth_fail")
            raise DataPlaneError("site binding mismatch", code=CODE_AUTH)
        metrics.incr("edge_grants_verified_ok")

    def _fill(
        self,
        *,
        asset_id: str,
        package_id: str,
        relative_path: str,
        cancel_check: Callable[[], None] | None = None,
    ) -> tuple[bool, str, bool]:
        """Fill from origin into cache. Returns (ok, reason_code, coalesced)."""
        if self.cache.draining:
            return False, DECISION_DRAINING, False
        if not self.settings.enable_branch_cache_pull_through:
            return False, DECISION_FALLBACK_CENTRAL, False

        def _do() -> None:
            if cancel_check:
                cancel_check()
            if not self._fill_sem.acquire(timeout=30):
                raise DataPlaneError("fill concurrency limit", code=CODE_ORIGIN)
            try:
                if cancel_check:
                    cancel_check()
                obj = self.origin.fetch(
                    asset_id=asset_id, package_id=package_id, relative_path=relative_path
                )
                self.cache.put_atomic(
                    relative_path,
                    obj.data,
                    content_type=obj.content_type,
                    checksum_sha256=obj.checksum_sha256,
                    origin_key=obj.key,
                    etag=obj.etag,
                    expected_size=obj.size_bytes,
                )
                metrics.incr("dp_fill_ok")
                metrics.incr("dp_bytes_origin", obj.size_bytes)
            finally:
                self._fill_sem.release()

        try:
            _, coalesced = self._flight.do(f"{package_id}:{relative_path}", _do)
            if coalesced:
                metrics.incr("dp_coalesced")
            return True, DECISION_MISS_FILL, coalesced
        except DataPlaneError:
            metrics.incr("dp_fill_fail")
            return False, DECISION_FALLBACK_CENTRAL, False
        except Exception:
            metrics.incr("dp_fill_fail")
            return False, DECISION_FALLBACK_CENTRAL, False

    def serve(
        self,
        *,
        grant_token: str,
        asset_id: str,
        package_id: str,
        session_id: str,
        relative_path: str,
        path_prefix: str,
        range_header: str | None = None,
        now: datetime | None = None,
        enforce_replay: bool = True,
    ) -> DataPlaneResponse:
        """Serve an object after grant verification. Never redirects clients."""
        if not self.settings.enable_branch_cache_data_plane_sim:
            metrics.incr("dp_fallback")
            return self._fallback_response(DECISION_DISABLED, CODE_DISABLED)

        try:
            rel = normalize_relative_path(relative_path)
        except DataPlaneError as exc:
            metrics.incr("dp_auth_fail")
            return self._error_response(403, DECISION_AUTH_DENIED, exc.code)

        # Auth BEFORE any cache/origin I/O
        try:
            self._verify_grant(
                grant_token,
                package_id=package_id,
                session_id=session_id,
                relative_path=rel,
                path_prefix=path_prefix,
                now=now,
                enforce_replay=enforce_replay,
            )
        except DataPlaneError as exc:
            return self._error_response(403, DECISION_AUTH_DENIED, exc.code)

        if not self.settings.enable_branch_cache_local_serve:
            return self._fallback_response(DECISION_FALLBACK_CENTRAL, "local_serve_off")

        if self.cache.draining and not self.cache.has(rel):
            metrics.incr("dp_fallback")
            return self._fallback_response(DECISION_DRAINING, "draining")

        coalesced = False
        from_cache = self.cache.has(rel)
        if not from_cache:
            metrics.incr("dp_miss")
            ok, reason, coalesced = self._fill(
                asset_id=asset_id, package_id=package_id, relative_path=rel
            )
            if not ok:
                metrics.incr("dp_fallback")
                return self._fallback_response(reason, reason)
            if not self.cache.has(rel):
                # Filled object was evicted immediately (capacity pressure): fall back.
                metrics.incr("dp_fallback")
                return self._fallback_response(DECISION_FALLBACK_CENTRAL, "evicted_after_fill")
            decision_code = DECISION_MISS_FILL
        else:
            metrics.incr("dp_hit")
            decision_code = DECISION_HIT

        try:

            def _size() -> int:
                with self.cache._lock:  # noqa: SLF001
                    entry = self.cache._index[rel]  # noqa: SLF001
                    return entry.size_bytes

            file_size = _size()
            try:
                br = parse_byte_range(range_header, file_size=file_size)
            except RangeError:
                metrics.incr("dp_fallback")
                return self._error_response(416, DECISION_BAD_RANGE, CODE_RANGE)

            if br is None:
                data, entry = self.cache.read_bytes(rel)
                status_code = 200
                content_range = None
            else:
                data, entry = self.cache.read_bytes(rel, start=br.start, end=br.end)
                status_code = 206
                content_range = f"bytes {br.start}-{br.end}/{entry.size_bytes}"

            metrics.incr("dp_bytes_served", len(data))
            ctype = entry.content_type or content_type_for(rel)
            is_playlist = rel.lower().endswith(".m3u8")
            cache_control = (
                "private, no-store, no-cache, must-revalidate"
                if is_playlist
                else "private, max-age=60"
            )
            headers = {
                "Content-Type": ctype,
                "Accept-Ranges": "bytes",
                "Cache-Control": cache_control,
                "X-Content-Type-Options": "nosniff",
                "X-Ifilm-Data-Plane": "sim",
                "X-Ifilm-Decision": decision_code,
            }
            if entry.etag:
                headers["ETag"] = entry.etag
            if content_range:
                headers["Content-Range"] = content_range
            decision = DataPlaneDecision(
                decision=decision_code,
                reason="ok",
                fallback_to_central=False,
                coalesced=coalesced,
                from_cache=from_cache,
            )
            return DataPlaneResponse(
                status_code=status_code,
                body=data,
                content_type=ctype,
                etag=entry.etag,
                content_length=len(data),
                content_range=content_range,
                accept_ranges="bytes",
                cache_control=cache_control,
                decision=decision,
                headers=headers,
            )
        except DataPlaneError as exc:
            metrics.incr("dp_fallback")
            return self._fallback_response(DECISION_FALLBACK_CENTRAL, exc.code)

    def run_prewarm_once(self) -> dict[str, Any]:
        """Process at most one prewarm item using LocalDirOriginFetcher only."""
        item = self.prewarm.pop_next()
        if item is None:
            return {"processed": False}
        try:
            assert_not_cancelled(self.prewarm, item)
            ok, reason, _coalesced = self._fill(
                asset_id=item.asset_id,
                package_id=item.package_id,
                relative_path=item.relative_path,
                cancel_check=lambda: assert_not_cancelled(self.prewarm, item),
            )
            if ok:
                self.prewarm.mark_done(item)
                metrics.incr("dp_prewarm_ok")
            else:
                self.prewarm.mark_done(item, error_code=reason)
                metrics.incr("dp_prewarm_fail")
            return {"processed": True, "ok": ok, "reason": reason}
        except DataPlaneError as exc:
            self.prewarm.mark_done(item, error_code=exc.code)
            metrics.incr("dp_prewarm_fail")
            return {"processed": True, "ok": False, "reason": exc.code}

    def _fallback_response(self, decision: str, reason: str) -> DataPlaneResponse:
        d = DataPlaneDecision(
            decision=decision,
            reason=reason,
            fallback_to_central=True,
            coalesced=False,
            from_cache=False,
        )
        return DataPlaneResponse(
            status_code=503,
            body=b"",
            content_type="application/octet-stream",
            etag=None,
            content_length=0,
            content_range=None,
            accept_ranges="bytes",
            cache_control="private, no-store",
            decision=d,
            headers={
                "Cache-Control": "private, no-store",
                "X-Ifilm-Data-Plane": "sim",
                "X-Ifilm-Decision": decision,
                "X-Ifilm-Fallback": "central_origin",
            },
        )

    def _error_response(self, status: int, decision: str, reason: str) -> DataPlaneResponse:
        d = DataPlaneDecision(
            decision=decision,
            reason=reason,
            fallback_to_central=decision != DECISION_AUTH_DENIED,
            coalesced=False,
            from_cache=False,
        )
        return DataPlaneResponse(
            status_code=status,
            body=b"",
            content_type="application/octet-stream",
            etag=None,
            content_length=0,
            content_range=None,
            accept_ranges="bytes",
            cache_control="private, no-store",
            decision=d,
            headers={
                "Cache-Control": "private, no-store",
                "X-Ifilm-Data-Plane": "sim",
                "X-Ifilm-Decision": decision,
            },
        )


def build_sim_engine(
    *,
    cache_root: Path,
    origin_root: Path,
    node_id: str,
    site_id: str,
    public_key_pem: str,
    settings: Settings,
    high_watermark_bytes: int = 10_000_000,
    low_watermark_bytes: int = 6_000_000,
    min_free_bytes: int = 1_000_000,
    draining: bool = False,
) -> BranchDataPlaneEngine:
    cache = CacheStore(
        cache_root,
        node_id=node_id,
        high_watermark_bytes=high_watermark_bytes,
        low_watermark_bytes=low_watermark_bytes,
        min_free_bytes=min_free_bytes,
        draining=draining,
    )
    origin = LocalDirOriginFetcher(origin_root)
    return BranchDataPlaneEngine(
        node_id=node_id,
        site_id=site_id,
        cache=cache,
        origin=origin,
        public_key_pem=public_key_pem,
        settings=settings,
    )
