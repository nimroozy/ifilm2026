"""Resolved Portal runtime configuration (DB + env)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortalRuntimeConfig:
    enabled: bool
    base_url: str
    api_prefix: str
    token: str
    client: str
    request_source: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    entitlement_cache_ttl_seconds: int
    source: str  # "db" | "env" | "default"

    @property
    def token_configured(self) -> bool:
        return bool((self.token or "").strip())

    @property
    def voice_ai_base(self) -> str:
        base = (self.base_url or "").rstrip("/")
        prefix = (self.api_prefix or "/api/voice-ai/v1").strip()
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        return f"{base}{prefix.rstrip('/')}"
