"""S3-compatible object storage (MinIO, Ceph RGW, AWS S3, optional Cloudflare R2).

Credentials are read from settings and never returned by health/status helpers.
boto3 is imported lazily so local/dev stays usable without object-storage usage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.object_storage.protocol import StoredObject
from app.services.object_storage.tiers import StorageProviderKind, StorageRole


@dataclass(frozen=True)
class S3CompatibleConfig:
    endpoint_url: str
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    force_path_style: bool = True
    provider_kind: StorageProviderKind = StorageProviderKind.S3_COMPATIBLE
    role: StorageRole = StorageRole.CENTRAL_ORIGIN


def _require_boto3() -> Any:
    try:
        import boto3
        from botocore.client import Config
    except ImportError as exc:  # pragma: no cover - exercised when dependency missing
        raise RuntimeError(
            "boto3 is required for s3_compatible / R2 object storage. "
            "Install backend requirements or keep ENABLE_OBJECT_STORAGE=false."
        ) from exc
    return boto3, Config


class S3CompatibleStorage:
    """Thin S3 API wrapper suitable for MinIO, Ceph, S3, and R2 endpoints."""

    def __init__(self, config: S3CompatibleConfig) -> None:
        if not (config.endpoint_url or "").strip():
            raise ValueError("S3-compatible endpoint_url is required")
        if not (config.bucket or "").strip():
            raise ValueError("S3-compatible bucket is required")
        if not (config.access_key_id or "").strip() or not (config.secret_access_key or "").strip():
            raise ValueError("S3-compatible access key and secret are required")

        boto3, Config = _require_boto3()
        self._config = config
        self._bucket = config.bucket.strip()
        self._client = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url.strip(),
            region_name=(config.region or "us-east-1").strip(),
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            config=Config(s3={"addressing_style": "path" if config.force_path_style else "auto"}),
        )

    @property
    def role(self) -> StorageRole:
        return self._config.role

    @property
    def provider_kind(self) -> StorageProviderKind:
        return self._config.provider_kind

    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str | None = None,
    ) -> StoredObject:
        extra_args = {"ContentType": content_type} if content_type else None
        if extra_args:
            self._client.upload_file(str(source), self._bucket, key, ExtraArgs=extra_args)
        else:
            self._client.upload_file(str(source), self._bucket, key)
        size = source.stat().st_size if source.is_file() else None
        return StoredObject(key=key, size_bytes=size, content_type=content_type)

    def get_file(self, *, key: str, destination: Path) -> StoredObject:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self._bucket, key, str(destination))
        size = destination.stat().st_size if destination.is_file() else None
        return StoredObject(key=key, size_bytes=size)

    def exists(self, *, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, *, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def healthcheck(self) -> dict[str, str | bool]:
        host = urlparse(self._config.endpoint_url).hostname or "configured"
        try:
            self._client.head_bucket(Bucket=self._bucket)
            ok = True
        except Exception:
            ok = False
        return {
            "ok": ok,
            "provider": self.provider_kind.value,
            "role": self.role.value,
            "endpoint_host": host,
            "bucket_configured": True,
        }
