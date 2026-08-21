"""Bounded prewarm planner/queue — simulation only (no live network)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum

from app.services.branch_cache.data_plane.errors import CODE_CANCELLED, DataPlaneError
from app.services.branch_cache.data_plane.keys import normalize_relative_path


class PrewarmState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class PrewarmItem:
    package_id: str
    relative_path: str
    asset_id: str
    state: PrewarmState = PrewarmState.QUEUED
    enqueued_at: float = field(default_factory=time.time)
    error_code: str | None = None


class PrewarmPlanner:
    """Dedupe + cancellation + per-package/object limits. Simulation only."""

    def __init__(
        self,
        *,
        max_queue: int = 256,
        max_per_package: int = 64,
        max_objects_total: int = 512,
    ) -> None:
        self.max_queue = int(max_queue)
        self.max_per_package = int(max_per_package)
        self.max_objects_total = int(max_objects_total)
        self._lock = threading.Lock()
        self._queue: list[PrewarmItem] = []
        self._by_key: dict[str, PrewarmItem] = {}
        self._cancelled: set[str] = set()

    @staticmethod
    def _key(asset_id: str, package_id: str, relative_path: str) -> str:
        rel = normalize_relative_path(relative_path)
        return f"{asset_id}|{package_id}|{rel}"

    def enqueue(
        self,
        *,
        asset_id: str,
        package_id: str,
        relative_path: str,
    ) -> PrewarmItem | None:
        """Enqueue or return existing item (dedupe). None if rejected by bounds."""
        rel = normalize_relative_path(relative_path)
        key = self._key(asset_id, package_id, rel)
        with self._lock:
            if key in self._by_key:
                existing = self._by_key[key]
                if existing.state in {PrewarmState.QUEUED, PrewarmState.RUNNING}:
                    return existing
            if len(self._queue) >= self.max_queue:
                return None
            if sum(1 for i in self._by_key.values() if i.state != PrewarmState.CANCELLED) >= (
                self.max_objects_total
            ):
                return None
            pkg_count = sum(
                1
                for i in self._by_key.values()
                if i.package_id == package_id
                and i.state in {PrewarmState.QUEUED, PrewarmState.RUNNING, PrewarmState.DONE}
            )
            if pkg_count >= self.max_per_package:
                return None
            item = PrewarmItem(package_id=package_id, relative_path=rel, asset_id=asset_id)
            self._by_key[key] = item
            self._queue.append(item)
            self._cancelled.discard(key)
            return item

    def cancel(self, *, asset_id: str, package_id: str, relative_path: str) -> bool:
        key = self._key(asset_id, package_id, relative_path)
        with self._lock:
            self._cancelled.add(key)
            item = self._by_key.get(key)
            if item and item.state in {PrewarmState.QUEUED, PrewarmState.RUNNING}:
                item.state = PrewarmState.CANCELLED
                return True
            return False

    def is_cancelled(self, *, asset_id: str, package_id: str, relative_path: str) -> bool:
        key = self._key(asset_id, package_id, relative_path)
        with self._lock:
            return key in self._cancelled

    def pop_next(self) -> PrewarmItem | None:
        with self._lock:
            while self._queue:
                item = self._queue.pop(0)
                key = self._key(item.asset_id, item.package_id, item.relative_path)
                if item.state == PrewarmState.CANCELLED or key in self._cancelled:
                    item.state = PrewarmState.CANCELLED
                    continue
                item.state = PrewarmState.RUNNING
                return item
            return None

    def mark_done(self, item: PrewarmItem, *, error_code: str | None = None) -> None:
        with self._lock:
            if item.state == PrewarmState.CANCELLED:
                return
            if error_code == CODE_CANCELLED:
                item.state = PrewarmState.CANCELLED
                item.error_code = error_code
            elif error_code:
                item.state = PrewarmState.FAILED
                item.error_code = error_code
            else:
                item.state = PrewarmState.DONE
                item.error_code = None

    def status(self) -> dict:
        with self._lock:
            counts: dict[str, int] = {}
            for item in self._by_key.values():
                counts[item.state.value] = counts.get(item.state.value, 0) + 1
            return {
                "queued": counts.get(PrewarmState.QUEUED.value, 0),
                "running": counts.get(PrewarmState.RUNNING.value, 0),
                "done": counts.get(PrewarmState.DONE.value, 0),
                "cancelled": counts.get(PrewarmState.CANCELLED.value, 0),
                "failed": counts.get(PrewarmState.FAILED.value, 0),
                "max_queue": self.max_queue,
                "max_per_package": self.max_per_package,
            }


def assert_not_cancelled(planner: PrewarmPlanner, item: PrewarmItem) -> None:
    if planner.is_cancelled(
        asset_id=item.asset_id, package_id=item.package_id, relative_path=item.relative_path
    ):
        raise DataPlaneError("prewarm cancelled", code=CODE_CANCELLED)
