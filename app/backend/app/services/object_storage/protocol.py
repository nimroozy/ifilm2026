"""Object storage protocol (provider-neutral)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.services.object_storage.tiers import StorageProviderKind, StorageRole


@dataclass(frozen=True)
class StoredObject:
    """Metadata for an object that exists (or was just written)."""

    key: str
    size_bytes: int | None = None
    etag: str | None = None
    content_type: str | None = None


@runtime_checkable
class ObjectStorage(Protocol):
    """Minimal durable-object operations used by later media pipeline phases."""

    @property
    def role(self) -> StorageRole: ...

    @property
    def provider_kind(self) -> StorageProviderKind: ...

    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str | None = None,
    ) -> StoredObject: ...

    def get_file(self, *, key: str, destination: Path) -> StoredObject: ...

    def exists(self, *, key: str) -> bool: ...

    def delete(self, *, key: str) -> None: ...

    def healthcheck(self) -> dict[str, str | bool]:
        """Return a secret-free health snapshot for ops."""
        ...
