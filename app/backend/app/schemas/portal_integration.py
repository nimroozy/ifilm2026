"""Admin Portal integration API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PortalIntegrationOut(BaseModel):
    enabled: bool
    base_url: str
    api_prefix: str
    client: str
    request_source: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    entitlement_ttl_seconds: int
    token_configured: bool
    updated_at: str | None = None
    last_test_at: str | None = None
    last_test_ok: bool | None = None
    last_test_http_status: int | None = None
    last_test_portal_reachable: bool | None = None
    last_test_credential_accepted: bool | None = None
    config_source: str | None = None


class PortalIntegrationUpdateIn(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    api_prefix: str | None = None
    client: str | None = None
    request_source: str | None = None
    connect_timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    read_timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    entitlement_ttl_seconds: int | None = Field(default=None, ge=60, le=86400)
    token: str | None = Field(default=None, max_length=4096)
    remove_token: bool = False


class PortalConnectionTestOut(BaseModel):
    ok: bool
    portal_reachable: bool
    credential_accepted: bool
    http_status: int | None = None
    message: str
