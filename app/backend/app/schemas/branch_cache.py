"""Pydantic schemas for branch-cache control plane (secret-free)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BranchCacheNodeCreateIn(BaseModel):
    node_id: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)
    site_id: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=512)
    branch_code: str | None = Field(default=None, max_length=64)
    capacity_bytes: int | None = Field(default=None, ge=0)
    software_version: str | None = Field(default=None, max_length=64)
    protocol_version: str | None = Field(default=None, max_length=32)
    issue_enrollment_token: bool = False


class BranchCacheNodeUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    site_id: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    branch_code: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=32)
    draining: bool | None = None
    disabled: bool | None = None
    capacity_bytes: int | None = Field(default=None, ge=0)
    software_version: str | None = Field(default=None, max_length=64)
    protocol_version: str | None = Field(default=None, max_length=32)


class BranchCacheHeartbeatIn(BaseModel):
    used_bytes: int | None = Field(default=None, ge=0)
    capacity_bytes: int | None = Field(default=None, ge=0)
    software_version: str | None = Field(default=None, max_length=64)
    protocol_version: str | None = Field(default=None, max_length=32)
    healthy: bool = True
    enrollment_token: str | None = Field(default=None, max_length=256)


class BranchCacheRouteDryRunIn(BaseModel):
    site_id: str = Field(min_length=1, max_length=64)
    package_id: str | None = Field(default=None, max_length=64)
    require_bytes: int = Field(default=0, ge=0)


class BranchCacheEdgeGrantIssueIn(BaseModel):
    node_id: str = Field(min_length=3, max_length=64)
    site_id: str = Field(min_length=1, max_length=64)
    package_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    path_prefix: str = Field(min_length=1, max_length=256)
    ttl_seconds: int | None = Field(default=None, ge=15, le=300)


class BranchCacheEdgeGrantVerifyIn(BaseModel):
    token: str = Field(min_length=1, max_length=8192)
    node_id: str = Field(min_length=3, max_length=64)
    package_id: str | None = Field(default=None, max_length=64)
    path: str | None = Field(default=None, max_length=512)


class BranchCacheNodeOut(BaseModel):
    id: str
    node_id: str
    display_name: str
    site_id: str
    branch_code: str | None = None
    base_url: str
    status: str
    draining: bool
    disabled: bool
    software_version: str | None = None
    protocol_version: str | None = None
    capacity_bytes: int | None = None
    used_bytes: int
    free_bytes: int | None = None
    last_heartbeat_at: str | None = None
    last_health_ok_at: str | None = None
    health_status: str
    has_heartbeat_token: bool
    node_key_id: str | None = None
    has_node_public_key: bool
    created_by_admin_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    disabled_at: str | None = None


class BranchCacheNodeCreateOut(BaseModel):
    node: BranchCacheNodeOut
    # Returned at most once when issue_enrollment_token=true; never stored/logged by API layer.
    enrollment_token: str | None = None
