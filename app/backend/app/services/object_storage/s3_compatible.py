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


def probe_s3_connection(config: S3CompatibleConfig) -> dict[str, Any]:
    """Secret-free connectivity probe: endpoint reachability + bucket access.

    Distinguishes network/endpoint failures from bucket permission errors so the
    admin UI can show ``reachable`` and ``bucket_accessible`` separately. Never
    includes credentials, request ids, or raw provider messages in the result.
    """
    host = urlparse(config.endpoint_url).hostname or "configured"
    try:
        storage = S3CompatibleStorage(config)
    except (ValueError, RuntimeError) as exc:
        return {
            "ok": False,
            "reachable": False,
            "bucket_accessible": False,
            "endpoint_host": host,
            "message": str(exc),
        }
    client = storage._client  # noqa: SLF001 — probe is part of this module
    try:
        client.head_bucket(Bucket=config.bucket.strip())
    except Exception as exc:  # noqa: BLE001 — classify without leaking provider payloads
        response = getattr(exc, "response", None)
        status_code = None
        if isinstance(response, dict):
            meta = response.get("ResponseMetadata") or {}
            status_code = meta.get("HTTPStatusCode")
            if status_code is None:
                error = response.get("Error") or {}
                code = str(error.get("Code") or "")
                status_code = int(code) if code.isdigit() else None
        if status_code is not None:
            reason = {
                403: "Bucket exists but the credentials are not allowed to access it",
                404: "Bucket was not found on this endpoint",
                301: "Bucket belongs to a different region or endpoint",
            }.get(int(status_code), f"Bucket check failed (HTTP {status_code})")
            return {
                "ok": False,
                "reachable": True,
                "bucket_accessible": False,
                "endpoint_host": host,
                "message": reason,
            }
        return {
            "ok": False,
            "reachable": False,
            "bucket_accessible": False,
            "endpoint_host": host,
            "message": f"Endpoint unreachable ({type(exc).__name__})",
        }
    return {
        "ok": True,
        "reachable": True,
        "bucket_accessible": True,
        "endpoint_host": host,
        "message": "Endpoint reachable and bucket accessible",
    }
