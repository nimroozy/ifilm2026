"""SAS / FreeRADIUS subscriber authentication bridge.

Live Radius mode is unverified against production SAS deployments.
Mock mode is restricted to development/test and explicit fixture users only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.runtime import RuntimeConfigurationError, is_dev_like

logger = logging.getLogger(__name__)

GENERIC_FAILURE = "Invalid credentials"


@dataclass
class RadiusAuthResult:
    success: bool
    message: str
    package: str | None = None
    branch: str | None = None
    expiration: str | None = None
    raw: dict | None = None


class RadiusService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def authenticate(self, username: str, password: str) -> RadiusAuthResult:
        if not self.settings.enable_radius_login:
            return RadiusAuthResult(success=False, message=GENERIC_FAILURE)

        if self.settings.radius_mode == "mock":
            return self._mock_authenticate(username, password)
        return self._live_authenticate(username, password)

    def _mock_authenticate(self, username: str, password: str) -> RadiusAuthResult:
        if not is_dev_like(self.settings.app_env):
            raise RuntimeConfigurationError(
                "Mock Radius authentication is not allowed outside development/test"
            )
        if not self.settings.radius_enabled:
            # Feature may be enabled for login path while radius_enabled toggles transport.
            # Mock fixtures still require explicit configuration.
            pass

        for user in self.settings.radius_mock_users:
            if user.get("username") == username and user.get("password") == password:
                return RadiusAuthResult(
                    success=True,
                    message="Authenticated (mock Radius fixture)",
                    package=user.get("package") or "Standard",
                    branch=user.get("branch") or "Kabul",
                    expiration=user.get("expiration") or "",
                )
        return RadiusAuthResult(success=False, message=GENERIC_FAILURE)

    def _live_authenticate(self, username: str, password: str) -> RadiusAuthResult:
        # NOTE: Live SAS Radius integration is unverified. Treat as experimental.
        if not self.settings.radius_enabled:
            return RadiusAuthResult(success=False, message=GENERIC_FAILURE)
        try:
            from pyrad import packet
            from pyrad.client import Client
            from pyrad.dictionary import Dictionary
        except Exception:
            logger.exception("Radius client library unavailable")
            return RadiusAuthResult(success=False, message=GENERIC_FAILURE)

        try:
            client = Client(
                server=self.settings.radius_server,
                authport=self.settings.radius_port,
                secret=self.settings.radius_secret.encode("utf-8"),
                dict=Dictionary(),
            )
            client.timeout = self.settings.radius_timeout_seconds
            req = client.CreateAuthPacket(code=packet.AccessRequest, User_Name=username)
            req["User-Password"] = req.PwCrypt(password)
            req["NAS-Identifier"] = self.settings.radius_nas_identifier
            reply = client.SendPacket(req)
            if reply.code == packet.AccessAccept:
                return RadiusAuthResult(success=True, message="Access-Accept", raw=dict(reply))
            return RadiusAuthResult(success=False, message=GENERIC_FAILURE)
        except Exception:
            logger.exception("Radius authentication failed")
            return RadiusAuthResult(success=False, message=GENERIC_FAILURE)
