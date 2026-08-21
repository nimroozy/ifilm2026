"""Provider-neutral media object storage (hybrid CDN Phase 1).

This package is the durable-object abstraction for a future hybrid CDN:

- ``local`` — development / encode workspace under MEDIA_ROOT (default)
- ``s3_compatible`` — central origin (MinIO, Ceph RGW, or any S3 API)
- optional R2 hot tier — same S3-compatible client, separate role/config

Feature flags default OFF. Experimental edge ``cdn_sync`` is unrelated and
must remain quarantined until a signed branch-cache protocol exists.
"""

from app.services.object_storage.factory import (
    get_central_origin_storage,
    get_hot_tier_storage,
    get_local_workspace_storage,
)
from app.services.object_storage.keys import ObjectKeyBuilder, StorageObjectKind
from app.services.object_storage.protocol import ObjectStorage, StoredObject
from app.services.object_storage.status import safe_storage_status
from app.services.object_storage.tiers import StorageProviderKind, StorageRole

__all__ = [
    "ObjectKeyBuilder",
    "ObjectStorage",
    "StorageObjectKind",
    "StorageProviderKind",
    "StorageRole",
    "StoredObject",
    "get_central_origin_storage",
    "get_hot_tier_storage",
    "get_local_workspace_storage",
    "safe_storage_status",
]
