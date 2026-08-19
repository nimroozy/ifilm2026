"""HTTP client for portal.mns.af Voice AI customer lookup (backend only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class PortalClientError(Exception):
    """Safe, non-secret portal client failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PortalLookupResult:
    success: bool
    verified: bool
    customer: dict[str, Any] | None
    http_status: int
    portal_code: str | None = None


def _voice_ai_base(settings: Settings) -> str:
    base = (settings.portal_base_url or "").rstrip("/")
    prefix = (settings.portal_voice_ai_prefix or "/api/voice-ai/v1").strip()
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    return f"{base}{prefix.rstrip('/')}"


def lookup_customer(
    settings: Settings,
    *,
    branch: str,
    username: str,
    password: str,
    http_client: httpx.Client | None = None,
) -> PortalLookupResult:
    """POST /customers/lookup. Never logs password or Authorization."""
    token = (settings.portal_voice_ai_token or "").strip()
    if not token:
        raise PortalClientError("provider_unavailable", "Portal credentials are not configured")

    url = f"{_voice_ai_base(settings)}/customers/lookup"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Mobin-Client": (settings.portal_voice_ai_client or "ifilm").strip(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = {
        "branch": branch,
        "username": username,
        "password": password,
        "request_source": (settings.portal_request_source or "ifilm").strip(),
    }

    timeout = httpx.Timeout(
        float(settings.portal_read_timeout_seconds),
        connect=float(settings.portal_connect_timeout_seconds),
    )
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout)
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        logger.warning("portal_lookup_timeout branch=%s", branch)
        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        ) from None
    except httpx.HTTPError:
        logger.warning("portal_lookup_http_error branch=%s", branch)
        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        ) from None
    finally:
        if owns_client:
            client.close()

    status = int(response.status_code)
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    portal_code = payload.get("code")
    if isinstance(portal_code, str):
        portal_code = portal_code.strip() or None
    else:
        portal_code = None

    if status >= 500:
        logger.warning("portal_lookup_upstream_error status=%s code=%s", status, portal_code)
        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        )

    if status == 401 and portal_code == "unauthorized":
        # Misconfigured iFilm→portal service credential (not subscriber password).
        logger.error("portal_lookup_service_unauthorized")
        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        )

    success = bool(payload.get("success"))
    verified = bool(payload.get("verified"))
    customer = payload.get("customer")
    if not isinstance(customer, dict):
        customer = None

    logger.info(
        "portal_lookup_complete status=%s success=%s verified=%s branch=%s",
        status,
        success,
        verified,
        branch,
    )
    return PortalLookupResult(
        success=success,
        verified=verified,
        customer=customer,
        http_status=status,
        portal_code=portal_code,
    )
