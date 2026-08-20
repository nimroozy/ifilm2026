"""Local disk cache store with root confinement, atomic fills, and LRU eviction."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.services.branch_cache.data_plane.errors import (
    CODE_CHECKSUM,
    CODE_OUTSIDE_ROOT,
    CODE_OVERSIZE,
    CODE_POISON,
    CODE_SIZE,
    CODE_SYMLINK,
    DataPlaneError,
)
from app.services.branch_cache.data_plane.keys import content_type_for, normalize_relative_path


@dataclass
class CacheEntryMeta:
    relative_path: str
    size_bytes: int
    content_type: str
    checksum_sha256: str
    etag: str
    filled_at: float
    last_access_at: float
    origin_key: str
    in_use: int = 0
    pinned: bool = False
    complete: bool = True

    def to_dict(self) -> dict:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "checksum_sha256": self.checksum_sha256,
            "etag": self.etag,
            "filled_at": self.filled_at,
            "last_access_at": self.last_access_at,
            "origin_key": self.origin_key,
            "pinned": self.pinned,
            "complete": self.complete,
            # Never store tokens, grants, private keys, or credentials.
        }

    @classmethod
    def from_dict(cls, data: dict) -> CacheEntryMeta:
        return cls(
            relative_path=str(data["relative_path"]),
            size_bytes=int(data["size_bytes"]),
            content_type=str(data["content_type"]),
            checksum_sha256=str(data["checksum_sha256"]),
            etag=str(data["etag"]),
            filled_at=float(data["filled_at"]),
            last_access_at=float(data["last_access_at"]),
            origin_key=str(data["origin_key"]),
            pinned=bool(data.get("pinned", False)),
            complete=bool(data.get("complete", True)),
            in_use=0,
        )


class CacheStore:
    """Dedicated cache-root engine. Never deletes outside configured root."""

    def __init__(
        self,
        root: Path,
        *,
        node_id: str,
        high_watermark_bytes: int,
        low_watermark_bytes: int,
        min_free_bytes: int,
        max_object_bytes: int = 64 * 1024 * 1024,
        draining: bool = False,
    ) -> None:
        self.root = root.resolve()
        self.node_id = node_id
        self.objects_dir = self.root / "objects"
        self.meta_dir = self.root / "meta"
        self.tmp_dir = self.root / "tmp"
        self.high_watermark_bytes = int(high_watermark_bytes)
        self.low_watermark_bytes = int(low_watermark_bytes)
        self.min_free_bytes = int(min_free_bytes)
        self.max_object_bytes = int(max_object_bytes)
        self.draining = bool(draining)
        self._lock = threading.RLock()
        self._index: dict[str, CacheEntryMeta] = {}
        self._ensure_layout()
        self._load_index()

    def _ensure_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for d in (self.objects_dir, self.meta_dir, self.tmp_dir):
            d.mkdir(parents=True, exist_ok=True)
            if d.is_symlink():
                raise DataPlaneError("cache directory must not be a symlink", code=CODE_SYMLINK)

    def _object_path(self, relative_path: str) -> Path:
        rel = normalize_relative_path(relative_path)
        # Flat hash layout avoids deep package trees escaping via odd names.
        digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()
        path = (self.objects_dir / digest[:2] / digest).resolve()
        try:
            path.relative_to(self.objects_dir.resolve())
        except ValueError as exc:
            raise DataPlaneError("object path outside cache root", code=CODE_OUTSIDE_ROOT) from exc
        return path

    def _meta_path(self, relative_path: str) -> Path:
        rel = normalize_relative_path(relative_path)
        digest = hashlib.sha256(rel.encode("utf-8")).hexdigest()
        path = (self.meta_dir / f"{digest}.json").resolve()
        try:
            path.relative_to(self.meta_dir.resolve())
        except ValueError as exc:
            raise DataPlaneError("meta path outside cache root", code=CODE_OUTSIDE_ROOT) from exc
        return path

    def _reject_symlinks(self, path: Path) -> None:
        if path.exists() and path.is_symlink():
            raise DataPlaneError("symlink rejected", code=CODE_SYMLINK)
        # Walk parents under root
        cur = path
        root = self.root.resolve()
        while cur != root and cur != cur.parent:
            if cur.is_symlink():
                raise DataPlaneError("symlink rejected", code=CODE_SYMLINK)
            cur = cur.parent

    def _load_index(self) -> None:
        for meta_file in self.meta_dir.glob("*.json"):
            if meta_file.is_symlink():
                continue
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                entry = CacheEntryMeta.from_dict(data)
                obj = self._object_path(entry.relative_path)
                if obj.is_file() and not obj.is_symlink() and entry.complete:
                    self._index[entry.relative_path] = entry
                else:
                    # Partial / missing — cleanup
                    self._safe_unlink(obj)
                    self._safe_unlink(meta_file)
            except (OSError, json.JSONDecodeError, KeyError, DataPlaneError):
                continue

    def _safe_unlink(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            resolved.relative_to(self.root.resolve())
        except (ValueError, OSError):
            return
        if resolved.is_symlink():
            return
        try:
            if resolved.is_file():
                resolved.unlink()
        except OSError:
            return

    def used_bytes(self) -> int:
        with self._lock:
            return sum(e.size_bytes for e in self._index.values() if e.complete)

    def has(self, relative_path: str) -> bool:
        rel = normalize_relative_path(relative_path)
        with self._lock:
            entry = self._index.get(rel)
            if entry is None or not entry.complete:
                return False
            path = self._object_path(rel)
            return path.is_file() and not path.is_symlink()

    def touch(self, relative_path: str) -> None:
        rel = normalize_relative_path(relative_path)
        with self._lock:
            entry = self._index.get(rel)
            if entry is None:
                return
            entry.last_access_at = time.time()
            self._persist_meta(entry)

    def mark_in_use(self, relative_path: str, delta: int = 1) -> None:
        rel = normalize_relative_path(relative_path)
        with self._lock:
            entry = self._index.get(rel)
            if entry is None:
                return
            entry.in_use = max(0, entry.in_use + delta)

    def pin(self, relative_path: str, pinned: bool = True) -> None:
        rel = normalize_relative_path(relative_path)
        with self._lock:
            entry = self._index.get(rel)
            if entry is None:
                return
            entry.pinned = pinned
            self._persist_meta(entry)

    def _persist_meta(self, entry: CacheEntryMeta) -> None:
        path = self._meta_path(entry.relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.tmp_dir / f"meta-{os.getpid()}-{threading.get_ident()}-{time.time_ns()}.json"
        tmp.write_text(json.dumps(entry.to_dict(), separators=(",", ":")), encoding="utf-8")
        with tmp.open("rb+") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def read_bytes(
        self, relative_path: str, *, start: int = 0, end: int | None = None
    ) -> tuple[bytes, CacheEntryMeta]:
        rel = normalize_relative_path(relative_path)
        with self._lock:
            entry = self._index.get(rel)
            if entry is None or not entry.complete:
                raise DataPlaneError("cache miss", code="miss")
            path = self._object_path(rel)
            self._reject_symlinks(path)
            size = entry.size_bytes
            if start < 0 or start >= size:
                raise DataPlaneError("invalid range", code="invalid_range")
            last = size - 1 if end is None else min(end, size - 1)
            if last < start:
                raise DataPlaneError("invalid range", code="invalid_range")
            entry.in_use += 1
            entry.last_access_at = time.time()
        try:
            with path.open("rb") as fh:
                fh.seek(start)
                data = fh.read(last - start + 1)
            if len(data) != (last - start + 1):
                raise DataPlaneError("short read", code=CODE_SIZE)
            return data, entry
        finally:
            with self._lock:
                if rel in self._index:
                    self._index[rel].in_use = max(0, self._index[rel].in_use - 1)
                    self._persist_meta(self._index[rel])

    def put_atomic(
        self,
        relative_path: str,
        data: bytes,
        *,
        content_type: str | None,
        checksum_sha256: str,
        origin_key: str,
        etag: str | None = None,
        expected_size: int | None = None,
    ) -> CacheEntryMeta:
        """Atomic temp write + fsync + rename. Rejects bad checksum/size; cleans partials."""
        if self.draining:
            raise DataPlaneError("cache draining; fills disabled", code="draining")
        rel = normalize_relative_path(relative_path)
        if len(data) > self.max_object_bytes:
            raise DataPlaneError("object too large", code=CODE_OVERSIZE)
        if expected_size is not None and len(data) != expected_size:
            raise DataPlaneError("size mismatch", code=CODE_SIZE)
        digest = hashlib.sha256(data).hexdigest()
        if digest != checksum_sha256:
            raise DataPlaneError("checksum mismatch", code=CODE_CHECKSUM)
        # Never cache empty poisoned markers
        if not data and checksum_sha256 == "0" * 64:
            raise DataPlaneError("poisoned origin object rejected", code=CODE_POISON)

        obj_path = self._object_path(rel)
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.tmp_dir / f"obj-{os.getpid()}-{threading.get_ident()}-{time.time_ns()}.part"
        try:
            with tmp.open("wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            if tmp.is_symlink():
                raise DataPlaneError("symlink rejected", code=CODE_SYMLINK)
            os.replace(tmp, obj_path)
            # fsync directory for durability best-effort
            try:
                dir_fd = os.open(str(obj_path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        except Exception:
            self._safe_unlink(tmp)
            raise

        now = time.time()
        entry = CacheEntryMeta(
            relative_path=rel,
            size_bytes=len(data),
            content_type=content_type or content_type_for(rel),
            checksum_sha256=digest,
            etag=etag or f'W/"{digest[:16]}"',
            filled_at=now,
            last_access_at=now,
            origin_key=origin_key,
            complete=True,
        )
        with self._lock:
            self._index[rel] = entry
            self._persist_meta(entry)
            self.enforce_capacity()
        return entry

    def enforce_capacity(self) -> list[str]:
        """Evict LRU until under low watermark / min free. Never evict in-use/pinned/partial."""
        evicted: list[str] = []
        with self._lock:
            used = sum(e.size_bytes for e in self._index.values())
            if (
                used <= self.high_watermark_bytes
                and (self.high_watermark_bytes - used) >= self.min_free_bytes
            ):
                # Also ensure free headroom vs high watermark
                headroom = self.high_watermark_bytes - used
                if headroom >= self.min_free_bytes and used <= self.high_watermark_bytes:
                    return evicted

            target = min(
                self.low_watermark_bytes, max(0, self.high_watermark_bytes - self.min_free_bytes)
            )
            used = sum(e.size_bytes for e in self._index.values())
            need_evict = (
                used > self.high_watermark_bytes
                or (self.high_watermark_bytes - used) < self.min_free_bytes
            )
            if not need_evict:
                return evicted

            candidates = sorted(
                (e for e in self._index.values() if e.complete and e.in_use == 0 and not e.pinned),
                key=lambda e: e.last_access_at,
            )
            for entry in candidates:
                used = sum(e.size_bytes for e in self._index.values())
                if used <= target:
                    break
                self._delete_entry(entry.relative_path)
                evicted.append(entry.relative_path)
            if evicted:
                from app.services.branch_cache import metrics as bc_metrics

                bc_metrics.incr("dp_evicted", len(evicted))
        return evicted

    def _delete_entry(self, relative_path: str) -> None:
        rel = normalize_relative_path(relative_path)
        entry = self._index.pop(rel, None)
        self._safe_unlink(self._object_path(rel))
        self._safe_unlink(self._meta_path(rel))
        _ = entry

    def cleanup_partials(self) -> int:
        removed = 0
        for part in self.tmp_dir.glob("*.part"):
            if part.is_symlink():
                continue
            self._safe_unlink(part)
            removed += 1
        return removed

    def status(self) -> dict:
        with self._lock:
            return {
                "node_id": self.node_id,
                "object_count": len(self._index),
                "used_bytes": sum(e.size_bytes for e in self._index.values()),
                "high_watermark_bytes": self.high_watermark_bytes,
                "low_watermark_bytes": self.low_watermark_bytes,
                "min_free_bytes": self.min_free_bytes,
                "draining": self.draining,
                "updated_at": datetime.now(UTC).isoformat(),
                # No paths, keys beyond counts, no secrets.
            }
