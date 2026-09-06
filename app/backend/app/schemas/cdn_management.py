from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class R2SettingsIn(BaseModel):
    enabled: bool = False
    provider: Literal["cloudflare_r2", "s3_compatible"] | None = None
    endpoint_url: str = Field(max_length=512)
    account_id: str | None = Field(default=None, max_length=128)
    bucket: str = Field(min_length=1, max_length=255)
    region: str = Field(default="auto", max_length=64)
    object_key_prefix: str | None = Field(default=None, max_length=64)
    access_key_id: str | None = Field(default=None, max_length=512)
    secret_access_key: str | None = Field(default=None, max_length=2048)
    remove_credentials: bool = False


RoleIn = Literal["main", "cache", "MAIN_CDN", "CACHE", "main_cdn"]
CredentialTypeIn = Literal["password", "private_key"]


class ManagedNodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: RoleIn
    host: str = Field(min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: str = Field(min_length=1, max_length=128)
    credential_type: CredentialTypeIn = "password"
    credential: str | None = Field(default=None, max_length=65536)
    branch: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    enabled: bool = True
    is_default: bool = False
    priority: int = Field(default=100, ge=0, le=100000)
    serve_base_url: str | None = Field(default=None, max_length=512)
    cache_limit_bytes: int | None = Field(default=None, ge=0)
    storage_limit_bytes: int | None = Field(default=None, ge=0)
    high_watermark_pct: int = Field(default=90, ge=1, le=100)
    low_watermark_pct: int = Field(default=80, ge=1, le=100)
    ssh_host_key_fingerprint: str | None = Field(default=None, max_length=128)
    issue_heartbeat_token: bool = True

    @field_validator("host")
    @classmethod
    def clean_host(cls, value: str) -> str:
        value = value.strip().lower().rstrip(".")
        if "/" in value or "://" in value or any(c.isspace() for c in value):
            raise ValueError("host must be an IP address or hostname")
        return value


class ManagedNodePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: RoleIn | None = None
    host: str | None = Field(default=None, min_length=1, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, min_length=1, max_length=128)
    credential_type: CredentialTypeIn | None = None
    credential: str | None = Field(default=None, max_length=65536)
    remove_credential: bool = False
    branch: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    enabled: bool | None = None
    is_default: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=100000)
    serve_base_url: str | None = Field(default=None, max_length=512)
    cache_limit_bytes: int | None = Field(default=None, ge=0)
    storage_limit_bytes: int | None = Field(default=None, ge=0)
    high_watermark_pct: int | None = Field(default=None, ge=1, le=100)
    low_watermark_pct: int | None = Field(default=None, ge=1, le=100)
    ssh_host_key_fingerprint: str | None = Field(default=None, max_length=128)


class PrefixRouteIn(BaseModel):
    cidr: str = Field(min_length=3, max_length=64)
    node_id: str = Field(min_length=1, max_length=36)
    priority: int = Field(default=100, ge=0, le=100000)
    enabled: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class PrefixRoutePatch(BaseModel):
    cidr: str | None = Field(default=None, min_length=3, max_length=64)
    node_id: str | None = Field(default=None, min_length=1, max_length=36)
    priority: int | None = Field(default=None, ge=0, le=100000)
    enabled: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ConfirmedActionIn(BaseModel):
    confirm: bool


class PinHostKeyIn(BaseModel):
    fingerprint: str = Field(min_length=20, max_length=128)
    confirm: bool


class NodeHeartbeatIn(BaseModel):
    disk_total_bytes: int | None = Field(default=None, ge=0)
    disk_used_bytes: int | None = Field(default=None, ge=0)
    disk_free_bytes: int | None = Field(default=None, ge=0)
    cache_used_bytes: int | None = Field(default=None, ge=0)
    cached_objects: int | None = Field(default=None, ge=0)
    cached_titles: int | None = Field(default=None, ge=0)
    cache_hits: int | None = Field(default=None, ge=0)
    cache_misses: int | None = Field(default=None, ge=0)
    bandwidth_bytes: int | None = Field(default=None, ge=0)
    rtt_ms: int | None = Field(default=None, ge=0, le=60000)
    software_version: str | None = Field(default=None, max_length=64)
    os_release: str | None = Field(default=None, max_length=64)
    degraded: bool = False
    last_error: str | None = Field(default=None, max_length=2000)


class RouteLookupIn(BaseModel):
    client_ip: str = Field(min_length=3, max_length=64)
