"""Local filesystem object-storage provider (MEDIA_ROOT workspace)."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.services.object_storage.protocol import StoredObject
from app.services.object_storage.tiers import StorageProviderKind, StorageRole


class LocalFilesystemStorage:
    """Maps object keys onto a local root directory (default: MEDIA_ROOT)."""

    def __init__(self, *, root: Path, role: StorageRole = StorageRole.LOCAL_WORKSPACE) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._role = role

    @property
    def role(self) -> StorageRole:
        return self._role

    @property
    def provider_kind(self) -> StorageProviderKind:
        return StorageProviderKind.LOCAL

    def _resolve(self, key: str) -> Path:
        # Keys use `/`; reject absolute and traversal.
        normalized = (key or "").replace("\\", "/").strip().lstrip("/")
        if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("Unsafe object key")
        dest = (self._root / normalized).resolve()
        try:
            dest.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("Object key escapes storage root") from exc
        return dest

    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str | None = None,
    ) -> StoredObject:
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return StoredObject(
            key=key,
            size_bytes=dest.stat().st_size,
            content_type=content_type,
        )

    def get_file(self, *, key: str, destination: Path) -> StoredObject:
        src = self._resolve(key)
        if not src.is_file():
            raise FileNotFoundError(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, destination)
        return StoredObject(key=key, size_bytes=src.stat().st_size)

    def exists(self, *, key: str) -> bool:
        path = self._resolve(key)
        return path.is_file()

    def delete(self, *, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()

    def healthcheck(self) -> dict[str, str | bool]:
        writable = False
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            probe = self._root / ".ifilm-storage-health"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            writable = True
        except OSError:
            writable = False
        return {
            "ok": writable,
            "provider": self.provider_kind.value,
            "role": self.role.value,
            "root_configured": True,
        }
