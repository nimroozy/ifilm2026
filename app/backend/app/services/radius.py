"""SAS / FreeRADIUS subscriber authentication bridge."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class RadiusAuthResult:
    success: bool
    message: str
    package: Optional[str] = None
    branch: Optional[str] = None
    expiration: Optional[str] = None
    raw: Optional[dict] = None


class RadiusService:
    """Authenticate ISP usernames against SAS Radius (FreeRADIUS-compatible).

    Modes:
    - mock: accept known demo credentials / any user when RADIUS_ENABLED=false
    - live: send Access-Request via pyrad
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def authenticate(self, username: str, password: str) -> RadiusAuthResult:
        if not self.settings.radius_enabled or self.settings.radius_mode == "mock":
            return self._mock_authenticate(username, password)
        return self._live_authenticate(username, password)

    def _mock_authenticate(self, username: str, password: str) -> RadiusAuthResult:
        # Demo Mobin Net style account used by the frontend mock login.
        if username == "mobin_user_001" and password == "password":
            return RadiusAuthResult(
                success=True,
                message="Authenticated (mock Radius)",
                package="Premium 50Mbps",
                branch="Kabul",
                expiration="2026-12-31",
            )
        if username and password:
            # Soft-success path for local development without a Radius server.
            return RadiusAuthResult(
                success=True,
                message="Authenticated (mock Radius fallback)",
                package="Standard",
                branch="Kabul",
                expiration="2026-12-31",
            )
        return RadiusAuthResult(success=False, message="Invalid credentials")

    def _live_authenticate(self, username: str, password: str) -> RadiusAuthResult:
        try:
            from pyrad.client import Client
            from pyrad.dictionary import Dictionary
            from pyrad import packet
        except Exception as exc:  # pragma: no cover - optional dependency path
            logger.exception("pyrad unavailable")
            return RadiusAuthResult(success=False, message=f"Radius client unavailable: {exc}")

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
            return RadiusAuthResult(success=False, message="Access-Reject", raw=dict(reply))
        except Exception as exc:
            logger.exception("Radius authentication failed")
            return RadiusAuthResult(success=False, message=str(exc))
