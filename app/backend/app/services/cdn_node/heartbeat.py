"""Heartbeat client: node → central every N seconds (token bearer, secret-free logs)."""

from __future__ import annotations

import logging
import os
import shutil
import threading
from collections.abc import Callable
from typing import Any

import httpx

from app.services.branch_cache import metrics
from app.services.branch_cache.data_plane.cache_store import CacheStore
from app.services.branch_cache.service.state import BranchServiceState
from app.services.cdn_node.config import NodeRuntimeConfig

logger = logging.getLogger("app.cdn_node.heartbeat")


def collect_metrics(cfg: NodeRuntimeConfig, cache: CacheStore, *, last_error: str | None = None) -> dict[str, Any]:
    counters = metrics.snapshot()
    try:
        usage = shutil.disk_usage(cfg.cache_root)
        disk = {"disk_total_bytes": usage.total, "disk_used_bytes": usage.used, "disk_free_bytes": usage.free}
    except OSError:
        disk = {}
    status = cache.status()
    payload: dict[str, Any] = {
        **disk,
        "cache_used_bytes": int(status.get("used_bytes") or 0),
        "cached_objects": int(status.get("object_count") or 0),
        "cache_hits": int(counters.get("dp_hit") or 0),
        "cache_misses": int(counters.get("dp_miss") or 0),
        "bandwidth_bytes": int(counters.get("dp_bytes_served") or 0),
        "software_version": cfg.software_version,
        "os_release": _os_release(),
    }
    if last_error:
        payload["last_error"] = last_error[:500]
        payload["degraded"] = True
    return payload


def _os_release() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            data = dict(
                line.strip().split("=", 1) for line in fh if "=" in line and not line.startswith("#")
            )
        return f"{data.get('ID', '').strip(chr(34))} {data.get('VERSION_ID', '').strip(chr(34))}".strip()[:64]
    except OSError:
        return os.uname().sysname[:64]


class HeartbeatClient:
    def __init__(
        self,
        cfg: NodeRuntimeConfig,
        *,
        cache: CacheStore,
        state: BranchServiceState,
        client: Any | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.cache = cache
        self.state = state
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(10.0, connect=cfg.connect_timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        self.last_ok = False
        self._sleep = sleep

    def send_once(self) -> bool:
        url = f"{self.cfg.central_url}/api/cdn/nodes/{self.cfg.node_id}/heartbeat"
        headers = {
            "Authorization": f"Bearer {self.cfg.node_token}",
            "X-Ifilm-Node-Id": self.cfg.node_id,
        }
        try:
            response = self._client.post(url, json=collect_metrics(self.cfg, self.cache, last_error=self.last_error), headers=headers)
        except httpx.HTTPError as exc:
            self.last_ok = False
            logger.warning("event=heartbeat_failed error=%s", type(exc).__name__)
            return False
        if response.status_code != 200:
            self.last_ok = False
            logger.warning("event=heartbeat_rejected status=%s", response.status_code)
            return False
        self.last_ok = True
        self.last_error = None
        try:
            desired = (response.json() or {}).get("desired") or {}
        except ValueError:
            desired = {}
        self.apply_desired(desired)
        return True

    def apply_desired(self, desired: dict[str, Any]) -> None:
        draining = bool(desired.get("draining"))
        if draining and not self.state.draining:
            self.state.start_drain()
            self.cache.draining = True
            logger.info("event=drain_requested")
        elif not draining and self.state.draining and not self.state.shutting_down:
            self.state.draining = False
            self.cache.draining = False
            logger.info("event=drain_cleared")

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.send_once()
            if self._sleep is not None:
                self._sleep(float(self.cfg.heartbeat_seconds))
            else:
                self._stop.wait(float(self.cfg.heartbeat_seconds))

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="ifilm-cdn-heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
