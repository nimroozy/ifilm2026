"""SAS / FreeRADIUS subscriber authentication bridge (legacy facade).

Prefer ``app.services.identity.get_identity_provider``. Live Radius mode remains
unverified against production SAS deployments. Fixture/mock mode is restricted
to development/test.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.services.identity.provider import (
    GENERIC_FAILURE,
    IdentityAuthResult,
    get_identity_provider,
)

# Backward-compatible alias
RadiusAuthResult = IdentityAuthResult


class RadiusService:
    """Thin adapter over SubscriberIdentityProvider for legacy callers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def authenticate(self, username: str, password: str) -> IdentityAuthResult:
        return get_identity_provider(self.settings).authenticate(username, password)


__all__ = ["GENERIC_FAILURE", "RadiusAuthResult", "RadiusService", "IdentityAuthResult"]
